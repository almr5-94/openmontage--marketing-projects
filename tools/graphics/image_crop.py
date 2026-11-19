"""image_crop: smart crops, batch operations, contact sheets and geometric-mask fragments.

Layer 2 of the editorial art stack. This is how real art becomes components: a CC0 painting
is cut into a circle, a hexagon, an arc, a stripe set, so the collage and layout stages can
build new pages from real material.

Operations (``operation``):

* ``smart_crop``  -- cover-scale to ``target`` (WxH) and choose the window by ``gravity``:
  center, north, south, east, west, entropy (busiest region) or attention (saliency: edges +
  saturation + local contrast). ``engine: "imagemagick"`` runs the vendored image-forge script
  instead (needs ImageMagick 7 ``magick``).
* ``batch``       -- the same op over many files: resize, format, strip (metadata), auto_orient,
  crop, thumbnail.
* ``montage``     -- a contact sheet of many images (for review and for the vision critic).
* ``mask``        -- cut a geometric fragment with an alpha mask: circle, ellipse, triangle,
  hexagon, polygon (points), arc (an annulus sector), stripe (n parallel bands at an angle).
  Optional feather (soft edge) and rim (a thin edge in ink colour for a "cut paper" look).

Every output lands under ``projects/<id>/assets/fragments/`` (unless ``output_path`` is given)
and is recorded in PROVENANCE.json as ``licence: derived`` with the exact crop parameters and
the parent asset, so a finished page can always be traced back to its museum object.

Free and local (Pillow + numpy). Never deletes or overwrites a source: outputs get new names.
"""

from __future__ import annotations

import math
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Optional

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps

from lib import provenance
from tools.base_tool import (
    BaseTool,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    ToolResult,
    ToolRuntime,
    ToolStability,
    ToolStatus,
    ToolTier,
)

REPO = Path(__file__).resolve().parents[2]
IMAGE_FORGE = REPO / "vendor" / "image-forge" / "skills" / "design-media" / "image-forge" / "scripts"
GRAVITIES = ["center", "north", "south", "east", "west", "entropy", "attention"]
SHAPES = ["circle", "ellipse", "triangle", "hexagon", "polygon", "arc", "stripe"]


def _parse_size(s: str | list | tuple) -> tuple[int, int]:
    if isinstance(s, (list, tuple)):
        return int(s[0]), int(s[1])
    w, h = str(s).lower().split("x")
    return int(w), int(h)


def _open(path: str | Path) -> Image.Image:
    im = Image.open(path)
    im = ImageOps.exif_transpose(im)
    return im


# ---------------------------------------------------------------- saliency maps
def _gray(im: Image.Image, max_side: int = 512) -> tuple[np.ndarray, float]:
    scale = min(1.0, max_side / max(im.size))
    small = im.convert("RGB").resize((max(1, round(im.width * scale)), max(1, round(im.height * scale))))
    return np.asarray(small, dtype=np.float32), scale


def attention_map(im: Image.Image) -> tuple[np.ndarray, float]:
    """Edges + saturation + local contrast, normalised 0..1, on a downscaled copy."""
    rgb, scale = _gray(im)
    g = rgb.mean(axis=2)
    gx = np.abs(np.diff(g, axis=1, prepend=g[:, :1]))
    gy = np.abs(np.diff(g, axis=0, prepend=g[:1, :]))
    edges = gx + gy
    mx, mn = rgb.max(axis=2), rgb.min(axis=2)
    sat = (mx - mn) / (mx + 1e-3)
    local = np.abs(g - np.asarray(Image.fromarray(g.astype(np.uint8)).filter(ImageFilter.GaussianBlur(8)), dtype=np.float32))
    m = 0.5 * edges / (edges.max() + 1e-6) + 0.25 * sat + 0.25 * local / (local.max() + 1e-6)
    m = np.asarray(Image.fromarray((m / (m.max() + 1e-6) * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(6)), dtype=np.float32) / 255
    return m, scale


def entropy_map(im: Image.Image) -> tuple[np.ndarray, float]:
    rgb, scale = _gray(im)
    g = rgb.mean(axis=2)
    gx = np.abs(np.diff(g, axis=1, prepend=g[:, :1]))
    gy = np.abs(np.diff(g, axis=0, prepend=g[:1, :]))
    return (gx + gy) / ((gx + gy).max() + 1e-6), scale


def _best_window(m: np.ndarray, win_w: int, win_h: int) -> tuple[int, int]:
    """Top-left of the window with the highest summed score (integral image)."""
    H, W = m.shape
    win_w, win_h = min(win_w, W), min(win_h, H)
    ii = np.pad(m, ((1, 0), (1, 0))).cumsum(0).cumsum(1)
    sums = ii[win_h:, win_w:] - ii[:-win_h, win_w:] - ii[win_h:, :-win_w] + ii[:-win_h, :-win_w]
    y, x = np.unravel_index(np.argmax(sums), sums.shape)
    return int(x), int(y)


def smart_crop_box(im: Image.Image, tw: int, th: int, gravity: str) -> tuple[float, tuple[int, int, int, int]]:
    """Return (cover scale, crop box in the scaled image)."""
    scale = max(tw / im.width, th / im.height)
    sw, sh = round(im.width * scale), round(im.height * scale)
    if gravity in ("entropy", "attention"):
        m, ms = (attention_map if gravity == "attention" else entropy_map)(im)
        # window size in map coordinates
        wx, wy = max(1, round(tw / scale * ms)), max(1, round(th / scale * ms))
        x, y = _best_window(m, wx, wy)
        left, top = round(x / ms * scale), round(y / ms * scale)
    else:
        left = {"west": 0, "east": sw - tw}.get(gravity, (sw - tw) // 2)
        top = {"north": 0, "south": sh - th}.get(gravity, (sh - th) // 2)
    left = max(0, min(left, sw - tw))
    top = max(0, min(top, sh - th))
    return scale, (left, top, left + tw, top + th)


# ---------------------------------------------------------------- geometric masks
def shape_mask(size: tuple[int, int], shape: str, p: dict[str, Any]) -> Image.Image:
    """An L-mode mask (255 = keep) for ``shape`` inside an image of ``size``.

    Common params: cx, cy (centre, 0..1 of width/height, default .5), r (radius as a
    fraction of the shorter side, default .45), rotation (degrees).
    """
    W, H = size
    S = min(W, H)
    cx, cy = p.get("cx", 0.5) * W, p.get("cy", 0.5) * H
    r = p.get("r", 0.45) * S
    rot = math.radians(p.get("rotation", 0))
    ss = 4  # supersample for smooth edges
    big = Image.new("L", (W * ss, H * ss), 0)
    d = ImageDraw.Draw(big)

    def pts(n: int, radius: float, phase: float) -> list[tuple[float, float]]:
        return [((cx + radius * math.cos(phase + rot + 2 * math.pi * k / n)) * ss,
                 (cy + radius * math.sin(phase + rot + 2 * math.pi * k / n)) * ss) for k in range(n)]

    if shape == "circle":
        d.ellipse([(cx - r) * ss, (cy - r) * ss, (cx + r) * ss, (cy + r) * ss], fill=255)
    elif shape == "ellipse":
        rx, ry = p.get("rx", 0.45) * W, p.get("ry", 0.3) * H
        d.ellipse([(cx - rx) * ss, (cy - ry) * ss, (cx + rx) * ss, (cy + ry) * ss], fill=255)
        if p.get("rotation"):
            big = big.rotate(-p["rotation"], center=(cx * ss, cy * ss), resample=Image.BICUBIC)
    elif shape == "triangle":
        d.polygon(pts(3, r, -math.pi / 2), fill=255)
    elif shape == "hexagon":
        d.polygon(pts(6, r, 0), fill=255)
    elif shape == "polygon":
        points = p.get("points")
        if not points or len(points) < 3:
            raise ValueError("polygon needs points: [[x,y],...] as 0..1 fractions")
        d.polygon([(x * W * ss, y * H * ss) for x, y in points], fill=255)
    elif shape == "arc":
        # annulus sector: inner radius ri, outer r, from start to end degrees
        ri = p.get("ri", 0.25) * S
        a0, a1 = p.get("start", 180), p.get("end", 360)
        box = [(cx - r) * ss, (cy - r) * ss, (cx + r) * ss, (cy + r) * ss]
        d.pieslice(box, a0 + math.degrees(rot), a1 + math.degrees(rot), fill=255)
        d.ellipse([(cx - ri) * ss, (cy - ri) * ss, (cx + ri) * ss, (cy + ri) * ss], fill=0)
    elif shape == "stripe":
        # Drawn at 1x on a square canvas that covers the image at any angle, rotated, then
        # centre-cropped (supersampling a canvas this size would exceed Pillow's pixel limit).
        n = int(p.get("count", 5))
        band = p.get("band", 0.5)  # fraction of each period that is kept
        angle = p.get("angle", 0)
        D = int(math.ceil(math.hypot(W, H)))
        period = D / n
        tmp = Image.new("L", (D, D), 0)
        td = ImageDraw.Draw(tmp)
        for k in range(n):
            y0 = k * period
            td.rectangle([0, y0, D, y0 + period * band], fill=255)
        tmp = tmp.rotate(angle, resample=Image.BICUBIC).filter(ImageFilter.GaussianBlur(0.6))
        left, top = (D - W) // 2, (D - H) // 2
        return _feather(tmp.crop((left, top, left + W, top + H)), p)
    else:
        raise ValueError(f"unknown shape {shape!r}; one of {SHAPES}")
    return _feather(big.resize((W, H), Image.LANCZOS), p)


def _feather(mask: Image.Image, p: dict[str, Any]) -> Image.Image:
    feather = float(p.get("feather", 0))
    return mask.filter(ImageFilter.GaussianBlur(feather)) if feather > 0 else mask


def apply_mask(im: Image.Image, mask: Image.Image, rim: Optional[dict[str, Any]] = None, trim: bool = True) -> Image.Image:
    out = im.convert("RGBA")
    a = ImageChops.multiply(out.getchannel("A"), mask)
    out.putalpha(a)
    if rim:
        width = max(1, int(rim.get("width", 3)))
        color = rim.get("color", "#1a1714")
        edge = ImageChops.subtract(mask.filter(ImageFilter.MaxFilter(width * 2 + 1)), mask)
        ink = Image.new("RGBA", out.size, color)
        ink.putalpha(edge)
        out = Image.alpha_composite(out, ink)
    if trim:
        bbox = out.getchannel("A").getbbox()
        if bbox:
            out = out.crop(bbox)
    return out


# ---------------------------------------------------------------- the tool
class ImageCrop(BaseTool):
    name = "image_crop"
    version = "0.1.0"
    tier = ToolTier.CORE
    capability = "image_crop"
    provider = "pillow"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC
    runtime = ToolRuntime.LOCAL
    dependencies = ["python:PIL", "python:numpy"]
    install_instructions = "Pillow and numpy (in requirements.txt). ImageMagick 7 (`magick`) is optional, for engine='imagemagick'."
    capabilities = ["smart_crop", "batch_ops", "montage", "geometric_mask_crop", "record_provenance"]
    supports = {"gravity": GRAVITIES, "shapes": SHAPES, "cost": "free (local)"}
    best_for = [
        "cropping real art and photos to exact slot sizes with subject-aware gravity",
        "cutting CC0 art into circles, hexagons, arcs, stripes for collage",
        "contact sheets for review",
    ]
    not_good_for = ["changing image content (Runway MCP edit, elected)", "upscaling (upscale tool)"]
    resource_profile = ResourceProfile(cpu_cores=1, ram_mb=1024, vram_mb=0, disk_mb=200)
    side_effects = ["writes new image files; never overwrites the source", "appends to assets/PROVENANCE.json"]
    agent_skills = ["image-forge"]
    input_schema = {
        "type": "object",
        "required": ["operation"],
        "properties": {
            "operation": {"type": "string", "enum": ["smart_crop", "batch", "montage", "mask", "cutout"]},
            "input_path": {"type": "string"},
            "input_paths": {"type": "array", "items": {"type": "string"}},
            "project_dir": {"type": "string"},
            "output_path": {"type": "string"},
            "target": {"type": "string", "description": "WxH, e.g. 2716x3543"},
            "gravity": {"type": "string", "enum": GRAVITIES, "default": "attention"},
            "engine": {"type": "string", "enum": ["pillow", "imagemagick"], "default": "pillow"},
            "op": {"type": "string", "enum": ["resize", "format", "strip", "auto_orient", "crop", "thumbnail"]},
            "width": {"type": "integer"}, "height": {"type": "integer"},
            "box": {"type": "array", "items": {"type": "number"}, "description": "op crop: exact [x0,y0,x1,y1] fractions"},
            "to": {"type": "string", "enum": ["png", "jpg", "webp", "tif"]},
            "quality": {"type": "integer", "default": 92},
            "shape": {"type": "string", "enum": SHAPES},
            "shape_params": {"type": "object"},
            "rim": {"type": "object", "properties": {"width": {"type": "integer"}, "color": {"type": "string"}}},
            "cols": {"type": "integer", "default": 4},
            "thumb": {"type": "string", "default": "400x400"},
            "label": {"type": "boolean", "default": True},
        },
    }

    def get_status(self) -> ToolStatus:
        return ToolStatus.AVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        return 0.0

    # -- helpers
    def _out(self, inputs: dict[str, Any], src: Path, suffix: str, ext: str) -> Path:
        if inputs.get("output_path"):
            p = Path(inputs["output_path"])
        else:
            base = Path(inputs["project_dir"]) / "assets" / "fragments" if inputs.get("project_dir") else src.parent / "fragments"
            p = base / f"{src.stem}-{suffix}.{ext}"
        p.parent.mkdir(parents=True, exist_ok=True)
        n = 2
        stem = p.stem
        while p.exists():  # never overwrite: version the name
            p = p.with_name(f"{stem}.v{n}{p.suffix}")
            n += 1
        return p

    def _record(self, inputs: dict[str, Any], out: Path, parents: list[Path], crop: dict[str, Any]) -> Optional[dict[str, Any]]:
        pd = inputs.get("project_dir")
        if not pd:
            return None
        return provenance.record(
            pd, out, kind="fragment", source="image_crop", licence="derived",
            parents=[provenance.rel(pd, x) for x in parents], crop=crop, tool=self.name,
        )

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        start = time.time()
        op = inputs.get("operation")
        try:
            fn = {"smart_crop": self._smart_crop, "batch": self._batch, "montage": self._montage, "mask": self._mask,
                  "cutout": self._cutout}.get(op)
            if fn is None:
                return ToolResult(success=False, error=f"unknown operation {op!r}")
            res = fn(inputs)
            res.duration_seconds = time.time() - start
            return res
        except Exception as e:
            return ToolResult(success=False, error=f"{type(e).__name__}: {e}")

    def _smart_crop(self, inputs: dict[str, Any]) -> ToolResult:
        src = Path(inputs["input_path"])
        tw, th = _parse_size(inputs["target"])
        gravity = inputs.get("gravity", "attention")
        ext = (inputs.get("to") or src.suffix.lstrip(".") or "png").replace("jpeg", "jpg")
        out = self._out(inputs, src, f"crop{tw}x{th}-{gravity}", ext)
        if inputs.get("engine") == "imagemagick":
            magick = shutil.which("magick")
            if not magick:
                return ToolResult(success=False, error="engine=imagemagick needs ImageMagick 7 (`magick`) on PATH")
            g = gravity if gravity in ("center", "north", "south", "east", "west") else "center"
            cmd = ["python3", str(IMAGE_FORGE / "smart_crop.py"), str(src), "--target", f"{tw}x{th}",
                   "--gravity", g, "--output", str(out.parent)]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if r.returncode != 0:
                return ToolResult(success=False, error=r.stderr[-400:])
            made = out.parent / f"{src.stem}_crop{src.suffix}"
            if made.exists():
                made.rename(out)
            box = None
        else:
            im = _open(src)
            scale, box = smart_crop_box(im, tw, th, gravity)
            scaled = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
            crop = scaled.crop(box)
            if ext == "jpg":
                crop.convert("RGB").save(out, quality=int(inputs.get("quality", 92)), subsampling=0)
            else:
                crop.save(out)
        up = max(tw / _open(src).width, th / _open(src).height)
        rec = self._record(inputs, out, [src], {"op": "smart_crop", "target": [tw, th], "gravity": gravity,
                                                  "scale": round(up, 4), "box_in_scaled": box,
                                                  "engine": inputs.get("engine", "pillow")})
        warn = [f"source upscaled x{up:.2f}: below native resolution"] if up > 1.0 else []
        return ToolResult(success=True, data={"path": str(out), "scale": up, "box": box, "warnings": warn,
                                              "provenance": rec}, artifacts=[str(out)])

    def _mask(self, inputs: dict[str, Any]) -> ToolResult:
        src = Path(inputs["input_path"])
        shape = inputs["shape"]
        params = inputs.get("shape_params") or {}
        im = _open(src)
        mask = shape_mask(im.size, shape, params)
        frag = apply_mask(im, mask, rim=inputs.get("rim"), trim=params.get("trim", True))
        out = self._out(inputs, src, shape, "png")
        frag.save(out)
        rec = self._record(inputs, out, [src], {"op": "mask", "shape": shape, "params": params, "rim": inputs.get("rim"),
                                                  "size": list(frag.size)})
        return ToolResult(success=True, data={"path": str(out), "size": list(frag.size), "provenance": rec},
                          artifacts=[str(out)])

    def _cutout(self, inputs: dict[str, Any]) -> ToolResult:
        """Lift an object off a plain studio ground (museum photographs) with OpenCV GrabCut.

        Free and local. ``inset`` is the fraction of each edge assumed to be ground (default 0.03).
        Writes an RGBA PNG trimmed to the object; the source stays untouched.
        """
        import cv2

        src = Path(inputs["input_path"])
        im = _open(src).convert("RGB")
        inset = float((inputs.get("shape_params") or {}).get("inset", 0.03))
        small = im.copy()
        small.thumbnail((1200, 1200))
        arr = cv2.cvtColor(np.array(small), cv2.COLOR_RGB2BGR)
        h, w = arr.shape[:2]
        box = (inputs.get("shape_params") or {}).get("rect")  # [x0, y0, x1, y1] as fractions: where the object is
        if box:
            rect = (int(w * box[0]), int(h * box[1]), int(w * (box[2] - box[0])), int(h * (box[3] - box[1])))
        else:
            rect = (int(w * inset), int(h * inset), int(w * (1 - 2 * inset)), int(h * (1 - 2 * inset)))
        mask = np.zeros((h, w), np.uint8)
        bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
        cv2.grabCut(arr, mask, rect, bgd, fgd, 6, cv2.GC_INIT_WITH_RECT)
        fg = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)
        n, lab, stats, _ = cv2.connectedComponentsWithStats(fg)
        if n > 1:  # keep the largest piece: the object, not specks of the ground
            keep = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
            fg = np.where(lab == keep, 255, 0).astype(np.uint8)
        if (inputs.get("shape_params") or {}).get("drop_neutral"):
            # cast shadows on a studio ground are light and colourless; a coloured object (bronze, glaze) is not
            hsv = cv2.cvtColor(arr, cv2.COLOR_BGR2HSV)
            neutral = (hsv[..., 1] < 28) & (hsv[..., 2] > 120)
            fg[neutral] = 0
            n2, lab2, st2, _ = cv2.connectedComponentsWithStats(fg)
            if n2 > 1:
                fg = np.where(lab2 == 1 + int(np.argmax(st2[1:, cv2.CC_STAT_AREA])), 255, 0).astype(np.uint8)
        if (inputs.get("shape_params") or {}).get("drop_shadow"):
            # a dark cast shadow on grey ground has no colour at all; a dark unglazed foot keeps a little.
            # smooth the saturation first so JPEG noise in the foot does not punch holes in it
            hsv = cv2.cvtColor(arr, cv2.COLOR_BGR2HSV)
            sat = cv2.medianBlur(hsv[..., 1], 9)
            fg[(sat < 7) & (hsv[..., 2] < 140)] = 0
            fg = cv2.morphologyEx(fg, cv2.MORPH_OPEN, np.ones((7, 7), np.uint8))
            n3, lab3, st3, _ = cv2.connectedComponentsWithStats(fg)
            if n3 > 1:
                fg = np.where(lab3 == 1 + int(np.argmax(st3[1:, cv2.CC_STAT_AREA])), 255, 0).astype(np.uint8)
        fg = cv2.morphologyEx(fg, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
        alpha = Image.fromarray(fg).resize(im.size, Image.LANCZOS).filter(ImageFilter.GaussianBlur(1.2))
        out_im = im.convert("RGBA")
        out_im.putalpha(alpha)
        bbox = alpha.point(lambda v: 255 if v > 24 else 0).getbbox()
        if bbox:
            out_im = out_im.crop(bbox)
        out = self._out(inputs, src, "cutout", "png")
        out_im.save(out)
        cover = float((np.array(alpha) > 127).mean())
        rec = self._record(inputs, out, [src], {"op": "cutout", "inset": inset, "size": list(out_im.size)})
        return ToolResult(success=True, data={"path": str(out), "size": list(out_im.size), "object_share": round(cover, 3),
                                              "provenance": rec}, artifacts=[str(out)])

    def _batch(self, inputs: dict[str, Any]) -> ToolResult:
        op = inputs["op"]
        outs = []
        for p in inputs["input_paths"]:
            src = Path(p)
            im = _open(src) if op != "strip" else Image.open(src)
            ext = (inputs.get("to") or src.suffix.lstrip(".")).replace("jpeg", "jpg")
            if op == "resize":
                w = inputs.get("width")
                h = inputs.get("height") or round(im.height * w / im.width)
                im = im.resize((int(w), int(h)), Image.LANCZOS)
            elif op == "thumbnail":
                im.thumbnail((int(inputs.get("width", 400)), int(inputs.get("height", 400))), Image.LANCZOS)
            elif op == "crop" and inputs.get("box"):
                # an exact rectangle, [x0, y0, x1, y1] as fractions: no rescaling, every source pixel kept
                x0, y0, x1, y1 = inputs["box"]
                im = im.crop((round(x0 * im.width), round(y0 * im.height), round(x1 * im.width), round(y1 * im.height)))
            elif op == "crop":
                tw, th = _parse_size(inputs["target"])
                scale, box = smart_crop_box(im, tw, th, inputs.get("gravity", "attention"))
                im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS).crop(box)
            elif op == "strip":
                clean = Image.new(im.mode, im.size)
                clean.putdata(list(im.getdata()))
                im = clean
            elif op in ("auto_orient", "format"):
                pass
            out = self._out(inputs, src, op, ext)
            if ext == "jpg":
                im.convert("RGB").save(out, quality=int(inputs.get("quality", 92)))
            else:
                im.save(out)
            self._record(inputs, out, [src], {"op": f"batch:{op}", "params": {k: inputs.get(k) for k in ("width", "height", "target", "to", "box")}})
            outs.append(str(out))
        return ToolResult(success=True, data={"paths": outs}, artifacts=outs)

    def _montage(self, inputs: dict[str, Any]) -> ToolResult:
        paths = [Path(p) for p in inputs["input_paths"]]
        cols = int(inputs.get("cols", 4))
        tw, th = _parse_size(inputs.get("thumb", "400x400"))
        label = inputs.get("label", True)
        lab_h = 28 if label else 0
        gap = 16
        rows = math.ceil(len(paths) / cols)
        sheet = Image.new("RGB", (cols * (tw + gap) + gap, rows * (th + lab_h + gap) + gap), "#f4f1ea")
        d = ImageDraw.Draw(sheet)
        for i, p in enumerate(paths):
            im = _open(p).convert("RGBA")  # keep alpha so masked fragments show their real shape
            im.thumbnail((tw, th), Image.LANCZOS)
            x = gap + (i % cols) * (tw + gap) + (tw - im.width) // 2
            y = gap + (i // cols) * (th + lab_h + gap) + (th - im.height) // 2
            sheet.paste(im, (x, y), im)
            if label:
                d.text((gap + (i % cols) * (tw + gap), gap + (i // cols) * (th + lab_h + gap) + th + 6),
                       f"{i + 1:02d}  {p.name[:42]}", fill="#3a352e")
        out = Path(inputs.get("output_path") or (Path(inputs.get("project_dir", paths[0].parent)) / "review" / "contact-sheet.jpg"))
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.exists():
            out = out.with_name(f"{out.stem}.v{int(time.time())}{out.suffix}")
        sheet.save(out, quality=90)
        return ToolResult(success=True, data={"path": str(out), "count": len(paths)}, artifacts=[str(out)])

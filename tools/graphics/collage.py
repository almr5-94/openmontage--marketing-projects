"""collage: compose fragments, generative layers and photos into page art from a JSON layout.

Layer 5 of the editorial art stack (the mechanics the vendored collage-layout-expert skill
describes but does not ship). Free and local (Pillow + numpy).

Layout (``layout``)::

    {"canvas": {"width_mm": 230, "height_mm": 300, "dpi": 300} | {"width_px": .., "height_px": ..},
     "background": "#efe6d2" | "path/to/plate.png",
     "paper": "uncoated_offwhite" | "cream" | "coated_silk" | "newsprint" | null,   # grain overlay
     "seed": 7,
     "layers": [
        {"src": "assets/fragments/met-1-circle.png",
         "x": 0.5, "y": 0.4,            # centre, fraction of canvas
         "width": 0.6,                  # fraction of canvas width (or "height")
         "rotation": -4,                # degrees
         "mask": {"shape": "hexagon", "params": {"r": 0.45}},   # optional, image_crop shapes
         "blend": "multiply",           # normal|multiply|screen|overlay|darken|lighten|soft_light|difference
         "opacity": 0.95,
         "shadow": {"dx": 0.004, "dy": 0.008, "blur": 0.006, "opacity": 0.35},
         "border": {"width": 0.012, "color": "#fbfaf6"},        # photo-print border (joiners)
         "torn": 0.0,                   # 0..1 rough cut edge
         "z": 3, "flip": false}
     ]}

Or a ``style`` with ``sources`` builds the layers for you: grid, mosaic, joiner (Hockney),
cutpaste (Dada / Surrealist / Pop), moodboard, editorial_overlay. Pass ``layout_only`` to get
the generated layout back for editing instead of rendering.

Output: PNG (and the resolved layout JSON next to it). Recorded in PROVENANCE.json as
``kind: collage, licence: derived`` with every source as a parent.
"""

from __future__ import annotations

import json
import math
import random
import time
from pathlib import Path
from typing import Any, Optional

import numpy as np
from PIL import Image, ImageChops, ImageFilter, ImageOps

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
from tools.graphics.image_crop import apply_mask, shape_mask, smart_crop_box

BLENDS = ["normal", "multiply", "screen", "overlay", "darken", "lighten", "soft_light", "difference"]
STYLES = ["grid", "mosaic", "joiner", "cutpaste", "moodboard", "editorial_overlay"]
PAPER = {"uncoated_offwhite": (243, 239, 230), "cream": (239, 230, 210), "coated_silk": (247, 246, 242),
         "newsprint": (228, 224, 212)}


def canvas_px(c: dict[str, Any]) -> tuple[int, int]:
    if c.get("width_px"):
        return int(c["width_px"]), int(c["height_px"])
    dpi = c.get("dpi", 300)
    return round(c["width_mm"] / 25.4 * dpi), round(c["height_mm"] / 25.4 * dpi)


def paper_grain(size: tuple[int, int], seed: int, strength: float = 0.025) -> Image.Image:
    """Seeded fibrous paper grain (L, 128 = neutral) for multiply/overlay."""
    W, H = size
    rng = np.random.default_rng(seed)
    small = rng.normal(0, 1, (max(1, H // 2), max(1, W // 2))).astype(np.float32)
    im = Image.fromarray(((small - small.min()) / (np.ptp(small) + 1e-6) * 255).astype(np.uint8))
    im = im.resize((W, H), Image.BICUBIC).filter(ImageFilter.GaussianBlur(1.2))
    fibres = Image.fromarray((rng.random((max(1, H // 10), max(1, W // 10))) * 255).astype(np.uint8)).resize((W, H), Image.BICUBIC)
    g = np.asarray(im, dtype=np.float32) * 0.7 + np.asarray(fibres, dtype=np.float32) * 0.3
    g = 128 + (g - g.mean()) * strength * 4
    return Image.fromarray(np.clip(g, 0, 255).astype(np.uint8))


def blend(base: np.ndarray, top: np.ndarray, mode: str) -> np.ndarray:
    """Separable blend modes on float RGB 0..1."""
    if mode == "multiply":
        return base * top
    if mode == "screen":
        return 1 - (1 - base) * (1 - top)
    if mode == "overlay":
        return np.where(base < 0.5, 2 * base * top, 1 - 2 * (1 - base) * (1 - top))
    if mode == "darken":
        return np.minimum(base, top)
    if mode == "lighten":
        return np.maximum(base, top)
    if mode == "soft_light":
        return (1 - 2 * top) * base ** 2 + 2 * top * base
    if mode == "difference":
        return np.abs(base - top)
    return top


def composite(canvas: Image.Image, layer: Image.Image, pos: tuple[int, int], mode: str, opacity: float) -> Image.Image:
    """Blend an RGBA layer onto an RGB canvas at pos (top-left), clipped to the canvas."""
    W, H = canvas.size
    x, y = pos
    lw, lh = layer.size
    x0, y0, x1, y1 = max(0, x), max(0, y), min(W, x + lw), min(H, y + lh)
    if x0 >= x1 or y0 >= y1:
        return canvas
    region = np.asarray(canvas.crop((x0, y0, x1, y1)), dtype=np.float32) / 255
    piece = np.asarray(layer.crop((x0 - x, y0 - y, x1 - x, y1 - y)), dtype=np.float32) / 255
    rgb, a = piece[..., :3], piece[..., 3:4] * opacity
    mixed = blend(region, rgb, mode)
    out = region * (1 - a) + mixed * a
    canvas.paste(Image.fromarray(np.clip(out * 255, 0, 255).astype(np.uint8)), (x0, y0))
    return canvas


def torn_edge(alpha: Image.Image, amount: float, seed: int) -> Image.Image:
    if amount <= 0:
        return alpha
    w, h = alpha.size
    rng = np.random.default_rng(seed)
    noise = Image.fromarray((rng.random((max(2, h // 6), max(2, w // 6))) * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC)
    er = alpha.filter(ImageFilter.MinFilter(max(3, int(min(w, h) * 0.01 * amount) | 1)))
    return Image.composite(alpha, er, noise.point(lambda v: 255 if v > 128 else 0))


def prepare_layer(spec: dict[str, Any], W: int, H: int, root: Path, seed: int) -> tuple[Image.Image, tuple[int, int], Optional[Image.Image]]:
    src = Path(spec["src"])
    if not src.is_absolute():
        src = root / src
    im = ImageOps.exif_transpose(Image.open(src)).convert("RGBA")
    if spec.get("region"):  # [x, y, w, h] fractions of the source: one detail of the scene (joiners)
        rx, ry, rw, rh = spec["region"]
        im = im.crop((round(max(0, rx) * im.width), round(max(0, ry) * im.height),
                      round(min(1, rx + rw) * im.width), round(min(1, ry + rh) * im.height)))
    if spec.get("crop_to"):  # aspect crop before scaling, e.g. [3, 4]
        aw, ah = spec["crop_to"]
        tw = im.width
        th = round(tw * ah / aw)
        if th > im.height:
            th = im.height
            tw = round(th * aw / ah)
        _, box = smart_crop_box(im, tw, th, spec.get("gravity", "attention"))
        im = im.crop(box)
    if spec.get("mask"):
        m = shape_mask(im.size, spec["mask"]["shape"], spec["mask"].get("params", {}))
        im = apply_mask(im, m, trim=spec["mask"].get("params", {}).get("trim", True))
    if spec.get("flip"):
        im = ImageOps.mirror(im)
    if "width" in spec:
        tw = max(1, round(spec["width"] * W))
        th = max(1, round(im.height * tw / im.width))
    else:
        th = max(1, round(spec.get("height", 0.5) * H))
        tw = max(1, round(im.width * th / im.height))
    im = im.resize((tw, th), Image.LANCZOS)
    if spec.get("border"):
        b = max(1, round(spec["border"].get("width", 0.012) * W))
        framed = Image.new("RGBA", (tw + 2 * b, th + 2 * b), spec["border"].get("color", "#fbfaf6"))
        framed.alpha_composite(im, (b, b))
        im = framed
    if spec.get("torn"):
        im.putalpha(torn_edge(im.getchannel("A"), float(spec["torn"]), seed))
    if spec.get("rotation"):
        im = im.rotate(-float(spec["rotation"]), resample=Image.BICUBIC, expand=True)
    cx, cy = spec.get("x", 0.5) * W, spec.get("y", 0.5) * H
    pos = (round(cx - im.width / 2), round(cy - im.height / 2))
    shadow = None
    if spec.get("shadow"):
        s = spec["shadow"]
        a = im.getchannel("A").filter(ImageFilter.GaussianBlur(max(1, s.get("blur", 0.006) * W)))
        shadow = Image.new("RGBA", im.size, (26, 20, 12, 0))
        shadow.putalpha(a.point(lambda v: int(v * s.get("opacity", 0.35))))
    return im, pos, shadow


# ------------------------------------------------------------------ style generators
def style_layers(style: str, sources: list[str], W: int, H: int, seed: int, opts: dict[str, Any]) -> list[dict[str, Any]]:
    r = random.Random(seed)
    L: list[dict[str, Any]] = []
    n = len(sources)
    if style == "grid":
        cols = int(opts.get("cols", math.ceil(math.sqrt(n))))
        rows = math.ceil(n / cols)
        g = opts.get("gutter", 0.012)
        m = opts.get("margin", 0.06)
        cw = (1 - 2 * m - (cols - 1) * g) / cols
        ch = (1 - 2 * m - (rows - 1) * g * W / H) / rows
        for i, s in enumerate(sources):
            c, rr = i % cols, i // cols
            L.append({"src": s, "crop_to": [cw * W, ch * H], "width": cw,
                      "x": m + c * (cw + g) + cw / 2, "y": m + rr * (ch + g * W / H) + ch / 2, "z": 1})
    elif style == "joiner":
        # Hockney: one scene rebuilt from overlapping prints, each a slightly rotated detail of
        # the part of the scene it covers. Pieces sit where their region sits in the scene.
        base = sources[0]
        k = int(opts.get("pieces", 16))
        cols = max(1, round(math.sqrt(k)))
        rows = math.ceil(k / cols)
        ov = float(opts.get("overlap", 0.18))
        area = 0.86
        for i in range(k):
            c, rr = i % cols, i // cols
            rw, rh = (1 + ov) / cols, (1 + ov) / rows
            rx, ry = c / cols - ov / cols / 2, rr / rows - ov / rows / 2
            L.append({"src": sources[i % n] if opts.get("mixed") else base,
                      "region": [rx + r.uniform(-0.02, 0.02), ry + r.uniform(-0.02, 0.02), rw, rh],
                      "width": area * rw * r.uniform(0.97, 1.06),
                      "x": 0.07 + area * (c + 0.5) / cols + r.uniform(-0.012, 0.012),
                      "y": 0.07 + area * (rr + 0.5) / rows + r.uniform(-0.012, 0.012),
                      "rotation": r.uniform(-6, 6), "border": {"width": 0.006, "color": "#fbfaf6"},
                      "shadow": {"blur": 0.004, "opacity": 0.3}, "z": r.randint(1, 50)})
    elif style == "cutpaste":
        for i, s in enumerate(sources):
            w = r.uniform(0.3, 0.55)
            L.append({"src": s, "width": w, "x": r.uniform(0.12 + w / 2, 0.88 - w / 2), "y": 0.18 + 0.64 * (i + r.uniform(0.2, 0.8)) / n,
                      "rotation": r.uniform(-14, 14), "torn": r.uniform(0.3, 1.0) if opts.get("torn", True) else 0,
                      "blend": r.choice(["normal", "normal", "multiply", "darken"]),
                      "shadow": {"blur": 0.005, "opacity": 0.32}, "z": i + 1,
                      "mask": {"shape": r.choice(["circle", "polygon", "stripe", "triangle"]),
                               "params": {"points": [[r.uniform(0, .3), r.uniform(0, .3)], [r.uniform(.7, 1), r.uniform(0, .3)],
                                                     [r.uniform(.7, 1), r.uniform(.7, 1)], [r.uniform(0, .3), r.uniform(.7, 1)]],
                                          "count": r.randint(3, 6), "angle": r.uniform(-30, 30)}} if r.random() < 0.6 else None})
    elif style == "moodboard":
        cols = int(opts.get("cols", 2 if n <= 4 else 3))
        rows = math.ceil(n / cols)
        for i, s in enumerate(sources):
            c, rr = i % cols, i // cols
            L.append({"src": s, "width": 0.82 / cols * r.uniform(0.85, 1.0),
                      "x": 0.09 + 0.82 * (c + 0.5) / cols + r.uniform(-0.03, 0.03),
                      "y": 0.09 + 0.82 * (rr + 0.5) / rows + r.uniform(-0.03, 0.03),
                      "rotation": r.uniform(-4, 4), "border": {"width": 0.006, "color": "#ffffff"},
                      "shadow": {"blur": 0.006, "opacity": 0.3}, "z": i + 1})
    elif style == "editorial_overlay":
        L.append({"src": sources[0], "crop_to": [W, H], "width": 1.0, "x": 0.5, "y": 0.5, "z": 0})
        for i, s in enumerate(sources[1:3]):
            L.append({"src": s, "width": 0.42 - 0.1 * i, "x": 0.68 - 0.36 * i, "y": 0.62 - 0.22 * i,
                      "mask": {"shape": ["circle", "arc"][i % 2], "params": {"r": 0.48, "ri": 0.3, "start": 180, "end": 360}},
                      "blend": opts.get("blend", "multiply"), "opacity": 0.92, "z": i + 1})
    elif style == "mosaic":
        L.append({"__mosaic__": True})
    else:
        raise ValueError(f"unknown style {style!r}; one of {STYLES}")
    return L


def photo_mosaic(target: str, sources: list[str], W: int, H: int, tiles: int, seed: int) -> Image.Image:
    """Classic photo mosaic: each cell of the target filled by the source tile nearest in colour."""
    tgt = ImageOps.fit(Image.open(target).convert("RGB"), (W, H))
    cols = tiles
    cw = W // cols
    rows = H // cw
    thumbs = []
    for s in sources:
        t = ImageOps.fit(Image.open(s).convert("RGB"), (cw, cw))
        thumbs.append((np.asarray(t, dtype=np.float32).reshape(-1, 3).mean(0), t))
    out = Image.new("RGB", (W, H))
    for j in range(rows + 1):
        for i in range(cols + 1):
            box = (i * cw, j * cw, min(W, (i + 1) * cw), min(H, (j + 1) * cw))
            if box[0] >= W or box[1] >= H:
                continue
            mean = np.asarray(tgt.crop(box), dtype=np.float32).reshape(-1, 3).mean(0)
            k = int(np.argmin([np.sum((m - mean) ** 2) for m, _ in thumbs]))
            tile = thumbs[k][1]
            tint = Image.new("RGB", tile.size, tuple(int(v) for v in mean))
            out.paste(Image.blend(tile, tint, 0.35).crop((0, 0, box[2] - box[0], box[3] - box[1])), box[:2])
    return out


class Collage(BaseTool):
    name = "collage"
    version = "0.1.0"
    tier = ToolTier.CORE
    capability = "collage"
    provider = "pillow"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.SEEDED
    runtime = ToolRuntime.LOCAL
    dependencies = ["python:PIL", "python:numpy"]
    capabilities = ["json_layout_composite", "blend_modes", "geometric_masks", "shadows", "paper_texture",
                    "style_grid", "style_mosaic", "style_joiner", "style_cutpaste", "style_moodboard", "style_editorial_overlay"]
    supports = {"styles": STYLES, "blends": BLENDS, "cost": "free (local)"}
    best_for = ["page art assembled from CC0 fragments, generative layers and photos",
                "Hockney joiners, Dada/Surrealist/Pop cut-and-paste, mood boards, editorial overlays"]
    not_good_for = ["inventing new imagery (art_source, generative_art, or the Runway MCP)"]
    resource_profile = ResourceProfile(cpu_cores=1, ram_mb=3072, vram_mb=0, disk_mb=300)
    side_effects = ["writes a PNG and its layout JSON under projects/<id>/assets/collage/", "appends to PROVENANCE.json"]
    agent_skills = ["collage-composition"]
    input_schema = {
        "type": "object",
        "properties": {
            "layout": {"type": "object"},
            "style": {"type": "string", "enum": STYLES},
            "sources": {"type": "array", "items": {"type": "string"}},
            "canvas": {"type": "object"},
            "seed": {"type": "integer", "default": 1},
            "options": {"type": "object"},
            "project_dir": {"type": "string"},
            "output_stem": {"type": "string"},
            "layout_only": {"type": "boolean", "default": False},
        },
    }

    def get_status(self) -> ToolStatus:
        return ToolStatus.AVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        return 0.0

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        start = time.time()
        try:
            pd = inputs.get("project_dir")
            root = Path(pd) if pd else Path.cwd()
            seed = int(inputs.get("seed", (inputs.get("layout") or {}).get("seed", 1)))
            layout = dict(inputs.get("layout") or {})
            if inputs.get("style"):
                layout.setdefault("canvas", inputs.get("canvas") or {"width_px": 2400, "height_px": 3000})
                W, H = canvas_px(layout["canvas"])
                layers = style_layers(inputs["style"], inputs["sources"], W, H, seed, inputs.get("options") or {})
                layout["layers"] = layers
                layout.setdefault("background", (inputs.get("options") or {}).get("background", "#efe6d2"))
                layout.setdefault("paper", (inputs.get("options") or {}).get("paper", "uncoated_offwhite"))
                layout["style"] = inputs["style"]
            layout["seed"] = seed
            if inputs.get("layout_only"):
                return ToolResult(success=True, data={"layout": layout})
            W, H = canvas_px(layout["canvas"])
            bg = layout.get("background", "#ffffff")
            if isinstance(bg, str) and bg.startswith("#"):
                canvas = Image.new("RGB", (W, H), bg)
            else:
                bp = Path(bg) if Path(bg).is_absolute() else root / bg
                canvas = ImageOps.fit(Image.open(bp).convert("RGB"), (W, H))
            sources_used: list[str] = [] if isinstance(bg, str) and bg.startswith("#") else [str(bg)]
            if layout.get("layers") and layout["layers"][0].get("__mosaic__"):
                srcs = inputs["sources"]
                canvas = photo_mosaic(str(root / srcs[0]) if not Path(srcs[0]).is_absolute() else srcs[0],
                                      [str(root / s) if not Path(s).is_absolute() else s for s in srcs[1:]],
                                      W, H, int((inputs.get("options") or {}).get("tiles", 40)), seed)
                sources_used += srcs
            else:
                for i, spec in enumerate(sorted(layout.get("layers", []), key=lambda s: s.get("z", 0))):
                    im, pos, shadow = prepare_layer(spec, W, H, root, seed + i)
                    if shadow is not None:
                        s = spec["shadow"]
                        canvas = composite(canvas, shadow, (pos[0] + round(s.get("dx", 0.004) * W), pos[1] + round(s.get("dy", 0.008) * W)), "multiply", 1.0)
                    canvas = composite(canvas, im, pos, spec.get("blend", "normal"), float(spec.get("opacity", 1.0)))
                    sources_used.append(spec["src"])
            if layout.get("paper"):
                grain = paper_grain((W, H), seed).convert("RGB")
                canvas = Image.fromarray(np.clip(np.asarray(canvas, dtype=np.float32) * (np.asarray(grain, dtype=np.float32) / 128.0) ** 0.5, 0, 255).astype(np.uint8))
            out_dir = root / "assets" / "collage" if pd else Path.cwd()
            out_dir.mkdir(parents=True, exist_ok=True)
            stem = inputs.get("output_stem") or f"collage-{layout.get('style', 'custom')}-s{seed}"
            out = out_dir / f"{stem}.png"
            k = 2
            while out.exists():
                out = out_dir / f"{stem}.v{k}.png"
                k += 1
            canvas.save(out, dpi=(layout["canvas"].get("dpi", 300),) * 2)
            out.with_suffix(".layout.json").write_text(json.dumps(layout, indent=2), encoding="utf-8")
            rec = None
            if pd:
                parents = [provenance.rel(pd, (root / s) if not Path(s).is_absolute() else s) for s in sources_used]
                rec = provenance.record(pd, out, kind="collage", source="collage", licence="derived", parents=parents,
                                        tool=self.name, seed=seed, crop={"layout": str(out.with_suffix('.layout.json').name)})
            return ToolResult(success=True, data={"path": str(out), "layout_path": str(out.with_suffix(".layout.json")),
                                                  "size_px": [W, H], "seed": seed, "provenance": rec},
                              artifacts=[str(out)], seed=seed, duration_seconds=time.time() - start)
        except Exception as e:
            return ToolResult(success=False, error=f"{type(e).__name__}: {e}")

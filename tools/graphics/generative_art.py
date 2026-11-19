"""generative_art: seeded, deterministic art plates at print resolution (PNG + SVG).

Layer 4 of the editorial art stack. Free and local. The same ``seed`` always produces the same
SVG, byte for byte, and therefore the same plate. The seed is returned, recorded in
PROVENANCE.json and logged in the decision log by the calling stage.

This engine exists to *avoid* the AP-2 failure ("a good idea, a cheap execution": thin,
uniform-stroke vector clip-art). Every algorithm draws with **material**:

* varied line weight: strokes are filled ribbons whose width follows a pressure curve,
* ink spread: edge roughening (turbulence displacement) plus a slight bleed,
* paper grain: a lit fractal-noise paper surface under the drawing (optional paper colour),
* metallic / foil: brushed-metal gradients with specular light (``finish: "brass"|"gold"|"silver"``),
* light and shadow: embossed objects cast a soft shadow on the paper.

Algorithms (``algorithm``):

=============  ==========================================================================
flow_field     ink lines traced through a seeded noise field (wind, water, hair, smoke); params heading, turn, weight steer it
engraving      hatched engraving whose line weight follows the tone of a source image
               (``source_image``) or a seeded light field; the classic banknote/plate look
arches         nested arches / thresholds rendered as an engraved, foil-finished object
               (the right way to draw an architectural motif)
voronoi        cell mosaic, each cell flat colour + inner hatching (stained glass, terrazzo)
stipple        tone rendered as ink dots, from ``source_image`` or a seeded field
botanical      L-system plant with tapering, pressure-varied strokes (pen-plotter herbarium)
truchet        arc tiles forming continuous lines (pattern papers, endpapers)
p5             run a p5.js sketch file (``sketch_path``) headless with a seeded tokenData hash,
               genart-skill style: ``random()`` and ``noise()`` are seeded from it
=============  ==========================================================================

Size: ``width_mm``/``height_mm`` + ``dpi`` (default 300) for print, or ``width_px``/``height_px``.
Output: ``<stem>.png`` (+ ``<stem>.svg`` for vector algorithms) under ``projects/<id>/assets/generative/``.
"""

from __future__ import annotations

import hashlib
import html
import json
import math
import random
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Optional

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
P5_JS = REPO / "vendor" / "p5" / "p5.min.js"

PAPERS = {
    "uncoated_offwhite": "#f3efe6",
    "cream": "#efe6d2",
    "coated_silk": "#f7f6f2",
    "newsprint": "#e4e0d4",
    "black": "#141210",
    "none": None,
}
FINISHES = {
    "ink": None,
    "brass": ["#5b4520", "#b8913f", "#f1d98c", "#9c7a32", "#4a3818"],
    "gold": ["#6b4e12", "#d4a73a", "#fff0b0", "#c2932c", "#5c420f"],
    "silver": ["#55585c", "#a9adb2", "#f4f6f8", "#8f9398", "#45484c"],
    "copper": ["#5a2b17", "#b4643c", "#f2b48e", "#9a5333", "#4a2212"],
}
ALGORITHMS = ["flow_field", "engraving", "arches", "voronoi", "stipple", "botanical", "truchet", "p5"]


# ------------------------------------------------------------------ seeded noise
class Noise:
    """2D value noise with smooth interpolation and octaves, fully seeded."""

    def __init__(self, seed: int):
        r = random.Random(seed ^ 0x5EED)
        self.perm = list(range(256))
        r.shuffle(self.perm)
        self.perm += self.perm
        self.vals = [r.random() for _ in range(256)]

    def _v(self, x: int, y: int) -> float:
        return self.vals[self.perm[(self.perm[x & 255] + y) & 255]]

    def value(self, x: float, y: float) -> float:
        xi, yi = math.floor(x), math.floor(y)
        xf, yf = x - xi, y - yi
        u, v = xf * xf * (3 - 2 * xf), yf * yf * (3 - 2 * yf)
        a, b = self._v(xi, yi), self._v(xi + 1, yi)
        c, d = self._v(xi, yi + 1), self._v(xi + 1, yi + 1)
        return (a + (b - a) * u) * (1 - v) + (c + (d - c) * u) * v

    def fbm(self, x: float, y: float, octaves: int = 4) -> float:
        total, amp, freq, norm = 0.0, 1.0, 1.0, 0.0
        for _ in range(octaves):
            total += amp * self.value(x * freq, y * freq)
            norm += amp
            amp *= 0.5
            freq *= 2.0
        return total / norm


# ------------------------------------------------------------------ SVG helpers
def f(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".")


def ribbon(points: list[tuple[float, float]], widths: list[float]) -> str:
    """A filled polygon around a polyline whose width varies per point (true pressure)."""
    if len(points) < 2:
        return ""
    left, right = [], []
    for i, (x, y) in enumerate(points):
        x0, y0 = points[max(0, i - 1)]
        x1, y1 = points[min(len(points) - 1, i + 1)]
        dx, dy = x1 - x0, y1 - y0
        n = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / n, dx / n
        w = widths[i] / 2
        left.append((x + nx * w, y + ny * w))
        right.append((x - nx * w, y - ny * w))
    pts = left + right[::-1]
    return "M" + " L".join(f"{f(x)} {f(y)}" for x, y in pts) + " Z"


def defs(W: int, H: int, seed: int, ink_spread: float, paper: Optional[str], finish: Optional[list[str]]) -> str:
    grain_seed = seed % 997
    out = [f'<defs>',
           f'<filter id="ink" x="-2%" y="-2%" width="104%" height="104%">'
           f'<feTurbulence type="fractalNoise" baseFrequency="{f(0.9 / max(1, W / 2480))}" numOctaves="2" seed="{grain_seed}" result="n"/>'
           f'<feDisplacementMap in="SourceGraphic" in2="n" scale="{f(ink_spread * 2.2)}" xChannelSelector="R" yChannelSelector="G" result="d"/>'
           f'<feGaussianBlur in="d" stdDeviation="{f(ink_spread * 0.35)}" result="b"/>'
           f'<feMerge><feMergeNode in="b"/><feMergeNode in="d"/></feMerge></filter>']
    if paper:
        out.append(
            f'<filter id="paper" x="0" y="0" width="100%" height="100%">'
            f'<feTurbulence type="fractalNoise" baseFrequency="{f(0.55 * 2480 / max(W, 1) * 0.6)}" numOctaves="4" seed="{grain_seed + 1}" result="g"/>'
            f'<feDiffuseLighting in="g" surfaceScale="1.6" lighting-color="#ffffff" result="l"><feDistantLight azimuth="235" elevation="58"/></feDiffuseLighting>'
            f'<feComposite in="l" in2="SourceGraphic" operator="arithmetic" k1="1" k2="0" k3="0" k4="0"/></filter>')
    if finish:
        stops = "".join(f'<stop offset="{f(i / (len(finish) - 1))}" stop-color="{c}"/>' for i, c in enumerate(finish))
        out.append(f'<linearGradient id="metal" x1="0" y1="0" x2="1" y2="1">{stops}</linearGradient>')
        out.append(
            '<filter id="foil" x="-5%" y="-5%" width="110%" height="110%">'
            f'<feTurbulence type="fractalNoise" baseFrequency="0.004 0.6" numOctaves="2" seed="{grain_seed + 2}" result="brush"/>'
            '<feGaussianBlur in="SourceAlpha" stdDeviation="2" result="a"/>'
            '<feSpecularLighting in="a" surfaceScale="4" specularConstant="0.9" specularExponent="24" lighting-color="#fff6d8" result="s">'
            '<fePointLight x="-400" y="-600" z="900"/></feSpecularLighting>'
            '<feComposite in="s" in2="SourceAlpha" operator="in" result="sh"/>'
            '<feComposite in="brush" in2="SourceAlpha" operator="in" result="br"/>'
            '<feBlend in="SourceGraphic" in2="br" mode="multiply" result="m"/>'
            '<feComposite in="m" in2="sh" operator="arithmetic" k1="0" k2="1" k3="0.55" k4="0"/></filter>')
    out.append(
        '<filter id="shadow" x="-10%" y="-10%" width="125%" height="130%">'
        f'<feDropShadow dx="{f(W * 0.004)}" dy="{f(W * 0.007)}" stdDeviation="{f(W * 0.006)}" flood-color="#1a140c" flood-opacity="0.38"/></filter>')
    out.append('</defs>')
    return "".join(out)


def paper_layer(W: int, H: int, paper: Optional[str]) -> str:
    if not paper:
        return ""
    return (f'<rect width="{W}" height="{H}" fill="{paper}"/>'
            f'<rect width="{W}" height="{H}" fill="{paper}" filter="url(#paper)" opacity="0.55" style="mix-blend-mode:multiply"/>')


# ------------------------------------------------------------------ tone sources
def tone_sampler(source_image: Optional[str], W: int, H: int, noise: Noise, contrast: float = 1.0) -> Callable[[float, float], float]:
    """Return t(x, y) in 0..1 where 1 = darkest. From an image (cover-fit) or seeded light."""
    if source_image:
        from PIL import Image, ImageOps

        im = ImageOps.exif_transpose(Image.open(source_image))
        if im.mode in ("RGBA", "LA") or "transparency" in im.info:
            # a cut-out: the ground is paper (no ink), and the whole object is kept in frame
            rgba = im.convert("RGBA")
            ground = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
            im = Image.alpha_composite(ground, rgba).convert("L")
            margin = 0.12
            fit = min(W * (1 - 2 * margin) / im.width, H * (1 - 2 * margin) / im.height)
            canvas = Image.new("L", (int(W), int(H)), 255)
            obj = im.resize((max(1, round(im.width * fit)), max(1, round(im.height * fit))), Image.LANCZOS)
            canvas.paste(obj, ((int(W) - obj.width) // 2, int(H * 0.55 - obj.height / 2)))
            im = canvas
        else:
            im = im.convert("L")
        scale = max(W / im.width, H / im.height)
        sw, sh = max(1, round(im.width * scale / 4)), max(1, round(im.height * scale / 4))
        im = im.resize((sw, sh))
        ox, oy = (sw - W / 4) / 2, (sh - H / 4) / 2
        px = im.load()

        def t(x: float, y: float) -> float:
            xi = min(sw - 1, max(0, int(x / 4 + ox)))
            yi = min(sh - 1, max(0, int(y / 4 + oy)))
            v = 1 - px[xi, yi] / 255
            return max(0.0, min(1.0, 0.5 + (v - 0.5) * contrast))

        return t

    def t(x: float, y: float) -> float:
        lx, ly = x / W - 0.3, y / H - 0.25
        light = math.hypot(lx, ly)
        return max(0.0, min(1.0, 0.15 + light * 0.75 + (noise.fbm(x / W * 3, y / H * 3) - 0.5) * 0.5))

    return t


# ------------------------------------------------------------------ algorithms
def algo_flow_field(W, H, r, noise, p, ink):
    n_lines = int(p.get("lines", 900))
    step = W / 500
    steps = int(p.get("length", 140))
    scale = p.get("scale", 2.2)
    # heading (degrees) and turn (how far a line may swing, 2 = any direction) steer the field:
    # heading 0, turn 0.12 draws long horizontal tide marks instead of smoke
    heading, turn = math.radians(p.get("heading", 0.0)), float(p.get("turn", 2.0))
    weight = float(p.get("weight", 1.0))
    out = []
    for _ in range(n_lines):
        x, y = r.uniform(-0.05, 1.05) * W, r.uniform(-0.05, 1.05) * H
        pts, ws = [], []
        base_w = W * r.uniform(0.0006, 0.0028) * weight
        for k in range(steps):
            a = heading + noise.fbm(x / W * scale, y / H * scale) * math.tau * turn
            pts.append((x, y))
            press = math.sin(math.pi * k / max(1, steps - 1))  # taper both ends
            ws.append(base_w * (0.25 + press))
            x += math.cos(a) * step
            y += math.sin(a) * step
        out.append(f'<path d="{ribbon(pts, ws)}" fill="{ink}" opacity="{f(r.uniform(0.55, 0.95))}"/>')
    return "".join(out)


def algo_engraving(W, H, r, noise, p, ink, tone):
    spacing = W * p.get("spacing", 0.0042)
    angle = math.radians(p.get("angle", -32))
    max_w = spacing * p.get("max_weight", 0.92)
    out = []
    ca, sa = math.cos(angle), math.sin(angle)
    D = math.hypot(W, H)
    n = int(D / spacing)
    for i in range(n):
        off = -D / 2 + i * spacing
        pts, ws = [], []
        seg = W / 260
        t_ = -D / 2
        while t_ <= D / 2:
            x = W / 2 + ca * t_ - sa * off
            y = H / 2 + sa * t_ + ca * off
            if -10 <= x <= W + 10 and -10 <= y <= H + 10:
                wob = (noise.value(t_ / W * 8, i * 0.37) - 0.5) * spacing * 0.25
                pts.append((x - sa * wob, y + ca * wob))
                ws.append(max(0.0, tone(x, y) ** 1.25 * max_w))
            elif pts:
                break
            t_ += seg
        # split where width is ~0 so light areas show paper (engraver lifts the burin)
        run_p, run_w = [], []
        for pt, w in zip(pts + [None], ws + [0]):
            if pt is not None and w > max_w * 0.06:
                run_p.append(pt)
                run_w.append(w)
            elif len(run_p) > 1:
                out.append(f'<path d="{ribbon(run_p, run_w)}" fill="{ink}"/>')
                run_p, run_w = [], []
            else:
                run_p, run_w = [], []
    if p.get("cross_hatch", True):
        q = dict(p, angle=p.get("angle", -32) + 64, cross_hatch=False, max_weight=p.get("max_weight", 0.92) * 0.7)
        out.append(algo_engraving(W, H, r, noise, q, ink, lambda x, y: max(0.0, tone(x, y) - 0.45) / 0.55))
    return "".join(out)


def algo_arches(W, H, r, noise, p, ink, finish_on):
    cx, base = W / 2, H * p.get("base", 0.86)
    rings = int(p.get("rings", 7))
    outer = W * p.get("width", 0.36)
    out = []
    fill = "url(#metal)" if finish_on else ink
    group_filter = 'filter="url(#foil)"' if finish_on else ""
    out.append(f'<g filter="url(#shadow)"><g {group_filter}>')
    for k in range(rings):
        rad = outer * (1 - k / (rings + 1.4))
        thick = outer * (0.055 - 0.0035 * k) * (0.85 + 0.3 * r.random())
        legs = H * p.get("legs", 0.32)
        pts, ws = [], []
        # left leg up, arch over, right leg down: one continuous engraved band
        for s in range(40):
            y = base - legs * s / 39
            pts.append((cx - rad, y))
        for s in range(1, 120):
            a = math.pi + math.pi * s / 119
            pts.append((cx + rad * math.cos(a), base - legs + rad * math.sin(a)))
        for s in range(40):
            pts.append((cx + rad, base - legs + legs * s / 39))
        for i, (x, y) in enumerate(pts):
            ws.append(thick * (0.82 + 0.36 * noise.value(i * 0.05, k * 1.7)))
        out.append(f'<path d="{ribbon(pts, ws)}" fill="{fill}"/>')
        # engraved inner line in each band (the burin's second pass)
        inner = [(x, y) for x, y in pts]
        out.append(f'<path d="{ribbon(inner, [w * 0.12 for w in ws])}" fill="{FINISHES["brass"][4] if finish_on else "#000"}" opacity="0.55"/>')
    # a threshold slab
    out.append(f'<rect x="{f(cx - outer * 1.25)}" y="{f(base)}" width="{f(outer * 2.5)}" height="{f(H * 0.035)}" fill="{fill}"/>')
    out.append("</g></g>")
    return "".join(out)


def algo_voronoi(W, H, r, noise, p, ink, palette):
    import numpy as np
    from scipy.spatial import Voronoi

    n = int(p.get("cells", 140))
    pts = np.array([[r.uniform(-0.1, 1.1) * W, r.uniform(-0.1, 1.1) * H] for _ in range(n)])
    vor = Voronoi(pts)
    out = []
    for pi, reg_i in enumerate(vor.point_region):
        reg = vor.regions[reg_i]
        if not reg or -1 in reg:
            continue
        poly = [tuple(vor.vertices[v]) for v in reg]
        cx = sum(x for x, _ in poly) / len(poly)
        cy = sum(y for _, y in poly) / len(poly)
        shrink = p.get("grout", 0.06)
        poly = [(x + (cx - x) * shrink, y + (cy - y) * shrink) for x, y in poly]
        col = palette[r.randrange(len(palette))]
        d = "M" + " L".join(f"{f(x)} {f(y)}" for x, y in poly) + " Z"
        out.append(f'<path d="{d}" fill="{col}" opacity="{f(r.uniform(0.82, 0.98))}"/>')
    out.append(f'<g opacity="0.16">{algo_flow_field(W, H, r, noise, {"lines": 260, "length": 60}, ink)}</g>')
    return "".join(out)


def algo_stipple(W, H, r, noise, p, ink, tone):
    n = int(p.get("dots", W * H / 22))  # density follows the plate area
    rad = W * p.get("dot", 0.0011)
    gamma = p.get("gamma", 1.8)
    out = []
    for _ in range(n * 4):
        if len(out) >= n:
            break
        x, y = r.random() * W, r.random() * H
        if r.random() < tone(x, y) ** gamma:
            out.append(f'<circle cx="{f(x)}" cy="{f(y)}" r="{f(rad * r.uniform(0.6, 1.3))}"/>')
    return f'<g fill="{ink}">{"".join(out)}</g>'


def algo_botanical(W, H, r, noise, p, ink):
    depth = int(p.get("depth", 7))
    out = []

    def branch(x, y, ang, length, width, d):
        if d == 0 or length < W * 0.004:
            # leaf: a small pressure-shaped ribbon
            lx, ly = x + math.cos(ang) * length * 2.2, y + math.sin(ang) * length * 2.2
            pts = [(x + (lx - x) * t, y + (ly - y) * t) for t in [i / 8 for i in range(9)]]
            ws = [width * 5 * math.sin(math.pi * i / 8) + 0.3 for i in range(9)]
            out.append(f'<path d="{ribbon(pts, ws)}" fill="{ink}" opacity="0.8"/>')
            return
        pts, ws = [], []
        cx, cy = x, y
        segs = 10
        for i in range(segs + 1):
            pts.append((cx, cy))
            ws.append(width * (1 - 0.45 * i / segs))
            if i == segs:
                break  # children start exactly where this stroke ends: no gaps
            bend = (noise.value(cx / W * 6, cy / H * 6) - 0.5) * 0.25
            cx += math.cos(ang + bend) * length / segs
            cy += math.sin(ang + bend) * length / segs
        out.append(f'<path d="{ribbon(pts, ws)}" fill="{ink}"/>')
        kids = 2 if r.random() < 0.75 else 3
        for k in range(kids):
            spread = r.uniform(0.25, 0.6) * (1 if k % 2 else -1)
            branch(cx, cy, ang + spread, length * r.uniform(0.62, 0.8), width * 0.66, d - 1)

    branch(W / 2, H * 0.96, -math.pi / 2, H * 0.24, W * 0.012, depth)
    return "".join(out)


def algo_truchet(W, H, r, noise, p, ink):
    n = int(p.get("tiles", 14))
    s = W / n
    rows = int(math.ceil(H / s))
    out = []
    lw = s * p.get("weight", 0.11)
    for j in range(rows):
        for i in range(n):
            x, y = i * s, j * s
            flip = r.random() < 0.5
            for (ax, ay, a0) in ([(x, y, 0), (x + s, y + s, math.pi)] if flip else [(x + s, y, math.pi / 2), (x, y + s, -math.pi / 2)]):
                pts = [(ax + s / 2 * math.cos(a0 + math.pi / 2 * t / 16), ay + s / 2 * math.sin(a0 + math.pi / 2 * t / 16)) for t in range(17)]
                ws = [lw * (0.8 + 0.4 * noise.value((x + t) / s, y / s)) for t in range(17)]
                out.append(f'<path d="{ribbon(pts, ws)}" fill="{ink}"/>')
    return "".join(out)


# ------------------------------------------------------------------ the tool
class GenerativeArt(BaseTool):
    name = "generative_art"
    version = "0.1.0"
    tier = ToolTier.GENERATE
    capability = "generative_art"
    provider = "openmontage"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.SEEDED
    runtime = ToolRuntime.LOCAL
    dependencies = ["python:PIL", "python:numpy", "python:scipy"]
    install_instructions = "Local. PNG output needs headless Chromium (the page_render tool)."
    capabilities = ["seeded_generative_plate", "svg_export", "print_resolution_png", "material_rendering", "p5_sketch_headless"]
    supports = {"algorithms": ALGORITHMS, "finishes": list(FINISHES), "papers": list(PAPERS), "cost": "free (local)"}
    best_for = [
        "backgrounds, endpapers, pattern layers and geometric motifs with real material",
        "engraved / stippled renderings of a CC0 artwork or photo (drawing-series plates)",
        "deterministic, reproducible art (same seed, same plate)",
    ]
    not_good_for = ["depicting real objects photographically (use art_source, stock or Runway)"]
    resource_profile = ResourceProfile(cpu_cores=2, ram_mb=2048, vram_mb=0, disk_mb=300)
    side_effects = ["writes PNG and SVG under projects/<id>/assets/generative/", "appends to assets/PROVENANCE.json"]
    agent_skills = ["generative-art"]
    idempotency_key_fields = ["algorithm", "seed", "width_px", "height_px", "width_mm", "height_mm", "dpi", "params"]
    input_schema = {
        "type": "object",
        "required": ["algorithm", "seed"],
        "properties": {
            "algorithm": {"type": "string", "enum": ALGORITHMS},
            "seed": {"type": "integer"},
            "width_mm": {"type": "number"}, "height_mm": {"type": "number"},
            "dpi": {"type": "integer", "default": 300},
            "width_px": {"type": "integer"}, "height_px": {"type": "integer"},
            "params": {"type": "object"},
            "ink": {"type": "string", "default": "#1b1712"},
            "palette": {"type": "array", "items": {"type": "string"}},
            "paper": {"type": "string", "enum": list(PAPERS), "default": "uncoated_offwhite"},
            "finish": {"type": "string", "enum": list(FINISHES), "default": "ink"},
            "ink_spread": {"type": "number", "default": 1.0},
            "source_image": {"type": "string", "description": "tone source for engraving/stipple"},
            "sketch_path": {"type": "string", "description": "p5 sketch (.js) for algorithm=p5"},
            "project_dir": {"type": "string"},
            "output_stem": {"type": "string"},
            "svg_only": {"type": "boolean", "default": False},
        },
    }

    def get_status(self) -> ToolStatus:
        return ToolStatus.AVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        return 0.0

    @staticmethod
    def size_px(inputs: dict[str, Any]) -> tuple[int, int]:
        if inputs.get("width_px") and inputs.get("height_px"):
            return int(inputs["width_px"]), int(inputs["height_px"])
        dpi = int(inputs.get("dpi", 300))
        return round(inputs["width_mm"] / 25.4 * dpi), round(inputs["height_mm"] / 25.4 * dpi)

    def build_svg(self, inputs: dict[str, Any]) -> str:
        algo = inputs["algorithm"]
        seed = int(inputs["seed"])
        W, H = self.size_px(inputs)
        r = random.Random(seed)
        noise = Noise(seed)
        p = inputs.get("params") or {}
        ink = inputs.get("ink", "#1b1712")
        paper = PAPERS.get(inputs.get("paper", "uncoated_offwhite"), inputs.get("paper"))
        finish = FINISHES.get(inputs.get("finish", "ink"))
        spread = float(inputs.get("ink_spread", 1.0)) * W / 2480
        palette = inputs.get("palette") or ["#1f3a4d", "#b8913f", "#8c2f1e", "#d9cdb0", "#2f4a36"]
        tone = lambda: tone_sampler(inputs.get("source_image"), W, H, noise, p.get("contrast", 1.2))  # noqa: E731
        body = {
            "flow_field": lambda: algo_flow_field(W, H, r, noise, p, ink),
            "engraving": lambda: algo_engraving(W, H, r, noise, p, ink, tone()),
            "arches": lambda: algo_arches(W, H, r, noise, p, ink, finish is not None),
            "voronoi": lambda: algo_voronoi(W, H, r, noise, p, ink, palette),
            "stipple": lambda: algo_stipple(W, H, r, noise, p, ink, tone()),
            "botanical": lambda: algo_botanical(W, H, r, noise, p, ink),
            "truchet": lambda: algo_truchet(W, H, r, noise, p, ink),
        }[algo]()
        ink_filter = 'filter="url(#ink)"' if algo != "arches" else ""
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">'
                f'<!-- generative_art {algo} seed={seed} -->'
                f'{defs(W, H, seed, spread, paper, finish)}{paper_layer(W, H, paper)}'
                f'<g {ink_filter}>{body}</g></svg>')

    def _p5_html(self, inputs: dict[str, Any], W: int, H: int) -> str:
        sketch = Path(inputs["sketch_path"]).read_text(encoding="utf-8")
        seed = int(inputs["seed"])
        token = "0x" + hashlib.sha256(str(seed).encode()).hexdigest()
        return f"""<!doctype html><html><head><meta charset="utf-8">
<style>html,body{{margin:0;background:#fff}}canvas{{display:block}}</style>
<script src="{P5_JS.as_uri()}"></script>
<script>
// genart-skill convention: tokenData.hash is the only source of randomness.
window.tokenData = {{ hash: "{token}" }};
window.OM_W = {W}; window.OM_H = {H};
const __seed = parseInt(tokenData.hash.slice(2, 14), 16);
const __setup = () => {{ randomSeed(__seed); noiseSeed(__seed); pixelDensity(1); }};
</script>
<script>{sketch}</script>
<script>
const __userSetup = window.setup;
window.setup = function() {{ __setup(); if (__userSetup) __userSetup(); }};
</script></head><body></body></html>"""

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        start = time.time()
        try:
            algo = inputs.get("algorithm")
            if algo not in ALGORITHMS:
                return ToolResult(success=False, error=f"unknown algorithm {algo!r}; one of {ALGORITHMS}")
            if "seed" not in inputs:
                return ToolResult(success=False, error="seed is required (determinism)")
            seed = int(inputs["seed"])
            W, H = self.size_px(inputs)
            pd = inputs.get("project_dir")
            out_dir = Path(pd) / "assets" / "generative" if pd else Path(tempfile.mkdtemp(prefix="om-genart-"))
            out_dir.mkdir(parents=True, exist_ok=True)
            stem = inputs.get("output_stem") or f"{algo}-s{seed}-{W}x{H}"
            png = out_dir / f"{stem}.png"
            svg_path: Optional[Path] = None
            n = 2
            while png.exists():  # never overwrite a take
                png = out_dir / f"{stem}.v{n}.png"
                n += 1
            if algo == "p5":
                page = out_dir / f".om-p5-{png.stem}.html"
                page.write_text(self._p5_html(inputs, W, H), encoding="utf-8")
                html_path = page
            else:
                svg = self.build_svg(inputs)
                svg_path = png.with_suffix(".svg")
                svg_path.write_text(svg, encoding="utf-8")
                if inputs.get("svg_only"):
                    return ToolResult(success=True, data={"svg": str(svg_path), "seed": seed, "size_px": [W, H]},
                                      artifacts=[str(svg_path)], seed=seed)
                page = out_dir / f".om-svg-{png.stem}.html"
                page.write_text(
                    "<!doctype html><html><head><meta charset='utf-8'><style>html,body{margin:0}"
                    f"img{{display:block;width:{W}px;height:{H}px}}</style></head><body>"
                    f"<img src='{html.escape(svg_path.name)}'></body></html>", encoding="utf-8")
                html_path = page
            from tools.graphics.page_render import PageRender

            r = PageRender().execute({"html_path": str(html_path), "mode": "still", "width_px": W, "height_px": H,
                                      "scale": 1, "output_path": str(png), "virtual_time_budget_ms": 8000})
            try:
                html_path.unlink()  # keep-media-ok: scratch HTML wrapper, holds no media
            except OSError:
                pass
            if not r.success:
                return ToolResult(success=False, error=f"rasterise failed: {r.error}")
            rec = None
            if pd:
                rec = provenance.record(
                    pd, png, kind="generative_art", source="generative_art", licence="generated-in-session",
                    tool=self.name, seed=seed,
                    parents=[provenance.rel(pd, inputs["source_image"])] if inputs.get("source_image") and provenance.find(pd, inputs["source_image"]) else [],
                    notes=json.dumps({"algorithm": algo, "params": inputs.get("params") or {}, "finish": inputs.get("finish", "ink"),
                                      "paper": inputs.get("paper", "uncoated_offwhite"), "size_px": [W, H], "dpi": inputs.get("dpi", 300)}),
                )
            dpi = inputs.get("dpi", 300) if not inputs.get("width_px") else None
            return ToolResult(
                success=True,
                data={"png": str(png), "svg": str(svg_path) if svg_path else None, "seed": seed, "size_px": [W, H],
                      "dpi": dpi, "provenance": rec,
                      "decision_log_hint": {"category": "concept_selection", "subject": f"generative plate {stem}",
                                            "seed": seed}},
                artifacts=[str(png)] + ([str(svg_path)] if svg_path else []), seed=seed,
                duration_seconds=time.time() - start,
            )
        except Exception as e:
            return ToolResult(success=False, error=f"{type(e).__name__}: {e}")

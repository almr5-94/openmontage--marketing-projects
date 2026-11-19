"""The anti-AI-tells gate: blocks any page that reads as "made by an AI" (AP-1 .. AP-7).

Blocking on every export of a magazine page, Maison issue, drawing plate, campaign ad or post.
Codes and negative examples: qa/anti-patterns/CATALOGUE.md (crops 01-21).

Automated checks, per page of the PDF:
  AP-1  copy-lint (EN + AR): operational / support-desk / CTA / urgency copy in display type
  AP-3  diagram detection: numbered badges, step lists, ruled tables, "01 / label" chips,
        breadcrumbs, dot-and-line timelines -- pages dominated by marks, rules and short labels
  AP-4  font audit: every embedded font must be a family declared in print-studio/fonts/FONTS.yaml
        (or narrower, the house/issue declaration); Noto, DejaVu, Arial ... fail outright
  AP-5  duplicate images: pHash (+ flipped) and ORB feature matching across the publication;
        the two halves of one spread are not duplicates
  AP-6  raster presence and effective dpi: a page whose visuals are code-drawn vector shapes
        fails; a key raster below the dpi floor fails; a publication with 0 rasters fails
  AP-7  placement: text-on-text collisions, text crossing the edge of an inset picture, card/box
        containers, text outside the safe area, vector shapes cut by the page edge, overflow
        (from the source HTML), RTL column order
Vision critics (per page PNG): the local vision model (lib/local_models) and Claude. Claude's
verdicts are read from qa/critic/claude_verdicts.json (written by the agent through the MCP tool
or by hand); missing verdicts keep the gate blocked unless offline mode is chosen explicitly.

Overrides: a page passes a code only when decision_log.json holds an ``anti_pattern_override``
for that code and page (with the user's own reason). A general "go ahead" never counts.

CLI: python -m qa.anti_ai_tells <pdf> [--project DIR] [--html FILE] [--no-vision] [--offline]
Report: projects/<id>/qa/anti_ai_tells.md (+ .json).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import yaml  # noqa: E402

MM = 72 / 25.4
BANNED_FONTS = ["noto", "dejavu", "arial", "helvetica", "roboto", "opensans", "open sans", "inter-", "inter ",
                "systemui", "system-ui", "tahoma", "segoe", "calibri", "timesnewroman", "times new roman", "times-roman",
                "liberation", "freeserif", "freesans", "droid", "verdana", "trebuchet", "georgia", "courier"]
CODES = {
    "AP-1": "operational or chatbot copy on an art page",
    "AP-2": "a good idea with a cheap execution (thin uniform-stroke clip-art)",
    "AP-3": "infographic / slide-deck drift (diagrams, steps, chips, tables, badges)",
    "AP-4": "fallback or undeclared fonts",
    "AP-5": "the same image reused (crop, zoom, flip, recolour)",
    "AP-6": "objects drawn in code instead of real imagery; low-resolution key image",
    "AP-7": "broken placement (collisions, cards, overflow, safe area, RTL order)",
}

# ---------------------------------------------------------------- AP-1 copy lint
COPY_RULES_EN = [
    (r"\b(our|the) team (will|shall|is going to)\b", "support-desk promise"),
    (r"\b(will|shall) (contact|reach out to|call|email|get back to) you\b", "support-desk promise"),
    (r"\bwithin (one|two|three|a few|\d+)( or (two|three|\d+))? (business )?(days?|hours?|weeks?)\b", "timeline"),
    (r"\bwe(?:'ll| will) (prepare|send|arrange|set up|review|contact)\b", "process promise"),
    (r"\b(get in touch|contact us|call us|message us|dm us|reach out)\b", "CTA"),
    (r"\b(sign up|register now|book (a|your) (call|demo|consultation)|order now|buy now|shop now|learn more|click here|"
     r"apply now|subscribe now|join now|start (your )?free)\b", "CTA"),
    (r"\b(limited[- ]time|act now|hurry|last chance|don'?t miss|only \d+ left|while stocks last|today only)\b", "urgency"),
    (r"\b(\d+% off|discount|sale ends|special offer|free shipping|promo code|best price)\b", "discount"),
    (r"\b(step \d+|steps? to|how it works|in \d+ (easy|simple) steps)\b", "instructions"),
    (r"\b(whatsapp|customer service|support team|help ?desk|faq)\b", "support register"),
    (r"\b(elevate|unlock|seamless(ly)?|game[- ]chang\w*|curated experience|next[- ]level|empower\w*|revolutioni[sz]\w*|"
     r"unleash|supercharge|cutting[- ]edge|world[- ]class)\b", "filler"),
]
COPY_RULES_AR = [
    (r"سيتواصل|سنتواصل|نتواصل معك|تواصل معنا|تواصلوا معنا|راسلنا|اتصل بنا", "support-desk promise / CTA"),
    (r"خلال (يوم|يومين|ساعات|أيام|ساعة|أسبوع|\d+)", "timeline"),
    (r"فريق\s*\S*\s*(سي|سوف)", "support-desk promise"),
    (r"(سنقوم|سوف نقوم|سنُعد|سنعد|نُعد لك|نعد لك|سنرسل|سنجهز)", "process promise"),
    (r"(احجز|سجّل الآن|سجل الآن|اطلب الآن|اشترِ الآن|اشتر الآن|اضغط|انقر|اشترك الآن)", "CTA"),
    (r"(لفترة محدودة|العرض ينتهي|آخر فرصة|لا تفوت|سارع)", "urgency"),
    (r"(خصم|تخفيض|عرض خاص|كود الخصم|أفضل سعر|مجاناً|مجانا)", "discount"),
    (r"(واتساب|خدمة العملاء|الدعم الفني)", "support register"),
    (r"(الخطوة \S+|خطوات|كيف يعمل)", "instructions"),
]
URGENCY_ANYWHERE = {"urgency", "discount"}


def lint_copy(text: str) -> list[str]:
    hits = []
    for rx, why in COPY_RULES_EN:
        m = re.search(rx, text, re.I)
        if m:
            hits.append(f"{why}: '{m.group(0)}'")
    for rx, why in COPY_RULES_AR:
        m = re.search(rx, text)
        if m:
            hits.append(f"{why}: '{m.group(0)}'")
    return hits


# ---------------------------------------------------------------- helpers
def font_family_key(name: str) -> str:
    base = re.sub(r"^[A-Z]{6}\+", "", name)
    return re.sub(r"[^a-z]", "", base.split("-")[0].lower())


def declared_font_keys(project_dir: Optional[Path]) -> tuple[set[str], str]:
    """Allowed families: the house/issue declaration if there is one, else the whole FONTS.yaml library."""
    lib = yaml.safe_load((REPO / "print-studio" / "fonts" / "FONTS.yaml").read_text(encoding="utf-8"))
    library = {re.sub(r"[^a-z]", "", f["family"].lower()) for f in lib["families"]}
    # PDF names drop "Display" etc. into the style part ("BodoniModa-Display"): match by prefix too
    if project_dir:
        for hy in list(project_dir.glob("house.yaml")) + list(project_dir.glob("*/house.yaml")):
            h = yaml.safe_load(hy.read_text(encoding="utf-8")) or {}
            fams = [v for k, v in (h.get("type") or {}).items() if isinstance(v, str) and k.endswith(("display", "text", "mono", "sans"))]
            if fams:
                return {re.sub(r"[^a-z]", "", f.lower()) for f in fams} & library or library, f"house.yaml ({hy})"
    return library, "print-studio/fonts/FONTS.yaml"


def font_ok(pdf_font: str, allowed: set[str]) -> bool:
    key = font_family_key(pdf_font)
    full = re.sub(r"[^a-z]", "", re.sub(r"^[A-Z]{6}\+", "", pdf_font).lower())
    return any(key == a or full.startswith(a) or a.startswith(key) and len(key) >= 6 for a in allowed)


def is_arabic(s: str) -> bool:
    return bool(re.search(r"[؀-ۿ]", s))


def area(b: tuple[float, float, float, float]) -> float:
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def inter(a, b) -> tuple[float, float, float, float]:
    return (max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3]))


def bbox(o: dict[str, Any]) -> tuple[float, float, float, float]:
    return (o["x0"], o["top"], o["x1"], o["bottom"])


@dataclass
class PageResult:
    page: int
    fails: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    notes: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    overridden: dict[str, list[str]] = field(default_factory=dict)

    def fail(self, code: str, why: str) -> None:
        self.fails[code].append(why)


# ---------------------------------------------------------------- the gate
class Gate:
    def __init__(self, pdf: Path, project_dir: Optional[Path] = None, html: Optional[Path] = None,
                 min_dpi: int = 300, safe_mm: float = 5.0, vision: bool = True, offline: bool = False,
                 rtl: Optional[bool] = None):
        import pdfplumber

        self.pdf_path = pdf
        self.pd = project_dir
        self.html = html
        self.min_dpi = min_dpi
        self.safe = safe_mm * MM
        self.vision = vision
        self.offline = offline
        self.pdf = pdfplumber.open(str(pdf))
        self.pages = [PageResult(i + 1) for i in range(len(self.pdf.pages))]
        self.doc_fails: dict[str, list[str]] = defaultdict(list)
        self.allowed, self.font_source = declared_font_keys(project_dir)
        self.rtl = rtl
        self.tmp = Path(tempfile.mkdtemp(prefix="om-aat-"))

    # ---------- AP-4
    def check_fonts(self) -> None:
        for pr, p in zip(self.pages, self.pdf.pages):
            used = Counter(c["fontname"] for c in p.chars if c["text"].strip())
            pr.metrics["fonts"] = sorted({re.sub(r"^[A-Z]{6}\+", "", f) for f in used})
            for f, n in used.items():
                low = f.lower().replace(" ", "")
                if any(b.replace(" ", "") in low for b in BANNED_FONTS):
                    pr.fail("AP-4", f"banned fallback font {re.sub(r'^[A-Z]{6}[+]', '', f)} ({n} glyphs)")
                elif not font_ok(f, self.allowed):
                    pr.fail("AP-4", f"undeclared font {re.sub(r'^[A-Z]{6}[+]', '', f)} ({n} glyphs; allowed: {self.font_source})")
        if shutil.which("pdffonts"):
            out = subprocess.run(["pdffonts", str(self.pdf_path)], capture_output=True, text=True).stdout.splitlines()[2:]
            for line in out:
                cols = line.split()
                if cols and len(cols) >= 5 and cols[-3] == "no":  # emb column
                    self.doc_fails["AP-4"].append(f"font not embedded: {cols[0]}")

    # ---------- AP-6 and image metrics
    def check_images(self) -> None:
        total_raster = 0
        for pr, p in zip(self.pages, self.pdf.pages):
            page_box = (0, 0, float(p.width), float(p.height))
            A = area(page_box)
            rasters = []
            for im in p.images:
                b = (im["x0"], im["top"], im["x1"], im["bottom"])
                vis = area(inter(b, page_box))
                if vis < 0.002 * A:
                    continue
                sw, sh = im.get("srcsize", (0, 0))
                w_in, h_in = (b[2] - b[0]) / 72, (b[3] - b[1]) / 72
                dpi = min(sw / w_in if w_in else 0, sh / h_in if h_in else 0)
                rasters.append({"box": b, "visible": vis / A, "dpi": round(dpi), "px": [sw, sh]})
            total_raster += len(rasters)
            cover = min(1.0, sum(r["visible"] for r in rasters))
            pr.metrics.update(raster_cover=round(cover, 3), rasters=len(rasters),
                              raster_dpi=[r["dpi"] for r in rasters])
            # key visual: the largest raster; must meet the dpi floor if it is a real visual
            key = max(rasters, key=lambda r: r["visible"], default=None)
            for r in rasters:
                if r["visible"] >= 0.08 and r["dpi"] < self.min_dpi:
                    pr.fail("AP-6", f"image at {r['dpi']} effective dpi ({r['px'][0]}x{r['px'][1]} px over "
                                    f"{(r['box'][2] - r['box'][0]) / MM:.0f} mm) is below {self.min_dpi} dpi")
            # code-drawn visuals: clusters of vector shapes with little text inside
            vec = self._vector_shapes(p)
            drawings = []
            for reg in _clusters(vec, gap=6.0):
                reg_a = area(inter(reg, page_box)) / A
                if reg_a < 0.04:
                    continue
                members = [v for v in vec if area(inter(v, reg)) > 0]
                chars_in = sum(1 for c in p.chars if c["text"].strip() and reg[0] <= c["x0"] <= reg[2] and reg[1] <= c["top"] <= reg[3])
                density = chars_in / max(1.0, area(reg) / (MM * MM) / 100)  # chars per cm2
                if density < 5 and len(members) >= 2:
                    drawings.append((reg_a, len(members), round(density, 1)))
            pr.metrics.update(vector_shapes=len(vec), drawn_regions=drawings)
            if drawings and cover < 0.05:
                big = max(drawings)
                pr.fail("AP-6", f"visual drawn in code: {big[1]} vector shapes over {big[0]:.0%} of the page, "
                                "no raster image")
                if self._uniform_strokes(p):
                    pr.fail("AP-2", "thin uniform-stroke line art (one weight, one colour)")
            if key is None and not vec:
                pr.metrics["visual"] = "text only"
        self.total_raster = total_raster
        if total_raster == 0 and len(self.pages) >= 2:
            self.doc_fails["AP-6"].append(f"0 raster images in {len(self.pages)} pages: every picture is code-drawn or missing")

    def _vector_shapes(self, p) -> list[tuple[float, float, float, float]]:
        """Non-trivial vector marks: not the page background, not hairline rules, not crop marks."""
        A = float(p.width) * float(p.height)
        out = []
        for o in list(p.rects) + list(p.curves):
            b = bbox(o)
            w, h = b[2] - b[0], b[3] - b[1]
            if area(b) >= 0.85 * A:
                continue  # page / bleed background
            if (w < 1.2 or h < 1.2) and max(w, h) < 40 * MM:
                continue  # rules and crop marks
            if not (o.get("fill") or o.get("stroke")):
                continue
            out.append(b)
        for o in p.lines:
            b = bbox(o)
            if max(b[2] - b[0], b[3] - b[1]) > 20 and not (b[0] < 1 or b[1] < 1 or b[2] > p.width - 1 or b[3] > p.height - 1):
                out.append(b)
        return out

    def _uniform_strokes(self, p) -> bool:
        widths = [round(float(o.get("linewidth") or 0), 1) for o in list(p.curves) + list(p.lines) if o.get("stroke")]
        return len(widths) >= 3 and len(set(widths)) <= 2 and max(widths) <= 2.0

    # ---------- AP-3
    def check_diagrams(self) -> None:
        for pr, p in zip(self.pages, self.pdf.pages):
            words = p.extract_words(extra_attrs=["size"], keep_blank_chars=False, use_text_flow=True)
            text = p.extract_text() or ""
            body_size = Counter(round(w["size"]) for w in words).most_common(1)[0][0] if words else 10
            # "01 / label" chips and "Name / Section" breadcrumbs
            chips = re.findall(r"(?m)^\s*(\d{1,2})\s*[/|·•—–-]\s*\S.{0,40}$", text)
            crumbs = [ln for ln in text.splitlines() if re.match(r"^[^\s/]{2,24}(\s?/\s?[^/]{2,40}){1,3}$", ln.strip())
                      and len(ln) < 60 and not re.search(r"\d{4}", ln)]
            # numbered badges: a 1-2 digit number inside a small filled box or circle, three or more
            badges = 0
            for w in words:
                if re.fullmatch(r"\d{1,2}", w["text"]):
                    wb = (w["x0"], w["top"], w["x1"], w["bottom"])
                    for o in list(p.rects) + list(p.curves):
                        ob = bbox(o)
                        if o.get("fill") and 6 < ob[2] - ob[0] < 40 and 6 < ob[3] - ob[1] < 40 and area(inter(wb, ob)) >= 0.6 * area(wb):
                            badges += 1
                            break
            # tables: a grid of rules / cell fills holding many short text runs
            rules_h = [o for o in p.lines + p.rects if (o["x1"] - o["x0"]) > 60 and (o["bottom"] - o["top"]) < 2]
            short_lines = [ln for ln in text.splitlines() if 0 < len(ln.split()) <= 4]
            table = len(rules_h) >= 8 and len(short_lines) >= 12
            # dot-and-line timelines: >= 3 small circles roughly in a row
            dots = [bbox(c) for c in p.curves if (c["x1"] - c["x0"]) < 16 and (c["bottom"] - c["top"]) < 16]
            row = max(Counter(round((d[1] + d[3]) / 2 / 8) for d in dots).values(), default=0)
            col = max(Counter(round((d[0] + d[2]) / 2 / 8) for d in dots).values(), default=0)
            timeline = max(row, col) >= 3
            pr.metrics.update(chips=len(chips), breadcrumbs=len(crumbs), badges=badges, table=table, dots=len(dots))
            if len(chips) >= 1:
                pr.fail("AP-3", f"section chip(s) like '{chips[0]} / ...': slide numbering, not a folio system")
            if crumbs:
                pr.fail("AP-3", f"breadcrumb label '{crumbs[0].strip()[:40]}'")
            if badges >= 3:
                pr.fail("AP-3", f"{badges} numbered badges: a step list / process flow")
            if table:
                pr.fail("AP-3", f"a ruled table ({len(rules_h)} rules, {len(short_lines)} short label lines)")
            if timeline:
                pr.fail("AP-3", f"{max(row, col)} dot markers in a line: a timeline or path diagram")
            # step words in display or label type
            if re.search(r"(?im)^\s*(step|phase|stage)\s+\d", text) or re.search(r"(الخطوة|المرحلة)\s+\S+", text):
                pr.fail("AP-3", "step / phase labels")
            pr.metrics["body_size"] = body_size

    # ---------- AP-1
    def check_copy(self) -> None:
        for pr, p in zip(self.pages, self.pdf.pages):
            words = p.extract_words(extra_attrs=["size"], use_text_flow=True)
            if not words:
                continue
            sizes = sorted(w["size"] for w in words)
            body = sizes[len(sizes) // 2]
            display = " ".join(w["text"] for w in words if w["size"] >= max(14, body * 1.5))
            alltext = " ".join(w["text"] for w in words)
            for h in lint_copy(display):
                pr.fail("AP-1", "display type: " + h)
            for h in lint_copy(alltext):
                if h.split(":")[0] in URGENCY_ANYWHERE:
                    pr.fail("AP-1", "anywhere: " + h)
            pr.metrics["display_text"] = display[:120]

    # ---------- AP-7
    def check_placement(self) -> None:
        for pr, p in zip(self.pages, self.pdf.pages):
            W, H = float(p.width), float(p.height)
            A = W * H
            words = p.extract_words(extra_attrs=["size"], use_text_flow=True)
            lines: dict[int, list[dict]] = defaultdict(list)
            for w in words:
                lines[round(w["top"])].append(w)
            # text-on-text: words from different lines overlapping
            # compare ink cores, not em boxes: the em box carries empty ascender/descender space, so a
            # 64 pt all-caps masthead "touches" the line under it although no ink does
            wb = [((w["x0"], w["top"] + 0.24 * w["size"], w["x1"], w["bottom"] - 0.22 * w["size"]), round(w["top"]))
                  for w in words]
            hits = 0
            for i in range(len(wb)):
                for j in range(i + 1, min(len(wb), i + 400)):
                    (a, la), (b, lb) = wb[i], wb[j]
                    if abs(la - lb) < 2:
                        continue
                    ov = area(inter(a, b))
                    if ov > 0.25 * min(area(a), area(b)) > 0:
                        hits += 1
            if hits:
                pr.fail("AP-7", f"{hits} text collision(s): words overlap other lines")
            # text crossing the edge of an inset picture (not a full-page bleed)
            rasters = [(im["x0"], im["top"], im["x1"], im["bottom"]) for im in p.images]
            inset = [r for r in rasters if area(inter(r, (0, 0, W, H))) < 0.6 * A and area(r) > 0.01 * A]
            crossing = 0
            for (b, _) in wb:
                for r in inset:
                    ov = area(inter(b, r))
                    if 0.1 * area(b) < ov < 0.9 * area(b):
                        crossing += 1
            if crossing:
                pr.fail("AP-7", f"{crossing} word(s) sit across the edge of a picture")
            # card / box containers holding text
            cards = 0
            for o in p.rects:
                b = bbox(o)
                bw, bh = b[2] - b[0], b[3] - b[1]
                if bw < 40 or bh < 20 or area(b) >= 0.85 * A or area(b) < 0.004 * A:
                    continue
                inside = sum(1 for w in words if b[0] <= w["x0"] and w["x1"] <= b[2] and b[1] <= w["top"] and w["bottom"] <= b[3])
                if inside >= 3 and (o.get("stroke") or (o.get("fill") and area(b) < 0.6 * A)):
                    cards += 1
            if cards:
                pr.fail("AP-7", f"{cards} card/box container(s) around text (a web-UI habit)")
            # safe area
            unsafe = [w["text"] for w in words if w["x0"] < self.safe or w["x1"] > W - self.safe
                      or w["top"] < self.safe or w["bottom"] > H - self.safe]
            if unsafe:
                pr.fail("AP-7", f"{len(unsafe)} word(s) outside the {self.safe / MM:.0f} mm safe area, e.g. '{unsafe[0]}'")
            # vector shapes cut by the page edge (rasters reaching the edge are declared bleeds)
            cut = 0
            for b in self._vector_shapes(p):
                crosses = b[0] < -0.5 or b[1] < -0.5 or b[2] > W + 0.5 or b[3] > H + 0.5
                if crosses and area(inter(b, (0, 0, W, H))) > 0.3 * area(b) and area(b) < 0.85 * A:
                    cut += 1
            if cut:
                pr.fail("AP-7", f"{cut} shape(s) cut off at the page edge")
            # RTL reading order: Arabic columns must run right to left in stream order
            ar = [w for w in words if is_arabic(w["text"])]
            if len(ar) > 30:
                order = []
                for w in ar:  # stream order
                    cx = (w["x0"] + w["x1"]) / 2
                    col = round(cx / (W / 4))
                    if not order or order[-1] != col:
                        order.append(col)
                cols = [c for i, c in enumerate(order) if c not in order[:i]]
                if len(cols) >= 2 and cols == sorted(cols):
                    pr.fail("AP-7", "RTL reading order broken: Arabic columns run left to right")
                pr.metrics["arabic_columns_order"] = cols

    def check_overflow_html(self) -> None:
        if not self.html or not self.html.exists():
            return
        try:
            from tools.graphics.page_render import PageRender, find_chromium

            chrome = find_chromium()
            if not chrome:
                return
            rep = PageRender()._layout_checks(chrome, self.html, {}, 180)
        except Exception as e:  # noqa: BLE001
            self.doc_fails["AP-7"].append(f"overflow check could not run: {e}")
            return
        for o in rep.get("overflow", []):
            try:
                n = int(o.get("page") or 0)
            except ValueError:
                n = 0
            msg = f"text overflows its box ({o['selector']}, {o['overflow_px']}): '{o.get('text_start', '')[:40]}'"
            if 1 <= n <= len(self.pages):
                self.pages[n - 1].fail("AP-7", msg)
            else:
                self.doc_fails["AP-7"].append(msg)

    # ---------- AP-5
    def check_duplicates(self) -> None:
        if not shutil.which("pdfimages"):
            self.doc_fails["AP-5"].append("pdfimages not installed: duplicate check could not run")
            return
        import imagehash
        from PIL import Image, ImageOps

        d = self.tmp / "imgs"
        d.mkdir()
        subprocess.run(["pdfimages", "-png", "-p", str(self.pdf_path), str(d / "i")], capture_output=True, check=False)
        items = []
        for f in sorted(d.glob("i-*.png")):
            page = int(f.stem.split("-")[1])
            try:
                im = Image.open(f)
                if im.mode in ("1", "L") and im.width * im.height < 40000:
                    continue  # soft masks
                rgb = im.convert("RGB")
            except Exception:  # noqa: BLE001
                continue
            if rgb.width < 64 or rgb.height < 64:
                continue
            items.append({"page": page, "file": f, "md5": hashlib.md5(f.read_bytes()).hexdigest(),
                          "ph": imagehash.phash(rgb), "phf": imagehash.phash(ImageOps.mirror(rgb)), "img": rgb})
        # placements per page to recognise the two halves of one spread
        pages_with = defaultdict(set)
        for it in items:
            pages_with[it["md5"]].add(it["page"])
        orb = _Orb()
        seen: list[tuple[int, int, str]] = []
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                a, b = items[i], items[j]
                if a["page"] == b["page"]:
                    continue
                if a["md5"] == b["md5"] and abs(a["page"] - b["page"]) == 1 and self._spread_pair(a["page"], b["page"]):
                    continue
                why = None
                if a["md5"] == b["md5"]:
                    why = "the same image file"
                elif a["ph"] - b["ph"] <= 8:
                    why = f"near-identical (pHash distance {a['ph'] - b['ph']})"
                elif a["ph"] - b["phf"] <= 8:
                    why = "a mirrored copy"
                else:
                    inl = orb.inliers(a["img"], b["img"])
                    if inl >= 40:
                        why = f"a crop/zoom of the same picture ({inl} matching features)"
                if why:
                    seen.append((a["page"], b["page"], why))
        for pa, pb, why in seen:
            self.pages[pb - 1].fail("AP-5", f"image repeats page {pa}: {why}")

    def _spread_pair(self, pa: int, pb: int) -> bool:
        """Facing pages that each show one half of the same picture, bled into the gutter."""
        lo, hi = sorted((pa, pb))
        p1, p2 = self.pdf.pages[lo - 1], self.pdf.pages[hi - 1]
        r1 = any(im["x1"] > float(p1.width) + 5 for im in p1.images)
        l2 = any(im["x0"] < -5 for im in p2.images)
        r2 = any(im["x1"] > float(p2.width) + 5 for im in p2.images)
        l1 = any(im["x0"] < -5 for im in p1.images)
        return (r1 and l2) or (l1 and r2)

    # ---------- vision critics
    def render_pages(self, dpi: int = 100) -> list[Path]:
        out = (self.pd / "qa" / "pages") if self.pd else (self.tmp / "pages")
        out.mkdir(parents=True, exist_ok=True)
        subprocess.run(["pdftoppm", "-r", str(dpi), "-png", str(self.pdf_path), str(out / "page")], capture_output=True, check=False)
        return sorted(out.glob("page-*.png"))

    def vision_local(self, pngs: list[Path]) -> None:
        from lib import local_models as lm

        catalogue = "; ".join(f"{k}: {v}" for k, v in CODES.items())
        q_codes = ("You are a strict luxury magazine art director. Faults to look for: " + catalogue +
                   ". Does this page show any of these faults? Answer NONE, or list the codes (e.g. AP-3, AP-6) "
                   "and a few words why.")
        # Measured 2026-11-19 on qwen2.5vl:7b: the fault question separates good pages ("NONE") from the
        # Sard pages ("AP-3 ..."); "would you publish it?" is answered "No" for every page and a 1-5 rating
        # barely separates them, so the rating only blocks at <= 2 and the publish verdict is Claude's.
        q_rate = ("Rate this page as a luxury magazine page from 1 (amateur slide or document) to 5 "
                  "(published art magazine). Answer with one number.")
        for pr, png in zip(self.pages, pngs):
            try:
                a = lm.see(png, q_codes, max_tokens=80)
                b = lm.see(png, q_rate, max_tokens=6)
            except Exception as e:  # noqa: BLE001
                pr.notes.append(f"local critic unavailable: {e}")
                continue
            codes = sorted(set(re.findall(r"AP-[1-7]", a)))
            m = re.search(r"[1-5]", b)
            rating = int(m.group(0)) if m else None
            pr.metrics["local_critic"] = {"codes": codes, "said": a[:160], "rating": rating,
                                          "model": lm.detect().get("vision")}
            for c in codes:
                pr.fail(c, f"local vision critic: {a[:120]}")
            if rating is not None and rating <= 2:
                pr.fail("CRITIC", f"local vision critic rates it {rating}/5")

    def claude_pack(self, pngs: list[Path]) -> Path:
        """Write the brief Claude answers per page; verdicts go to qa/critic/claude_verdicts.json."""
        base = (self.pd / "qa" / "critic") if self.pd else (self.tmp / "critic")
        base.mkdir(parents=True, exist_ok=True)
        lines = ["# Claude page critic", "",
                 "Review every page at 100% against qa/anti-patterns/CATALOGUE.md and the 21 negative crops in",
                 "qa/anti-patterns/. For each page answer two questions:",
                 "1. Does this page show any of AP-1 .. AP-7? (list codes, or none)",
                 "2. Would a luxury art director publish it? (yes / no)", "",
                 "Record the answers in claude_verdicts.json as",
                 '`{"pdf_sha256": "...", "pages": {"1": {"codes": [], "publish": true, "note": "..."}}}`', "",
                 f"PDF sha256: `{_sha(self.pdf_path)}`", "", "| Page | PNG |", "|---|---|"]
        lines += [f"| {i + 1} | {p} |" for i, p in enumerate(pngs)]
        (base / "claude_pack.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        return base / "claude_verdicts.json"

    def vision_claude(self, verdicts: Path) -> None:
        if not verdicts.exists():
            if self.offline:
                self.doc_fails.setdefault("NOTE", []).append("Claude critic not run (offline mode chosen)")
            else:
                self.doc_fails["CRITIC"].append(f"Claude critic verdicts missing: answer {verdicts.parent / 'claude_pack.md'}")
            return
        v = json.loads(verdicts.read_text(encoding="utf-8"))
        if v.get("pdf_sha256") != _sha(self.pdf_path):
            self.doc_fails["CRITIC"].append("Claude verdicts are for a different version of this PDF: review again")
            return
        for pr in self.pages:
            pv = v.get("pages", {}).get(str(pr.page))
            if pv is None:
                pr.fail("CRITIC", "Claude critic gave no verdict for this page")
                continue
            pr.metrics["claude_critic"] = pv
            for c in pv.get("codes", []):
                pr.fail(c, f"Claude critic: {pv.get('note', '')}")
            if not pv.get("publish", False):
                pr.fail("CRITIC", f"Claude critic would not publish it: {pv.get('note', '')}")

    # ---------- overrides and report
    def apply_overrides(self) -> None:
        if not self.pd:
            return
        from lib.decision_log import overrides

        ov = overrides(self.pd)
        for pr in self.pages:
            for code in list(pr.fails):
                if pr.page in ov.get(code, set()):
                    pr.overridden[code] = pr.fails.pop(code)

    def run(self, critics: bool = True) -> dict[str, Any]:
        self.check_fonts()
        self.check_images()
        self.check_diagrams()
        self.check_copy()
        self.check_placement()
        self.check_overflow_html()
        self.check_duplicates()
        if critics:
            pngs = self.render_pages()
            if self.vision:
                self.vision_local(pngs)
            self.vision_claude(self.claude_pack(pngs))
        self.apply_overrides()
        doc_blocking = {k: v for k, v in self.doc_fails.items() if k != "NOTE"}
        failed_pages = [pr.page for pr in self.pages if pr.fails]
        codes = sorted({c for pr in self.pages for c in pr.fails} | set(doc_blocking))
        return {"pdf": str(self.pdf_path), "pass": not failed_pages and not doc_blocking, "pages": len(self.pages),
                "failed_pages": failed_pages, "codes": codes, "doc": dict(self.doc_fails),
                "font_source": self.font_source,
                "per_page": [{"page": pr.page, "pass": not pr.fails, "fails": dict(pr.fails), "overridden": pr.overridden,
                              "notes": pr.notes, "metrics": pr.metrics} for pr in self.pages]}


class _Orb:
    def __init__(self) -> None:
        try:
            import cv2

            self.cv2 = cv2
            self.orb = cv2.ORB_create(1500)
        except ImportError:
            self.cv2 = None
        self.cache: dict[int, Any] = {}

    def _feat(self, im):
        k = id(im)
        if k not in self.cache:
            import numpy as np

            g = im.convert("L")
            g.thumbnail((900, 900))
            self.cache[k] = self.orb.detectAndCompute(np.asarray(g), None)
        return self.cache[k]

    def inliers(self, a, b) -> int:
        if not self.cv2:
            return 0
        import numpy as np

        ka, da = self._feat(a)
        kb, db = self._feat(b)
        if da is None or db is None or len(ka) < 20 or len(kb) < 20:
            return 0
        m = self.cv2.BFMatcher(self.cv2.NORM_HAMMING).knnMatch(da, db, k=2)
        good = [x[0] for x in m if len(x) == 2 and x[0].distance < 0.75 * x[1].distance]
        if len(good) < 12:
            return 0
        src = np.float32([ka[g.queryIdx].pt for g in good]).reshape(-1, 1, 2)
        dst = np.float32([kb[g.trainIdx].pt for g in good]).reshape(-1, 1, 2)
        _, mask = self.cv2.findHomography(src, dst, self.cv2.RANSAC, 6.0)
        return int(mask.sum()) if mask is not None else 0


def _clusters(boxes: list[tuple[float, float, float, float]], gap: float) -> list[tuple[float, float, float, float]]:
    """Merge boxes that overlap or sit within `gap` points of each other."""
    out = [list(b) for b in boxes]
    merged = True
    while merged:
        merged = False
        res: list[list[float]] = []
        for b in out:
            for r in res:
                if b[0] <= r[2] + gap and r[0] <= b[2] + gap and b[1] <= r[3] + gap and r[1] <= b[3] + gap:
                    r[0], r[1], r[2], r[3] = min(r[0], b[0]), min(r[1], b[1]), max(r[2], b[2]), max(r[3], b[3])
                    merged = True
                    break
            else:
                res.append(list(b))
        out = res
    return [tuple(b) for b in out]


def _sha(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def write_report(res: dict[str, Any], out_md: Path) -> Path:
    out_md.parent.mkdir(parents=True, exist_ok=True)
    verdict = "PASS" if res["pass"] else "FAIL"
    L = [f"# Anti-AI-tells gate: {verdict}", "",
         f"- PDF: `{res['pdf']}`",
         f"- Pages: {res['pages']}; failing pages: {len(res['failed_pages'])}",
         f"- Codes tripped: {', '.join(res['codes']) or 'none'}",
         f"- Fonts allowed from: {res['font_source']}", ""]
    if res["doc"]:
        L += ["## Whole-publication findings", ""]
        for code, whys in res["doc"].items():
            for w in whys:
                L.append(f"- **{code}** {w}")
        L.append("")
    L += ["## Per page", "", "| Page | Result | Codes | Reasons |", "|---|---|---|---|"]
    for pp in res["per_page"]:
        codes = ", ".join(pp["fails"]) or "-"
        why = "; ".join(f"{c}: {w}" for c, ws in pp["fails"].items() for w in ws[:2])
        if pp["overridden"]:
            why += ("; " if why else "") + "overridden by user election: " + ", ".join(pp["overridden"])
        L.append(f"| {pp['page']} | {'pass' if pp['pass'] else 'FAIL'} | {codes} | {why.replace('|', '/')[:400] or '-'} |")
    L += ["", "Failing pages go back to their stage with these reasons. An override needs an",
          "`anti_pattern_override` decision with the user's own reason for that code and page.", ""]
    out_md.write_text("\n".join(L), encoding="utf-8")
    out_md.with_suffix(".json").write_text(json.dumps(res, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return out_md


def run_gate(pdf: str | Path, project_dir: str | Path | None = None, html: str | Path | None = None,
             vision: bool = True, offline: bool = False, critics: bool = True, min_dpi: int = 300) -> dict[str, Any]:
    """Run the gate and write projects/<id>/qa/anti_ai_tells.md. The single entry point for CLI and MCP."""
    pd = Path(project_dir) if project_dir else None
    g = Gate(Path(pdf), pd, Path(html) if html else None, min_dpi=min_dpi, vision=vision, offline=offline)
    try:
        res = g.run(critics=critics)
    finally:
        shutil.rmtree(g.tmp, ignore_errors=True)  # keep-media-ok: scratch extraction of images that stay inside the PDF
    out = (pd / "qa" / "anti_ai_tells.md") if pd else Path(pdf).with_name(Path(pdf).stem + ".anti_ai_tells.md")
    res["report"] = str(write_report(res, out))
    return res


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("pdf")
    ap.add_argument("--project")
    ap.add_argument("--html")
    ap.add_argument("--no-vision", action="store_true", help="skip the local vision critic")
    ap.add_argument("--no-critics", action="store_true", help="automated checks only")
    ap.add_argument("--offline", action="store_true", help="no Claude critic (recorded in the report)")
    ap.add_argument("--min-dpi", type=int, default=300)
    a = ap.parse_args(argv)
    res = run_gate(a.pdf, a.project, a.html, vision=not a.no_vision, offline=a.offline,
                   critics=not a.no_critics, min_dpi=a.min_dpi)
    print(f"anti-AI-tells: {'PASS' if res['pass'] else 'FAIL'} | pages failing {len(res['failed_pages'])}/{res['pages']} "
          f"| codes {', '.join(res['codes']) or 'none'} | report {res['report']}")
    return 0 if res["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())

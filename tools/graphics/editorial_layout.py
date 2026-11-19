"""editorial_layout: print magazines and campaign pages from a JSON issue, via Chromium.

Layer 6 of the editorial art stack. Builds HTML against print-studio/css/editorial.css on the
curated OFL type library, then renders with page_render:

  * trims: a4 (210x297), us_letter (215.9x279.4), magazine_230x300 -- 3 mm bleed by default;
  * print PDF: every sheet = trim + bleed + slug, with crop marks and a slug line;
  * screen PDF: trim only; PNG per page from it; paper-stock proof PNGs (uncoated, silk, ...);
  * page types: cover, contents, opening_spread, feature_spread, art_page, pull_quote,
    text_page, campaign, back_cover, colophon (credits written from PROVENANCE.json);
  * 12-column grid and a baseline grid (``show_grid`` draws both for review);
  * ``dir: rtl`` mirrors the book: odd pages fall on the left, spreads read right to left.

Every image path in the issue is relative to the project folder. Fonts and CSS are copied into
``projects/<id>/layout/`` so the layout folder renders on its own. Free and local.

Issue (``issue``)::

    {"title": "...", "trim": "a4", "bleed_mm": 3, "dir": "ltr", "lang": "en",
     "tokens": {"paper": "#f4f0e7", "ink": "#1b1813", "accent": "#7a2e1f",
                "font_display": "Bodoni Moda Display", "font_text": "EB Garamond", "baseline_pt": 13},
     "masthead": "LANTERN", "section": "Winter",
     "pages": [{"type": "cover", "image": "assets/collage/x.png", "issue_line": "No. 1 - Winter 2026",
                "headline": "...", "lines": ["...", "..."]}, ...]}
"""

from __future__ import annotations

import html as _html
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Optional

import numpy as np
import yaml
from PIL import Image

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
STUDIO = REPO / "print-studio"
TRIMS = {"a4": (210.0, 297.0), "us_letter": (215.9, 279.4), "magazine_230x300": (230.0, 300.0),
         # campaign placements: 4:5 and 9:16 social stills (1080 px wide at ~127 dpi), out-of-home posters
         "social_4x5": (216.0, 270.0), "social_9x16": (216.0, 384.0),
         "ooh_portrait": (420.0, 594.0), "ooh_landscape": (594.0, 420.0)}
PAGE_TYPES = ["cover", "contents", "opening_spread", "feature_spread", "art_page", "pull_quote",
              "text_page", "campaign", "back_cover", "colophon"]
SPREADS = {"opening_spread", "feature_spread"}
# Paper stocks for soft proofs: paper white (multiplied in), ink density, grain strength.
STOCKS = {
    "uncoated_offwhite": {"paper": (243, 238, 226), "density": 0.90, "grain": 0.030},
    "cream": {"paper": (240, 230, 208), "density": 0.90, "grain": 0.030},
    "coated_silk": {"paper": (248, 247, 243), "density": 0.98, "grain": 0.010},
    "newsprint": {"paper": (226, 221, 207), "density": 0.80, "grain": 0.050},
}


def allowed_families() -> set[str]:
    data = yaml.safe_load((STUDIO / "fonts" / "FONTS.yaml").read_text(encoding="utf-8"))
    return {f["family"] for f in data["families"]}


def esc(s: Any) -> str:
    return _html.escape(str(s or ""), quote=True)


def paras(text: Any) -> list[str]:
    if isinstance(text, list):
        return [str(t) for t in text if str(t).strip()]
    return [p.strip() for p in re.split(r"\n\s*\n", str(text or "")) if p.strip()]


def latin_digits(n: int) -> str:
    return str(int(n))  # str() of an int is always 0-9; never locale-formatted


class Book:
    """Turns the issue into a list of physical pages with folio and side."""

    def __init__(self, issue: dict[str, Any], project_dir: Path, layout_dir: Path):
        self.issue = issue
        self.pd = project_dir
        self.ld = layout_dir
        self.rtl = issue.get("dir", "ltr") == "rtl"
        self.trim = TRIMS[issue.get("trim", "a4")] if isinstance(issue.get("trim", "a4"), str) else tuple(issue["trim"])
        self.bleed = float(issue.get("bleed_mm", 3))
        self.warnings: list[str] = []
        self.images: list[str] = []
        self.pages: list[dict[str, Any]] = []  # physical pages: {"spec", "half", "folio"}
        for spec in issue["pages"]:
            if spec.get("type") not in PAGE_TYPES:
                raise ValueError(f"unknown page type {spec.get('type')!r}; one of {PAGE_TYPES}")
            if spec["type"] in SPREADS:
                self.pages.append({"spec": spec, "half": 0})
                self.pages.append({"spec": spec, "half": 1})
            else:
                self.pages.append({"spec": spec, "half": None})
        for i, p in enumerate(self.pages, start=1):
            p["folio"] = i
            p["side"] = self.side(i)
        if len(self.pages) % 2:
            self.warnings.append(f"{len(self.pages)} pages: a bound issue needs an even count (saddle stitch: a multiple of 4)")
        for i, p in enumerate(self.pages, start=1):
            if p["half"] == 0 and p["side"] != ("right" if self.rtl else "left"):
                self.warnings.append(f"spread '{p['spec'].get('title', p['spec']['type'])}' starts on page {i}: "
                                     "its halves do not face each other (add or remove a page before it)")
        self.ids = {p["spec"].get("id"): p["folio"] for p in self.pages if p["spec"].get("id") and p["half"] in (None, 0)}

    def side(self, folio: int) -> str:
        odd = folio % 2 == 1
        return ("left" if odd else "right") if self.rtl else ("right" if odd else "left")

    def img(self, rel: Optional[str]) -> str:
        if not rel:
            return ""
        src = (self.pd / rel) if not Path(rel).is_absolute() else Path(rel)
        if not src.exists():
            self.warnings.append(f"missing image {rel}")
        self.images.append(str(src))
        return esc(os.path.relpath(src, self.ld))


def figure_html(book: Book, spec: dict[str, Any], cls: str = "bleed-img", pos: Optional[str] = None) -> str:
    position = pos or spec.get("image_position", "50% 50%")
    return f'<img class="{cls}" src="{book.img(spec.get("image"))}" alt="{esc(spec.get("alt", ""))}" style="object-position:{esc(position)}">'


def folio_html(p: dict[str, Any], book: Book) -> str:
    sec = book.issue.get("section") or book.issue.get("title", "")
    return f'<div class="folio label"><span>{latin_digits(p["folio"])}</span> &nbsp; {esc(sec)}</div>'


def body_html(text: Any, cols: int, dropcap: bool = True, fill: bool = False) -> str:
    ps = paras(text)
    out = []
    for i, t in enumerate(ps):
        cls = ' class="first"' if (i == 0 and dropcap) else ""
        out.append(f"<p{cls}>{esc(t)}</p>")
    return f'<div class="body frame cols-{cols}{" fill" if fill else ""}" style="height:100%">{"".join(out)}</div>'


def page_inner(p: dict[str, Any], book: Book) -> tuple[str, str]:
    """Return (classes, inner html of .page) for one physical page."""
    s = p["spec"]
    t = s["type"]
    side = p["side"]
    folio = folio_html(p, book)
    if t == "cover":
        ink = s.get("cover_ink")
        style = f' style="--cover-ink:{esc(ink)}"' if ink else ""
        lines = "".join(f'<div class="label">{esc(x)}</div>' for x in s.get("lines", []))
        return "cover", (figure_html(book, s) + f'<div class="trim"{style}><div class="live">'
                         f'<div class="masthead display">{esc(book.issue.get("masthead", book.issue.get("title")))}</div>'
                         f'<div class="issue-line label">{esc(s.get("issue_line", ""))}</div>'
                         f'<div class="cover-head"><h1 class="display">{esc(s.get("headline", ""))}</h1>'
                         f'<div class="cover-lines">{lines}</div></div></div></div>')
    if t == "contents":
        rows = []
        for e in s.get("entries", []):
            n = book.ids.get(e.get("ref"), e.get("page", ""))
            if e.get("ref") and e["ref"] not in book.ids:
                book.warnings.append(f"contents entry {e.get('title')!r} points at unknown page id {e['ref']!r}")
            rows.append(f'<div class="entry"><div class="n">{esc(n)}</div><div><div class="t">{esc(e.get("title"))}</div>'
                        f'<div class="d">{esc(e.get("dek", ""))}</div></div></div>')
        pic = ""
        if s.get("image"):
            pic = (f'<div style="position:absolute;left:0;right:0;bottom:calc(var(--baseline)*2);height:38%">'
                   f'<img class="inset-img" src="{book.img(s["image"])}" alt="" style="height:100%;object-position:{esc(s.get("image_position", "50% 50%"))}"></div>')
        return "contents", (f'<div class="trim"><div class="live">'
                            f'<div class="label kicker">{esc(s.get("kicker", "Contents"))}</div>'
                            f'<h2 class="display" style="font-size:30pt;line-height:calc(var(--baseline)*2.6)">{esc(s.get("title", "Contents"))}</h2>'
                            f'<div class="entries frame">{"".join(rows)}</div>{pic}</div>{folio}</div>')
    if t == "opening_spread":
        img = f'<img class="spread-img" src="{book.img(s.get("image"))}" alt="" style="object-position:{esc(s.get("image_position", "50% 50%"))}">'
        title_half = s.get("title_on", 1)  # which half carries the title (0 = first page in reading order)
        text = ""
        if p["half"] == title_half:
            ink = s.get("title_ink")
            st = f' style="color:{esc(ink)}"' if ink else ""
            text = (f'<div class="opener-title"{st}><div class="label kicker"{st}>{esc(s.get("kicker", ""))}</div>'
                    f'<h1 class="display">{esc(s.get("title", ""))}</h1>'
                    f'<p class="dek">{esc(s.get("dek", ""))}</p><div class="label byline"{st}>{esc(s.get("byline", ""))}</div></div>')
        return f"opening {side}", img + f'<div class="trim"><div class="live">{text}</div></div>'
    if t == "feature_spread":
        image_half = s.get("image_on", 1)
        if p["half"] == image_half:
            cap = ""
            if s.get("caption"):
                cap = (f'<div class="trim"><div class="live"><div class="caption" style="position:absolute;bottom:0;'
                       f'{"right" if side == "right" else "left"}:0;width:45%;color:{esc(s.get("caption_ink", "var(--paper)"))}">'
                       f'{esc(s["caption"])}</div></div></div>')
            return f"feature {side}", figure_html(book, s) + cap
        head = (f'<div class="feature-head" style="margin-bottom:calc(var(--baseline)*1.5)">'
                f'<div class="label kicker">{esc(s.get("kicker", ""))}</div>'
                f'<h2 class="display">{esc(s.get("title", ""))}</h2>'
                f'<p class="dek">{esc(s.get("dek", ""))}</p><div class="label byline">{esc(s.get("byline", ""))}</div></div>')
        return f"feature {side}", (f'<div class="trim"><div class="live" style="display:flex;flex-direction:column">{head}'
                                   f'<div style="flex:1;min-height:0">{body_html(s.get("body"), int(s.get("columns", 2)))}</div>'
                                   f'</div>{folio}</div>')
    if t == "text_page":
        return f"text {side}", (f'<div class="trim"><div class="live">{body_html(s.get("body"), int(s.get("columns", 2)), s.get("dropcap", False), fill=True)}'
                                f'</div>{folio}</div>')
    if t == "art_page":
        cap = ""
        if s.get("caption") or s.get("credit"):
            cap = (f'<div class="trim"><div class="live"><div class="caption" style="position:absolute;bottom:0;left:0;width:55%;'
                   f'color:{esc(s.get("caption_ink", "var(--ink-soft)"))}"><b>{esc(s.get("caption", ""))}</b> {esc(s.get("credit", ""))}</div></div></div>')
        if s.get("fit") == "plate":  # the work on a paper mat, not bled
            return f"art {side}", (f'<div class="trim"><div class="live" style="display:flex;align-items:center;justify-content:center;'
                                   f'bottom:calc(var(--margin-bottom) + var(--baseline)*3)">'
                                   f'<img src="{book.img(s.get("image"))}" alt="" style="max-width:100%;max-height:100%;display:block"></div></div>' + cap)
        return f"art {side}", figure_html(book, s) + cap
    if t == "pull_quote":
        bg = figure_html(book, s) if s.get("image") else ""
        st = f' style="color:{esc(s["ink"])}"' if s.get("ink") else ""
        return f"pullq {side}", bg + (f'<div class="trim"><div class="live"><div class="pull"{st}><blockquote>{esc(s.get("quote", ""))}</blockquote>'
                                      f'<div class="attr label"{st}>{esc(s.get("attribution", ""))}</div></div></div>{folio}</div>')
    if t == "campaign":
        ink = s.get("ink")
        st = f' style="--cover-ink:{esc(ink)}"' if ink else ""
        return "campaign", figure_html(book, s) + (f'<div class="trim"{st}><div class="live"><div class="claim">'
                                                   f'<h1 class="display">{esc(s.get("claim", ""))}</h1>'
                                                   f'<div class="label">{esc(s.get("signature", ""))}</div></div></div></div>')
    if t == "back_cover":
        color = f"color:{esc(s['ink'])};" if s.get("ink") else ""
        return "back", figure_html(book, s) + (f'<div class="trim"><div class="live"><div class="label" '
                                               f'style="position:absolute;bottom:0;left:0;right:0;text-align:center;{color}">'
                                               f'{esc(s.get("line", ""))}</div></div></div>')
    if t == "colophon":
        credits = s.get("credits") or credit_lines(book)
        cred = "".join(f"<p>{esc(c)}</p>" for c in credits)
        return f"colophon {side}", (f'<div class="trim"><div class="live"><div class="label kicker">{esc(s.get("kicker", "Colophon"))}</div>'
                                    f'<p class="dek">{esc(s.get("text", ""))}</p><div class="credits frame">{cred}</div></div>{folio}</div>')
    raise ValueError(t)


def credit_lines(book: Book) -> list[str]:
    """Credit lines for every museum/stock root behind the images used, from PROVENANCE.json."""
    seen, lines = set(), []
    for path in dict.fromkeys(book.images):
        for rec in provenance.lineage(book.pd, path):
            if rec.get("kind") in ("museum", "stock", "user") and rec["path"] not in seen:
                seen.add(rec["path"])
                bits = [rec.get("title"), rec.get("creator"), rec.get("date")]
                lic = {"CC0": "CC0", "public-domain": "Public domain"}.get(rec.get("licence"), rec.get("licence"))
                lines.append(", ".join(b for b in bits if b) + f" - {rec.get('source')}. {lic}.")
    lines.append("Typefaces: " + ", ".join(sorted({book.issue.get('tokens', {}).get('font_display', 'Bodoni Moda Display'),
                                                    book.issue.get('tokens', {}).get('font_text', 'EB Garamond')})) + " (SIL Open Font License).")
    return lines


def crop_marks() -> str:
    """Eight marks at the trim corners, offset outside the bleed (all in the slug)."""
    m = []
    for vert in ("top", "bottom"):
        for horiz in ("left", "right"):
            # horizontal mark: level with the trim edge, out in the slug
            m.append(f'<div class="mark h" style="{vert}:calc(var(--slug) + var(--bleed));{horiz}:0"></div>')
            # vertical mark: level with the trim edge, out in the slug
            m.append(f'<div class="mark v" style="{horiz}:calc(var(--slug) + var(--bleed));{vert}:0"></div>')
    return "".join(m)


def build_html(book: Book, mode: str) -> str:
    iss = book.issue
    tok = dict(iss.get("tokens") or {})
    allowed = allowed_families()
    rtl = book.rtl
    fd = tok.get("font_display", "Amiri" if rtl else "Bodoni Moda Display")
    ft = tok.get("font_text", "IBM Plex Sans Arabic" if rtl else "EB Garamond")
    for f in (fd, ft):
        if f not in allowed:
            raise ValueError(f"font {f!r} is not in print-studio/fonts/FONTS.yaml (AP-4: fallback faces are banned)")
    fdw = tok.get("font_display_weight", 500 if fd == "Bodoni Moda Display" else 400)
    W, H = book.trim
    slug = 8.0 if (mode == "print" and iss.get("crop_marks", True)) else (0.0 if mode == "print" else -book.bleed)
    sheet_w = W + 2 * (book.bleed + slug)
    sheet_h = H + 2 * (book.bleed + slug)
    root = {
        "--trim-w": f"{W}mm", "--trim-h": f"{H}mm", "--bleed": f"{book.bleed}mm", "--slug": f"{slug}mm",
        "--baseline": f"{tok.get('baseline_pt', 13)}pt", "--size-body": f"{tok.get('size_body_pt', 9.6)}pt",
        "--paper": tok.get("paper", "#f4f0e7"), "--ink": tok.get("ink", "#1b1813"),
        "--ink-soft": tok.get("ink_soft", "#5b554b"), "--accent": tok.get("accent", "#7a2e1f"),
        "--rule": tok.get("rule", "#cfc7b6"), "--font-display": f'"{fd}"', "--font-display-weight": str(fdw),
        "--font-text": f'"{ft}"',
    }
    for k in ("margin_inner", "margin_outer", "margin_top", "margin_bottom"):
        if tok.get(k + "_mm"):
            root["--" + k.replace("_", "-")] = f"{tok[k + '_mm']}mm"
    css_root = ":root{" + ";".join(f"{k}:{v}" for k, v in root.items()) + "}"
    sheets = []
    total = len(book.pages)
    slug_line = esc(f"{iss.get('title', '')} | {W:g}x{H:g} mm trim, {book.bleed:g} mm bleed")
    for p in book.pages:
        cls, inner = page_inner(p, book)
        marks = crop_marks() if mode == "print" and iss.get("crop_marks", True) else ""
        info = f'<div class="slug-info">{slug_line} | page {latin_digits(p["folio"])} of {latin_digits(total)}</div>' if marks else ""
        lang = p["spec"].get("lang")
        lattr = f' lang="{esc(lang)}"' if lang else ""
        sheets.append(f'<section class="sheet" data-page="{p["folio"]}" data-clip-ok>{marks}{info}'
                      f'<div class="page {p["side"]} {cls}" data-clip-ok{lattr}>{inner}</div></section>')
    grid = " show-grid" if iss.get("show_grid") else ""
    return (f'<!doctype html><html lang="{esc(iss.get("lang", "ar" if rtl else "en"))}" dir="{"rtl" if rtl else "ltr"}">'
            f'<head><meta charset="utf-8"><title>{esc(iss.get("title", "Issue"))}</title>'
            f'<link rel="stylesheet" href="fonts/fonts.css"><link rel="stylesheet" href="css/editorial.css">'
            f'<style>@page{{size:{sheet_w:.2f}mm {sheet_h:.2f}mm;margin:0}}{css_root}</style></head>'
            f'<body class="{mode}{grid}">{"".join(sheets)}</body></html>')


def soft_proof(png: Path, out: Path, stock: str, seed: int = 1) -> Path:
    """Simulate a paper stock: multiply paper white, lift ink (dot gain / density), add grain."""
    from tools.graphics.collage import paper_grain

    s = STOCKS[stock]
    im = np.asarray(Image.open(png).convert("RGB"), dtype=np.float32) / 255
    ink = 1 - (1 - im) * s["density"]
    paper = np.array(s["paper"], dtype=np.float32) / 255
    g = np.asarray(paper_grain((im.shape[1], im.shape[0]), seed, s["grain"]), dtype=np.float32)[..., None] / 128.0
    outp = np.clip(ink * paper * g ** 0.5 * 255, 0, 255).astype(np.uint8)
    out.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(outp).save(out)
    return out


class EditorialLayout(BaseTool):
    name = "editorial_layout"
    version = "0.1.0"
    tier = ToolTier.CORE
    capability = "editorial_layout"
    provider = "chromium"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC
    runtime = ToolRuntime.LOCAL
    dependencies = ["chromium (page_render)", "pdftoppm"]
    capabilities = ["print_pdf_with_bleed", "crop_marks", "screen_pdf", "page_pngs", "paper_soft_proof",
                    "rtl_books", "baseline_grid", "twelve_column_grid", "spreads"]
    supports = {"trims": sorted(TRIMS), "page_types": PAGE_TYPES, "stocks": sorted(STOCKS), "cost": "free (local)"}
    best_for = ["magazines, art books, drawing series, single-page campaign ads"]
    not_good_for = ["long running text over many pages (use text_page and check overflow)"]
    resource_profile = ResourceProfile(cpu_cores=2, ram_mb=2048, vram_mb=0, disk_mb=500)
    side_effects = ["writes projects/<id>/layout/ (HTML, fonts, css, PDFs, page PNGs, proofs)"]
    agent_skills = ["editorial-design"]
    input_schema = {
        "type": "object",
        "required": ["issue", "project_dir"],
        "properties": {
            "issue": {"type": "object"},
            "project_dir": {"type": "string"},
            "name": {"type": "string", "default": "issue"},
            "outputs": {"type": "array", "items": {"type": "string", "enum": ["print_pdf", "screen_pdf", "pngs", "proofs"]}},
            "png_dpi": {"type": "integer", "default": 150},
            "proof_stock": {"type": "string", "enum": sorted(STOCKS)},
        },
    }

    def get_status(self) -> ToolStatus:
        from tools.graphics.page_render import find_chromium

        return ToolStatus.AVAILABLE if find_chromium() else ToolStatus.UNAVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        return 0.0

    def prepare(self, issue: dict[str, Any], project_dir: Path, name: str = "issue") -> dict[str, Any]:
        """Write the layout folder (fonts, css, print + screen HTML). No rendering."""
        ld = project_dir / "layout"
        ld.mkdir(parents=True, exist_ok=True)
        if not (ld / "fonts" / "fonts.css").exists():
            shutil.copytree(STUDIO / "fonts", ld / "fonts", dirs_exist_ok=True)
        (ld / "css").mkdir(exist_ok=True)
        shutil.copy2(STUDIO / "css" / "editorial.css", ld / "css" / "editorial.css")
        book = Book(issue, project_dir, ld)
        out = {}
        for mode in ("print", "screen"):
            h = ld / f"{name}.{mode}.html"
            h.write_text(build_html(book, mode), encoding="utf-8")
            out[mode] = h
        (ld / f"{name}.issue.json").write_text(json.dumps(issue, indent=2, ensure_ascii=False), encoding="utf-8")
        return {"book": book, "html": out, "layout_dir": ld}

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        from tools.graphics.page_render import PageRender

        start = time.time()
        try:
            pd = Path(inputs["project_dir"])
            name = inputs.get("name", "issue")
            outputs = inputs.get("outputs") or ["print_pdf", "screen_pdf", "pngs"]
            prep = self.prepare(inputs["issue"], pd, name)
            book: Book = prep["book"]
            ld: Path = prep["layout_dir"]
            outd = ld / "out"
            outd.mkdir(exist_ok=True)
            data: dict[str, Any] = {"layout_dir": str(ld), "pages": len(book.pages), "warnings": book.warnings,
                                    "trim_mm": list(book.trim), "bleed_mm": book.bleed}
            artifacts: list[str] = []
            pr = PageRender()
            if "print_pdf" in outputs:
                slug = 8.0 if inputs["issue"].get("crop_marks", True) else 0.0
                W, H = book.trim
                r = pr.execute({"html_path": str(prep["html"]["print"]), "mode": "pdf", "preview_dpi": 0,
                                "width_mm": W + 2 * (book.bleed + slug), "height_mm": H + 2 * (book.bleed + slug),
                                "output_path": str(outd / f"{name}-print.pdf"), "expected_pages": len(book.pages)})
                if not r.success:
                    return ToolResult(success=False, error=f"print PDF: {r.error}", data=data)
                data["print_pdf"] = r.data["output_path"]
                data["print_checks"] = r.data.get("checks")
                artifacts.append(r.data["output_path"])
            if {"screen_pdf", "pngs", "proofs"} & set(outputs):
                W, H = book.trim
                pages_dir = outd / f"{name}-pages"
                if pages_dir.exists():  # never delete renders: the previous run moves to components/
                    keep = outd / "components" / f"{name}-pages.{time.strftime('%Y%m%d-%H%M%S')}"
                    keep.parent.mkdir(parents=True, exist_ok=True)
                    pages_dir.rename(keep)
                r = pr.execute({"html_path": str(prep["html"]["screen"]), "mode": "pdf",
                                "width_mm": W, "height_mm": H, "expected_pages": len(book.pages),
                                "preview_dpi": int(inputs.get("png_dpi", 150)) if ({"pngs", "proofs"} & set(outputs)) else 0,
                                "preview_dir": str(pages_dir), "output_path": str(outd / f"{name}-screen.pdf")})
                if not r.success:
                    return ToolResult(success=False, error=f"screen PDF: {r.error}", data=data)
                data["screen_pdf"] = r.data["output_path"]
                data["checks"] = r.data.get("checks")
                data["page_pngs"] = r.data.get("page_previews", [])
                artifacts += [r.data["output_path"]] + data["page_pngs"]
            if "proofs" in outputs:
                stock = inputs.get("proof_stock") or inputs["issue"].get("paper_stock", "uncoated_offwhite")
                proofs = [str(soft_proof(Path(p), outd / f"{name}-proof" / f"{Path(p).stem}-{stock}.png", stock))
                          for p in data.get("page_pngs", [])]
                data["proofs"] = proofs
                artifacts += proofs
            for k in ("print_pdf", "screen_pdf"):
                if data.get(k):
                    provenance.record(pd, data[k], kind="render", source="editorial_layout", licence="derived",
                                      parents=[provenance.rel(pd, i) for i in dict.fromkeys(book.images) if Path(i).exists()],
                                      tool=self.name)
            return ToolResult(success=True, data=data, artifacts=artifacts, duration_seconds=time.time() - start)
        except Exception as e:
            return ToolResult(success=False, error=f"{type(e).__name__}: {e}")

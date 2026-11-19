"""Print and still renderer: HTML -> PNG stills, or HTML -> print PDF + page PNGs.

This is the composition engine for the two print pipelines:

* ``image-studio`` -- single images and image sets (social posts, posters, ad
  stills, carousels, thumbnails). One HTML file per frame, rendered to PNG/JPG
  at an exact pixel size.
* ``magazine`` -- multi-page publications. One HTML file with one
  ``<section class="page">`` per page, rendered to a print PDF whose page size
  comes from CSS ``@page``, plus one PNG preview per page.

It drives the headless Chromium already present on the machine (Playwright's
cached build, or a system Chrome/Chromium), so it costs nothing and needs no
API key. Besides rendering it runs the print checks a human proofreader would:

* text that overflows its box (a frame with ``overflow: hidden`` or ``clip``
  whose content is taller or wider than the frame, or a ``.page`` that spills),
* images the HTML references that do not exist on disk,
* Arabic-Indic or Persian digits in the visible text (owner rule: Latin digits
  only, everywhere),
* the PDF page count and page size against what the plan expected,
* fonts that are not embedded in the PDF.

Findings are returned in ``data["checks"]``; ``data["checks"]["pass"]`` is the
single verdict the review stage reads.
"""

from __future__ import annotations

import glob
import json
import os
import re
import shutil
import subprocess
import time
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Optional
from urllib.parse import unquote, urlparse

from tools.base_tool import (
    BaseTool,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    ToolResult,
    ToolStability,
    ToolStatus,
    ToolTier,
)

MM_PER_PT = 25.4 / 72.0

# Named sizes. Pixel sizes are for screen deliverables; millimetre sizes are
# trim sizes for print (the HTML adds bleed through CSS @page if wanted).
SIZE_PRESETS: dict[str, dict[str, float]] = {
    # Social / screen stills (pixels)
    "instagram_post": {"width_px": 1080, "height_px": 1350},
    "instagram_square": {"width_px": 1080, "height_px": 1080},
    "instagram_story": {"width_px": 1080, "height_px": 1920},
    "facebook_post": {"width_px": 1200, "height_px": 630},
    "linkedin_post": {"width_px": 1200, "height_px": 627},
    "x_post": {"width_px": 1600, "height_px": 900},
    "youtube_thumbnail": {"width_px": 1280, "height_px": 720},
    "presentation_16_9": {"width_px": 1920, "height_px": 1080},
    # Print trim sizes (millimetres)
    "a4": {"width_mm": 210, "height_mm": 297},
    "a5": {"width_mm": 148, "height_mm": 210},
    "a3": {"width_mm": 297, "height_mm": 420},
    "us_letter": {"width_mm": 215.9, "height_mm": 279.4},
    "magazine_standard": {"width_mm": 230, "height_mm": 300},
    "magazine_us": {"width_mm": 203.2, "height_mm": 276.2},
    "poster_18x24": {"width_mm": 457.2, "height_mm": 609.6},
    "poster_a2": {"width_mm": 420, "height_mm": 594},
}

ARABIC_INDIC_DIGITS = re.compile(r"[٠-٩۰-۹]")

# Injected into a scratch copy of the page for the check pass. It marks every
# box whose content does not fit and writes a JSON report into the DOM, which
# Chromium's --dump-dom then hands back to us.
_CHECK_SCRIPT = r"""
<script>
(function () {
  function label(el) {
    var s = el.tagName.toLowerCase();
    if (el.id) s += '#' + el.id;
    if (el.className && typeof el.className === 'string') s += '.' + el.className.trim().split(/\s+/).join('.');
    var page = el.closest('[data-page], .page');
    var where = page ? (page.getAttribute('data-page') || page.id || '') : '';
    return {selector: s, page: where};
  }
  function run() {
    var found = [];
    var all = document.body ? document.body.querySelectorAll('*') : [];
    for (var i = 0; i < all.length; i++) {
      var el = all[i];
      var cs = getComputedStyle(el);
      var clips = /(hidden|clip)/.test(cs.overflow + cs.overflowX + cs.overflowY);
      var isPage = el.classList.contains('page') || el.hasAttribute('data-page');
      if (!clips && !isPage) continue;
      var dh = el.scrollHeight - el.clientHeight, dw = el.scrollWidth - el.clientWidth;
      if (dh > 2 || dw > 2) {
        var l = label(el); l.overflow_px = {x: Math.max(dw, 0), y: Math.max(dh, 0)};
        l.text_start = (el.innerText || '').trim().slice(0, 60);
        found.push(l);
      }
    }
    var pre = document.createElement('pre');
    pre.id = 'om-check-report';
    pre.textContent = JSON.stringify({overflow: found});
    document.documentElement.appendChild(pre);
  }
  var go = function () { (document.fonts && document.fonts.ready ? document.fonts.ready : Promise.resolve()).then(function () { setTimeout(run, 50); }); };
  if (document.readyState === 'complete') go(); else window.addEventListener('load', go);
})();
</script>
"""


class _TextAndRefs(HTMLParser):
    """Collect visible text and local resource references from HTML."""

    def __init__(self) -> None:
        super().__init__()
        self.text: list[str] = []
        self.refs: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        if tag in ("script", "style"):
            self._skip += 1
        for key, value in attrs:
            if not value:
                continue
            if (tag in ("img", "source", "image", "use") and key in ("src", "href", "xlink:href")) or (
                tag == "link" and key == "href"
            ):
                self.refs.append(value)
            if key == "style":
                self.refs.extend(re.findall(r"url\(\s*['\"]?([^'\")]+)", value))

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style") and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if self._skip:
            # Collect CSS url() references from <style> blocks too.
            self.refs.extend(re.findall(r"url\(\s*['\"]?([^'\")]+)", data))
            return
        self.text.append(data)


def find_chromium() -> Optional[str]:
    """Locate a headless-capable Chromium binary. Returns None if none exists."""
    env = os.environ.get("OM_CHROMIUM")
    if env and Path(env).exists():
        return env
    home = Path.home()
    patterns = [
        str(home / ".cache/ms-playwright/chromium-*/chrome-linux*/chrome"),
        str(home / "Library/Caches/ms-playwright/chromium-*/chrome-mac*/Chromium.app/Contents/MacOS/Chromium"),
        str(home / "Library/Caches/ms-playwright/chromium-*/chrome-mac*/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"),
    ]
    for pattern in patterns:
        hits = sorted(glob.glob(pattern), reverse=True)
        if hits:
            return hits[0]
    for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable", "chrome"):
        path = shutil.which(name)
        if path:
            return path
    mac = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    if Path(mac).exists():
        return mac
    return None


def resolve_size(inputs: dict[str, Any]) -> dict[str, float]:
    """Merge a named preset with explicit width/height overrides."""
    size: dict[str, float] = {}
    preset = inputs.get("size_preset")
    if preset:
        if preset not in SIZE_PRESETS:
            raise ValueError(f"Unknown size_preset {preset!r}. Known: {sorted(SIZE_PRESETS)}")
        size.update(SIZE_PRESETS[preset])
    for key in ("width_px", "height_px", "width_mm", "height_mm"):
        if inputs.get(key):
            size[key] = float(inputs[key])
    return size


def scan_html(html_path: Path) -> dict[str, Any]:
    """Static checks: Arabic-Indic digits in visible text, missing local files."""
    parser = _TextAndRefs()
    parser.feed(html_path.read_text(encoding="utf-8"))
    text = "".join(parser.text)
    bad_digits = ARABIC_INDIC_DIGITS.findall(text)
    missing: list[str] = []
    for ref in parser.refs:
        parsed = urlparse(ref)
        if parsed.scheme in ("http", "https", "data", "mailto"):
            continue
        if ref.startswith("#"):
            continue
        local = Path(unquote(parsed.path)) if parsed.scheme == "file" else (html_path.parent / unquote(parsed.path))
        if parsed.path and not local.exists():
            missing.append(ref)
    return {
        "non_latin_digits": len(bad_digits),
        "non_latin_digit_samples": sorted(set(bad_digits))[:10],
        "missing_resources": sorted(set(missing)),
    }


def pdf_report(pdf_path: Path) -> dict[str, Any]:
    """Page count, page sizes (mm), and fonts that are not embedded."""
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    sizes = []
    not_embedded: set[str] = set()
    for page in reader.pages:
        box = page.mediabox
        sizes.append(
            [round(float(box.width) * MM_PER_PT, 1), round(float(box.height) * MM_PER_PT, 1)]
        )
        fonts = (page.get("/Resources") or {}).get("/Font") or {}
        for ref in fonts.values():
            font = ref.get_object()
            descriptors = [font.get("/FontDescriptor")]
            for desc in font.get("/DescendantFonts") or []:
                descriptors.append(desc.get_object().get("/FontDescriptor"))
            embedded = False
            for desc in descriptors:
                if desc is None:
                    continue
                desc = desc.get_object()
                if any(k in desc for k in ("/FontFile", "/FontFile2", "/FontFile3")):
                    embedded = True
            if not embedded and font.get("/Subtype") != "/Type3":
                not_embedded.add(str(font.get("/BaseFont", "?")))
    return {"pages": len(reader.pages), "page_sizes_mm": sizes, "fonts_not_embedded": sorted(not_embedded)}


class PageRender(BaseTool):
    name = "page_render"
    version = "0.1.0"
    tier = ToolTier.CORE
    capability = "layout_render"
    provider = "chromium"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC

    dependencies = ["python:pypdf"]  # Chromium is located dynamically, see get_status
    install_instructions = (
        "Needs a headless Chromium. Either run `npx playwright install chromium` "
        "(the build lands in ~/.cache/ms-playwright), install Google Chrome/Chromium, "
        "or point OM_CHROMIUM at a chrome binary. Page PNGs from a PDF also need "
        "`pdftoppm` (poppler-utils)."
    )
    agent_skills = ["tailwind-design-system"]

    capabilities = [
        "render_still",
        "render_print_pdf",
        "render_page_previews",
        "check_text_overflow",
        "check_missing_images",
        "check_latin_digits",
    ]
    supports = {
        "formats": ["png", "jpg", "pdf"],
        "size_presets": sorted(SIZE_PRESETS),
        "rtl": True,
        "cost": "free (local)",
    }
    best_for = [
        "magazine and brochure layout to print PDF",
        "social posts, posters and ad stills with exact typography",
        "Arabic and English typesetting (real font shaping, RTL)",
        "turning generated images into finished designed pieces",
    ]
    not_good_for = [
        "generating the picture itself (use image_selector or a provider image tool)",
        "animation or video (use video_compose)",
    ]
    resource_profile = ResourceProfile(cpu_cores=2, ram_mb=1024, vram_mb=0, disk_mb=200)
    idempotency_key_fields = ["html_path", "mode", "size_preset", "width_px", "height_px", "scale"]
    side_effects = ["writes the output PNG/JPG/PDF files and page previews"]
    user_visible_verification = [
        "Open the PDF or PNG and look at every page",
        "data.checks.pass is true and data.checks lists no overflow, missing images or non-Latin digits",
    ]

    input_schema = {
        "type": "object",
        "required": ["html_path", "mode"],
        "properties": {
            "html_path": {"type": "string", "description": "HTML file to render (absolute or repo-relative)"},
            "mode": {
                "type": "string",
                "enum": ["still", "pdf"],
                "description": "still = one PNG/JPG at an exact size; pdf = print PDF (+ page PNGs)",
            },
            "output_path": {
                "type": "string",
                "description": "Output file (.png/.jpg for still, .pdf for pdf). Must sit under projects/<id>/",
            },
            "size_preset": {"type": "string", "enum": sorted(SIZE_PRESETS)},
            "width_px": {"type": "number"},
            "height_px": {"type": "number"},
            "width_mm": {"type": "number", "description": "pdf mode: expected trim width, checked against the PDF"},
            "height_mm": {"type": "number", "description": "pdf mode: expected trim height, checked against the PDF"},
            "scale": {
                "type": "number",
                "default": 2,
                "description": "still mode: device scale factor (2 = retina-sharp; output is width_px*scale wide unless keep_exact_size)",
            },
            "keep_exact_size": {
                "type": "boolean",
                "default": True,
                "description": "still mode: downscale the hi-dpi render back to exactly width_px x height_px",
            },
            "preview_dpi": {"type": "integer", "default": 110, "description": "pdf mode: DPI of page PNG previews (0 = none)"},
            "preview_dir": {"type": "string", "description": "pdf mode: where page PNGs go (default: <pdf stem>_pages/ beside the PDF)"},
            "expected_pages": {"type": "integer", "description": "pdf mode: page count the layout plan promised"},
            "run_checks": {"type": "boolean", "default": True},
            "timeout_seconds": {"type": "integer", "default": 120},
        },
    }

    output_schema = {
        "type": "object",
        "properties": {
            "output_path": {"type": "string"},
            "page_previews": {"type": "array", "items": {"type": "string"}},
            "checks": {"type": "object"},
        },
    }

    # ---- status ----

    def get_status(self) -> ToolStatus:
        try:
            self.check_dependencies()
        except Exception:
            return ToolStatus.UNAVAILABLE
        return ToolStatus.AVAILABLE if find_chromium() else ToolStatus.UNAVAILABLE

    def estimate_runtime(self, inputs: dict[str, Any]) -> float:
        return 15.0 if inputs.get("mode") == "pdf" else 5.0

    # ---- helpers ----

    @staticmethod
    def _base_flags(chrome: str) -> list[str]:
        return [
            chrome,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--hide-scrollbars",
            "--no-first-run",
            "--no-default-browser-check",
            "--allow-file-access-from-files",
            "--run-all-compositor-stages-before-draw",
            "--virtual-time-budget=8000",
            "--font-render-hinting=none",
        ]

    def _run(self, cmd: list[str], timeout: int) -> subprocess.CompletedProcess:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

    def _layout_checks(self, chrome: str, html: Path, size: dict[str, float], timeout: int) -> dict[str, Any]:
        """Render a scratch copy with the checker script and read its report."""
        source = html.read_text(encoding="utf-8")
        injected = source.replace("</body>", _CHECK_SCRIPT + "</body>") if "</body>" in source else source + _CHECK_SCRIPT
        scratch = html.parent / f".om-check-{html.stem}.html"
        scratch.write_text(injected, encoding="utf-8")
        try:
            cmd = self._base_flags(chrome)
            if size.get("width_px") and size.get("height_px"):
                w, h = int(size["width_px"]), int(size["height_px"])
                pad_w, pad_h = self._viewport_shortfall(chrome, w, h, timeout)
                cmd.append(f"--window-size={w + pad_w},{h + pad_h}")
            cmd += ["--dump-dom", scratch.resolve().as_uri()]
            proc = self._run(cmd, timeout)
            match = re.search(r'<pre id="om-check-report">(.*?)</pre>', proc.stdout, re.S)
            if not match:
                return {"overflow": [], "overflow_check": "not_run", "note": "checker script produced no report"}
            import html as _html

            report = json.loads(_html.unescape(match.group(1)))
            report["overflow_check"] = "ran"
            return report
        finally:
            scratch.unlink(missing_ok=True)  # keep-media-ok: scratch HTML copy, holds no media

    # ---- execution ----

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        start = time.time()
        chrome = find_chromium()
        if not chrome:
            return ToolResult(success=False, error=f"No Chromium found. {self.install_instructions}")

        html = Path(inputs["html_path"]).expanduser()
        if not html.is_absolute():
            html = Path.cwd() / html
        if not html.exists():
            return ToolResult(success=False, error=f"HTML not found: {html}")

        mode = inputs["mode"]
        try:
            size = resolve_size(inputs)
        except ValueError as exc:
            return ToolResult(success=False, error=str(exc))
        timeout = int(inputs.get("timeout_seconds", 120))

        default_ext = ".pdf" if mode == "pdf" else ".png"
        out = Path(inputs.get("output_path") or html.with_suffix(default_ext)).expanduser()
        if not out.is_absolute():
            out = Path.cwd() / out
        out.parent.mkdir(parents=True, exist_ok=True)

        data: dict[str, Any] = {"mode": mode, "chromium": chrome, "size": size}
        artifacts: list[str] = []

        try:
            if mode == "still":
                if not (size.get("width_px") and size.get("height_px")):
                    return ToolResult(success=False, error="still mode needs size_preset or width_px + height_px")
                result = self._render_still(chrome, html, out, size, inputs, timeout)
            elif mode == "pdf":
                result = self._render_pdf(chrome, html, out, inputs, timeout)
            else:
                return ToolResult(success=False, error=f"Unknown mode {mode!r}")
        except subprocess.TimeoutExpired:
            return ToolResult(success=False, error=f"Chromium timed out after {timeout}s rendering {html}")

        if not result.get("ok"):
            return ToolResult(success=False, error=result.get("error", "render failed"), data=data)

        data.update({k: v for k, v in result.items() if k != "ok"})
        artifacts.append(str(out))
        artifacts.extend(result.get("page_previews", []))

        if inputs.get("run_checks", True):
            checks: dict[str, Any] = scan_html(html)
            checks.update(self._layout_checks(chrome, html, size, timeout))
            problems: list[str] = []
            if checks["overflow"]:
                problems.append(f"{len(checks['overflow'])} box(es) overflow")
            if checks["missing_resources"]:
                problems.append(f"{len(checks['missing_resources'])} missing resource(s)")
            if checks["non_latin_digits"]:
                problems.append(f"{checks['non_latin_digits']} Arabic-Indic/Persian digit(s) in text")
            if mode == "pdf":
                pdf = data.get("pdf", {})
                checks["pages"] = pdf.get("pages")
                checks["fonts_not_embedded"] = pdf.get("fonts_not_embedded", [])
                if checks["fonts_not_embedded"]:
                    problems.append("fonts not embedded: " + ", ".join(checks["fonts_not_embedded"]))
                expected = inputs.get("expected_pages")
                if expected and pdf.get("pages") != int(expected):
                    problems.append(f"page count {pdf.get('pages')} != expected {expected}")
                if size.get("width_mm") and size.get("height_mm") and pdf.get("page_sizes_mm"):
                    want = (size["width_mm"], size["height_mm"])
                    off = [
                        i + 1
                        for i, (w, h) in enumerate(pdf["page_sizes_mm"])
                        if abs(w - want[0]) > 1.0 or abs(h - want[1]) > 1.0
                    ]
                    if off:
                        problems.append(f"page size differs from {want[0]}x{want[1]} mm on page(s) {off[:10]}")
            checks["problems"] = problems
            checks["pass"] = not problems
            data["checks"] = checks

        return ToolResult(
            success=True,
            data=data,
            artifacts=artifacts,
            cost_usd=0.0,
            duration_seconds=round(time.time() - start, 2),
            model="chromium-headless",
        )

    def _viewport_shortfall(self, chrome: str, w: int, h: int, timeout: int) -> tuple[int, int]:
        """How many pixels the browser UI steals from --window-size.

        New headless Chrome reserves room for its (invisible) toolbar, so a
        1080x1350 window yields a ~1080x1263 viewport and a still whose vh-based
        layout is cut short. We measure once and pad the window by the gap.
        """
        import tempfile

        probe = (
            "<!doctype html><html><body><script>addEventListener('load',function(){"
            "var p=document.createElement('pre');p.id='om-vp';"
            "p.textContent=innerWidth+'x'+innerHeight;document.body.appendChild(p);});"
            "</script></body></html>"
        )
        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as fh:
            fh.write(probe)
            probe_path = Path(fh.name)
        cmd = self._base_flags(chrome) + [
            f"--window-size={w},{h}",
            "--dump-dom",
            probe_path.as_uri(),
        ]
        try:
            proc = self._run(cmd, timeout)
        finally:
            probe_path.unlink(missing_ok=True)  # keep-media-ok: scratch HTML probe, holds no media
        match = re.search(r'id="om-vp">(\d+)x(\d+)<', proc.stdout)
        if not match:
            return 0, 0
        return max(w - int(match.group(1)), 0), max(h - int(match.group(2)), 0)

    def _render_still(
        self, chrome: str, html: Path, out: Path, size: dict[str, float], inputs: dict[str, Any], timeout: int
    ) -> dict[str, Any]:
        w, h = int(size["width_px"]), int(size["height_px"])
        scale = float(inputs.get("scale", 2) or 1)
        raw = out.with_name(out.stem + ".raw.png")
        pad_w, pad_h = self._viewport_shortfall(chrome, w, h, timeout)
        cmd = self._base_flags(chrome) + [
            f"--window-size={w + pad_w},{h + pad_h}",
            f"--force-device-scale-factor={scale}",
            f"--screenshot={raw}",
            "--default-background-color=00000000",
            html.resolve().as_uri(),
        ]
        proc = self._run(cmd, timeout)
        if not raw.exists():
            return {"ok": False, "error": f"Chromium wrote no screenshot. stderr: {proc.stderr[-800:]}"}

        from PIL import Image

        img = Image.open(raw)
        img.load()
        # The capture is the padded window; keep the top-left viewport area only.
        vw, vh = int(round(w * scale)), int(round(h * scale))
        if img.size[0] > vw or img.size[1] > vh:
            img = img.crop((0, 0, min(vw, img.size[0]), min(vh, img.size[1])))
        if inputs.get("keep_exact_size", True) and img.size != (w, h):
            img = img.resize((w, h), Image.LANCZOS)
        if out.suffix.lower() in (".jpg", ".jpeg"):
            img.convert("RGB").save(out, quality=92, optimize=True)
        else:
            img.save(out, optimize=True)
        raw.unlink(missing_ok=True)  # keep-media-ok: temporary hi-dpi capture; the final still stays on disk
        return {"ok": True, "output_path": str(out), "pixel_size": list(img.size), "viewport_padding_px": [pad_w, pad_h]}

    def _render_pdf(
        self, chrome: str, html: Path, out: Path, inputs: dict[str, Any], timeout: int
    ) -> dict[str, Any]:
        if out.suffix.lower() != ".pdf":
            out = out.with_suffix(".pdf")
        cmd = self._base_flags(chrome) + [
            f"--print-to-pdf={out}",
            "--no-pdf-header-footer",
            "--generate-pdf-document-outline",
            html.resolve().as_uri(),
        ]
        proc = self._run(cmd, timeout)
        if not out.exists() or out.stat().st_size == 0:
            return {"ok": False, "error": f"Chromium wrote no PDF. stderr: {proc.stderr[-800:]}"}

        result: dict[str, Any] = {"ok": True, "output_path": str(out), "pdf": pdf_report(out)}
        dpi = int(inputs.get("preview_dpi", 110) or 0)
        previews: list[str] = []
        if dpi > 0:
            if shutil.which("pdftoppm") is None:
                result["preview_note"] = "pdftoppm not installed; no page previews"
            else:
                pdir = Path(inputs.get("preview_dir") or out.with_name(out.stem + "_pages"))
                pdir.mkdir(parents=True, exist_ok=True)
                prefix = pdir / "page"
                subprocess.run(
                    ["pdftoppm", "-r", str(dpi), "-png", str(out), str(prefix)],
                    capture_output=True,
                    timeout=timeout,
                    check=False,
                )
                previews = sorted(str(p) for p in pdir.glob("page-*.png"))
        result["page_previews"] = previews
        return result

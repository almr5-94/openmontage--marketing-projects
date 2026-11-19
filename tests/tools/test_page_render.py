"""page_render: the print studio's HTML -> PNG / PDF engine and its proof checks.

Static checks (digits, missing files, size presets) run everywhere. Render tests
need a headless Chromium and are skipped on machines without one.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.graphics.page_render import (
    SIZE_PRESETS,
    PageRender,
    find_chromium,
    resolve_size,
    scan_html,
)

REPO = Path(__file__).resolve().parents[2]
needs_chromium = pytest.mark.skipif(find_chromium() is None, reason="no headless Chromium on this machine")


def _page(tmp_path: Path, body: str, css: str = "") -> Path:
    html = tmp_path / "doc.html"
    html.write_text(
        "<!doctype html><html><head><meta charset='utf-8'><style>"
        "@page{size:100mm 100mm;margin:0} html,body{margin:0}"
        ".page{width:100mm;height:100mm;overflow:hidden;break-after:page;font:12pt serif}"
        ".page:last-child{break-after:auto}"
        f"{css}</style></head><body>{body}</body></html>",
        encoding="utf-8",
    )
    return html


# ---------- static checks ----------

def test_arabic_indic_digits_in_text_are_flagged(tmp_path):
    html = _page(tmp_path, "<section class='page'><p>السعر ١٢٣ دينار</p></section>")
    report = scan_html(html)
    assert report["non_latin_digits"] == 3


def test_digits_inside_script_or_style_are_ignored(tmp_path):
    html = _page(tmp_path, "<section class='page'><p>Price 123</p><script>var a='٣'</script></section>")
    assert scan_html(html)["non_latin_digits"] == 0


def test_persian_digits_are_flagged(tmp_path):
    html = _page(tmp_path, "<section class='page'><p>۲۰۲۶</p></section>")
    assert scan_html(html)["non_latin_digits"] == 4


def test_missing_local_image_is_flagged(tmp_path):
    (tmp_path / "here.png").write_bytes(b"x")
    html = _page(
        tmp_path,
        "<section class='page'><img src='here.png'><img src='gone.png'>"
        "<div style=\"background:url('also-gone.jpg')\"></div>"
        "<img src='https://example.com/remote.png'></section>",
    )
    assert scan_html(html)["missing_resources"] == ["also-gone.jpg", "gone.png"]


def test_size_presets_resolve_and_override():
    assert resolve_size({"size_preset": "instagram_post"}) == {"width_px": 1080, "height_px": 1350}
    assert resolve_size({"size_preset": "a4", "width_mm": 216}) == {"width_mm": 216.0, "height_mm": 297}
    with pytest.raises(ValueError):
        resolve_size({"size_preset": "nope"})


def test_every_preset_has_a_complete_pair():
    for name, size in SIZE_PRESETS.items():
        assert ("width_px" in size and "height_px" in size) or ("width_mm" in size and "height_mm" in size), name


def test_tool_is_registered_free_and_print_capable():
    from tools.tool_registry import registry

    registry.discover()
    info = registry.get("page_render").get_info()
    assert info["capability"] == "layout_render"
    assert PageRender().estimate_cost({"mode": "pdf"}) == 0.0
    assert {"render_still", "render_print_pdf", "check_text_overflow"} <= set(info["capabilities"])


# ---------- real renders ----------

@needs_chromium
def test_pdf_page_count_size_and_pass(tmp_path):
    html = _page(tmp_path, "<section class='page'>one</section><section class='page'>two</section>")
    r = PageRender().execute({
        "html_path": str(html), "mode": "pdf", "output_path": str(tmp_path / "out.pdf"),
        "width_mm": 100, "height_mm": 100, "expected_pages": 2, "preview_dpi": 40,
    })
    assert r.success, r.error
    checks = r.data["checks"]
    assert checks["pages"] == 2
    assert checks["pass"], checks["problems"]
    assert checks["fonts_not_embedded"] == []


@needs_chromium
def test_overflowing_frame_fails_the_render(tmp_path):
    long_text = "word " * 600
    html = _page(
        tmp_path,
        f"<section class='page' data-page='1'><div class='frame' style='height:20mm;overflow:hidden'>{long_text}</div></section>",
    )
    r = PageRender().execute({"html_path": str(html), "mode": "pdf", "output_path": str(tmp_path / "o.pdf"), "preview_dpi": 0})
    assert r.success, r.error
    checks = r.data["checks"]
    assert checks["overflow_check"] == "ran"
    assert not checks["pass"]
    assert any(item["page"] == "1" for item in checks["overflow"])


@needs_chromium
def test_wrong_page_count_fails(tmp_path):
    html = _page(tmp_path, "<section class='page'>only one</section>")
    r = PageRender().execute({
        "html_path": str(html), "mode": "pdf", "output_path": str(tmp_path / "o.pdf"),
        "expected_pages": 4, "preview_dpi": 0,
    })
    assert not r.data["checks"]["pass"]
    assert any("page count" in p for p in r.data["checks"]["problems"])


@needs_chromium
def test_still_is_exact_size_and_fills_the_whole_frame(tmp_path):
    """Regression: new headless Chrome's viewport is ~87 px shorter than
    --window-size, which left a blank band at the bottom of every still."""
    from PIL import Image

    html = tmp_path / "still.html"
    html.write_text(
        "<!doctype html><html><head><style>html,body{margin:0}"
        ".s{width:100vw;height:100vh;background:#ff0000}</style></head>"
        "<body><div class='s'></div></body></html>",
        encoding="utf-8",
    )
    out = tmp_path / "still.png"
    r = PageRender().execute({"html_path": str(html), "mode": "still", "size_preset": "instagram_post", "output_path": str(out)})
    assert r.success, r.error
    img = Image.open(out).convert("RGB")
    assert img.size == (1080, 1350)
    # Bottom rows must be the frame colour, not the empty page background.
    assert img.getpixel((540, 1345))[0] > 200 and img.getpixel((540, 1345))[1] < 60


@needs_chromium
def test_shipped_templates_render_clean(tmp_path):
    r = PageRender().execute({
        "html_path": str(REPO / "print-studio/templates/magazine/issue.html"), "mode": "pdf",
        "output_path": str(tmp_path / "issue.pdf"), "size_preset": "magazine_standard",
        "expected_pages": 6, "preview_dpi": 0,
    })
    assert r.success, r.error
    assert r.data["checks"]["pass"], r.data["checks"]["problems"]

    r = PageRender().execute({
        "html_path": str(REPO / "print-studio/templates/stills/social-post.html"), "mode": "still",
        "size_preset": "instagram_story", "output_path": str(tmp_path / "story.jpg"),
    })
    assert r.success, r.error
    assert r.data["checks"]["pass"], r.data["checks"]["problems"]

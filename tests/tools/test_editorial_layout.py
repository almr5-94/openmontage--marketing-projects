"""editorial_layout: geometry, sides, RTL, fonts, crop marks, and a real Chromium render."""

from __future__ import annotations

import re
import shutil
import subprocess

import pytest
from PIL import Image

from tools.graphics.editorial_layout import Book, EditorialLayout, build_html
from tools.graphics.page_render import find_chromium


def _issue(**kw):
    base = {"title": "T", "trim": "a4", "pages": [
        {"type": "cover", "image": "assets/a.jpg", "headline": "H"},
        {"type": "art_page", "image": "assets/a.jpg"},
        {"type": "contents", "entries": [{"ref": "f", "title": "Feature"}]},
        {"id": "f", "type": "opening_spread", "image": "assets/a.jpg", "title": "Feature"},
        {"type": "back_cover", "image": "assets/a.jpg", "line": "End"},
    ]}
    base.update(kw)
    return base


@pytest.fixture()
def pd(tmp_path):
    (tmp_path / "assets").mkdir()
    Image.new("RGB", (2600, 3600), (120, 100, 80)).save(tmp_path / "assets" / "a.jpg")
    return tmp_path


def test_sides_ltr_and_rtl(pd):
    ltr = Book(_issue(), pd, pd / "layout")
    assert [p["side"] for p in ltr.pages] == ["right", "left", "right", "left", "right", "left"]
    rtl = Book(_issue(dir="rtl"), pd, pd / "layout")
    assert [p["side"] for p in rtl.pages] == ["left", "right", "left", "right", "left", "right"]
    assert ltr.ids["f"] == 4 and not ltr.warnings


def test_spread_on_wrong_side_and_odd_count_warn(pd):
    iss = _issue()
    del iss["pages"][1]
    w = " ".join(Book(iss, pd, pd / "layout").warnings)
    assert "do not face" in w and "even count" in w


def test_print_has_marks_and_bleed_screen_does_not(pd):
    b = Book(_issue(), pd, pd / "layout")
    pr, sc = build_html(b, "print"), build_html(b, "screen")
    assert pr.count('class="mark h"') == 6 * 4
    assert "size:232.00mm 319.00mm" in pr and "size:210.00mm 297.00mm" in sc
    assert 'class="mark' not in sc


def test_banned_font_refused(pd):
    with pytest.raises(ValueError, match="AP-4"):
        build_html(Book(_issue(tokens={"font_text": "Noto Serif"}), pd, pd / "layout"), "print")


def test_rtl_uses_arabic_faces_and_latin_folios(pd):
    html = build_html(Book(_issue(dir="rtl"), pd, pd / "layout"), "screen")
    assert 'dir="rtl"' in html and '"Amiri"' in html and '"IBM Plex Sans Arabic"' in html
    assert not re.search(r"[٠-٩۰-۹]", html)


@pytest.mark.skipif(not find_chromium() or not shutil.which("pdfinfo"), reason="needs Chromium and poppler")
def test_real_render_print_and_screen(pd):
    r = EditorialLayout().execute({"issue": _issue(), "project_dir": str(pd), "outputs": ["print_pdf", "screen_pdf", "pngs"],
                                   "png_dpi": 30})
    assert r.success, r.error
    assert r.data["pages"] == 6 and len(r.data["page_pngs"]) == 6
    assert r.data["checks"]["pass"], r.data["checks"]["problems"]
    info = subprocess.run(["pdfinfo", r.data["print_pdf"]], capture_output=True, text=True).stdout
    w, h = map(float, re.search(r"Page size:\s+([\d.]+) x ([\d.]+)", info).groups())
    assert abs(w / 72 * 25.4 - 232) < 0.5 and abs(h / 72 * 25.4 - 319) < 0.5
    fonts = subprocess.run(["pdffonts", r.data["print_pdf"]], capture_output=True, text=True).stdout
    assert "Noto" not in fonts and "DejaVu" not in fonts
    assert (pd / "layout" / "fonts" / "fonts.css").exists()

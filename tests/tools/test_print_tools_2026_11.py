"""Regression tests for the November 2026 print-studio changes: freeform pages, sink, cutout fill_holes /
neutral_v, the local critic's cut-off answers, and the CUDA upscaler tiling."""

from __future__ import annotations

import inspect
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from lib import provenance
from qa.anti_ai_tells import local_codes
from tools.graphics.editorial_layout import Book, build_html
from tools.graphics.image_crop import ImageCrop


@pytest.fixture()
def pd(tmp_path: Path) -> Path:
    (tmp_path / "assets").mkdir()
    Image.new("RGB", (2600, 3600), (120, 100, 80)).save(tmp_path / "assets" / "a.jpg")
    return tmp_path


# ---------- editorial_layout: freeform pages ----------

def _free_issue():
    return {"title": "T", "trim": "a4", "dir": "rtl", "css": ".x-house{color:#123456}", "pages": [
        {"type": "freeform", "html": '<img class="bl" src="{{img:assets/a.jpg}}">{{folio}}'},
        {"type": "freeform_spread", "cls": "free ever", "html": ["<p>RIGHT-HALF</p>", "<p>LEFT-HALF</p>"]},
        {"type": "freeform", "html": "<p>end</p>"},
    ]}


def test_freeform_resolves_and_credits_images(pd):
    book = Book(_free_issue(), pd, pd / "layout")
    html = build_html(book, "screen")
    assert "{{img:" not in html and "{{folio}}" not in html
    assert "../assets/a.jpg" in html  # relative to the layout folder
    assert str(pd / "assets" / "a.jpg") in book.images  # so the colophon and provenance see it
    assert not book.warnings


def test_freeform_spread_gives_each_half_its_own_html_and_issue_css_lands(pd):
    book = Book(_free_issue(), pd, pd / "layout")
    assert len(book.pages) == 4  # the spread is two physical pages
    html = build_html(book, "screen")
    assert html.index("RIGHT-HALF") < html.index("LEFT-HALF")
    assert html.count("RIGHT-HALF") == 1 and html.count("LEFT-HALF") == 1
    assert ".x-house{color:#123456}" in html
    assert html.count(" free ever ") == 2  # both halves carry the spread's own class


def test_text_page_sink_lets_the_body_take_its_natural_height(pd):
    issue = {"title": "T", "trim": "a4", "pages": [
        {"type": "text_page", "title": "A", "body": "one\n\ntwo", "sink": True},
        {"type": "text_page", "title": "B", "body": "three"}]}
    html = build_html(Book(issue, pd, pd / "layout"), "screen")
    first, second = html.split('data-page="2"')
    assert "height:auto;padding-bottom:6pt" in first and "flex:none" in first
    assert 'style="height:100%"' in second


# ---------- image_crop cutout ----------

@pytest.fixture()
def object_on_ground(tmp_path: Path) -> tuple[Path, Path]:
    """A brown disc on a pale studio ground, with a pale grey engraving in its middle."""
    arr = np.full((400, 400, 3), 238, np.uint8)
    yy, xx = np.mgrid[:400, :400]
    disc = (yy - 200) ** 2 + (xx - 200) ** 2 < 140 ** 2
    arr[disc] = (110, 70, 40)
    hole = (yy - 200) ** 2 + (xx - 200) ** 2 < 35 ** 2
    arr[hole] = (205, 205, 205)  # colourless and bright: drop_neutral takes it for ground
    src = tmp_path / "assets" / "art" / "met-2.jpg"
    src.parent.mkdir(parents=True)
    Image.fromarray(arr).save(src, quality=97)
    provenance.record(tmp_path, src, kind="museum", source="Met", licence="CC0", object_id="2")
    return tmp_path, src


def _cut(pd, src, **params):
    r = ImageCrop().execute({"operation": "cutout", "input_path": str(src), "project_dir": str(pd),
                             "shape_params": {"drop_neutral": True, **params}})
    assert r.success, r.error
    return np.asarray(Image.open(r.data["path"]))[..., 3]


def test_cutout_fill_holes_restores_a_solid_object(object_on_ground):
    pd, src = object_on_ground
    a = _cut(pd, src)
    h, w = a.shape
    assert a[h // 2, w // 2] < 60  # the engraving was punched out
    b = _cut(pd, src, fill_holes=True)
    assert b[h // 2, w // 2] > 200  # and fill_holes puts it back
    assert b[2, 2] < 60  # the ground stays transparent


def test_cutout_neutral_v_keeps_grey_darker_than_the_threshold(object_on_ground):
    pd, src = object_on_ground
    a = _cut(pd, src, neutral_v=215)  # the 205-grey engraving is no longer "ground"
    h, w = a.shape
    assert a[h // 2, w // 2] > 200


# ---------- anti_ai_tells: the local critic ----------

def test_local_codes_ignores_an_answer_cut_off_mid_statement():
    assert local_codes("AP-1: The page does not contain chips.\nAP-3: The page does") == ([], [])
    firm, _ = local_codes("AP-1: The page does not contain chips.\nAP-3: the page uses chips and badges.")
    assert firm == ["AP-3"]


# ---------- upscale ----------

def test_upscaler_tiles_on_cuda():
    """A full-frame CUDA pass of a print-size photo ran out of memory on a shared 16 GB card."""
    from tools.enhancement import upscale

    src = inspect.getsource(upscale)
    assert '"tile": 512 if _device == "cuda" else 256' in src


def test_local_codes_trusts_the_statement_over_a_closing_summary():
    """Measured on qwen2.5vl:7b, 2026-11-20: it judged AP-6 "not drawn in code", then listed it under Faults."""
    a = ("AP-1: The page does not contain any operational copy.\n"
         "AP-6: The objects are not drawn in code; they are real imagery.\n\nFaults: AP-6")
    assert local_codes(a) == ([], [])
    assert local_codes("AP-5: The same image is not reused in different forms. The page has one image.") == ([], [])
    firm, _ = local_codes("AP-6: a tablet drawn from rounded rectangles.\n\nFaults: AP-6")
    assert firm == ["AP-6"]


def test_editorial_layout_gives_chromium_a_longer_render_limit():
    """A 28-page photo issue timed out at the renderer's 120 s default on a loaded host, 2026-11-20."""
    from tools.graphics import editorial_layout

    src = inspect.getsource(editorial_layout)
    assert src.count('"timeout_seconds": int(inputs.get("timeout_seconds", 300))') == 2


def test_issue_images_finds_pictures_inside_freeform_html():
    """The quality gate missed every freeform picture and face-checked the whole project instead, 2026-11-20."""
    from lib.studio_api import issue_images

    issue = {"pages": [{"type": "art_page", "image": "assets/a.jpg"},
                       {"type": "freeform", "html": '<img src="{{img:assets/b.jpg}}"><img src="{{img: assets/c.png }}">'},
                       {"type": "freeform_spread", "html": ['<img src="{{img:assets/b.jpg}}">', "<p>no picture</p>"]}]}
    assert issue_images(issue) == ["assets/a.jpg", "assets/b.jpg", "assets/c.png"]

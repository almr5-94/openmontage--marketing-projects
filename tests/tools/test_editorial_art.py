"""image_crop, generative_art and collage: local, free, provenance-recorded (no network)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from lib import provenance
from tools.graphics.collage import Collage, blend
from tools.graphics.generative_art import GenerativeArt
from tools.graphics.image_crop import ImageCrop, shape_mask


@pytest.fixture()
def project(tmp_path: Path) -> tuple[Path, Path]:
    art = tmp_path / "assets" / "art" / "met-1.jpg"
    art.parent.mkdir(parents=True)
    rng = np.random.default_rng(0)
    arr = (rng.random((600, 800, 3)) * 60 + 90).astype(np.uint8)
    arr[200:400, 500:700] = 240  # a bright, detailed subject off-centre
    Image.fromarray(arr).save(art, quality=95)
    provenance.record(tmp_path, art, kind="museum", source="Met", licence="CC0", object_id="1")
    return tmp_path, art


# ---------- image_crop ----------

@pytest.mark.parametrize("shape,params", [
    ("circle", {}), ("ellipse", {}), ("triangle", {}), ("hexagon", {}),
    ("polygon", {"points": [[0.1, 0.1], [0.9, 0.2], [0.5, 0.9]]}),
    ("arc", {"ri": 0.3, "start": 180, "end": 360}), ("stripe", {"count": 5, "angle": 20}),
])
def test_every_mask_shape_has_inside_and_outside(shape, params):
    m = np.asarray(shape_mask((400, 300), shape, params))
    assert m.max() == 255 and m.min() == 0


def test_mask_writes_fragment_with_alpha_and_derived_provenance(project):
    pd, art = project
    r = ImageCrop().execute({"operation": "mask", "input_path": str(art), "shape": "hexagon", "project_dir": str(pd)})
    assert r.success, r.error
    out = Image.open(r.data["path"])
    assert out.mode == "RGBA" and np.asarray(out)[..., 3].min() == 0
    rec = provenance.find(pd, r.data["path"])
    assert rec["licence"] == "derived" and rec["parents"] == ["assets/art/met-1.jpg"]
    assert provenance.check_complete(pd, [r.data["path"]])["pass"]


def test_smart_crop_exact_size_and_never_overwrites(project):
    pd, art = project
    t = ImageCrop()
    a = t.execute({"operation": "smart_crop", "input_path": str(art), "target": "300x300", "project_dir": str(pd)})
    b = t.execute({"operation": "smart_crop", "input_path": str(art), "target": "300x300", "project_dir": str(pd)})
    assert a.success and b.success
    assert Image.open(a.data["path"]).size == (300, 300)
    assert a.data["path"] != b.data["path"]


# ---------- generative_art ----------

def test_same_seed_same_svg_different_seed_different():
    g = GenerativeArt()
    base = {"algorithm": "flow_field", "width_px": 300, "height_px": 400, "paper": "cream"}
    assert g.build_svg({**base, "seed": 7}) == g.build_svg({**base, "seed": 7})
    assert g.build_svg({**base, "seed": 7}) != g.build_svg({**base, "seed": 8})


@pytest.mark.parametrize("algo", ["arches", "voronoi", "botanical", "truchet"])
def test_algorithms_build_svg(algo):
    svg = GenerativeArt().build_svg({"algorithm": algo, "seed": 3, "width_px": 300, "height_px": 400})
    assert svg.startswith("<svg") and "</svg>" in svg


def test_size_from_millimetres_at_300dpi():
    assert GenerativeArt.size_px({"width_mm": 210, "height_mm": 297}) == (2480, 3508)


# ---------- collage ----------

def test_blend_modes():
    a, b = np.full((1, 1, 3), 0.5), np.full((1, 1, 3), 0.5)
    assert blend(a, b, "multiply")[0, 0, 0] == pytest.approx(0.25)
    assert blend(a, b, "screen")[0, 0, 0] == pytest.approx(0.75)


@pytest.mark.parametrize("style", ["grid", "joiner", "cutpaste", "moodboard", "editorial_overlay"])
def test_styles_render_and_record_parents(project, style):
    pd, art = project
    r = Collage().execute({"style": style, "sources": ["assets/art/met-1.jpg"] * 3, "seed": 5,
                           "canvas": {"width_px": 480, "height_px": 600}, "project_dir": str(pd),
                           "options": {"pieces": 4}})
    assert r.success, r.error
    assert Image.open(r.data["path"]).size == (480, 600)
    rec = provenance.find(pd, r.data["path"])
    assert rec["kind"] == "collage" and "assets/art/met-1.jpg" in rec["parents"]
    assert json.loads(Path(r.data["layout_path"]).read_text())["seed"] == 5


def test_collage_is_deterministic_for_a_seed(project):
    pd, _ = project
    args = {"style": "cutpaste", "sources": ["assets/art/met-1.jpg"] * 2, "seed": 9,
            "canvas": {"width_px": 300, "height_px": 400}, "project_dir": str(pd)}
    a = Collage().execute(args)
    b = Collage().execute(args)
    assert np.array_equal(np.asarray(Image.open(a.data["path"])), np.asarray(Image.open(b.data["path"])))


def test_layout_only_returns_editable_layout(project):
    pd, _ = project
    r = Collage().execute({"style": "grid", "sources": ["a.jpg", "b.jpg"], "layout_only": True})
    assert r.success and len(r.data["layout"]["layers"]) == 2


def test_registered_and_free():
    from tools.tool_registry import registry

    registry.discover()
    for n in ("image_crop", "generative_art", "collage"):
        assert registry.get(n).estimate_cost({}) == 0.0

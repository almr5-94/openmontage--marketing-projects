"""Gates: anti-AI-tells (Sard regression + a clean page), copy lint, overrides, brand_lint, face gate."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from lib import decision_log
from lib.face_gate import run_face_gate
from qa.anti_ai_tells import _pdf_stem, font_ok, lint_copy, local_codes, run_gate
from tools.graphics.page_render import find_chromium

REPO = Path(__file__).resolve().parents[2]
SARD = REPO / "qa" / "fixtures" / "sard_private_editions_v0.pdf"
sys.path.insert(0, str(REPO / "maison" / "critique"))
from brand_lint import lint, scan_text  # noqa: E402

needs_poppler = pytest.mark.skipif(not shutil.which("pdfimages"), reason="needs poppler-utils")


# ---------- anti-AI-tells ----------

@needs_poppler
def test_sard_fixture_fails_on_ap3_ap4_ap6(tmp_path):
    pdf = tmp_path / "sard.pdf"
    shutil.copy(SARD, pdf)
    r = run_gate(pdf, critics=False)
    assert not r["pass"]
    assert {"AP-3", "AP-4", "AP-6"} <= set(r["codes"]), r["codes"]
    assert any("0 raster images" in w for w in r["doc"]["AP-6"])
    assert Path(r["report"]).read_text().startswith("# Anti-AI-tells gate: FAIL")


@pytest.mark.skipif(not find_chromium() or not shutil.which("pdfimages"), reason="needs Chromium and poppler")
def test_clean_art_page_passes_automated_checks(tmp_path):
    from tools.graphics.editorial_layout import EditorialLayout

    rng = np.random.default_rng(3)
    (tmp_path / "assets").mkdir()
    for i, name in enumerate(("a", "b")):
        arr = (rng.random((3600, 2600, 3)) * 255).astype(np.uint8)
        arr[:, :, i] = 40  # two clearly different pictures
        Image.fromarray(arr).save(tmp_path / "assets" / f"{name}.jpg", quality=80)
    issue = {"title": "Clean", "trim": "a4", "pages": [
        {"type": "art_page", "image": "assets/a.jpg", "caption": "Plate I.", "credit": "Test field."},
        {"type": "pull_quote", "quote": "Iron turns green only when the fire is starved of air.", "attribution": "On celadon"},
        {"type": "art_page", "image": "assets/b.jpg"},
        {"type": "colophon", "text": "Set in Bodoni Moda Display and EB Garamond."}]}
    lay = EditorialLayout().execute({"issue": issue, "project_dir": str(tmp_path), "outputs": ["screen_pdf"], "png_dpi": 0})
    assert lay.success, lay.error
    r = run_gate(lay.data["screen_pdf"], tmp_path, html=tmp_path / "layout" / "issue.screen.html", critics=False)
    assert r["pass"], [(p["page"], p["fails"]) for p in r["per_page"] if p["fails"]] + [r["doc"]]


def test_copy_lint_en_and_ar():
    assert lint_copy("Our team will contact you within two days and prepare an offer")
    assert lint_copy("سيتواصل معك فريق سرد خلال يومين")
    assert lint_copy("Book a call today - 20% off")
    assert not lint_copy("The glaze is the colour of water under a willow")
    assert not lint_copy("لون الطلاء هو لون الماء تحت شجرة الصفصاف")


def test_font_policy():
    lib = {"bodonimodadisplay", "bodonimoda", "ebgaramond", "amiri", "ibmplexsansarabic"}
    assert font_ok("ABCDEF+BodoniModa-Display", lib)
    assert font_ok("EBGaramond-Italic", lib)
    assert not font_ok("NotoSans-Regular", lib)
    assert not font_ok("DejaVuSans-Bold", lib)


def test_override_needs_reason_and_pages(tmp_path):
    with pytest.raises(ValueError):
        decision_log.record_override(tmp_path, "AP-3", [4], "ok")
    decision_log.record_override(tmp_path, "AP-3", [4], "The reader asked for the route map on this page.")
    assert decision_log.overrides(tmp_path) == {"AP-3": {4}}
    log = decision_log.load(tmp_path)
    assert log["decisions"][0]["category"] == "anti_pattern_override" and log["decisions"][0]["user_approved"]


def test_paid_election_requires_cost_and_approval(tmp_path):
    import jsonschema

    with pytest.raises(jsonschema.ValidationError):
        decision_log.record(tmp_path, stage="assets", category="paid_election", subject="runway image",
                            options=[{"option_id": "runway", "label": "Runway", "score": 1, "reason": "x"}],
                            selected="runway", reason="needed", election_id="e-1")


# ---------- brand_lint ----------

def test_brand_lint_blocks_houses_marks_and_living_artists():
    assert scan_text("in the style of Hermès, orange box", "prompt")
    assert scan_text("a Birkin on a chair", "copy")
    assert scan_text("حقيبة من هيرمس", "copy")
    assert [f["kind"] for f in scan_text("lit like a Tim Walker photograph", "prompt")] == ["living_artist"]


def test_brand_lint_is_about_the_situation_not_the_word():
    assert not scan_text("Henry Tudor's portrait hangs in the hall", "copy")
    assert scan_text("a Tudor watch on a wrist", "copy")
    assert not scan_text("The omega of the alphabet", "copy")
    assert not scan_text("Tim Walker took the photograph", "copy")  # artists are checked in prompts only
    review = scan_text("in the style of Rembrandt", "prompt")
    assert review and review[0]["severity"] == "review"


def test_brand_lint_skips_references_and_allows_own_brand(tmp_path):
    (tmp_path / "references").mkdir()
    (tmp_path / "references" / "study.md").write_text("Notes on Hermès La Lanterne.", encoding="utf-8")
    (tmp_path / "house.yaml").write_text("name: Sard\nbrand_owner: self\n", encoding="utf-8")
    (tmp_path / "briefs").mkdir()
    (tmp_path / "briefs" / "cover.prompt.txt").write_text("A Sard brass seal, raking light", encoding="utf-8")
    assert lint([tmp_path])["pass"]
    (tmp_path / "briefs" / "bad.prompt.txt").write_text("like a Rolex ad", encoding="utf-8")
    assert not lint([tmp_path])["pass"]


# ---------- face gate (fake vision model) ----------

def _ask(answers):
    def ask(_p, q):
        for key, a in answers.items():
            if key in q:
                return a
        return "No."
    return ask


def test_face_gate_no_person_passes(tmp_path):
    img = tmp_path / "x.png"
    Image.new("RGB", (8, 8)).save(img)
    assert run_face_gate(img, "photo", _ask({"Is there a person": "No."}))["pass"]


def test_face_gate_photo_counts_eyes_and_allows_teeth(tmp_path):
    img = tmp_path / "x.png"
    Image.new("RGB", (8, 8)).save(img)
    ok = {"Is there a person": "Yes.", "How many human faces": "1", "How many human eyes": "2"}
    assert run_face_gate(img, "photo", _ask(ok))["pass"]
    one_eye = {**ok, "How many human eyes": "1", "side profile": "No."}
    r = run_face_gate(img, "photo", _ask(one_eye))
    assert not r["pass"] and "eye_count" in r["failed"]
    profile = {**one_eye, "side profile": "Yes."}
    assert run_face_gate(img, "photo", _ask(profile))["pass"]
    bad_hand = {**ok, "Is any hand deformed": "Yes."}
    assert "hands" in run_face_gate(img, "photo", _ask(bad_hand))["failed"]


def test_local_critic_denials_are_not_findings():
    # the 7B critic restates a code's definition and then denies it; that is not a finding
    denied = ("AP-1: The page does not contain any operational copy.\n"
              "AP-2: There is no thin uniform-stroke clip art.\n"
              "AP-3: Infographic drift. The page lacks any diagrams.\nAP-4: None.")
    assert local_codes(denied) == ([], [])
    firm, hedged = local_codes("AP-3: the page uses chips and a numbered step diagram.\nAP-5: the vase might repeat")
    assert firm == ["AP-3"] and hedged == ["AP-5"]


def test_claude_verdicts_are_kept_per_pdf():
    assert _pdf_stem(Path("out/social-4x5-screen.pdf")) == "social-4x5"
    assert _pdf_stem(Path("out/master-a4-print.pdf")) == "master-a4"
    assert _pdf_stem(Path("x/plain.pdf")) == "plain"


def test_colophon_credits_stock_photographer_not_alt_text(tmp_path):
    from lib import provenance
    from tools.graphics.editorial_layout import credit_lines

    img = tmp_path / "assets" / "images" / "p.jpg"
    img.parent.mkdir(parents=True)
    Image.new("RGB", (10, 10)).save(img)
    provenance.record(tmp_path, img, kind="stock", source="pexels", licence="pexels-license",
                      title="Black and white photo of hands molding clay, showcasing craftsmanship", creator="A. Das")

    class B:
        pd, images, issue = tmp_path, [str(img)], {}
    lines = credit_lines(B())
    assert lines[0] == "Photograph by A. Das - Pexels. Pexels License."
    assert not any("molding" in ln for ln in lines)


def test_face_gate_sends_the_vision_model_a_small_copy(tmp_path):
    # the vision server answers HTTP 400 to full-size print files; the cartoon check gets a <=1600 px JPEG
    from lib.face_gate import _vision_copy

    big = tmp_path / "print.png"
    Image.new("RGB", (2900, 3700), (200, 190, 170)).save(big)
    small = _vision_copy(big)
    with Image.open(small) as im:
        assert max(im.size) <= 1600 and im.format == "JPEG"
    jpg = tmp_path / "ok.jpg"
    Image.new("RGB", (800, 600)).save(jpg)
    assert _vision_copy(jpg) == jpg


def test_urgency_lint_is_about_the_call_not_the_word():
    assert lint_copy("Hurry, only 3 left!")
    assert not lint_copy("Nothing in the pictures is in a hurry.")
    assert not lint_copy("There is no hurry at low tide.")

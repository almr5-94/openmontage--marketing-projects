"""Contracts for the print studio (image-studio and magazine pipelines).

Every stage skill a print manifest names must exist, every artifact a stage
produces must have a schema, and a minimal run must checkpoint stage by stage
with schema-valid artifacts.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from lib.checkpoint import get_pipeline_stages, validate_checkpoint
from schemas.artifacts import ARTIFACT_NAMES, validate_artifact

REPO = Path(__file__).resolve().parents[2]
PRINT_PIPELINES = ["image-studio", "magazine"]


def _manifest(name: str) -> dict:
    return yaml.safe_load((REPO / "pipeline_defs" / f"{name}.yaml").read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", PRINT_PIPELINES)
def test_every_named_skill_exists(name):
    m = _manifest(name)
    skills = set(m["required_skills"]) | {s["skill"] for s in m["stages"] if s.get("skill")}
    skills.add(m["orchestration"]["skill"])
    missing = [s for s in skills if not (REPO / "skills" / f"{s}.md").exists()]
    assert not missing, missing


@pytest.mark.parametrize("name", PRINT_PIPELINES)
def test_every_produced_artifact_has_a_schema(name):
    for stage in _manifest(name)["stages"]:
        for art in stage.get("produces", []):
            assert art in ARTIFACT_NAMES, f"{name}.{stage['name']} produces unknown artifact {art}"


@pytest.mark.parametrize("name", PRINT_PIPELINES)
def test_tools_named_in_manifest_exist(name):
    from tools.tool_registry import registry

    registry.discover()
    for stage in _manifest(name)["stages"]:
        for tool in stage.get("tools_available", []):
            assert registry.get(tool) is not None, f"{name}.{stage['name']}: unknown tool {tool}"


@pytest.mark.parametrize("name", PRINT_PIPELINES)
def test_print_stages_avoid_video_canonical_names(name):
    """Canonical video stage names (compose, scene_plan, edit ...) force a video
    artifact (render_report, edit_decisions) on completion; print stages must
    not reuse them except for the generic ones."""
    allowed_canonical = {"assets", "publish"}
    video_only = {"research", "proposal", "idea", "script", "scene_plan", "edit", "compose"}
    stages = set(get_pipeline_stages(name))
    assert not (stages & video_only), stages & video_only
    assert allowed_canonical <= stages


def test_print_meta_skill_mentions_latin_digit_rule():
    text = (REPO / "skills/meta/print-production.md").read_text(encoding="utf-8")
    assert "Latin digits" in text and "ar-KW-u-nu-latn" in text


# ---------- minimal artifacts validate ----------

BRIEF = {
    "version": "1.0", "kind": "magazine", "title": "Issue 01", "purpose": "Explain the studio",
    "audience": "small business owners",
    "formats": [{"name": "magazine_standard", "width_mm": 230, "height_mm": 300}],
    "languages": [{"code": "en", "direction": "ltr"}, {"code": "ar", "direction": "rtl"}],
    "tone": "warm", "page_count": 8, "success_criteria": ["reads in 10 minutes"],
}
PROPOSAL = {
    "version": "1.0",
    "concept_options": [
        {"id": "a", "title": "Editorial", "visual_approach": "photo", "typography": "serif", "palette": ["#111"], "why_this_works": "x"},
        {"id": "b", "title": "Graphic", "visual_approach": "flat", "typography": "sans", "palette": ["#f60"], "why_this_works": "y"},
    ],
    "selected_concept": {"concept_id": "a", "rationale": "fits"},
    "tool_plan": [{"capability": "layout_render", "tool": "page_render", "reason": "free"}],
    "cost_estimate": {"total_estimated_usd": 0, "line_items": [{"item": "render", "tool": "page_render", "quantity": 1, "unit_usd": 0}]},
    "approval": {"status": "approved"},
}
COPY = {"version": "1.0", "pieces": [{"id": "feat", "type": "feature", "headline": "H", "body": "B", "word_count": 1, "language": "en"}]}
LAYOUT = {
    "version": "1.0", "units": "pages", "template": "print-studio/templates/magazine/issue.html",
    "frames": [{"id": "p01", "role": "cover", "format": "magazine_standard", "elements": [{"type": "image", "slot": "hero", "min_px": [2716, 3543]}]}],
}
RENDER = {"version": "1.0", "source_html": ["layout/issue.html"], "outputs": [{"path": "renders/i.pdf", "format": "pdf", "pages": 8, "checks_pass": True}]}
_check = {"status": "pass", "notes": "ok"}
REVIEW = {
    "version": "1.0", "status": "pass", "frames_viewed": ["p01"],
    "checks": {k: _check for k in ("technical", "text_fit", "image_quality", "typography", "language_and_digits", "brief_promise")},
}


@pytest.mark.parametrize(
    "name,data",
    [("print_brief", BRIEF), ("studio_proposal", PROPOSAL), ("editorial_copy", COPY),
     ("layout_plan", LAYOUT), ("print_render", RENDER), ("print_review", REVIEW)],
)
def test_minimal_artifacts_validate(name, data):
    validate_artifact(name, data)


def test_review_without_viewed_frames_is_rejected():
    import jsonschema

    bad = dict(REVIEW, frames_viewed=[])
    with pytest.raises(jsonschema.ValidationError):
        validate_artifact("print_review", bad)


def test_proposal_needs_two_concepts():
    import jsonschema

    bad = dict(PROPOSAL, concept_options=PROPOSAL["concept_options"][:1])
    with pytest.raises(jsonschema.ValidationError):
        validate_artifact("studio_proposal", bad)


def test_magazine_checkpoints_walk_the_stages(tmp_path):
    """A magazine run can write a valid checkpoint for each stage in order."""
    from lib.checkpoint import write_checkpoint

    produced = {
        "brief": {"print_brief": BRIEF},
        "concept": {"studio_proposal": PROPOSAL},
        "editorial": {"editorial_copy": COPY},
        "layout": {"layout_plan": LAYOUT},
        "assets": {"asset_manifest": {"version": "1.0", "assets": [{"id": "a1", "type": "image", "path": "assets/images/p01.png", "source_tool": "pexels_image", "scene_id": "p01"}]}},
        "render": {"print_render": RENDER},
        "review": {"print_review": REVIEW},
        "publish": {"publish_log": {"version": "1.0", "entries": [{"platform": "print", "status": "exported", "timestamp": "2026-11-19T10:00:00Z"}]}},
    }
    assert list(produced) == get_pipeline_stages("magazine")
    for stage, arts in produced.items():
        validate_checkpoint({
            "version": "1.0", "project_id": "mag-test", "pipeline_type": "magazine", "stage": stage,
            "status": "completed", "timestamp": "2026-11-19T10:00:00Z", "artifacts": arts,
        })
        write_checkpoint(
            tmp_path, "mag-test", stage, "completed", arts, pipeline_type="magazine",
            human_approval_required=True, human_approved=True,
        )

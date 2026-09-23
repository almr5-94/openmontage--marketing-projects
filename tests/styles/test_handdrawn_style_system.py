"""The hand-drawn style system must stay three separate systems.

The forensic study's central finding is that the three reference videos are three
contradictory illustration families, and that merging them is what produces
almost-right output. These tests hold the parts of that contract a file can break:
one trigger per family, no cross-family vocabulary, no source-channel name anywhere
in the pipeline, and no reference imagery in a public repository.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

from styles.playbook_loader import load_playbook, validate_accessibility

ROOT = Path(__file__).resolve().parents[2]
STYLE = ROOT / "assets" / "style" / "handdrawn"
FAMILIES = {"A": ("a", "hdx_paperfolk", "handdrawn-paperfolk"),
            "B": ("b", "hdx_incise", "handdrawn-incise"),
            "C": ("c", "hdx_biotext", "handdrawn-biotext")}

# the source recordings belong to a third party; their name must not reach a
# trigger, caption, prompt, playbook or filename
BRAND = re.compile(r"\bted[\s\-_]?ed\b|\bted\b", re.I)

LEXICON = json.loads((STYLE / "lexicon.json").read_text(encoding="utf-8"))
CAPTIONING = yaml.safe_load((STYLE / "captioning.yaml").read_text(encoding="utf-8"))


@pytest.mark.parametrize("family,spec", sorted(FAMILIES.items()))
def test_playbook_loads_and_is_accessible(family: str, spec: tuple) -> None:
    playbook = load_playbook(spec[2])
    assert playbook["identity"]["name"]
    report = validate_accessibility(playbook)
    assert report["pass"], [i["message"] for i in report["issues"] if i["severity"] == "error"]


@pytest.mark.parametrize("family,spec", sorted(FAMILIES.items()))
def test_playbook_carries_only_its_own_trigger(family: str, spec: tuple) -> None:
    text = (ROOT / "styles" / f"{spec[2]}.yaml").read_text(encoding="utf-8")
    assert spec[1] in text, f"{spec[2]} does not name its own trigger"
    for other, other_spec in FAMILIES.items():
        if other != family:
            assert other_spec[1] not in text, f"{spec[2]} mentions {other}'s trigger"


@pytest.mark.parametrize("family,spec", sorted(FAMILIES.items()))
def test_construction_spec_matches_family(family: str, spec: tuple) -> None:
    data = yaml.safe_load((STYLE / "construction" / f"{spec[0]}.yaml").read_text(encoding="utf-8"))
    assert data["family"]["trigger"] == spec[1]
    assert data["family"]["key"].upper() == family


def test_lexicon_phrases_are_scoped() -> None:
    assert len(LEXICON["phrases"]) == 80, "the study defines 80 scoped phrases"
    for entry in LEXICON["phrases"]:
        assert entry["family"] in FAMILIES
        assert entry["use_condition"].strip(), f"{entry['phrase']} has no use condition"
    banned = {t["term"] if isinstance(t, dict) else t for t in LEXICON["banned_terms"]}
    lowered = " ".join(e["phrase"].lower() for e in LEXICON["phrases"])
    for term in banned:
        assert str(term).lower() not in lowered, f"banned term {term} appears in a phrase"


def test_captioning_keeps_the_families_apart() -> None:
    for family, spec in FAMILIES.items():
        block = CAPTIONING["families"][family]
        assert block["trigger"] == spec[1]
        for key in ("boilerplate", "environment_only_boilerplate", "negative_extension"):
            text = block[key]
            assert spec[1] in text or key == "negative_extension"
            for other, other_spec in FAMILIES.items():
                if other != family:
                    assert other_spec[1] not in text, f"{family}.{key} mentions {other}'s trigger"


def test_universal_negative_bans_only_capture_failures() -> None:
    negative = CAPTIONING["universal_negative"].lower()
    # the study is explicit: these are valid traits of at least one family and
    # must never be suppressed for everyone
    for keep in ("gradient", "saturated", "nostril", "black", "detailed iris"):
        assert keep not in negative, f"universal negative must not ban '{keep}'"
    for artefact in ("progress bar", "browser chrome", "cursor"):
        assert artefact in negative


@pytest.mark.parametrize("path", sorted(
    list(STYLE.rglob("*.json")) + list(STYLE.rglob("*.yaml")) + list(STYLE.rglob("*.md"))
    + list((ROOT / "styles").glob("handdrawn-*.yaml"))))
def test_no_source_channel_name_in_the_pipeline(path: Path) -> None:
    hits = [line for line in path.read_text(encoding="utf-8").splitlines() if BRAND.search(line)]
    assert not hits, f"{path.name} names the source channel: {hits[:2]}"


def test_no_reference_frames_are_tracked_in_git() -> None:
    import subprocess
    out = subprocess.run(["git", "ls-files", "assets/references"], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout.split()
    images = [f for f in out if f.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".mov", ".mp4"))]
    assert not images, f"reference imagery must not be committed: {images[:3]}"

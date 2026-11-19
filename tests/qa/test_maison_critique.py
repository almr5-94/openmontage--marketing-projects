"""Maison critique gate: lowest critic wins, below 4 is sent back, Claude is required unless offline."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from maison.critique import critique as cq
from schemas.artifacts import validate_artifact

HOUSE = Path(__file__).resolve().parents[2] / "maison/houses/maison-example/house.yaml"


def _scores(v: int) -> dict:
    return {c: {"score": v, "evidence": f"page 2 shows this at level {v}", "send_back_to": cq.SEND_BACK[c]}
            for c in cq.CRITERIA}


def test_merge_lowest_wins_and_sends_back():
    claude = {"critic": "claude", "model": "x", "scores": _scores(5)}
    local = {"critic": "local", "model": "y", "scores": {**_scores(5), "craft": {"score": 3, "evidence": "clip-art on page 4",
                                                                                 "send_back_to": "assets"}}}
    res = cq.merge("t.pdf", [claude, local], offline=False, has_arabic_edition=True)
    validate_artifact("maison_critique", res)
    assert res["pass"] is False
    assert [(s["criterion"], s["stage"]) for s in res["send_backs"]] == [("craft", "assets")]


def test_merge_needs_claude_unless_offline():
    local = {"critic": "local", "model": "y", "scores": _scores(5)}
    assert cq.merge("t", [dict(local)], offline=False, has_arabic_edition=True)["pass"] is False
    assert cq.merge("t", [dict(local)], offline=True, has_arabic_edition=True)["pass"] is True


def test_merge_arabic_not_applicable():
    s = _scores(4)
    s["arabic_edition"] = {"not_applicable": "English-only target"}
    res = cq.merge("t", [{"critic": "claude", "model": "x", "scores": s}], offline=False, has_arabic_edition=False)
    assert res["pass"] is True


def test_run_critique_with_fake_local_models(tmp_path, monkeypatch):
    pngs = []
    for i in range(2):
        p = tmp_path / f"p{i}.png"
        Image.new("RGB", (420, 594), (240, 236, 228)).save(p)
        pngs.append(p)
    monkeypatch.setattr(cq.lm, "see", lambda img, q, **k: "no" if "yes or no" in q else "4")
    monkeypatch.setattr(cq.lm, "chat", lambda prompt, **k: "SCORE: 4 | EVIDENCE: 'the brass is turned by hand'")
    monkeypatch.setattr(cq.lm, "detect", lambda: {"vision": "v", "planner": "p"})
    monkeypatch.setattr(cq, "pdf_text", lambda pdf: ("Water, by hand", "ماء"))
    res = cq.run_critique(tmp_path, tmp_path / "x.pdf", HOUSE, claude_scores={"model": "c", "scores": _scores(5)},
                          pngs=pngs)
    assert res["pass"] is True, res["send_backs"]
    out = json.loads((tmp_path / "qa/maison_critique.json").read_text())
    assert {c["critic"] for c in out["critics"]} == {"claude", "local"}
    assert (tmp_path / "qa/maison_critique.md").read_text().startswith("# Maison critique: PASS")


def test_local_questions_only_where_they_apply(tmp_path, monkeypatch):
    # a text-free single-page ad: no typography to judge, and one page is not a set
    p = tmp_path / "p0.png"
    Image.new("RGB", (420, 594), (240, 236, 228)).save(p)
    asked = []
    monkeypatch.setattr(cq.lm, "see", lambda img, q, **k: asked.append(q) or ("no" if "yes or no" in q else "4"))
    monkeypatch.setattr(cq.lm, "chat", lambda prompt, **k: "SCORE: 4 | EVIDENCE: 'x'")
    sc = cq.local_scores([p], {}, "", "", tmp_path, kinds=[{"image": True, "text": False}])
    assert "not_applicable" in sc["typography"]
    assert "not_applicable" in sc["cohesion"] and "not_applicable" in sc["archive_dialogue"]
    assert sc["craft"]["score"] == 4 and sc["one_idea"]["score"] == 4
    assert not any("typography" in q.lower() for q in asked)
    # a colophon page with text and no picture is not scored for imagery
    sc2 = cq.local_scores([p, p], {}, "", "", tmp_path,
                          kinds=[{"image": True, "text": True}, {"image": False, "text": True}])
    assert "pages [1]" in sc2["craft"]["evidence"]

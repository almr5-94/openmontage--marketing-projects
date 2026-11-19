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

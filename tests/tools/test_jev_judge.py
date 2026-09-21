"""JevJudge: shape and gating logic, with a fake TypeSafe client (no network)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

pytest.importorskip("typesafe_sdk")

from tools.analysis.jev_judge import SCRIPT_RISKS, JevJudge


class FakeClient:
    def __init__(self, answer_fn):
        self.answer_fn = answer_fn
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def system_one(self, state, questions):
        self.calls.append((state, questions))
        answers = {name: self.answer_fn(name, state) for name in questions}
        return SimpleNamespace(model="jev-test", answers=answers,
                               usage=SimpleNamespace(input_tokens=10, output_tokens=2))


def make_tool(answer_fn):
    tool = JevJudge()
    client = FakeClient(answer_fn)
    tool.client_factory = lambda: client
    return tool, client


def test_script_check_flags_only_risky_lines():
    def answer(name, state):
        risky = "guarantee" in state["line"] and name == "promises_outcome"
        return SimpleNamespace(noul=0.95 if risky else 0.05)

    tool, client = make_tool(answer)
    result = tool.execute({"operation": "script_check",
                           "lines": ["Meet Law Triage.", "We guarantee you win.", "  "]})
    assert result.success
    assert result.data["flagged_indices"] == [1]
    assert result.data["lines"][1]["flags"] == ["promises_outcome"]
    assert result.data["passed"] is False
    assert len(client.calls) == 2  # blank line skipped
    assert set(client.calls[0][1]) == set(SCRIPT_RISKS)
    assert result.data["usage"] == {"input_tokens": 20, "output_tokens": 4}


def test_rank_assets_sorts_by_relevance():
    scores = {"c0": 0.5, "c1": 3.0, "c2": 1.5}
    tool, _ = make_tool(lambda name, state: SimpleNamespace(score=scores[name], confidence=0.9))
    result = tool.execute({"operation": "rank_assets", "scene": "lawyer at desk",
                           "candidates": [{"id": "a", "description": "beach"},
                                          {"id": "b", "description": "lawyer at desk"},
                                          {"id": "c", "description": "office"}]})
    assert result.success
    assert [r["id"] for r in result.data["ranked"]] == ["b", "c", "a"]
    assert result.data["best_id"] == "b"
    assert result.data["ranked"][0]["relevance"] == 1.0


def test_route_brief_returns_choice():
    tool, client = make_tool(lambda name, state: SimpleNamespace(
        choice="talking-head", confidence=0.8,
        probabilities={"talking-head": 0.8, "avatar-spokesperson": 0.15, "cinematic": 0.05}))
    result = tool.execute({"operation": "route_brief", "brief": "edit my webcam recording"})
    assert result.success
    assert result.data["pipeline"] == "talking-head"
    criteria = client.calls[0][1]["pipeline"].criteria
    assert "framework-smoke" not in criteria and "talking-head" in criteria


def test_bad_inputs_fail_cleanly():
    tool, _ = make_tool(lambda *a: None)
    assert not tool.execute({"operation": "nope"}).success
    assert not tool.execute({"operation": "script_check", "lines": []}).success
    assert not tool.execute({"operation": "rank_assets", "scene": "x"}).success

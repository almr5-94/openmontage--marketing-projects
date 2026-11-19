"""Studio API: one source of truth for the MCP server and the om CLI."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from PIL import Image
from typer.testing import CliRunner

from lib import decision_log, election
from lib import studio_api as api


@pytest.fixture()
def projects(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path))
    return tmp_path


def _image(pd: Path) -> str:
    p = pd / "assets" / "images" / "src.png"
    p.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (800, 600), (120, 90, 60)).save(p)
    return str(p)


def _shape(entry: dict) -> dict:
    """Everything but who/when/which id: what must match between the MCP and the CLI."""
    return {k: v for k, v in entry.items() if k not in ("decision_id", "actor", "recorded_at")}


def test_cli_and_mcp_stage_runs_log_identical_structure(projects):
    from cli.om import app
    from mcp_server.openmontage_mcp import mcp

    api.init_project("par-mcp", "editorial-magazine", "Parity")
    api.init_project("par-cli", "editorial-magazine", "Parity")
    out = {}
    for pid in ("par-mcp", "par-cli"):
        out[pid] = {"operation": "smart_crop", "input_path": _image(projects / pid), "target": "300x300",
                    "output_path": str(projects / pid / "assets" / "fragments" / "f.png")}
    asyncio.run(mcp.call_tool("run_stage", {"project_id": "par-mcp", "stage": "fragments", "tool": "image_crop",
                                            "inputs": out["par-mcp"], "reason": "crop one fragment"}))
    r = CliRunner().invoke(app, ["stage", "par-cli", "fragments", "--tool", "image_crop",
                                 "--inputs", json.dumps(out["par-cli"]), "--reason", "crop one fragment"])
    assert r.exit_code == 0, r.output
    a = decision_log.load(projects / "par-mcp")["decisions"][-1]
    b = decision_log.load(projects / "par-cli")["decisions"][-1]
    assert (a["actor"], b["actor"]) == ("claude", "human")
    assert _shape(a) == _shape(b)
    assert set(a) == set(b)
    assert (projects / "par-mcp/assets/fragments/f.png").exists() and (projects / "par-cli/assets/fragments/f.png").exists()


def test_paid_tool_needs_an_approved_election(projects, monkeypatch):
    api.init_project("paid", "editorial-magazine", "Paid")
    pd = projects / "paid"
    from tools.graphics.image_crop import ImageCrop

    monkeypatch.setattr(ImageCrop, "estimate_cost", lambda self, i: 0.08)
    inp = {"operation": "smart_crop", "input_path": _image(pd), "target": "100x100"}
    with pytest.raises(election.ElectionRequired):
        api.run_stage("paid", "fragments", tool="image_crop", inputs=inp)
    with pytest.raises(election.ElectionRequired):
        api.run_stage("paid", "fragments", tool="image_crop", inputs=inp, election_id="el-made-up")
    d = api.record_election("paid", stage="fragments", subject="test", reason="the human said yes in the test")
    assert d["cost"] == {"amount": 8.0, "unit": "credits", "provider": "runway_mcp"}
    r = api.run_stage("paid", "fragments", tool="image_crop", inputs=inp, election_id=d["election_id"])
    assert r["result"]["success"] and r["decision"]["election_id"] == d["election_id"]


def test_tool_outside_the_stage_is_refused(projects):
    api.init_project("scope", "editorial-magazine", "Scope")
    with pytest.raises(api.StudioError):
        api.run_stage("scope", "feeling_brief", tool="collage", inputs={})


def test_prepare_runway_call_quotes_and_lints(projects):
    api.init_project("rw", "maison-campaign", "Runway")
    q = api.prepare_runway_call("rw", stage="assets", prompt="a brass compass on raw linen, raking window light",
                                count=2)
    assert q["quote"]["credits"] == 16 and q["status"] == "awaiting_election"
    assert not [d for d in decision_log.load(projects / "rw")["decisions"] if d["category"] == "paid_election"]
    with pytest.raises(api.StudioError):
        api.prepare_runway_call("rw", stage="assets", prompt="a handbag in the style of Hermes")


def test_maison_project_and_export_gate(projects):
    r = api.maison_new("issue", "mx", "maison-example", "Water")
    assert r["pipeline"] == "maison-issue" and Path(r["house_snapshot"]).exists()
    st = api.get_project_status("mx")
    assert st["house"] == "maison-example" and st["next_stage"] == "house_brief"
    with pytest.raises(api.StudioError, match="quality_gate"):
        api.maison_export("mx")
    with pytest.raises(api.StudioError, match="not a Maison project"):
        api.init_project("plain", "editorial-magazine", "Plain")
        api.maison_critique("plain")


def test_capabilities_list_every_new_family():
    caps = api.list_capabilities()
    assert all(caps["new_families"].values())
    for p in ("editorial-magazine", "maison-issue", "maison-drawing-series", "maison-campaign"):
        assert p in caps["pipelines"]

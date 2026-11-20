"""OpenMontage studio MCP server (official MCP Python SDK, stdio).

Every tool is a one-line call into ``lib/studio_api.py`` -- the same functions the ``om`` CLI
calls -- so Claude Desktop, Claude Code and the terminal produce identical files and
decision-log entries. Paid actions need an ``election_id`` from ``record_election``; images and
video are generated only on the Runway MCP connector (``prepare_runway_call`` quotes it).

Run:  python -m mcp_server.openmontage_mcp      (stdio)
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from mcp.server.mcpserver import MCPServer  # noqa: E402
from mcp.types import ToolAnnotations  # noqa: E402

from lib import studio_api as api  # noqa: E402

ACTOR = "claude"
RO = ToolAnnotations(readOnlyHint=True)

mcp = MCPServer(
    name="openmontage",
    instructions=(
        "OpenMontage print studio: editorial magazines, Maison issues, drawing series and campaigns. "
        "Read AGENT_GUIDE.md first. Free sources first; images and video are generated ONLY through the "
        "Runway MCP connector after the human elects the call (prepare_runway_call -> ask -> record_election). "
        "Every gate is blocking: qa_anti_ai_tells, run_face_gate, maison_critique, brand_lint."),
)


@mcp.tool(annotations=RO)
def list_capabilities(families_only: bool = False) -> dict[str, Any]:
    """Tool families with status, and every pipeline (read-only)."""
    return api.list_capabilities(families_only)


@mcp.tool()
def init_project(project_id: str, pipeline: str, title: str) -> dict[str, Any]:
    """Create projects/<project_id> for a pipeline and log the pipeline choice."""
    return api.init_project(project_id, pipeline, title, actor=ACTOR)


@mcp.tool()
def run_stage(project_id: str, stage: str, tool: Optional[str] = None, inputs: Optional[dict[str, Any]] = None,
              artifacts: Optional[dict[str, Any]] = None, status: str = "completed", reason: str = "",
              election_id: Optional[str] = None, human_approved: bool = False) -> dict[str, Any]:
    """Run one stage step: execute one of the stage's tools and/or write its checkpoint artifacts.
    A tool with a cost needs election_id."""
    return api.run_stage(project_id, stage, tool=tool, inputs=inputs, artifacts=artifacts, status=status,
                         reason=reason, actor=ACTOR, election_id=election_id, human_approved=human_approved)


@mcp.tool(annotations=RO)
def get_project_status(project_id: str) -> dict[str, Any]:
    """Stages done, next stage, gate results (read-only)."""
    return api.get_project_status(project_id)


@mcp.tool(annotations=RO)
def list_assets(project_id: str) -> dict[str, Any]:
    """Every image in the project with its provenance (read-only)."""
    return api.list_assets(project_id)


@mcp.tool(annotations=RO)
def get_decision_log(project_id: str) -> dict[str, Any]:
    """The project's decision log (read-only)."""
    return api.get_decision_log(project_id)


@mcp.tool()
def prepare_runway_call(project_id: str, stage: str, prompt: str, model: str = "gen4_image", count: int = 1,
                        ratio: str = "1080:1350", resolution: str = "1080p") -> dict[str, Any]:
    """Quote a Runway generation (credits and dollars) and lint the prompt. Spends nothing.
    Show `ask_human` to the human; only after a yes call record_election, then the Runway MCP."""
    return api.prepare_runway_call(project_id, stage=stage, prompt=prompt, model=model, count=count, ratio=ratio,
                                   resolution=resolution)


@mcp.tool()
def record_election(project_id: str, stage: str, subject: str, reason: str, model: str = "gen4_image",
                    count: int = 1, resolution: str = "1080p") -> dict[str, Any]:
    """Record the HUMAN's explicit yes to a paid call; returns the election_id. Never call it on your own."""
    return api.record_election(project_id, stage=stage, subject=subject, model=model, count=count,
                               resolution=resolution, reason=reason, actor="human")


@mcp.tool()
def search_free_images(project_id: str, query: str, source: str = "pexels", count: int = 5) -> dict[str, Any]:
    """Search and download from Pexels or Pixabay (free)."""
    return api.search_free_images(project_id, query, source, count)


@mcp.tool()
def run_face_gate(image: str, mode: str = "auto") -> dict[str, Any]:
    """Check one image that may show a person (mode: auto, photo, cartoon). Local vision model."""
    return api.run_face_gate(image, mode)


@mcp.tool()
def export_pdf(project_id: str, issue: dict[str, Any], name: str = "issue",
               outputs: Optional[list[str]] = None) -> dict[str, Any]:
    """Lay out and render an issue JSON: print PDF (bleed, crop marks), screen PDF, page PNGs, proofs."""
    return api.export_pdf(project_id, issue, name, outputs)


@mcp.tool()
def qa_anti_ai_tells(project_id: str, pdf: Optional[str] = None, offline: bool = False,
                     vision: bool = True) -> dict[str, Any]:
    """The anti-AI-tells gate (AP-1..AP-7) on the latest screen PDF; writes qa/anti_ai_tells.md."""
    return api.qa_anti_ai_tells(project_id, pdf, vision=vision, offline=offline)


@mcp.tool(annotations=RO)
def maison_list_houses() -> list[dict[str, Any]]:
    """Every house file in maison/houses (read-only)."""
    return api.maison_list_houses()


@mcp.tool()
def maison_new_house(house_id: str, name: str, brand_owner: str = "invented",
                     languages: Optional[list[str]] = None) -> dict[str, Any]:
    """Start a house file (brand_owner: self, client or invented) and brand_lint it."""
    return api.maison_new_house(house_id, name, brand_owner=brand_owner, languages=languages)


@mcp.tool()
def maison_new_issue(project_id: str, house: str, theme: str, title: Optional[str] = None) -> dict[str, Any]:
    """Start a maison-issue project."""
    return api.maison_new("issue", project_id, house, theme, title, actor=ACTOR)


@mcp.tool()
def maison_new_series(project_id: str, house: str, theme: str, title: Optional[str] = None) -> dict[str, Any]:
    """Start a maison-drawing-series project."""
    return api.maison_new("series", project_id, house, theme, title, actor=ACTOR)


@mcp.tool()
def maison_new_campaign(project_id: str, house: str, theme: str, title: Optional[str] = None) -> dict[str, Any]:
    """Start a maison-campaign project."""
    return api.maison_new("campaign", project_id, house, theme, title, actor=ACTOR)


@mcp.tool()
def maison_run_stage(project_id: str, stage: str, tool: Optional[str] = None, inputs: Optional[dict[str, Any]] = None,
                     artifacts: Optional[dict[str, Any]] = None, status: str = "completed", reason: str = "",
                     election_id: Optional[str] = None, human_approved: bool = False) -> dict[str, Any]:
    """run_stage for a Maison project."""
    return api.maison_run_stage(project_id, stage, tool=tool, inputs=inputs, artifacts=artifacts, status=status,
                                reason=reason, actor=ACTOR, election_id=election_id, human_approved=human_approved)


@mcp.tool()
def maison_critique(project_id: str, claude_scores: Optional[dict[str, Any]] = None, offline: bool = False) -> dict[str, Any]:
    """The Maison critique gate: your rubric scores plus the local models'; lower wins; <4 is sent back."""
    return api.maison_critique(project_id, claude_scores=claude_scores, offline=offline)


@mcp.tool()
def approve_critique(project_id: str, criterion: str, reason: str, critic: str = "local",
                     pdf: Optional[str] = None) -> dict[str, Any]:
    """Record the HUMAN's approval over one critic's low score, for the exact PDF last critiqued.
    Never call it on your own: pass the human's own words as reason. Then re-run maison_critique."""
    return api.approve_critique(project_id, criterion=criterion, critic=critic, reason=reason, pdf=pdf,
                                actor="human")


@mcp.tool()
def maison_quality_gate(project_id: str) -> dict[str, Any]:
    """Assemble qa/quality_gate.json from anti-AI-tells, face gate, provenance, brand_lint and the critique."""
    return api.quality_gate(project_id)


@mcp.tool()
def maison_export(project_id: str) -> dict[str, Any]:
    """Final print + screen PDFs, PNGs and paper proof; refuses unless quality_gate passes."""
    return api.maison_export(project_id)


def main() -> None:
    mcp.run("stdio")


if __name__ == "__main__":
    main()

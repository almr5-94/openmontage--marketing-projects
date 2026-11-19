"""Elections: a paid action runs only with an election ID the human approved.

Flow (identical for the MCP server, the ``om`` CLI and the agent):
  1. ``quote_runway(model, count, resolution)`` -> credits and dollars, shown to the human.
  2. The human elects it -> ``record_election(...)`` writes a ``paid_election`` decision
     (user_approved=True, cost, election_id) to the project's decision log.
  3. Before the paid call, ``require(project_dir, election_id)`` checks the log; no election, no call.
Free actions (CC0 museums, Pexels, Pixabay, seeded drawing, local layout) need no election.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Optional

import yaml

from lib import decision_log

COSTS = Path(__file__).resolve().parents[1] / "config" / "runway_costs.yaml"


class ElectionRequired(PermissionError):
    """Raised when a paid action is attempted without an approved election."""


def quote_runway(model: str = "gen4_image", count: int = 1, resolution: str = "1080p",
                 seconds: float = 0) -> dict[str, Any]:
    table = yaml.safe_load(COSTS.read_text(encoding="utf-8"))
    if model in table["image"]:
        per = table["image"][model]
        credits_each = per.get(resolution, per.get("any"))
        if credits_each is None:
            raise ValueError(f"{model} has no price for {resolution}: {sorted(per)}")
        credits = credits_each * count
    elif model in table["video_per_second"]:
        credits_each = table["video_per_second"][model] * seconds
        credits = credits_each * count
    else:
        raise ValueError(f"unknown Runway model {model!r}; known: {sorted(table['image']) + sorted(table['video_per_second'])}")
    return {"provider": "runway_mcp", "model": model, "count": count, "resolution": resolution,
            "credits_each": credits_each, "credits": credits, "usd": round(credits * table["credit_usd"], 2),
            "source": str(COSTS.relative_to(COSTS.parents[1]))}


def record_election(project_dir: str | Path, *, stage: str, subject: str, quote: dict[str, Any],
                    reason: str, actor: str = "human", options: Optional[list[dict[str, Any]]] = None) -> dict[str, Any]:
    """The human said yes to this paid call (with this cost). Returns the decision with its election_id."""
    eid = "el-" + uuid.uuid4().hex[:10]
    opts = options or [
        {"option_id": "pay", "label": f"{quote['model']} x{quote['count']} via Runway MCP", "score": 1,
         "reason": f"{quote['credits']} credits (~${quote['usd']})"},
        {"option_id": "free", "label": "free route (museums, Pexels, Pixabay, seeded drawing)", "score": 0,
         "reason": "no cost"}]
    return decision_log.record(project_dir, stage=stage, category="paid_election", subject=subject, options=opts,
                               selected="pay", reason=reason, actor=actor, user_approved=True, election_id=eid,
                               cost={"amount": float(quote["credits"]), "unit": "credits", "provider": quote["provider"]})


def require(project_dir: str | Path, election_id: Optional[str]) -> dict[str, Any]:
    """Return the approved election or raise ElectionRequired."""
    if not election_id:
        raise ElectionRequired("this action costs credits: quote it, let the human elect it, then pass election_id")
    for d in decision_log.load(project_dir)["decisions"]:
        if d.get("category") == "paid_election" and d.get("election_id") == election_id and d.get("user_approved"):
            return d
    raise ElectionRequired(f"no approved election {election_id!r} in {decision_log.path(project_dir)}")

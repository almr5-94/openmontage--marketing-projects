"""Append-only project decision log (projects/<id>/decision_log.json), schema-validated.

The same file lib/checkpoint.py merges stage decisions into. The MCP server, the `om` CLI and
the agent flow all record through ``record`` so their logs have an identical structure — only
the ``actor`` field says who drove the decision (claude, human, local_model).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from schemas.artifacts import validate_artifact


def path(project_dir: str | Path) -> Path:
    return Path(project_dir) / "decision_log.json"


def load(project_dir: str | Path) -> dict[str, Any]:
    p = path(project_dir)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"version": "1.0", "project_id": Path(project_dir).name, "decisions": []}


def next_id(log: dict[str, Any], prefix: str = "d") -> str:
    n = sum(1 for d in log["decisions"] if d["decision_id"].startswith(prefix + "-")) + 1
    return f"{prefix}-{n:03d}"


def record(project_dir: str | Path, *, stage: str, category: str, subject: str,
           options: list[dict[str, Any]], selected: str, reason: str, actor: str = "claude",
           user_approved: bool = False, decision_id: Optional[str] = None, **extra: Any) -> dict[str, Any]:
    """Validate and append one decision. Raises jsonschema.ValidationError on a bad entry."""
    log = load(project_dir)
    entry: dict[str, Any] = {
        "decision_id": decision_id or next_id(log),
        "stage": stage, "category": category, "subject": subject,
        "options_considered": options, "selected": selected, "reason": reason,
        "user_visible": True, "user_approved": bool(user_approved), "actor": actor,
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    entry.update({k: v for k, v in extra.items() if v is not None})
    candidate = {**log, "decisions": log["decisions"] + [entry]}
    validate_artifact("decision_log", candidate)
    path(project_dir).parent.mkdir(parents=True, exist_ok=True)
    path(project_dir).write_text(json.dumps(candidate, indent=2, ensure_ascii=False), encoding="utf-8")
    return entry


def overrides(project_dir: str | Path) -> dict[str, set[int]]:
    """{"AP-3": {4, 5}, ...}: pages where the user elected a prohibited pattern."""
    out: dict[str, set[int]] = {}
    for d in load(project_dir)["decisions"]:
        if d.get("category") == "anti_pattern_override" and d.get("user_approved"):
            out.setdefault(d["anti_pattern"], set()).update(d.get("pages", []))
    return out


def record_override(project_dir: str | Path, anti_pattern: str, pages: list[int], reason: str,
                    actor: str = "human") -> dict[str, Any]:
    """Log a user's explicit election of a prohibited pattern for specific pages.

    A general "go ahead" never counts: the caller must pass the user's own reason and the pages.
    """
    if not reason or len(reason.strip()) < 8:
        raise ValueError("an anti-pattern override needs the user's own reason")
    return record(project_dir, stage="qa", category="anti_pattern_override",
                  subject=f"{anti_pattern} on page(s) {', '.join(map(str, pages))}",
                  options=[{"option_id": "keep", "label": "keep the pattern (user elected)", "score": 1, "reason": reason},
                           {"option_id": "fix", "label": "fix the page", "score": 0, "reason": "default"}],
                  selected="keep", reason=reason, actor=actor, user_approved=True,
                  anti_pattern=anti_pattern, pages=pages)


def record_critique_override(project_dir: str | Path, *, criterion: str, critic: str, score: int,
                             pdf_sha256: str, reason: str, actor: str = "human") -> dict[str, Any]:
    """Log the human's approval of one critic's low score on one criterion, for one exact PDF.

    It covers only that critic, that criterion, scores of ``score`` or higher, and the PDF whose
    sha256 is given: a re-render, a lower score or the other critic still sends the work back.
    A general "go ahead" never counts: the caller must pass the human's own reason.
    """
    if not reason or len(reason.strip()) < 8:
        raise ValueError("a critique override needs the human's own reason")
    return record(project_dir, stage="critique", category="critique_override",
                  subject=f"{critic} {criterion} {score}/5 on {pdf_sha256[:12]}",
                  options=[{"option_id": "approve", "label": "approve over the critic (human)", "score": 1,
                            "reason": reason},
                           {"option_id": "send_back", "label": "send back to its stage", "score": 0,
                            "reason": "default rule: below 4 goes back"}],
                  selected="approve", reason=reason, actor=actor, user_approved=True,
                  criterion=criterion, critic=critic, max_score=int(score), pdf_sha256=pdf_sha256)


def critique_overrides(project_dir: str | Path, pdf_sha256: str) -> list[dict[str, Any]]:
    """Human-approved critique overrides that cover the PDF with this sha256."""
    return [d for d in load(project_dir)["decisions"]
            if d.get("category") == "critique_override" and d.get("user_approved")
            and d.get("pdf_sha256") == pdf_sha256]

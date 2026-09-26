"""The editorial brain: read the KLI repository, write back to its three allowed paths."""
from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path

from .common import read_json, series_config

READING_ORDER = [
    "00_OWNER_CONTROL_PANEL.md",
    "01_ACCOUNT_STRATEGY/01_PROMISE_AND_AUDIENCE.md",
    "01_ACCOUNT_STRATEGY/02_PILLARS_AND_EXPERIMENTS.md",
    "02_VERIFIED_KNOWLEDGE/01_SOURCING_AND_CLAIMS.md",
    "03_VOICE_AND_VISUAL_IDENTITY/01_ARABIC_VOICE.md",
    "03_VOICE_AND_VISUAL_IDENTITY/02_FACELESS_UGC_AND_VARIETY.md",
    "03_VOICE_AND_VISUAL_IDENTITY/03_RECURRING_WORLD.md",
    "07_OUTPUTS/SCRIPT_LEDGER.md",
    "09_LEARNING/REJECTION_REGISTER.md",
]
JUDGE_CONTRACT = "05_JUDGING_STANDARDS/01_BLUNT_REVIEW_CONTRACT.md"
IDEA_BANK = "09_LEARNING/IDEA_BANK.jsonl"
SCRIPT_LEDGER = "07_OUTPUTS/SCRIPT_LEDGER.md"
REJECTION_REGISTER = "09_LEARNING/REJECTION_REGISTER.md"
OBSERVATIONS = "09_LEARNING/observations"


def root() -> Path:
    cfg = series_config()
    p = Path(cfg["source_repo"])
    if not (p / "RESTART.md").exists():
        raise RuntimeError(f"KLI repo not found or not restarted at {p}")
    return p


def head_commit() -> str:
    return subprocess.check_output(["git", "-C", str(root()), "rev-parse", "HEAD"], text=True).strip()


def verify_min_commit() -> None:
    want = series_config().get("source_repo_min_commit")
    if not want:
        return
    r = subprocess.run(["git", "-C", str(root()), "merge-base", "--is-ancestor", want, "HEAD"])
    if r.returncode != 0:
        raise RuntimeError(f"KLI repo is behind the required commit {want}")


def reading_pack() -> str:
    """The editorial documents, concatenated in reading-map order."""
    parts = []
    for rel in READING_ORDER:
        p = root() / rel
        if p.exists():
            parts.append(f"\n\n===== {rel} =====\n" + p.read_text(encoding="utf-8"))
    return "".join(parts)


def judge_contract() -> str:
    return (root() / JUDGE_CONTRACT).read_text(encoding="utf-8")


def idea_bank() -> list[dict]:
    rows = []
    for line in (root() / IDEA_BANK).read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def used_topic_text() -> str:
    """Everything the ledger and register say was used or rejected — for exclusion."""
    return (root() / SCRIPT_LEDGER).read_text(encoding="utf-8") + (root() / REJECTION_REGISTER).read_text(encoding="utf-8")


def observations() -> list[dict]:
    d = root() / OBSERVATIONS
    return [read_json(p) for p in sorted(d.glob("*.json"))] if d.exists() else []


# ---- the three write-back paths ------------------------------------------

def append_ledger_row(cells: list[str]) -> None:
    p = root() / SCRIPT_LEDGER
    text = p.read_text(encoding="utf-8")
    row = "| " + " | ".join(c.replace("|", "/").replace("\n", " ") for c in cells) + " |\n"
    marker = "\n## Already used"
    if marker in text:
        head, tail = text.split(marker, 1)
        text = head.rstrip("\n") + "\n" + row + marker + tail
    else:
        text = text.rstrip("\n") + "\n" + row
    p.write_text(text, encoding="utf-8")


def append_rejection_row(cells: list[str]) -> None:
    p = root() / REJECTION_REGISTER
    row = "| " + " | ".join(c.replace("|", "/").replace("\n", " ") for c in cells) + " |\n"
    p.write_text(p.read_text(encoding="utf-8").rstrip("\n") + "\n" + row, encoding="utf-8")


def write_observation(date_str: str, data: dict) -> Path:
    d = root() / OBSERVATIONS
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{date_str}.json"
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def commit_writeback(message: str) -> None:
    """Commit the factory's own write-backs so the brain's history stays honest."""
    r = root()
    subprocess.run(["git", "-C", str(r), "add", SCRIPT_LEDGER, REJECTION_REGISTER, OBSERVATIONS], check=False)
    subprocess.run(["git", "-C", str(r), "-c", "user.name=kli-factory", "-c", "user.email=factory@kli.local",
                    "commit", "-q", "-m", message + "\n\nCo-Authored-By: Claude Opus 5 <noreply@anthropic.com>"], check=False)

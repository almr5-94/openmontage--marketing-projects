"""Spend guard: one ledger (events.jsonl) per reel, one ceiling per month.

Refuses a paid call *before* it happens when the estimate would breach the
per-reel cap, and refuses a whole run when the month is over its ceiling.
"""
from __future__ import annotations

import glob
import json
from pathlib import Path

from .common import PROJECTS_DIR, SERIES_DIR, read_json


class BudgetExceeded(RuntimeError):
    pass


def limits() -> dict:
    return read_json(SERIES_DIR / "budget.json", {"per_reel_usd": 15.0, "monthly_usd": 400.0})


def spent(project_dir: Path) -> float:
    total = 0.0
    path = Path(project_dir) / "events.jsonl"
    if not path.exists():
        return 0.0
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("event") == "finish" and e.get("cost_usd"):
            total += float(e["cost_usd"])
    return round(total, 4)


def spent_this_month(yyyymm: str) -> float:
    return round(sum(spent(Path(p)) for p in glob.glob(str(PROJECTS_DIR / f"kli-{yyyymm}*"))), 4)


def assert_can_spend(project_dir: Path, estimate_usd: float, what: str) -> None:
    lim = limits()
    so_far = spent(project_dir)
    if so_far + estimate_usd > lim["per_reel_usd"]:
        raise BudgetExceeded(
            f"refusing {what}: spent {so_far:.2f} + estimate {estimate_usd:.2f} "
            f"> per-reel cap {lim['per_reel_usd']:.2f} USD"
        )
    month = Path(project_dir).name[4:10]
    monthly = spent_this_month(month)
    if monthly + estimate_usd > lim["monthly_usd"]:
        raise BudgetExceeded(
            f"refusing {what}: month {month} spent {monthly:.2f} + {estimate_usd:.2f} "
            f"> monthly ceiling {lim['monthly_usd']:.2f} USD"
        )


def snapshot(project_dir: Path) -> dict:
    lim = limits()
    return {
        "spent_usd": spent(project_dir),
        "per_reel_cap_usd": lim["per_reel_usd"],
        "month_spent_usd": spent_this_month(Path(project_dir).name[4:10]),
        "monthly_cap_usd": lim["monthly_usd"],
    }

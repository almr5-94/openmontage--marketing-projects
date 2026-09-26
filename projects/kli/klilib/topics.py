"""Rank the idea bank for tomorrow's reel.

Score = posterior follows-per-1000-views for the topic's pillar and hook family
(shrunk toward the global mean when few observations exist), with saves and
shares as tie-breakers, plus an explore bonus for the least-tested pillar.
Topics already used or rejected are excluded by id and by ledger text.
"""
from __future__ import annotations

import glob
import re
from collections import defaultdict
from pathlib import Path

from .common import PROJECTS_DIR, read_json
from . import kli_repo

EXPLORE_EPSILON = 0.3
PRIOR_WEIGHT = 3.0


def _used_ids_from_reels() -> set[str]:
    ids = set()
    for p in glob.glob(str(PROJECTS_DIR / "kli-*" / "artifacts" / "brief.json")):
        try:
            ids.add(read_json(Path(p)).get("metadata", {}).get("topic_id", ""))
        except Exception:
            pass
    return ids - {""}


def rank(limit: int = 5) -> list[dict]:
    bank = kli_repo.idea_bank()
    used_text = kli_repo.used_topic_text()
    used_ids = _used_ids_from_reels()
    obs = kli_repo.observations()

    per_pillar: dict[str, list[float]] = defaultdict(list)
    per_hook: dict[str, list[float]] = defaultdict(list)
    saves: dict[str, list[float]] = defaultdict(list)
    shares: dict[str, list[float]] = defaultdict(list)
    all_rates: list[float] = []
    for o in obs:
        d = o.get("derived", {})
        f = d.get("follows_per_1000_views")
        if f is None:
            continue
        all_rates.append(f)
        per_pillar[o.get("pillar", "")].append(f)
        per_hook[o.get("hook_family", "")].append(f)
        saves[o.get("pillar", "")].append(d.get("saves_per_1000") or 0)
        shares[o.get("pillar", "")].append(d.get("shares_per_1000") or 0)
    global_mean = sum(all_rates) / len(all_rates) if all_rates else 1.0

    def posterior(values: list[float]) -> float:
        n = len(values)
        return (sum(values) + PRIOR_WEIGHT * global_mean) / (n + PRIOR_WEIGHT)

    tested = {p: len(v) for p, v in per_pillar.items()}
    least = min(tested.values()) if tested else 0

    ranked = []
    for t in bank:
        status = str(t.get("status", "candidate"))
        if not status.startswith("candidate"):
            continue
        if t["topic_id"] in used_ids or re.search(re.escape(t["topic_id"]) + r"\b", used_text):
            continue
        score = 0.6 * posterior(per_pillar.get(t["pillar"], [])) + 0.4 * posterior(per_hook.get(t["hook_family"], []))
        score += 0.05 * posterior(saves.get(t["pillar"], [])) + 0.05 * posterior(shares.get(t["pillar"], []))
        if tested.get(t["pillar"], 0) == least:
            score += EXPLORE_EPSILON * global_mean
        ranked.append({**t, "score": round(score, 4)})
    ranked.sort(key=lambda r: -r["score"])
    return ranked[:limit]

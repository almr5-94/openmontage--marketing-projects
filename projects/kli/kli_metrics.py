#!/usr/bin/env python
"""Pull 48-hour Instagram insights for every published reel and write the observation back to the brain.

    .venv/bin/python projects/kli/kli_metrics.py [--now] [--date YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import glob
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from klilib.common import PROJECTS_DIR, SERIES_DIR, log, read_json, write_json, now_iso  # noqa: E402
from klilib import meta, kli_repo  # noqa: E402

METRICS = ["views", "reach", "shares", "saved", "likes", "comments", "total_interactions", "follows", "ig_reels_avg_watch_time"]


def collect(pid: str, entry: dict, lateness_s: float) -> dict:
    media_id = entry["video_id"]
    out, errors = {}, {}
    for m in METRICS:
        try:
            r = meta.call("GET", f"/{media_id}/insights", {"metric": m})
            vals = r.get("data", [{}])[0].get("values", [{}])
            out[m] = vals[0].get("value") if vals else r.get("data", [{}])[0].get("total_value", {}).get("value")
        except Exception as exc:  # per-metric availability differs by account and media type
            out[m] = None
            errors[m] = str(exc)[:160]
    comments = []
    try:
        c = meta.call("GET", f"/{media_id}/comments", {"fields": "id,text,timestamp,like_count", "limit": 250})
        comments = c.get("data", [])
    except Exception as exc:
        errors["comments_list"] = str(exc)[:160]
    views = out.get("views") or 0
    derived = {k: (round(1000 * (out.get(src) or 0) / views, 3) if views else None)
               for k, src in (("follows_per_1000_views", "follows"), ("saves_per_1000", "saved"), ("shares_per_1000", "shares"))}
    brief = read_json(PROJECTS_DIR / pid / "artifacts" / "brief.json")["metadata"]
    plan = read_json(PROJECTS_DIR / pid / "artifacts" / "scene_plan.json", {"metadata": {"shots": []}})
    return {"project": pid, "media_id": media_id, "permalink": entry.get("url"), "posted_at": entry.get("timestamp"), "collected_at": now_iso(),
            "lateness_s": round(lateness_s), "metrics": out, "errors": errors, "derived": derived, "comments": comments,
            "topic_id": brief["topic_id"], "pillar": brief["pillar"], "hook_family": brief["hook_family"], "stage": brief.get("stage"),
            "settings": [s.get("setting_id") for s in plan["metadata"]["shots"]]}


def main(now_flag: bool, only_date: str | None) -> int:
    done = 0
    for logp in sorted(glob.glob(str(PROJECTS_DIR / "kli-*" / "artifacts" / "publish_log.json"))):
        pid = Path(logp).parents[1].name
        date_str = f"{pid[4:8]}-{pid[8:10]}-{pid[10:12]}"
        if only_date and date_str != only_date:
            continue
        for entry in read_json(Path(logp))["entries"]:
            if entry.get("status") != "published" or not entry.get("video_id"):
                continue
            out = SERIES_DIR / "metrics" / f"{date_str}.json"
            if out.exists():
                continue
            posted = datetime.fromisoformat(entry["timestamp"].replace("+0000", "+00:00").replace("Z", "+00:00"))
            due = posted + timedelta(hours=48)
            now = datetime.now(timezone.utc)
            if now < due and not now_flag:
                continue
            obs = collect(pid, entry, (now - due).total_seconds())
            write_json(out, obs)
            kli_repo.write_observation(date_str, obs)
            kli_repo.commit_writeback(f"factory: 48h observation for {pid}")
            log(f"{pid}: views={obs['metrics'].get('views')} follows/1000={obs['derived']['follows_per_1000_views']}")
            done += 1
    log(f"{done} observation(s) written")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--now", action="store_true", help="collect even before the 48 h mark")
    ap.add_argument("--date")
    a = ap.parse_args()
    sys.exit(main(a.now, a.date))

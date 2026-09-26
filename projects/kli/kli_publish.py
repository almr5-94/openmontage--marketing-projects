#!/usr/bin/env python
"""Publish today's judged reel to Instagram Reels — only when the owner's switch is on.

    .venv/bin/python projects/kli/kli_publish.py --date YYYY-MM-DD [--dry-run] [--force]

Preconditions, all enforced here: live_enabled.json signed and unexpired; inside 16:00-20:00
Asia/Kuwait (unless --force); a PASS verdict whose sha256 matches renders/final_vN.mp4; the
account boundary and credential checks from the KLI repo. The video is exposed at an
unguessable path on kli-media.a-pika.com only for the minutes Meta needs, then removed.
"""
from __future__ import annotations

import argparse
import json
import secrets
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from klilib.common import PROJECTS_DIR, SERIES_DIR, kuwait_now, log, project_dir, read_json, reel_id, sha256_file, write_json, now_iso  # noqa: E402
from klilib import meta  # noqa: E402
from lib.checkpoint import write_checkpoint  # noqa: E402
from schemas.artifacts import validate_artifact  # noqa: E402

SITE_PUBLIC = Path("/home/abood/sites/kli-media/public")
SITE_URL = "https://kli-media.a-pika.com"
WINDOW = (16, 20)


def live_switch() -> dict | None:
    p = SERIES_DIR / "live_enabled.json"
    if not p.exists():
        return None
    s = read_json(p)
    if not (s.get("enabled") and s.get("signed_by") and s.get("signed_at")):
        return None
    exp = s.get("expires")
    if exp and datetime.fromisoformat(exp) < datetime.now(datetime.fromisoformat(exp).tzinfo):
        return None
    return s


def latest_pass(pid: str) -> tuple[Path, dict] | None:
    pdir = project_dir(pid)
    for v in (2, 1):
        vp = pdir / "artifacts" / f"kli_verdict_v{v}.json"
        if vp.exists():
            verdict = read_json(vp)
            if verdict["verdict"] == "PASS":
                final = pdir / "renders" / f"final_v{v}.mp4"
                if final.exists() and sha256_file(final) == verdict["asset_sha256"]:
                    return final, verdict
                log(f"v{v}: file sha256 does not match the verdict — refusing")
            return None
    return None


def expose(final: Path, date_str: str) -> tuple[str, Path]:
    token = secrets.token_hex(16)
    d = SITE_PUBLIC / token
    d.mkdir(parents=True, exist_ok=False)
    dst = d / f"{date_str}.mp4"
    shutil.copy2(final, dst)
    url = f"{SITE_URL}/{token}/{date_str}.mp4"
    for _ in range(12):
        r = subprocess.run(["curl", "-sI", "-m", "15", url], capture_output=True, text=True)
        if "200" in r.stdout.splitlines()[0] if r.stdout else False:
            return url, d
        time.sleep(5)
    shutil.rmtree(d, ignore_errors=True)
    raise RuntimeError(f"public URL never answered 200: {url}")


def publish(date_str: str, dry_run: bool, force: bool) -> int:
    pid = reel_id(date_str)
    pdir = project_dir(pid)
    log_entry = {"platform": "instagram", "status": "draft", "timestamp": now_iso(), "visibility": "public"}
    if read_json(pdir / "project.json", {}).get("provisional"):
        log(f"{pid} is a provisional machinery-test reel — never published")
        return 0
    sw = live_switch()
    if not sw and not dry_run:
        log("live_enabled.json absent, unsigned or expired — skipping (status skipped_disabled)")
        _write_log(pid, {**log_entry, "status": "pending_review", "error": "skipped_disabled"})
        return 0
    now = kuwait_now()
    if not force and not dry_run and not (WINDOW[0] <= now.hour < WINDOW[1]):
        log(f"outside the {WINDOW[0]}:00-{WINDOW[1]}:00 window ({now:%H:%M}) — skipping")
        return 0
    found = latest_pass(pid)
    if not found:
        log(f"{pid}: no PASS verdict bound to a file — nothing to publish")
        _write_log(pid, {**log_entry, "status": "pending_review", "error": "no_pass_verdict"})
        return 0
    final, verdict = found
    if (pdir / "artifacts" / "publish_log.json").exists() and any(e.get("status") == "published" for e in read_json(pdir / "artifacts" / "publish_log.json")["entries"]):
        log(f"{pid} already published")
        return 0
    ig, username = meta.identity()
    script = read_json(pdir / "artifacts" / "script.json")
    caption = script["metadata"]["ig_caption"].strip() + "\n\n" + script["metadata"].get("source_line", "") + "\n\n" + " ".join(script["metadata"].get("hashtags", [])[:8])
    shutil.copy2(final, SERIES_DIR / "publish" / f"{date_str}.mp4")
    url, exposed_dir = expose(final, date_str)
    log(f"exposed for Meta at {url}")
    entry = {**log_entry, "metadata_used": {"title": script["title"], "description": caption, "hashtags": script["metadata"].get("hashtags", [])}}
    try:
        c = meta.call("POST", f"/{ig}/media", {"media_type": "REELS", "video_url": url, "caption": caption, "share_to_feed": "true"})
        container = c["id"]
        status = None
        for _ in range(36):
            s = meta.call("GET", f"/{container}", {"fields": "status_code,status"})
            status = s.get("status_code")
            log(f"container {container}: {status}")
            if status in ("FINISHED", "ERROR", "EXPIRED"):
                break
            time.sleep(10)
        if status != "FINISHED":
            raise RuntimeError(f"container ended {status}: {s}")
        if dry_run:
            log("dry run: container FINISHED, not publishing")
            entry.update({"status": "draft", "video_id": container, "error": "dry_run"})
        else:
            p = meta.call("POST", f"/{ig}/media_publish", {"creation_id": container})
            media_id = p["id"]
            info = meta.call("GET", f"/{media_id}", {"fields": "id,permalink,timestamp"})
            entry.update({"status": "published", "video_id": media_id, "url": info.get("permalink", ""), "timestamp": info.get("timestamp", now_iso())})
            log(f"published {media_id} {info.get('permalink')}")
    except Exception as exc:
        entry.update({"status": "failed", "error": str(exc)[:500]})
        log(f"publish failed: {exc}")
    finally:
        shutil.rmtree(exposed_dir, ignore_errors=True)
        log("public copy removed")
    _write_log(pid, entry, approval_ref=sha256_file(SERIES_DIR / "live_enabled.json") if sw else None)
    return 0 if entry["status"] in ("published", "draft") else 1


def _write_log(pid: str, entry: dict, approval_ref: str | None = None) -> None:
    pdir = project_dir(pid)
    p = pdir / "artifacts" / "publish_log.json"
    data = read_json(p, {"version": "1.0", "entries": [], "metadata": {}})
    data["entries"].append(entry)
    validate_artifact("publish_log", data)
    write_json(p, data)
    if entry["status"] == "published":
        write_checkpoint(PROJECTS_DIR, pid, "publish", "completed", {"publish_log": data}, pipeline_type="kli-daily-reel",
                         human_approval_required=True, human_approved=True, metadata={"approval_ref": approval_ref, "approval_source": "projects/kli/live_enabled.json"})


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=kuwait_now().strftime("%Y-%m-%d"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    sys.exit(publish(a.date, a.dry_run, a.force))

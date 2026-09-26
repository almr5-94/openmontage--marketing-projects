#!/usr/bin/env python
"""Kuwait Legal Insider — the daily driver.

    .venv/bin/python projects/kli/kli_daily.py run [--date YYYY-MM-DD]
    .venv/bin/python projects/kli/kli_daily.py stage <name> --date ...
    .venv/bin/python projects/kli/kli_daily.py judge --date ...
    .venv/bin/python projects/kli/kli_daily.py revise --date ...
    .venv/bin/python projects/kli/kli_daily.py status --date ...

One OpenMontage project per reel (projects/kli-YYYYMMDD). Every stage writes an
OpenMontage checkpoint so the Backlot board shows the rail, and every paid call is
metered in that reel's events.jsonl, which the budget guard reads before spending.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from klilib.common import (OM_ROOT, PROJECTS_DIR, SERIES_DIR, kuwait_now, log, media_duration, project_dir,  # noqa: E402
                           read_json, reel_id, run_tool, sha256_file, write_json, now_iso)
from klilib import budget, captions, gemini, judge as judge_mod, kli_repo, motion, stills, topics, voice  # noqa: E402
from klilib.prompts import IDEA_PICK, SCRIPT, SCENE_PLAN  # noqa: E402
from lib.arabic_captions import to_latin_digits, assert_caption_safe  # noqa: E402
from lib.checkpoint import init_project, write_checkpoint, get_next_stage  # noqa: E402
from schemas.artifacts import validate_artifact  # noqa: E402

PIPELINE = "kli-daily-reel"
WORDS_PER_SECOND = 2.3


# ---------------------------------------------------------------------------
# small helpers

def _decisions(project_id: str, *entries: dict) -> dict:
    return {"version": "1.0", "project_id": project_id, "decisions": list(entries)}


def _decision(stage: str, category: str, subject: str, options: list[tuple[str, float, str, str | None]],
              selected: str, reason: str, approved: bool = True) -> dict:
    return {"decision_id": f"d-{stage}-{int(time.time() * 1000) % 10_000_000}", "stage": stage, "category": category,
            "subject": subject, "selected": selected, "reason": reason, "user_visible": True, "user_approved": approved,
            "options_considered": [{"option_id": oid, "label": oid, "score": sc, "reason": rs, **({"rejected_because": rb} if rb else {})}
                                   for oid, sc, rs, rb in options]}


ELECTIONS = [  # standing authority from the owner's plan approval, 2026-09-27
    ("provider_selection", "Narration provider", "elevenlabs_tts",
     [("elevenlabs_tts", 0.9, "signed male Kuwaiti voice, WER-checked", None), ("google_tts", 0.4, "Gulf voice flagged accent in Sard casting", "accent"), ("piper_tts", 0.1, "free, but no Arabic voice installed", "no Arabic voice")]),
    ("provider_selection", "Per-shot stills", "qwen_image_edit_local",
     [("qwen_image_edit_local", 0.9, "local, free, edits the accepted world reference", None), ("google_imagen", 0.5, "USD 0.04, no reference conditioning", "loses the recurring world"), ("pexels_image", 0.2, "free stock", "cannot hold the recurring world")]),
    ("provider_selection", "Motion", "veo_video",
     [("veo_video", 0.85, "image-to-video 9:16 6 s on the configured Google key", None), ("pexels_video", 0.2, "free stock", "cannot hold the world"), ("runway_mcp", 0.3, "MCP only", "not available unattended")]),
    ("music_source", "Music bed", "google_music",
     [("google_music", 0.8, "Lyria, ~USD 0.10", None), ("music_library", 0.0, "empty", "no cleared tracks"), ("pixabay_music", 0.0, "free key not set", "no key")]),
    ("render_runtime_selection", "Composition runtime", "hyperframes",
     [("hyperframes", 0.9, "RTL captions proven in the Sard reels", None), ("remotion", 0.4, "no RTL caption component", "RTL"), ("ffmpeg", 0.3, "ASS dropped lam-alef ligatures in KLI tests", "ligatures")]),
]


def _ckpt(pid: str, stage: str, status: str, artifacts: dict, **kw) -> None:
    write_checkpoint(PROJECTS_DIR, pid, stage, status, artifacts, pipeline_type=PIPELINE,
                     checkpoint_policy="auto_noncreative", cost_snapshot=budget.snapshot(project_dir(pid)), **kw)


def _art(pid: str, name: str) -> dict:
    return read_json(project_dir(pid) / "artifacts" / f"{name}.json")


def _save_art(pid: str, name: str, data: dict, validate: bool = True) -> dict:
    if validate:
        validate_artifact(name, data)
    write_json(project_dir(pid) / "artifacts" / f"{name}.json", data)
    return data


def _latest_version(pid: str) -> int:
    vs = [int(m.group(1)) for p in (project_dir(pid) / "renders").glob("final_v*.mp4") if (m := re.search(r"final_v(\d+)\.mp4$", p.name))]
    return max(vs) if vs else 0


def _fetch_source(url: str) -> str:
    import requests
    from bs4 import BeautifulSoup

    if not url.startswith("http"):
        return ""
    r = requests.get(url, timeout=25, headers={"User-Agent": "Mozilla/5.0 (KLI editorial fetch)"})
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    for t in soup(["script", "style", "nav", "footer", "header"]):
        t.decompose()
    text = re.sub(r"\s+", " ", soup.get_text(" ")).strip()
    return text[:14000]


RESEARCH = """Find the single most authoritative PRIMARY web page (official Kuwaiti government, ministry, regulator, court,
or the official vendor documentation) whose text directly supports or bounds this claim for a Kuwaiti audience:

Claim: {claim}
Territory: {pillar}. Preferred discovery route: {route}

Answer in exactly two lines:
URL: <one https URL to the specific page, not a homepage>
WHY: <one sentence on what that page states>
If no primary page supports the claim, answer: URL: none"""


def _research_source(project_dir: Path, topic: dict) -> tuple[str, str]:
    """Return (url, passage). Grounded search for a specific page, else the topic's route page."""
    try:
        ans = gemini.ask_grounded(RESEARCH.format(claim=topic["claim"], pillar=topic["pillar"], route=topic["source_ref"]),
                                  model=gemini.FLASH, project_dir=project_dir, purpose="source_research")
        m = re.search(r"URL:\s*(https?://\S+)", ans)
        if m:
            url = m.group(1).rstrip(").,")
            text = _fetch_source(url)
            if len(text) > 400:
                return url, text
            log(f"research url fetched too little text ({len(text)}): {url}")
    except Exception as exc:
        log(f"grounded research failed: {exc}")
    return topic["source_ref"], _fetch_source(topic["source_ref"])


# ---------------------------------------------------------------------------
# stages

def stage_idea(pid: str) -> None:
    pdir = project_dir(pid)
    kli_repo.verify_min_commit()
    shortlist = topics.rank(5)
    if not shortlist:
        raise RuntimeError("idea bank has no unused candidate topics")
    excerpts, urls = {}, {}
    for t in shortlist:
        try:
            urls[t["topic_id"]], excerpts[t["topic_id"]] = _research_source(pdir, t)
        except Exception as exc:
            urls[t["topic_id"]], excerpts[t["topic_id"]] = t["source_ref"], ""
            log(f"source fetch failed for {t['topic_id']}: {exc}")
    fetched = [t for t in shortlist if len(excerpts[t["topic_id"]]) > 400]
    if not fetched:
        raise RuntimeError("no shortlisted topic has a fetchable source passage")
    pick = gemini.ask_json(IDEA_PICK.format(pack=kli_repo.reading_pack()[:60000],
                                            shortlist=json.dumps([{**t, "source_excerpt": excerpts[t["topic_id"]][:3000]} for t in fetched], ensure_ascii=False)),
                           model=gemini.PRO, project_dir=pdir, purpose="idea_pick")
    chosen = next((t for t in fetched if t["topic_id"] == pick.get("topic_id")), fetched[0])
    if pick.get("supported_by_passage") is False:
        chosen = fetched[0] if fetched[0]["topic_id"] != pick.get("topic_id") else (fetched[1] if len(fetched) > 1 else fetched[0])
    brief = {
        "version": "1.0", "title": f"KLI {pid[4:]} — {chosen['topic_id']}", "hook": chosen["claim"],
        "key_points": [chosen["claim"]], "core_message": chosen["claim"], "tone": "warm, direct, insider, high FOMO without deception",
        "style": "realistic faceless POV, recurring world, word-timed Arabic captions", "target_audience": f"Kuwaiti law {chosen['stage']}",
        "target_platform": "instagram", "target_duration_seconds": 28,
        "metadata": {"topic_id": chosen["topic_id"], "pillar": chosen["pillar"], "stage": chosen["stage"], "hook_family": chosen["hook_family"],
                     "source_ref": urls[chosen["topic_id"]], "source_route": chosen["source_ref"], "demo_object": chosen["demo_object"], "score": chosen.get("score"),
                     "source_excerpt": excerpts[chosen["topic_id"]], "pick_reason": pick.get("reason", ""),
                     "shortlist": [t["topic_id"] for t in shortlist], "kli_repo_commit": kli_repo.head_commit()},
    }
    _save_art(pid, "brief", brief)
    dl = _decisions(pid,
                    _decision("idea", "concept_selection", "Topic for this reel",
                              [(t["topic_id"], min(1.0, t["score"] / max(1e-6, shortlist[0]["score"])), t["claim"][:80], None if t is chosen else "not chosen") for t in shortlist],
                              chosen["topic_id"], pick.get("reason", "top of the ranked shortlist")),
                    *[_decision("idea", cat, subj, opts, sel, "standing authority: owner-approved plan 2026-09-27") for cat, subj, sel, opts in ELECTIONS])
    _ckpt(pid, "idea", "completed", {"brief": brief, "decision_log": dl})


def stage_script(pid: str) -> None:
    pdir = project_dir(pid)
    brief = _art(pid, "brief")
    m = brief["metadata"]
    prompt = SCRIPT.format(claim=brief["hook"], pillar=m["pillar"], stage=m["stage"], hook_family=m["hook_family"], demo_object=m["demo_object"],
                           source_url=m["source_ref"], source_excerpt=m["source_excerpt"][:9000], pack=kli_repo.reading_pack()[:60000])
    for attempt in range(2):
        s = gemini.ask_json(prompt, model=gemini.PRO, project_dir=pdir, purpose="script", temperature=0.6)
        lines = [to_latin_digits(l["text_ar"]).strip() for l in s["lines"]]
        chunks = [[to_latin_digits(c) for c in l["caption_chunks"]] for l in s["lines"]]
        try:
            for cl in chunks:
                for c in cl:
                    assert_caption_safe(c.lstrip("*"))
            if not (4 <= len(lines) <= 6):
                raise ValueError(f"{len(lines)} lines")
            words = sum(len(l.split()) for l in lines)
            if not (30 <= words <= 90):
                raise ValueError(f"{words} words")
        except ValueError as exc:
            log(f"script attempt {attempt + 1} rejected: {exc}")
            prompt += f"\n\nYour previous reply was rejected: {exc}. Fix it."
            continue
        jev = run_tool("jev_judge", {"operation": "script_check", "lines": lines, "threshold": 0.6,
                                     "context": "a Kuwaiti legal-understanding reel for law students and lawyers; no product is sold"}).data
        if jev.get("passed"):
            break
        flagged = [jev["lines"][i] for i in jev.get("flagged_indices", [])]
        log(f"jev flagged {len(flagged)} lines: {[f['flags'] for f in flagged]}")
        prompt += "\n\nA legal-promise checker flagged these lines; rewrite them without the flagged risk: " + json.dumps(flagged, ensure_ascii=False)
    else:
        raise RuntimeError("script rejected twice (caption rules or legal-promise checker)")
    t, sections = 0.0, []
    for i, text in enumerate(lines, 1):
        d = round(len(text.split()) / WORDS_PER_SECOND, 2)
        sections.append({"id": f"l{i:02d}", "label": "hook" if i == 1 else ("takeaway" if i == len(lines) else f"line {i}"),
                         "text": text, "start_seconds": round(t, 2), "end_seconds": round(t + d, 2), "source_ref": m["source_ref"],
                         "delivery_cues": {"pace": "measured" if i in (1, len(lines)) else "conversational", "pause_before_seconds": 0.55}})
        t += d + 0.55
    script = {"version": "1.0", "title": to_latin_digits(s.get("title_ar", brief["title"])), "total_duration_seconds": round(t + 2.4, 2),
              "voice_performance": {"performance_intent": "one confident adult Kuwaiti narrator, warm then intense at the reveal",
                                    "pacing_profile": "conversational", "pause_policy": "0.55 s between lines, 0.85 s before the takeaway"},
              "sections": sections,
              "metadata": {"caption_chunks": chunks, "takeaway": to_latin_digits(s["takeaway_ar"]), "ig_caption": to_latin_digits(s["ig_caption_ar"]),
                           "hashtags": s.get("hashtags", []), "source_line": s.get("source_line", ""), "claims": s.get("claims", []),
                           "source_url": m["source_ref"], "jev": {"passed": jev.get("passed"), "flagged": jev.get("flagged_indices", [])}}}
    _save_art(pid, "script", script)
    (pdir / "assets" / "audio").mkdir(parents=True, exist_ok=True)
    (pdir / "assets" / "audio" / "narration.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    write_json(pdir / "assets" / "audio" / "captions.json", chunks)
    _ckpt(pid, "script", "completed", {"script": script})


def stage_scene_plan(pid: str) -> None:
    pdir = project_dir(pid)
    script = _art(pid, "script")
    settings = stills.accepted_settings()
    if len(settings) < 2:
        raise RuntimeError("fewer than 2 world settings are accepted by the owner (projects/kli/world/world.json)")
    lines = "\n".join(f"{s['id']} ({s['end_seconds'] - s['start_seconds']:.1f}s): {s['text']}" for s in script["sections"])
    plan = gemini.ask_json(SCENE_PLAN.format(constants=stills.constants(), settings=json.dumps([{"id": s["id"], "description": s["description"]} for s in settings]),
                                             lines=lines), model=gemini.FLASH, project_dir=pdir, purpose="scene_plan", temperature=0.5)
    shots = plan["shots"][:4]
    if len(shots) != 4:
        raise RuntimeError(f"scene plan returned {len(shots)} shots, need 4")
    valid = {s["id"] for s in settings}
    scenes = []
    by_id = {s["id"]: s for s in script["sections"]}
    for sh in shots:
        if sh["setting_id"] not in valid:
            sh["setting_id"] = settings[len(scenes) % len(settings)]["id"]
        secs = [by_id[i] for i in sh["section_ids"] if i in by_id] or [script["sections"][len(scenes)]]
        for bad in ("face", "text", "logo"):
            if re.search(rf"\b{bad}\b", sh["still_prompt"], re.I) and not re.search(rf"\bno {bad}", sh["still_prompt"], re.I):
                sh["still_prompt"] += f" No {bad}."
        scenes.append({"id": sh["id"], "type": "generated", "description": sh["still_prompt"], "start_seconds": secs[0]["start_seconds"],
                       "end_seconds": secs[-1]["end_seconds"], "script_section_id": secs[0]["id"], "framing": sh.get("shot_size", "close_up"),
                       "movement": "handheld", "narrative_role": "evidence", "required_assets": [{"type": "video", "description": sh["motion_prompt"], "source": "generate"}]})
    scene_plan = {"version": "1.0", "scenes": scenes, "metadata": {"shots": shots, "world_version": stills.world().get("version")}}
    _save_art(pid, "scene_plan", scene_plan)
    _ckpt(pid, "scene_plan", "completed", {"scene_plan": scene_plan})


def stage_assets(pid: str) -> None:
    pdir = project_dir(pid)
    script, plan = _art(pid, "script"), _art(pid, "scene_plan")
    shots = plan["metadata"]["shots"]
    settings = {s["id"]: s for s in stills.world()["settings"]}
    world_seed = int(stills.world().get("seed", 4242))
    assets, fallbacks = [], 0
    # 1. stills: render all (Qwen), free the card, gate all (Ollama), re-render failures — never both models at once
    gates = stills.generate_stills(pdir, [{"shot_id": sh["id"], "setting": settings[sh["setting_id"]], "prompt": sh["still_prompt"], "seed": world_seed + i}
                                          for i, sh in enumerate(shots)])
    still_paths = {sh["id"]: pdir / "assets" / "images" / f"{sh['id']}.png" for sh in shots}
    for sh in shots:
        gate = gates[sh["id"]]
        assets.append({"id": f"{sh['id']}_still", "type": "image", "path": str(still_paths[sh["id"]].relative_to(OM_ROOT)), "source_tool": gate["attempts"][-1]["tool"],
                       "scene_id": sh["id"], "prompt": gate["prompt"], "seed": gate["attempts"][-1].get("seed"), "resolution": "768x1376"})
    # 2. motion (network: Veo)
    clip_paths = {}
    for i, sh in enumerate(shots):
        clip, info = motion.generate_clip(pdir, sh["id"], still_paths[sh["id"]], sh["motion_prompt"], world_seed * 7 + i)
        clip_paths[sh["id"]] = clip
        if clip is None:
            fallbacks += 1
            log(f"{sh['id']}: still fallback ({info})")
        else:
            assets.append({"id": f"{sh['id']}_clip", "type": "video", "path": str(clip.relative_to(OM_ROOT)), "source_tool": "veo_video",
                           "scene_id": sh["id"], "prompt": sh["motion_prompt"], "seed": info.get("seed"), "duration_seconds": round(media_duration(clip), 2), "resolution": "1080x1920"})
    if fallbacks >= 2:
        raise RuntimeError(f"{fallbacks} of 4 shots fell back to stills — that is a slideshow, not a reel")
    # 3. narration (GPU: Whisper)
    lines = [s["text"] for s in script["sections"]]
    timeline = voice.build_narration(pdir, lines, script["metadata"]["caption_chunks"])
    assets.append({"id": "narration", "type": "narration", "path": str(Path(timeline["master"]).relative_to(OM_ROOT)), "source_tool": "elevenlabs_tts",
                   "scene_id": "all", "duration_seconds": timeline["total"], "quality_score": round(1 - timeline["wer_max"], 3),
                   "voice_performance": {"delivery_cues_applied": True, "provider_text_used": True, "sample_approved": True, "sample_path": str(SERIES_DIR / "voice" / "pick.json")}})
    # 4. music bed (network: Lyria) — music_library is empty and pixabay has no key (logged in the elections)
    music = pdir / "assets" / "music" / "lyria.mp3"
    if not music.exists():
        budget.assert_can_spend(pdir, 0.12, "google_music")
        run_tool("google_music", {"prompt": ("Quiet minimal underscore for a 30-second Arabic spoken-word reel about law: soft felt piano, low warm pad, "
                                            "very sparse, 72 BPM, generous headroom for a male voice, no drums, no melody hooks, no vocals, no abrupt ending."),
                                  "duration_seconds": int(timeline["total"]) + 8, "output_path": str(music)})
    assets.append({"id": "music", "type": "music", "path": str(music.relative_to(OM_ROOT)), "source_tool": "google_music", "scene_id": "all"})
    # 5. fit each clip to its narration span
    spans = _spans(script, plan, timeline)
    for sh in shots:
        fit = pdir / "assets" / "video" / f"{sh['id']}_fit.mp4"
        how = motion.fit_clip(clip_paths[sh["id"]], still_paths[sh["id"]], fit, spans[sh["id"]][1])
        assets.append({"id": f"{sh['id']}_fit", "type": "video", "path": str(fit.relative_to(OM_ROOT)), "source_tool": "ffmpeg", "scene_id": sh["id"],
                       "duration_seconds": round(spans[sh["id"]][1], 2), "generation_summary": how})
    manifest = {"version": "1.0", "assets": assets, "total_cost_usd": budget.spent(pdir),
                "metadata": {"fallbacks": fallbacks, "spans": spans, "wer_per_line": timeline["wer_per_line"], "total_seconds": timeline["total"]}}
    _save_art(pid, "asset_manifest", manifest)
    dl = _decisions(pid, *[_decision("assets", "fallback_decision", f"Shot {sid} motion", [("veo_video", 0.0, "failed twice", "provider failure"), ("still_push_in", 1.0, "slow push-in on the gated still", None)],
                                     "still_push_in", "Veo failed twice; one still-fallback is allowed per reel") for sid, c in clip_paths.items() if c is None])
    _ckpt(pid, "assets", "completed", {"asset_manifest": manifest, **({"decision_log": dl} if dl["decisions"] else {})})


def _spans(script: dict, plan: dict, timeline: dict) -> dict[str, tuple[float, float]]:
    """shot id -> (start, duration) from the real narration timeline; the last shot runs to the end card."""
    idx = {s["id"]: i for i, s in enumerate(script["sections"])}
    starts, durs = timeline["starts"], timeline["durations"]
    n = len(starts)
    shots = plan["metadata"]["shots"]
    out = {}
    for k, sh in enumerate(shots):
        first = min(idx[i] for i in sh["section_ids"] if i in idx) if any(i in idx for i in sh["section_ids"]) else k
        st = 0.0 if k == 0 else max(0.0, starts[first] - 0.3)
        if k + 1 < len(shots):
            nxt = shots[k + 1]
            nf = min(idx[i] for i in nxt["section_ids"] if i in idx) if any(i in idx for i in nxt["section_ids"]) else k + 1
            en = max(0.0, starts[min(nf, n - 1)] - 0.3)
        else:
            en = timeline["total"]
        out[sh["id"]] = (round(st, 2), round(max(1.0, en - st), 2))
    return out


def stage_edit(pid: str) -> None:
    pdir = project_dir(pid)
    script, manifest = _art(pid, "script"), _art(pid, "asset_manifest")
    timeline = read_json(pdir / "assets" / "audio" / "vo" / "timeline.json")
    spans = manifest["metadata"]["spans"]
    shots = [{"id": sid, "start": st, "duration": d, "path": str(OM_ROOT / next(a["path"] for a in manifest["assets"] if a["id"] == f"{sid}_fit"))}
             for sid, (st, d) in spans.items()]
    end_at = round(timeline["total"] - voice.TAIL + 0.15, 2)
    comp = captions.build_composition(pdir, pid, script["title"], shots, timeline["chunks"], script["metadata"]["takeaway"],
                                      script["metadata"].get("source_line", ""), timeline["total"], end_at)
    ed = {"version": "1.0",
          "cuts": [{"id": s["id"], "source": f"{s['id']}_fit", "in_seconds": 0.0, "out_seconds": s["duration"], "layer": "primary"} for s in shots],
          "subtitles": {"enabled": True, "style": "kli-word-timed", "source": "assets/audio/vo/timeline.json", "font": "Tajawal", "font_size": 58,
                        "color": "#ffffff", "position": "bottom-center", "max_words_per_line": 4},
          "music": {"asset_id": "music", "volume": 0.16, "ducking": True, "fade_in_seconds": 1.0, "fade_out_seconds": 1.5},
          "render_runtime": "hyperframes", "composition_mode": "atelier",
          "bespoke": {"entry": str((comp / "index.html").relative_to(OM_ROOT)), "composition_id": pid,
                      "art_direction": "realistic faceless POV phone footage from the recurring world; captions typeset in the composition; end card with takeaway and handle"},
          "metadata": {"loudnorm_target": -14, "end_card_at": end_at, "total_seconds": timeline["total"]}}
    _save_art(pid, "edit_decisions", ed)
    _ckpt(pid, "edit", "completed", {"edit_decisions": ed})


def stage_compose(pid: str, version: int | None = None) -> None:
    pdir = project_dir(pid)
    ed = _art(pid, "edit_decisions")
    comp = pdir / "composition"
    version = version or (_latest_version(pid) + 1)
    t0 = time.time()
    for cmd in (["npx", "hyperframes", "lint", str(comp)], ["npx", "hyperframes", "validate", str(comp)]):
        r = subprocess.run(cmd, cwd=OM_ROOT, capture_output=True, text=True, timeout=600)
        log(f"{' '.join(cmd[1:3])}: rc={r.returncode} {r.stdout.strip()[-300:]}")
        if r.returncode != 0:
            raise RuntimeError(f"{cmd[2]} failed: {r.stderr[-800:] or r.stdout[-800:]}")
    silent = pdir / "renders" / f"silent_v{version}.mp4"
    env = {**os.environ, "NODE_OPTIONS": "--max-old-space-size=8192"}
    r = subprocess.run(["npx", "hyperframes", "render", str(comp), "-o", str(silent), "-q", "delivery", "-w", "4", "--quiet"], cwd=OM_ROOT,
                       capture_output=True, text=True, timeout=2400, env=env)
    if r.returncode != 0 or not silent.exists():
        raise RuntimeError(f"hyperframes render failed: {(r.stderr or r.stdout)[-1200:]}")
    vo = pdir / "assets" / "audio" / "vo" / "vo_master.wav"
    music = OM_ROOT / next(a["path"] for a in _art(pid, "asset_manifest")["assets"] if a["id"] == "music")
    mixed = pdir / "assets" / "audio" / f"mix_v{version}.wav"
    run_tool("audio_mixer", {"operation": "duck", "primary_audio": str(vo), "secondary_audio": str(music), "duck_level": -14,
                             "normalize": True, "loudnorm_target": ed["metadata"]["loudnorm_target"], "output_path": str(mixed)})
    final = pdir / "renders" / f"final_v{version}.mp4"
    total = ed["metadata"]["total_seconds"]
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(silent), "-i", str(mixed), "-filter_complex",
                    f"[1:a]afade=t=out:st={total - 1.5:.2f}:d=1.5,atrim=0:{total:.2f}[a]", "-map", "0:v", "-map", "[a]",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-t", f"{total:.2f}", "-movflags", "+faststart", str(final)], check=True)
    fmt = judge_mod.format_gate(final)
    report = {"version": "1.0", "outputs": [{"path": str(final.relative_to(OM_ROOT)), "format": "mp4", "codec": fmt["codec"], "audio_codec": fmt["audio_codec"],
                                            "resolution": f"{fmt['width']}x{fmt['height']}", "fps": fmt["fps"], "duration_seconds": fmt["duration"],
                                            "file_size_bytes": fmt["file_size_bytes"], "platform_target": "instagram"}],
              "render_time_seconds": round(time.time() - t0, 1), "warnings": [] if fmt["ok"] else [f"format gate failed: {fmt}"],
              "verification_notes": [f"ffprobe {fmt['width']}x{fmt['height']} {fmt['fps']}fps {fmt['duration']}s lufs={fmt['lufs']}", f"sha256 {sha256_file(final)}"],
              "metadata": {"version": version, "silent": str(silent.relative_to(OM_ROOT))}}
    _save_art(pid, "render_report", report)
    if not fmt["ok"]:
        raise RuntimeError(f"render failed the format gate: {fmt}")
    _ckpt(pid, "compose", "completed", {"render_report": report})


def stage_judge(pid: str) -> dict:
    pdir = project_dir(pid)
    version = _latest_version(pid)
    if version == 0:
        raise RuntimeError("nothing rendered yet")
    final = pdir / "renders" / f"final_v{version}.mp4"
    script = _art(pid, "script")
    verdict = judge_mod.judge(pdir, final, script, script["metadata"].get("source_url", ""), version)
    fr = judge_mod.final_review_artifact(pdir, verdict, final)
    _save_art(pid, "final_review", fr)
    log(f"JUDGE v{version}: {verdict['verdict']} total={verdict['total']} gates_failed={[g for g, v in verdict['gates'].items() if not v]}")
    brief = _art(pid, "brief")["metadata"]
    if verdict["verdict"] == "PASS":
        _ckpt(pid, "judge", "completed", {"final_review": fr}, review={"status": "approved", "reviewer": verdict["judge_model"], "total": verdict["total"]})
        kli_repo.append_ledger_row([pid, pid[4:], brief["topic_id"] + ": " + brief.get("pick_reason", "")[:60], script["sections"][0]["text"][:60],
                                    brief["source_ref"], str(round(verdict["format"]["duration"])), "word-timed", brief["demo_object"],
                                    f"approved v{version} sha256 {verdict['asset_sha256'][:12]}"])
        kli_repo.commit_writeback(f"factory: {pid} approved v{version}")
    else:
        top = verdict["issues"][0] if verdict["issues"] else {}
        kli_repo.append_rejection_row([pid, f"v{version}", verdict["asset_sha256"][:12], str(verdict["total"]),
                                       ",".join(g for g, v in verdict["gates"].items() if not v) or "-",
                                       f"{top.get('id', '-')} · {top.get('timecode', '-')} · {top.get('severity', '-')}", top.get("correction", "-"), "-"])
        kli_repo.commit_writeback(f"factory: {pid} rejected v{version}")
        if version >= 2:
            marker = read_json(pdir / "project.json")
            marker["status"] = "rejected"
            write_json(pdir / "project.json", marker)
            _ckpt(pid, "judge", "failed", {"final_review": fr}, error=f"REJECT v{version}: {verdict['total']}")
        else:
            _ckpt(pid, "judge", "in_progress", {"final_review": fr}, metadata={"needs_revision": True})
    return verdict


def revise(pid: str) -> None:
    """One revision: act on the v1 issues' targets, re-fit, re-compose as v2."""
    pdir = project_dir(pid)
    v = read_json(pdir / "artifacts" / "kli_verdict_v1.json")
    if v["verdict"] == "PASS":
        log("v1 passed; nothing to revise")
        return
    targets = {i.get("target", "") for i in v["issues"]}
    if any(t == "script" for t in targets):
        log("issues target the script itself — no automated fact rewriting; leaving REJECT")
        return
    script, plan, manifest = _art(pid, "script"), _art(pid, "scene_plan"), _art(pid, "asset_manifest")
    settings = {s["id"]: s for s in stills.world()["settings"]}
    world_seed = int(stills.world().get("seed", 4242)) + 500
    for t in sorted(targets):
        m = re.match(r"shot:(s\d\d)", t)
        if m and m.group(1) in {s["id"] for s in plan["metadata"]["shots"]}:
            sid = m.group(1)
            sh = next(s for s in plan["metadata"]["shots"] if s["id"] == sid)
            for f in (pdir / "assets" / "images" / f"{sid}.png", pdir / "assets" / "images" / f"{sid}.gate.json", pdir / "assets" / "video" / f"{sid}.mp4"):
                f.unlink(missing_ok=True)
            stills.generate_stills(pdir, [{"shot_id": sid, "setting": settings[sh["setting_id"]], "prompt": sh["still_prompt"], "seed": world_seed}])
            still = pdir / "assets" / "images" / f"{sid}.png"
            clip, _ = motion.generate_clip(pdir, sid, still, sh["motion_prompt"], world_seed)
            motion.fit_clip(clip, still, pdir / "assets" / "video" / f"{sid}_fit.mp4", manifest["metadata"]["spans"][sid][1])
        m = re.match(r"narration:(l\d\d|all)", t)
        if m:
            for raw in (pdir / "assets" / "audio" / "vo").glob("l*.raw.mp3" if m.group(1) == "all" else f"{m.group(1)}.raw.mp3"):
                raw.unlink()
            tl = voice.build_narration(pdir, [s["text"] for s in script["sections"]], script["metadata"]["caption_chunks"])
            manifest["metadata"]["spans"] = _spans(script, plan, tl)
            for sh in plan["metadata"]["shots"]:
                motion.fit_clip(pdir / "assets" / "video" / f"{sh['id']}.mp4" if (pdir / "assets" / "video" / f"{sh['id']}.mp4").exists() else None,
                                pdir / "assets" / "images" / f"{sh['id']}.png", pdir / "assets" / "video" / f"{sh['id']}_fit.mp4", manifest["metadata"]["spans"][sh["id"]][1])
            _save_art(pid, "asset_manifest", manifest)
    stage_edit(pid)
    stage_compose(pid, version=2)


STAGES = {"idea": stage_idea, "script": stage_script, "scene_plan": stage_scene_plan, "assets": stage_assets,
          "edit": stage_edit, "compose": stage_compose, "judge": stage_judge}


def run(date_str: str) -> int:
    pid = reel_id(date_str)
    if (SERIES_DIR / "PAUSE").exists():
        log("projects/kli/PAUSE exists — production paused")
        return 0
    voice.voice_pick()  # refuses to run on an unsigned voice
    budget.assert_can_spend(project_dir(pid) if project_dir(pid).exists() else SERIES_DIR, 0.0, "run")
    init_project(pid, title=f"Kuwait Legal Insider — {date_str}", pipeline_type=PIPELINE)
    marker = read_json(project_dir(pid) / "project.json")
    if marker.get("status") in ("rejected", "judged"):
        log(f"{pid} already {marker['status']}")
        return 0
    while True:
        nxt = get_next_stage(PROJECTS_DIR, pid, PIPELINE)
        if nxt in (None, "publish"):
            break
        log(f"=== {pid}: stage {nxt}")
        if nxt == "judge":
            verdict = stage_judge(pid)
            if verdict["verdict"] == "REJECT" and verdict["version"] == 1:
                log("=== revision round")
                revise(pid)
                if _latest_version(pid) == 2:
                    verdict = stage_judge(pid)
            marker = read_json(project_dir(pid) / "project.json")
            marker["status"] = "judged" if verdict["verdict"] == "PASS" else "rejected"
            marker["verdict"] = verdict["verdict"]
            write_json(project_dir(pid) / "project.json", marker)
            break
        _ckpt(pid, nxt, "in_progress", {})
        STAGES[nxt](pid)
    log(f"done: {pid} spend {budget.spent(project_dir(pid)):.2f} USD")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["run", "stage", "judge", "revise", "status"])
    ap.add_argument("name", nargs="?")
    ap.add_argument("--date", default=kuwait_now().strftime("%Y-%m-%d"))
    a = ap.parse_args()
    pid = reel_id(a.date)
    if a.command == "run":
        return run(a.date)
    if a.command == "stage":
        init_project(pid, title=f"Kuwait Legal Insider — {a.date}", pipeline_type=PIPELINE)
        _ckpt(pid, a.name, "in_progress", {})
        STAGES[a.name](pid)
        return 0
    if a.command == "judge":
        return 0 if stage_judge(pid)["verdict"] == "PASS" else 1
    if a.command == "revise":
        revise(pid)
        return 0
    if a.command == "status":
        print(json.dumps({"project": pid, "next_stage": get_next_stage(PROJECTS_DIR, pid, PIPELINE) if project_dir(pid).exists() else "not started",
                          "budget": budget.snapshot(project_dir(pid)) if project_dir(pid).exists() else None,
                          "marker": read_json(project_dir(pid) / "project.json", {})}, indent=2, ensure_ascii=False))
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())

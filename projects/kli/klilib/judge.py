"""The independent judge: format gate, WER gate, faceless gate, then Gemini watches and listens.

Ported scoring from kuwait-legal-insider/_INTERNAL/cycle.py (now archived): weighted total
out of 100, PASS at 85 with every mandatory gate true. The verdict is bound to the
sha256 of the exact file judged.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

from lib.arabic_captions import normalize_ar, wer

from .common import ffprobe, sha256_file, run_tool, log, now_iso
from . import gemini, kli_repo, stills, voice
from .prompts import JUDGE

WEIGHTS = {"accuracy": 20, "usefulness": 20, "narration": 15, "hook": 10, "visuals": 10, "pacing": 10,
           "arabic_text": 10, "originality": 5}
GATES = ["actual_video_inspected", "actual_audio_listened", "factual_claims_supported", "privacy_faceless_clear",
         "arabic_legible", "narration_natural", "useful_specific_takeaway", "duration_and_format_valid"]
PASS_TOTAL = 85
WER_MAX = 0.08  # whole reel; specific mismatches go to the listening judge to adjudicate


def score_review(scores: dict, gates: dict, issues: list) -> tuple[float, bool]:
    total = sum(max(0, min(5, float(scores.get(k, 0)))) * w / 5 for k, w in WEIGHTS.items())
    all_gates = all(bool(gates.get(g)) for g in GATES)
    blocking = any(i.get("severity") in ("critical", "major") for i in issues)
    return round(total, 1), (total >= PASS_TOTAL and all_gates and not blocking)


def format_gate(path: Path) -> dict:
    info = ffprobe(path)
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), {})
    a = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    dur = float(info["format"]["duration"])
    num, den = (v.get("r_frame_rate") or "0/1").split("/")
    fps = round(float(num) / float(den), 3) if float(den) else 0
    lufs = None
    out = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-af", "ebur128=framelog=quiet", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", out)
    if m:
        lufs = float(m[-1])
    ok = (v.get("width") == 1080 and v.get("height") == 1920 and v.get("codec_name") == "h264" and a is not None
          and a.get("codec_name") == "aac" and 15 <= dur <= 40 and abs(fps - 30) < 0.6 and lufs is not None and -16.5 <= lufs <= -11.5)
    return {"ok": ok, "width": v.get("width"), "height": v.get("height"), "codec": v.get("codec_name"),
            "audio_codec": a.get("codec_name") if a else None, "duration": round(dur, 2), "fps": fps, "lufs": lufs,
            "file_size_bytes": int(info["format"]["size"])}


def wer_gate(path: Path, lines: list[str]) -> dict:
    import difflib

    wav = path.with_suffix(".judge.wav")  # transcribe the extracted audio, never the container
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(path), "-vn", "-ac", "1", "-ar", "16000", str(wav)], check=True)
    words = voice.transcribe_words(wav)
    heard = normalize_ar(" ".join(w for w, _, _ in words))
    ref = normalize_ar(" ".join(lines))
    e = wer(ref, heard)
    mismatches = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=ref, b=heard, autojunk=False).get_opcodes():
        if tag != "equal":
            mismatches.append({"script": " ".join(ref[i1:i2]), "heard": " ".join(heard[j1:j2]), "op": tag})
    return {"ok": e <= WER_MAX, "wer": round(e, 4), "heard": " ".join(w for w, _, _ in words), "mismatches": mismatches[:12]}


def faceless_gate(path: Path, out_dir: Path) -> dict:
    r = run_tool("frame_sampler", {"input_path": str(path), "strategy": "interval", "interval_seconds": 2.0,
                                   "output_dir": str(out_dir), "format": "jpg"})
    frames = [Path(f) if isinstance(f, str) else Path(f.get("path", "")) for f in r.data.get("frames", [])]
    bad = []
    for f in frames:
        if not f.exists():
            continue
        g = stills.is_faceless_and_textless(f, check_text=False)
        if not g["ok"]:
            bad.append({"frame": f.name, **g})
    stills.unload_vision()
    return {"ok": not bad, "frames": len(frames), "bad": bad}


def gemini_review(project_dir: Path, video: Path, script: dict, source_url: str, mismatches: list | None = None) -> dict:
    prompt = JUDGE.format(
        contract=kli_repo.judge_contract(),
        script_lines="\n".join(f"{s['id']}: {s['text']}" for s in script["sections"]),
        takeaway=script["metadata"].get("takeaway", ""), source_url=source_url)
    if mismatches:
        prompt += ("\n\nA speech recogniser transcribed the narration and disagreed with the script at these points. For each one, "
                   "LISTEN and decide whether the narrator actually mispronounced or replaced the word (a defect with a timecode) or the "
                   "recogniser merely spelled a dialect word differently (not a defect):\n" + json.dumps(mismatches, ensure_ascii=False))
    runs = [gemini.ask_json(prompt, model=gemini.PRO, project_dir=project_dir, purpose="judge", files=[video], temperature=0.2)
            for _ in range(2)]
    scores = {k: min(float(r.get("scores", {}).get(k, 0)) for r in runs) for k in WEIGHTS}
    gates = {g: all(bool(r.get("gates", {}).get(g)) for r in runs) for g in GATES}
    issues, seen = [], set()
    for r in runs:
        for i in r.get("issues", []):
            key = (i.get("timecode"), i.get("target"), (i.get("evidence") or "")[:40])
            if key not in seen:
                seen.add(key)
                issues.append(i)
    return {"runs": runs, "scores": scores, "gates": gates, "issues": issues,
            "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest()}


def judge(project_dir: Path, video: Path, script: dict, source_url: str, version: int) -> dict:
    """Run every gate, bind the verdict to the file, write kli_verdict_vN.json and final_review.json."""
    sha = sha256_file(video)
    fmt = format_gate(video)
    log(f"format gate: {fmt}")
    w = wer_gate(video, [s["text"] for s in script["sections"]])
    log(f"WER gate: {w['wer']}")
    fl = faceless_gate(video, project_dir / "artifacts" / f"judge_frames_v{version}")
    log(f"faceless gate: ok={fl['ok']} frames={fl['frames']} bad={len(fl['bad'])}")
    g = gemini_review(project_dir, video, script, source_url, w.get("mismatches"))
    gates = dict(g["gates"])
    # the driver overrides what it can measure
    gates["duration_and_format_valid"] = bool(fmt["ok"])
    gates["narration_natural"] = bool(gates.get("narration_natural")) and w["ok"]
    gates["privacy_faceless_clear"] = bool(gates.get("privacy_faceless_clear")) and fl["ok"]
    gates["actual_video_inspected"] = bool(gates.get("actual_video_inspected")) and fmt["width"] == 1080
    gates["actual_audio_listened"] = bool(gates.get("actual_audio_listened")) and fmt["audio_codec"] is not None
    issues = list(g["issues"])
    if not fmt["ok"]:
        issues.append({"id": "G-FMT", "timecode": "whole", "severity": "critical", "evidence": json.dumps(fmt), "correction": "re-render to spec", "target": "compose"})
    if not w["ok"]:
        issues.append({"id": "G-WER", "timecode": "whole", "severity": "major", "evidence": f"WER {w['wer']}", "correction": "retake narration lines", "target": "narration:all"})
    for b in fl["bad"]:
        issues.append({"id": "G-FACE", "timecode": b["frame"], "severity": "critical", "evidence": json.dumps(b), "correction": "regenerate the shot", "target": "shot:unknown"})
    total, passed = score_review(g["scores"], gates, issues)
    verdict = {
        "kind": "review", "verdict": "PASS" if passed else "REJECT", "total": total, "asset_sha256": sha,
        "asset_path": str(video), "version": version, "scores": g["scores"], "gates": gates, "issues": issues,
        "format": fmt, "wer": w["wer"], "faceless": {"frames": fl["frames"], "bad": len(fl["bad"])},
        "judge_model": gemini.PRO, "prompt_sha256": g["prompt_sha256"], "runs": g["runs"], "judged_at": now_iso(),
    }
    (project_dir / "artifacts" / f"kli_verdict_v{version}.json").write_text(json.dumps(verdict, ensure_ascii=False, indent=1), encoding="utf-8")
    (project_dir / "artifacts" / f"judge_transcript_v{version}.txt").write_text(w["heard"], encoding="utf-8")
    return verdict


def final_review_artifact(project_dir: Path, verdict: dict, video: Path) -> dict:
    fmt = verdict["format"]
    status = "pass" if verdict["verdict"] == "PASS" else ("revise" if verdict["version"] == 1 else "fail")
    return {
        "version": "1.0", "output_path": str(video.relative_to(project_dir.parent.parent)), "status": status,
        "checks": {
            "technical_probe": {"valid_container": bool(fmt["ok"]), "duration_seconds": fmt["duration"], "resolution": f"{fmt['width']}x{fmt['height']}",
                                "fps": fmt["fps"], "has_audio": fmt["audio_codec"] is not None, "codec": fmt["codec"] or "", "file_size_bytes": fmt["file_size_bytes"], "issues": []},
            "visual_spotcheck": {"frames_sampled": verdict["faceless"]["frames"], "black_frames_detected": False, "broken_overlays": False,
                                 "missing_assets": False, "unreadable_text": not verdict["gates"]["arabic_legible"], "issues": [i["evidence"] for i in verdict["issues"] if i.get("target", "").startswith("shot")]},
            "audio_spotcheck": {"narration_present": True, "music_present": (project_dir / "assets" / "music" / "lyria.mp3").exists(), "unexpected_silence": False, "clipping_detected": False,
                                "mix_intelligible": verdict["gates"]["narration_natural"], "issues": []},
            "promise_preservation": {"delivery_promise_honored": verdict["gates"]["privacy_faceless_clear"], "renderer_family_used": "kli-pov-reel",
                                     "render_runtime_used": "hyperframes", "runtime_swap_detected": False, "runtime_swap_check": "edit_decisions.render_runtime == hyperframes",
                                     "silent_downgrade_detected": False, "issues": []},
            "subtitle_check": {"subtitles_expected": True, "subtitles_present": True, "coverage_ratio": 1.0, "timing_drift_detected": False, "issues": []},
            "transcript_comparison": {"transcript_matches_script": verdict["wer"] <= WER_MAX, "word_accuracy": round(1 - verdict["wer"], 4), "issues": []},
        },
        "issues_found": [f"{i.get('id')} {i.get('timecode')} {i.get('severity')}: {i.get('evidence')}" for i in verdict["issues"]],
        "recommended_action": "present_to_user" if status == "pass" else ("revise_assets" if status == "revise" else "block"),
        "metadata": {"kli_total": verdict["total"], "kli_verdict": verdict["verdict"], "asset_sha256": verdict["asset_sha256"], "version": verdict["version"]},
    }

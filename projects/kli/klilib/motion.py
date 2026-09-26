"""Veo image-to-video for each still, then fit every clip to its narration span."""
from __future__ import annotations

import subprocess
from pathlib import Path

from .common import run_tool, media_duration, log
from . import budget, stills

CLIP_SECONDS = 6
VEO_USD_PER_SECOND_SILENT = 0.40  # tools/video/veo_video.py 1080p base rate; the tool reports actual
MAX_SLOWDOWN = 1.6


def generate_clip(project_dir: Path, shot_id: str, still: Path, motion_prompt: str, seed: int) -> tuple[Path | None, dict]:
    out = project_dir / "assets" / "video" / f"{shot_id}.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        return out, {"cached": True}
    prompt = (f"{motion_prompt} Real handheld phone footage, natural daylight, subtle hand and camera movement only. "
              f"Keep everything exactly as in the image: same hands, watch, cufflinks, devices, no new objects. "
              f"No face, no person entering the frame, no text.")
    negative = stills.negative() + ", cinematic grade, camera cuts, zoom, morphing, extra fingers"
    errors = []
    for s in (seed, seed + 1):
        budget.assert_can_spend(project_dir, CLIP_SECONDS * VEO_USD_PER_SECOND_SILENT, f"veo_video {shot_id}")
        log(f"{shot_id}: veo image_to_video seed {s}")
        r = run_tool_safe("veo_video", {
            "prompt": prompt, "backend": "google", "operation": "image_to_video", "image_path": str(still),
            "duration": f"{CLIP_SECONDS}s", "aspect_ratio": "9:16", "resolution": "1080p", "generate_audio": False,
            "negative_prompt": negative, "seed": s, "output_path": str(out)})
        if r is None:
            errors.append(f"seed {s} failed")
            continue
        if out.exists() and media_duration(out) >= 3.0:
            return out, {"seed": s, "cost_usd": r.cost_usd}
        errors.append(f"seed {s}: no usable output")
    return None, {"fallback": "still", "errors": errors}


def run_tool_safe(name, inputs):
    try:
        return run_tool(name, inputs)
    except Exception as exc:  # a provider failure is a retry, not a crash
        log(f"{name}: {exc}")
        return None


def fit_clip(src: Path | None, still: Path, dst: Path, span: float) -> str:
    """Make a clip exactly `span` seconds long at 1080x1920/30fps.

    Video: trim if long; slow down up to 1.6x if short; hold the last frame for the rest.
    Still fallback: a slow push-in on the still for the whole span.
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    vf_scale = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30,format=yuv420p"
    if src is None:
        frames = int(span * 30) + 1
        vf = (f"scale=1296:2304,zoompan=z='min(zoom+0.0006,1.2)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps=30,"
              f"format=yuv420p")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-i", str(still), "-t", f"{span:.3f}", "-vf", vf,
                        "-an", "-c:v", "libx264", "-crf", "17", "-preset", "medium", str(dst)], check=True)
        return "still"
    d = media_duration(src)
    if d >= span:
        vf = vf_scale
    else:
        factor = min(span / d, MAX_SLOWDOWN)
        vf = f"setpts={factor:.4f}*PTS,{vf_scale},tpad=stop_mode=clone:stop_duration={max(0.0, span - d * factor) + 0.5:.3f}"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vf", vf, "-t", f"{span:.3f}", "-an",
                    "-c:v", "libx264", "-crf", "17", "-preset", "medium", str(dst)], check=True)
    return "slowed" if d < span else "trimmed"

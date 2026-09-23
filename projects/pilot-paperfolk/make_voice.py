"""Narrate the pilot with ElevenLabs, one file per line plus the full track.

Per-line files give the composition real scene durations instead of guesses:
each scene lasts exactly as long as its own line, plus a small breath.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from tools.audio.elevenlabs_tts import ElevenLabsTTS

BREATH = 0.45  # seconds of silence after each line
PROJECT = Path("projects/pilot-paperfolk")
VOICE = {"stability": 0.45, "similarity_boost": 0.8, "style": 0.15, "speed": 0.95}


def duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", str(path)], capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def main() -> None:
    script = json.loads((PROJECT / "script.json").read_text(encoding="utf-8"))
    audio_dir = PROJECT / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    tts = ElevenLabsTTS()

    timings, parts = [], []
    start = 0.0
    for scene in script["scenes"]:
        dest = audio_dir / f'{scene["id"]}.mp3'
        result = tts.execute({"text": scene["line"], "output_path": str(dest), **VOICE})
        if not result.success:
            raise SystemExit(f'{scene["id"]}: {result.error}')
        seconds = duration(dest)
        timings.append({"id": scene["id"], "start": round(start, 3),
                        "duration": round(seconds + BREATH, 3), "line": scene["line"]})
        start += seconds + BREATH
        parts.append(dest)
        print(f'{scene["id"]}: {seconds:.2f}s')

    # one continuous track, with the same breaths between lines
    list_file = audio_dir / "concat.txt"
    silence = audio_dir / "breath.mp3"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                    "-i", f"anullsrc=r=44100:cl=mono", "-t", str(BREATH), str(silence)], check=True)
    lines = []
    for part in parts:
        lines += [f"file '{part.resolve()}'", f"file '{silence.resolve()}'"]
    list_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    narration = PROJECT / "narration.mp3"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat",
                    "-safe", "0", "-i", str(list_file), "-c", "copy", str(narration)], check=True)

    (PROJECT / "timing.json").write_text(json.dumps(
        {"total": round(start, 3), "scenes": timings}, indent=2), encoding="utf-8")
    print(f"narration {duration(narration):.2f}s -> {narration}")


if __name__ == "__main__":
    main()

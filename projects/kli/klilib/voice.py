"""Narration: one signed ElevenLabs voice, one line per script section, word-timed by Whisper.

Per-line synthesis (not one long read) so a single bad line can be retaken
without re-rendering the others, and so every line carries its own WER.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from lib.arabic_captions import normalize_ar, wer, chunks_from_words, to_latin_digits

from .common import SERIES_DIR, read_json, run_tool, media_duration, log
from . import budget

WER_MAX = 0.10  # per line: at most one substitution in a 10-word line; the listening judge adjudicates the specific word
GAP_DEFAULT = 0.55
GAP_BEFORE_LAST = 0.85
TAIL = 2.4  # end card after the last word
ELEVENLABS_USD_PER_CHAR = 0.0003  # Creator tier estimate; the tool reports its own figure


def voice_pick() -> dict:
    pick = read_json(SERIES_DIR / "voice" / "pick.json")
    if not pick.get("signed_by"):
        raise RuntimeError("voice/pick.json is not signed by the owner — casting is not accepted yet")
    return pick


_whisper = None


def whisper():
    global _whisper
    if _whisper is None:
        from faster_whisper import WhisperModel

        _whisper = WhisperModel("large-v3", device="cuda", compute_type="float16")
    return _whisper


def transcribe_words(path: Path) -> list[tuple[str, float, float]]:
    segs, _ = whisper().transcribe(str(path), language="ar", word_timestamps=True, beam_size=5,
                                   condition_on_previous_text=False)
    return [(w.word.strip(), float(w.start), float(w.end)) for s in segs for w in s.words]


def trim_silence(src: Path, dst: Path) -> None:
    subprocess.run([
        "ffmpeg", "-v", "error", "-y", "-i", str(src), "-af",
        "silenceremove=start_periods=1:start_threshold=-45dB,areverse,"
        "silenceremove=start_periods=1:start_threshold=-45dB,areverse,"
        "afade=t=in:d=0.02,apad=pad_dur=0.08,aresample=48000",
        "-ac", "1", str(dst)], check=True)


def synth_line(project_dir: Path, idx: int, text: str, pick: dict, retake: bool = False) -> Path:
    vo = project_dir / "assets" / "audio" / "vo"
    vo.mkdir(parents=True, exist_ok=True)
    raw = vo / f"l{idx:02d}.raw.mp3"
    if raw.exists() and not retake:
        return raw
    budget.assert_can_spend(project_dir, len(text) * ELEVENLABS_USD_PER_CHAR, f"elevenlabs_tts line {idx}")
    settings = pick.get("settings", {})
    run_tool("elevenlabs_tts", {
        "text": text, "voice_id": pick["voice_id"], "model_id": pick.get("model_id", "eleven_multilingual_v2"),
        "stability": settings.get("stability", 0.45), "similarity_boost": settings.get("similarity_boost", 0.8),
        "style": settings.get("style", 0.25), "speed": settings.get("speed", 1.0),
        "output_path": str(raw), "output_format": "mp3_44100_192",
    })
    return raw


def build_narration(project_dir: Path, lines: list[str], caption_chunks: list[list[str]]) -> dict:
    """Synthesize, verify and assemble the narration. Returns the timeline dict."""
    pick = voice_pick()
    vo = project_dir / "assets" / "audio" / "vo"
    vo.mkdir(parents=True, exist_ok=True)
    durations, words_per_line, wers = [], [], []
    for i, text in enumerate(lines, 1):
        text = to_latin_digits(text)
        wav = vo / f"l{i:02d}.wav"
        best = None
        for attempt in range(2):
            raw = synth_line(project_dir, i, text, pick, retake=attempt > 0)
            trim_silence(raw, wav)
            words = transcribe_words(wav)
            heard = normalize_ar(" ".join(w for w, _, _ in words))
            ref = normalize_ar(text)
            e = wer(ref, heard)
            log(f"line {i} attempt {attempt + 1}: WER {e:.3f} ({len(heard)}/{len(ref)} words)")
            if best is None or e < best[0]:
                best = (e, words)
            if e <= WER_MAX and len(heard) == len(ref):
                break
        e, words = best
        if e > WER_MAX:
            raise RuntimeError(f"line {i} narration WER {e:.3f} > {WER_MAX} after a retake: {text}")
        durations.append(round(media_duration(wav), 3))
        words_per_line.append(words)
        wers.append(round(e, 4))

    starts, t = [], 0.0
    n = len(lines)
    for i, d in enumerate(durations):
        t += GAP_BEFORE_LAST if i == n - 1 else GAP_DEFAULT
        starts.append(round(t, 3))
        t += d
    total = round(t + TAIL, 2)

    chunks = []
    for i, (st, chs) in enumerate(zip(starts, caption_chunks)):
        chunks += chunks_from_words(chs, words_per_line[i], offset=st)

    ins, flt = [], []
    for i, st in enumerate(starts):
        ins += ["-i", str(vo / f"l{i + 1:02d}.wav")]
        ms = int(st * 1000)
        flt.append(f"[{i}]adelay={ms}|{ms}[a{i}]")
    flt.append("".join(f"[a{i}]" for i in range(n)) + f"amix=inputs={n}:normalize=0,apad=whole_dur={total}[o]")
    master = vo / "vo_master.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", *ins, "-filter_complex", ";".join(flt), "-map", "[o]",
                    "-ar", "48000", "-ac", "1", str(master)], check=True)
    timeline = {"starts": starts, "durations": durations, "total": total, "chunks": chunks,
                "wer_per_line": wers, "wer_max": max(wers), "voice_id": pick["voice_id"],
                "voice_sha256": pick.get("sample_sha256"), "master": str(master)}
    (vo / "timeline.json").write_text(json.dumps(timeline, ensure_ascii=False, indent=1), encoding="utf-8")
    return timeline

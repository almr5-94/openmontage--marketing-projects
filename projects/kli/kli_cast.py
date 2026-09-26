#!/usr/bin/env python
"""Cast the narrator once: male Arabic ElevenLabs voices, scored by Whisper WER and Gemini, ranked, then signed by the owner.

    .venv/bin/python projects/kli/kli_cast.py run [--max 8]
    .venv/bin/python projects/kli/kli_cast.py sign <voice_key> --by "<owner name>"

Ported from projects/sard-sept-ted-ad/assets/audio/cast2.py and rank.py.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from klilib.common import SERIES_DIR, run_tool, sha256_file, now_iso, log  # noqa: E402
from klilib import gemini, voice  # noqa: E402
from lib.arabic_captions import normalize_ar, wer  # noqa: E402

CAST = SERIES_DIR / "voice" / "casting"
TEST_LINES = [
    "تحس إن العقد واضح؟ الشرط اللي يغيّر كل شي مو مكتوب بالصفحة الأولى.",
    "المادة 1 تعطيك القاعدة، بس المادة 12 تحدد متى ما تنطبق.",
    "شوف التاريخ اللي بداخل الملف، مو التاريخ اللي مكتوب على الغلاف.",
]
JUDGE = """You are judging candidate narrators for a Kuwaiti legal-understanding reel account. The narrator must be ONE
adult male Kuwaiti/Gulf Arabic speaker: confident, warm, natural, not a news anchor, not a children's storyteller,
not robotic. Listen to the whole clip. Reply with JSON:
{"gulf_kuwaiti_accent": 1-10, "register": "kuwaiti_conversational|msa_bulletin|mixed|other", "sounds_adult_male": true/false,
 "naturalness": 1-10, "warmth": 1-10, "glitches": ["..."], "mispronounced": ["..."], "verdict": "accept|maybe|reject", "why": "one sentence"}"""


def _shared(h: dict, **params) -> list[dict]:
    r = requests.get("https://api.elevenlabs.io/v1/shared-voices", headers=h, params={"page_size": 30, **params}, timeout=30)
    return r.json().get("voices", []) if r.ok else []


def candidates(max_n: int) -> list[dict]:
    """Native Arabic male voices first: Kuwaiti by name/accent, then Gulf, then Saudi, then any
    non-premade Arabic male voice already in the library. Stock English library voices are excluded —
    round 1 showed they all score the same on accent and none is Kuwaiti."""
    key = os.environ["ELEVENLABS_API_KEY"]
    h = {"xi-api-key": key}
    pools = [
        [v for v in _shared(h, search="kuwait") if v.get("gender") == "male"],
        [v for v in _shared(h, language="ar", gender="male", accent="gulf") if v.get("accent") == "gulf"],
        sorted([v for v in _shared(h, language="ar", gender="male", accent="saudi")], key=lambda v: -(v.get("cloned_by_count") or 0))[:3],
    ]
    out, seen = [], set()
    for pool in pools:
        for v in sorted(pool, key=lambda v: -(v.get("cloned_by_count") or 0)):
            if v["voice_id"] in seen:
                continue
            seen.add(v["voice_id"])
            out.append({"key": "el_" + v["name"].split(" - ")[0].split(" – ")[0].lower().replace(" ", "_"), "voice_id": v["voice_id"], "name": v["name"],
                        "labels": {"accent": v.get("accent"), "age": v.get("age")}, "source": "shared", "public_owner_id": v.get("public_owner_id")})
    mine = requests.get("https://api.elevenlabs.io/v1/voices", headers=h, timeout=30).json().get("voices", [])
    for v in mine:
        lab = {k.lower(): str(x).lower() for k, x in (v.get("labels") or {}).items()}
        if v.get("category") == "premade" or v["voice_id"] in seen:
            continue
        if lab.get("gender") == "male" and ("arab" in json.dumps(lab) or "kuwait" in v["name"].lower() or "salem" in v["name"].lower()):
            seen.add(v["voice_id"])
            out.append({"key": "el_" + v["name"].split(" - ")[0].lower().replace(" ", "_"), "voice_id": v["voice_id"], "name": v["name"], "labels": lab, "source": "library"})
    return out[:max_n]


def run(max_n: int) -> None:
    CAST.mkdir(parents=True, exist_ok=True)
    cands = candidates(max_n)
    log(f"{len(cands)} candidate voices")
    ref = normalize_ar(" ".join(TEST_LINES))
    results = []
    for c in cands:
        for model_id in ("eleven_multilingual_v2", "eleven_v3"):
            key = f"{c['key']}__{model_id.split('_')[1]}"
            mp3 = CAST / f"{key}.mp3"
            try:
                if not mp3.exists():
                    if c["source"] == "shared":  # shared voices must be added to the library first
                        _ = requests.post(f"https://api.elevenlabs.io/v1/voices/add/{c['public_owner_id']}/{c['voice_id']}", headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"]},
                                      json={"new_name": c["name"]}, timeout=30)
                    run_tool("elevenlabs_tts", {"text": " ".join(TEST_LINES), "voice_id": c["voice_id"], "model_id": model_id, "stability": 0.45,
                                                "similarity_boost": 0.8, "style": 0.25, "output_path": str(mp3), "output_format": "mp3_44100_192"})
                words = voice.transcribe_words(mp3)
                e = wer(ref, normalize_ar(" ".join(w for w, _, _ in words)))
                g = gemini.ask_json(JUDGE, model=gemini.PRO, files=[mp3], purpose="casting", temperature=0.2)
                row = {"key": key, "voice_id": c["voice_id"], "name": c["name"], "model_id": model_id, "wer": round(e, 4), "gemini": g, "sample": str(mp3), "sample_sha256": sha256_file(mp3)}
                log(f"{key}: WER {e:.3f} accent {g.get('gulf_kuwaiti_accent')} register {g.get('register')} verdict {g.get('verdict')}")
            except Exception as exc:
                row = {"key": key, "voice_id": c["voice_id"], "name": c["name"], "model_id": model_id, "error": str(exc)[:200]}
                log(f"{key}: {exc}")
            results.append(row)
    ok = [r for r in results if "error" not in r and r["gemini"].get("sounds_adult_male") and r["gemini"].get("verdict") != "reject"]
    # WER first (it is the only measurement that discriminated in round 1), then the listening scores
    ok.sort(key=lambda r: (round(r["wer"], 2), -(r["gemini"].get("naturalness", 0) + r["gemini"].get("warmth", 0) + r["gemini"].get("gulf_kuwaiti_accent", 0))))
    (SERIES_DIR / "voice" / "casting.json").write_text(json.dumps({"cast_at": now_iso(), "test_lines": TEST_LINES, "results": results, "ranked": [r["key"] for r in ok]}, ensure_ascii=False, indent=1), encoding="utf-8")
    if ok:
        top = ok[0]
        (SERIES_DIR / "voice" / "pick.json").write_text(json.dumps({"voice_key": top["key"], "voice_id": top["voice_id"], "name": top["name"], "model_id": top["model_id"],
                                                                     "settings": {"stability": 0.45, "similarity_boost": 0.8, "style": 0.25, "speed": 1.0},
                                                                     "wer": top["wer"], "scores": top["gemini"], "sample": top["sample"], "sample_sha256": top["sample_sha256"],
                                                                     "signed_by": None, "signed_at": None, "note": "unsigned proposal — the owner signs with kli_cast.py sign"},
                                                                    ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"top 3: {[r['key'] for r in ok[:3]]}")


def sign(voice_key: str, by: str) -> None:
    cast = json.loads((SERIES_DIR / "voice" / "casting.json").read_text(encoding="utf-8"))
    row = next((r for r in cast["results"] if r.get("key") == voice_key and "error" not in r), None)
    if not row:
        raise SystemExit(f"unknown or failed voice {voice_key}")
    pick = {"voice_key": row["key"], "voice_id": row["voice_id"], "name": row["name"], "model_id": row["model_id"],
            "settings": {"stability": 0.45, "similarity_boost": 0.8, "style": 0.25, "speed": 1.0}, "wer": row["wer"], "scores": row["gemini"],
            "sample": row["sample"], "sample_sha256": row["sample_sha256"], "signed_by": by, "signed_at": now_iso()}
    (SERIES_DIR / "voice" / "pick.json").write_text(json.dumps(pick, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"signed {voice_key} by {by}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["run", "sign"])
    ap.add_argument("voice", nargs="?")
    ap.add_argument("--by", default="")
    ap.add_argument("--max", type=int, default=8)
    a = ap.parse_args()
    run(a.max) if a.command == "run" else sign(a.voice, a.by)

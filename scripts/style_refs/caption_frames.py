"""Write a training caption next to every cleaned reference frame.

Usage:
    python -m scripts.style_refs.caption_frames assets/references/ted-ed [--model qwen2.5vl:7b]

A style LoRA learns "the look" from what the captions do NOT say: the captions
describe the subject and the layout, and the style itself is carried by the
trigger word, which stays constant. Each frame gets

    tededstyle, <substyle>, <one line about the subject>

and lands in <ref>/dataset/<video>_<frame>.txt next to a copy of the image, the
folder layout kohya sd-scripts expects.

Captions come from a vision model served by the local Ollama (no network, no
API cost). Frames whose caption fails are copied with a plain fallback caption.
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import shutil
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

OLLAMA = "http://localhost:11434/api/generate"
TRIGGER = "tededstyle"

# One reference video per sub-style: they were drawn by different illustrators,
# so a single averaged look would lose all three.
SUBSTYLE = {
    "ted-ed1": "flat character scene",
    "ted-ed2": "black silhouette myth scene",
    "ted-ed3": "textured nature scene",
}

PROMPT = (
    "Describe only WHAT is in this illustration in one short line: the subject, how many "
    "figures, what they are doing, and the layout (centred, left, wide shot, close up). "
    "Do not describe the art style, colours, texture, mood or quality. No full sentences, "
    "no preamble, under 20 words."
)

BANNED = re.compile(r"\b(cartoon|illustration|flat|minimalist|style|hand-drawn|vector|drawing|artwork|image)\b", re.I)


def caption(path: Path, model: str, timeout: int = 180) -> str:
    body = json.dumps({
        "model": model,
        "prompt": PROMPT,
        "images": [base64.b64encode(path.read_bytes()).decode()],
        "stream": False,
        "options": {"temperature": 0.2, "num_predict": 60, "seed": 7},
    }).encode()
    req = urllib.request.Request(OLLAMA, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        text = json.loads(r.read())["response"]
    text = " ".join(text.split()).strip(" .\"'")
    text = BANNED.sub("", text)
    return " ".join(text.split())[:180]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("ref_dir", type=Path)
    ap.add_argument("--model", default="qwen2.5vl:7b")
    ap.add_argument("--workers", type=int, default=2)
    args = ap.parse_args()

    clean = args.ref_dir / "clean"
    dataset = args.ref_dir / "dataset"
    dataset.mkdir(parents=True, exist_ok=True)
    for old in dataset.glob("*"):
        old.unlink()

    frames = sorted(p for p in clean.glob("*.png"))
    failures = []

    def one(p: Path) -> None:
        video = p.stem.rsplit("_", 1)[0]
        sub = SUBSTYLE.get(video, "scene")
        try:
            desc = caption(p, args.model)
        except Exception as exc:  # noqa: BLE001 - fall back, never lose a frame
            failures.append(f"{p.name}: {exc}")
            desc = sub
        shutil.copy2(p, dataset / p.name)
        (dataset / f"{p.stem}.txt").write_text(f"{TRIGGER}, {sub}, {desc}\n", encoding="utf-8")

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(one, frames))

    texts = sorted(dataset.glob("*.txt"))
    print(f"captioned {len(texts)} frames into {dataset} ({len(failures)} fell back)")
    for t in texts[:5]:
        print(" ", t.read_text(encoding="utf-8").strip())
    if failures:
        print("failures:", failures[:5])


if __name__ == "__main__":
    main()

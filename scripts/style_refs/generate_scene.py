"""Generate one scene image in a family's style, and check it before accepting it.

Usage:
    python -m scripts.style_refs.generate_scene a "two people shaking hands, centred" \
        --subjects 2 --out renders/scene01.png

Two failures showed up in the acceptance pass that no amount of training fixes,
because they are failures of the base model, not of the style:

  * the count is wrong - "two people" comes back as three
  * any card, sign or label carries gibberish lettering

Both are checkable, so this generator checks them instead of hoping. It renders
with the family adapter, asks the local vision model how many subjects it sees and
whether any lettering is present, and moves to the next seed when the answer is
wrong. Text stays out by design: a label area is left blank and the real words are
typeset in the composition, where they can be spelled correctly and translated.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import urllib.request
from pathlib import Path

import yaml

from tools._comfyui.client import ComfyUIClient

OLLAMA = "http://localhost:11434/api/generate"
WORKFLOW = Path("tools/_comfyui/workflows/sdxl-lora-txt2img.json")
STYLE_DIR = Path("assets/style/handdrawn")
LETTERS = {"a": "A", "b": "B", "c": "C"}
LORA = {"a": "hdx_a_sdxl_v1.safetensors", "b": "hdx_b_sdxl_v1.safetensors",
        "c": "hdx_c_sdxl_v1.safetensors"}
# asking for text is how gibberish gets in; the composition typesets it instead
NO_TEXT = ("text, lettering, words, letters, captions, signage, handwriting, "
           "numbers, watermark, signature")


def ask_vision(image: Path, question: str, model: str = "qwen2.5vl:7b", timeout: int = 180) -> str:
    body = json.dumps({
        "model": model, "prompt": question,
        "images": [base64.b64encode(image.read_bytes()).decode()],
        "stream": False, "options": {"temperature": 0, "num_predict": 8, "seed": 7},
    }).encode()
    req = urllib.request.Request(OLLAMA, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())["response"].strip()


def count_subjects(image: Path, noun: str) -> int | None:
    answer = ask_vision(image, f"How many {noun} are in this picture? Answer with one number only.")
    match = re.search(r"\d+", answer)
    return int(match.group(0)) if match else None


def has_lettering(image: Path) -> bool:
    answer = ask_vision(image, "Does this picture contain any written words or letters? Answer yes or no.")
    return answer.lower().startswith("y")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("family", choices=["a", "b", "c"])
    ap.add_argument("description", help="what the scene shows, in plain words")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--subjects", type=int, help="how many subjects the scene must contain")
    ap.add_argument("--noun", default="people", help="what to count (people, mushrooms, containers)")
    ap.add_argument("--allow-text", action="store_true", help="skip the lettering check")
    ap.add_argument("--seeds", type=int, nargs="+", default=[7, 101, 202, 303, 404, 505])
    ap.add_argument("--strength", type=float, default=0.85)
    args = ap.parse_args()

    letter = LETTERS[args.family]
    playbooks = {"a": "handdrawn-paperfolk", "b": "handdrawn-incise", "c": "handdrawn-biotext"}
    from styles.playbook_loader import load_playbook
    playbook = load_playbook(playbooks[args.family])
    captioning = yaml.safe_load((STYLE_DIR / "captioning.yaml").read_text(encoding="utf-8"))

    prompt = f"{playbook['asset_generation']['image_prompt_prefix'].strip()} {args.description}"
    negative = playbook["asset_generation"]["image_negative_prompt"].strip()
    if not args.allow_text:
        prompt += ", any label area left blank"
        negative += ", " + NO_TEXT
    negative += ", " + captioning["families"][letter]["negative_extension"].strip()

    client = ComfyUIClient(server_url=os.environ.get("COMFYUI_SERVER_URL", "http://127.0.0.1:8188"))
    if not client.is_available():
        raise SystemExit(client.unavailable_reason())
    base = ComfyUIClient.load_workflow(WORKFLOW)
    args.out.parent.mkdir(parents=True, exist_ok=True)

    attempts = []
    for seed in args.seeds:
        workflow = ComfyUIClient.patch_workflow(base, {
            "3": {"text": " ".join(prompt.split())},
            "4": {"text": " ".join(negative.split())},
            "6": {"seed": seed},
            "2": {"lora_name": LORA[args.family],
                  "strength_model": args.strength, "strength_clip": args.strength},
        })
        client.generate(workflow, output_node="9", dest=args.out, timeout=900)
        problems = []
        if args.subjects is not None:
            seen = count_subjects(args.out, args.noun)
            if seen != args.subjects:
                problems.append(f"counted {seen} {args.noun}, wanted {args.subjects}")
        if not args.allow_text and has_lettering(args.out):
            problems.append("lettering appeared")
        attempts.append({"seed": seed, "problems": problems})
        print(f"seed {seed}: " + ("accepted" if not problems else "; ".join(problems)))
        if not problems:
            print(json.dumps({"accepted_seed": seed, "file": str(args.out), "attempts": attempts}))
            return

    print(json.dumps({"accepted_seed": None, "file": str(args.out), "attempts": attempts}))
    raise SystemExit(f"no seed passed the checks for: {args.description}")


if __name__ == "__main__":
    main()

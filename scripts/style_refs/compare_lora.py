"""Render the fixed evaluation set with and without a family's style adapter.

Usage:
    python -m scripts.style_refs.compare_lora a --seeds 7 101 --out docs/handdrawn

For each of the family's five evaluation cases (assets/style/handdrawn/eval-prompts.yaml)
the same prompt and seed is rendered twice - base SDXL, then SDXL plus that family's
LoRA - and the pairs are composed into one sheet. Two renders that differ only by the
adapter are the only honest way to see what the adapter taught; a pretty picture on its
own proves nothing (study 5.7).

Needs a ComfyUI server: bash .ml/serve_comfyui.sh  (then COMFYUI_SERVER_URL=http://127.0.0.1:8188)
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import yaml
from PIL import Image, ImageDraw

from tools._comfyui.client import ComfyUIClient

WORKFLOW = Path("tools/_comfyui/workflows/sdxl-lora-txt2img.json")
STYLE_DIR = Path("assets/style/handdrawn")
LORA_NAMES = {"a": "hdx_a_sdxl_v1.safetensors",
              "b": "hdx_b_sdxl_v1.safetensors",
              "c": "hdx_c_sdxl_v1.safetensors"}
LETTERS = {"a": "A", "b": "B", "c": "C"}


def render(client: ComfyUIClient, base: dict, prompt: str, negative: str, seed: int,
           lora: str | None, dest: Path) -> Path:
    patches = {
        "3": {"text": prompt},
        "4": {"text": negative},
        "6": {"seed": seed},
        "2": {"lora_name": lora or LORA_NAMES["a"],
              "strength_model": 0.85 if lora else 0.0,
              "strength_clip": 0.85 if lora else 0.0},
    }
    workflow = ComfyUIClient.patch_workflow(base, patches)
    client.generate(workflow, output_node="9", dest=dest, timeout=900)
    return dest


def label(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, box_w: int) -> None:
    draw.rectangle([xy[0], xy[1], xy[0] + box_w, xy[1] + 26], fill="white")
    draw.text((xy[0] + 6, xy[1] + 6), text, fill="black")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("family", choices=["a", "b", "c"])
    ap.add_argument("--seeds", type=int, nargs="+", default=[7])
    ap.add_argument("--out", type=Path, default=Path("assets/references/handdrawn/work/compare"))
    ap.add_argument("--strength", type=float, default=0.85)
    args = ap.parse_args()

    cfg = yaml.safe_load((STYLE_DIR / "eval-prompts.yaml").read_text(encoding="utf-8"))
    captioning = yaml.safe_load((STYLE_DIR / "captioning.yaml").read_text(encoding="utf-8"))
    letter = LETTERS[args.family]
    negative = (captioning["universal_negative"] + ", "
                + captioning["families"][letter]["negative_extension"]).replace("\n", " ")

    cases = [c for c in cfg["cases"] if str(c.get("family", "")).upper() == letter]
    if not cases:
        raise SystemExit(f"no evaluation cases for family {letter} in eval-prompts.yaml")

    client = ComfyUIClient(server_url=os.environ.get("COMFYUI_SERVER_URL", "http://127.0.0.1:8188"))
    if not client.is_available():
        raise SystemExit(client.unavailable_reason())
    base = ComfyUIClient.load_workflow(WORKFLOW)

    raw = args.out / f"family-{args.family}"
    raw.mkdir(parents=True, exist_ok=True)
    log: list[dict] = []
    tiles: list[tuple[str, Path, Path]] = []

    for case in cases:
        for seed in args.seeds:
            name = f"{case['id']}_seed{seed}"
            without = raw / f"{name}_base.png"
            with_lora = raw / f"{name}_lora.png"
            started = time.time()
            render(client, base, case["prompt"], negative, seed, None, without)
            render(client, base, case["prompt"], negative, seed, LORA_NAMES[args.family], with_lora)
            log.append({"case": case["id"], "seed": seed, "prompt": case["prompt"],
                        "checks": case.get("checks"), "seconds": round(time.time() - started, 1)})
            tiles.append((f"{case['id']} · seed {seed}", without, with_lora))
            print(f"rendered {name}")

    # one row per case: base on the left, adapter on the right
    tile_w, tile_h = 640, 360
    sheet = Image.new("RGB", (tile_w * 2 + 30, (tile_h + 40) * len(tiles) + 40), "#f2f2f2")
    draw = ImageDraw.Draw(sheet)
    draw.text((12, 12), f"Family {letter} — same prompt, same seed. LEFT: base model. "
                        f"RIGHT: with the {args.family} adapter at {args.strength}.", fill="black")
    for i, (title, left, right) in enumerate(tiles):
        y = 40 + i * (tile_h + 40)
        draw.text((12, y), title, fill="black")
        for j, path in enumerate((left, right)):
            img = Image.open(path).convert("RGB")
            img.thumbnail((tile_w, tile_h))
            x = 10 + j * (tile_w + 10)
            sheet.paste(img, (x, y + 18))
            label(draw, (x, y + 18), "base" if j == 0 else f"adapter {args.family}", 120)
    sheet_path = args.out / f"comparison-family-{args.family}.jpg"
    sheet.save(sheet_path, quality=86)
    (args.out / f"comparison-family-{args.family}.json").write_text(json.dumps(log, indent=2), encoding="utf-8")
    print(f"sheet: {sheet_path} ({len(tiles)} pairs)")


if __name__ == "__main__":
    main()

"""Caption the per-family datasets to the study's captioning contract.

Usage:
    python -m scripts.style_refs.caption_frames assets/references/handdrawn [--family a] [--variant boilerplate]

Follows forensic-illustration-study.md Part 5 Section A:

- one family per dataset, one trigger per family, never two triggers in a caption
- the caption describes what is visible, in the study's field order: framing and
  mode, subject count and type, action, props, arrangement, variable attributes,
  then the family boilerplate last
- a plate with no figure gets the environment-only boilerplate, so the caption
  never claims a construction the picture does not show
- style vocabulary may only come from lexicon.json, and only for that family
- uncertainty stays in the manifest, never in the caption

Two caption variants are produced so the training run can ablate them
(study 5.6): `minimal` is the trigger plus the literal content; `boilerplate`
adds the family's style string. Both are written; `--variant` selects which one
lands in the `.txt` files a trainer reads.

Writes
    <ref>/dataset-<f>/<image>.txt        the selected caption variant
    <ref>/captions-<f>.jsonl             both variants plus the mode, per image
    updates <ref>/dataset-manifest.jsonl with caption, mode and caption_status
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

OLLAMA = "http://localhost:11434/api/generate"

FRAMINGS = ["full-body plate", "medium plate", "wide environment", "close-up", "diagram"]
ARRANGEMENTS = ["centred", "left of centre", "right of centre", "shared baseline",
                "network", "foreground framing", "scattered", "two groups"]

# Asking for free text made the model echo the option list and invent detail, so it
# now fills fixed fields and the caption is assembled here from what it returns.
CONTENT_PROMPT = (
    "Look at this illustration and answer ONLY with JSON, no prose, using exactly these keys:\n"
    '{"framing": one of ' + json.dumps(FRAMINGS) + ',\n'
    ' "subjects": "<how many and what, e.g. two people, one mushroom, six circular containers>",\n'
    ' "action": "<what they are doing or how they relate, 8 words max, or \"none\">",\n'
    ' "props": "<the objects that matter, 8 words max, or \"none\">",\n'
    ' "arrangement": one of ' + json.dumps(ARRANGEMENTS) + '}\n'
    "Rules: describe only what is visible. Never name a real person; describe their appearance "
    "instead. No art style, colours, texture, mood or quality words. No guessing feelings, jobs "
    "or stories. If something is unclear, write \"none\"."
)

MODE_PROMPT = (
    "Answer with ONE word from this list and nothing else: "
    "character_plate, environment, prop, relationship_board, diagram, biological_detail, close_up_face."
)

# style words must come from the lexicon, never from the vision model
STYLE_WORDS = re.compile(
    r"\b(cartoon|illustration|flat|minimalist|style|hand-?drawn|vector|drawing|artwork|image|"
    r"aesthetic|beautiful|detailed|texture[d]?|palette|colou?rful|lighting|render(ed|ing)?)\b", re.I)
# the vision model sometimes guesses; a guess must not become a training label
UNCERTAIN = re.compile(r"[^,]*\b(unknown|unclear|unidentified|possibly|probably|appears?|"
                       r"seems?|maybe|likely|might)\b[^,]*", re.I)
FIGURE_WORDS = re.compile(r"\b(person|people|figure|figures|man|men|woman|women|character|child|"
                          r"warrior|performer|face|hand|silhouette)\b", re.I)


def ask(model: str, prompt: str, image: Path, predict: int, timeout: int = 240,
        attempts: int = 3) -> str:
    """One question about one image. The first call after an idle period has to
    load the model, so a timeout here is normal and is retried rather than
    losing the whole run."""
    body = json.dumps({
        "model": model,
        "prompt": prompt,
        "images": [base64.b64encode(image.read_bytes()).decode()],
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": predict, "seed": 7},
    }).encode()
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            req = urllib.request.Request(OLLAMA, data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())["response"]
        except Exception as exc:  # noqa: BLE001 - network and decode failures are both retryable
            last = exc
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"caption model failed for {image.name}: {last}")


def clean(text: str) -> str:
    text = " ".join(text.split()).strip(" .\"'")
    text = STYLE_WORDS.sub("", text)
    text = UNCERTAIN.sub("", text)
    text = re.sub(r"\s*,\s*,+", ", ", text).strip(" ,")
    return " ".join(text.split())[:120]


def parse_fields(raw: str) -> dict:
    """Read the model's JSON answer, keeping only values it was allowed to give."""
    match = re.search(r"\{.*\}", raw, re.S)
    data = {}
    if match:
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            data = {}
    framing = str(data.get("framing", "")).strip().lower()
    arrangement = str(data.get("arrangement", "")).strip().lower()
    return {
        "framing": framing if framing in FRAMINGS else "",
        "subjects": clean(str(data.get("subjects", ""))),
        "action": clean(str(data.get("action", ""))),
        "props": clean(str(data.get("props", ""))),
        "arrangement": arrangement if arrangement in ARRANGEMENTS else "",
    }


def assemble(fields: dict, extra: str | None) -> str:
    """Caption field order of the study: framing, subject, action, props, arrangement."""
    parts = [fields["framing"], fields["subjects"]]
    for key in ("action", "props"):
        value = fields[key]
        if value and value.lower() not in {"none", "n/a", "unclear"}:
            parts.append(value)
    parts += [fields["arrangement"], extra]
    return ", ".join(p for p in parts if p)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("ref_dir", type=Path)
    ap.add_argument("--family", default="all", help="a, b, c or all")
    ap.add_argument("--variant", default="boilerplate", choices=["boilerplate", "minimal"])
    ap.add_argument("--model", default="qwen2.5vl:7b")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--style-dir", type=Path, default=Path("assets/style/handdrawn"))
    args = ap.parse_args()

    cfg = yaml.safe_load((args.style_dir / "captioning.yaml").read_text(encoding="utf-8"))
    core = cfg["master_core"]
    keys = ["a", "b", "c"] if args.family == "all" else [args.family]
    letters = {"a": "A", "b": "B", "c": "C"}

    manifest_path = args.ref_dir / "dataset-manifest.jsonl"
    manifest = [json.loads(line) for line in manifest_path.read_text(encoding="utf-8").splitlines()]
    by_id = {r["image_id"]: r for r in manifest}

    for key in keys:
        fam = cfg["families"][letters[key]]
        dataset = args.ref_dir / f"dataset-{key}"
        images = sorted(dataset.glob("*.png"))
        if not images:
            print(f"{letters[key]}: no images")
            continue
        rows: list[dict] = []

        def one(path: Path) -> None:
            fields = parse_fields(ask(args.model, CONTENT_PROMPT, path, 160))
            mode = clean(ask(args.model, MODE_PROMPT, path, 8)).lower().replace(" ", "_")[:24]
            if not fields["framing"]:
                fields["framing"] = {"close_up_face": "close-up", "diagram": "diagram",
                                     "environment": "wide environment"}.get(mode, "medium plate")
            has_figure = bool(FIGURE_WORDS.search(fields["subjects"] + " " + fields["action"])) \
                or mode in {"character_plate", "close_up_face"}
            boiler = fam["boilerplate"] if has_figure else fam["environment_only_boilerplate"]
            record = by_id.get(path.stem, {})
            detail = record.get("crop_status") == "detail_crop_of_contaminated_frame"
            framing_note = "detail crop, edges of the original view excluded" if detail else None
            content_full = assemble(fields, framing_note)
            rows.append({
                "image_id": path.stem,
                "mode": mode,
                "fields": fields,
                "has_figure": has_figure,
                "minimal": f"{fam['trigger']}, {content_full}",
                "boilerplate": f"{content_full}, {core}, {boiler.strip()}",
            })

        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            list(pool.map(one, images))

        rows.sort(key=lambda r: r["image_id"])
        with (args.ref_dir / f"captions-{key}.jsonl").open("w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row) + "\n")
        for row in rows:
            (dataset / f"{row['image_id']}.txt").write_text(row[args.variant] + "\n", encoding="utf-8")
            rec = by_id.get(row["image_id"])
            if rec:
                rec.update({"mode": row["mode"], "caption": row[args.variant], "caption_status": f"auto_{args.variant}"})
        env_only = sum(1 for r in rows if not r["has_figure"])
        print(f"{letters[key]} ({fam['name']}): {len(rows)} captions, {env_only} environment-only, "
              f"variant={args.variant}")
        print("   e.g.", rows[0][args.variant][:160])

    with manifest_path.open("w", encoding="utf-8") as fh:
        for record in manifest:
            fh.write(json.dumps(record) + "\n")


if __name__ == "__main__":
    main()

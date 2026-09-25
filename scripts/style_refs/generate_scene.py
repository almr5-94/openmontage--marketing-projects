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


def shows(image: Path, description: str) -> bool:
    """The check that matters: is the thing the line describes actually drawn?

    Counting subjects and rejecting lettering cannot catch a picture that is
    beautifully on-style and shows the wrong idea, which is how a pilot ends up
    as a slideshow of unrelated stills.
    """
    answer = ask_vision(image, f"Does this picture clearly show {description}? Answer yes or no.")
    return answer.lower().startswith("y")


def face_is_whole(image: Path) -> bool:
    """Both eyes drawn, each with a pupil, and one mouth.

    Always run, on every render. A picture with no people passes trivially, and
    a picture with a half-drawn face never reaches a composition. Family A faces
    are two pale ovals with small dark pupils; dropping one pupil reads as a
    broken stare that the count, lettering and meaning checks all miss.
    """
    if ask_vision(image, "Is there a person, face or character in this picture? "
                         "Answer yes or no.").lower().startswith("n"):
        return True
    answers = [
        ask_vision(image, "Does every person in this picture have two eyes, each with a "
                          "visible dark pupil inside it? Answer yes or no."),
        ask_vision(image, "Is any face in this picture distorted, with a missing eye, a missing "
                          "pupil, or a doubled mouth? Answer yes or no."),
    ]
    if not (answers[0].lower().startswith("y") and answers[1].lower().startswith("n")):
        return False
    # then measure: a model happily calls a rim-painted pupil an eye
    geometry = eye_geometry(image)
    if geometry.get("ok") is False:
        return False
    # the mouth: a family A face is a single line or small curve. Measuring the
    # marks under the eyes caught nose and jaw contours too, but the model is
    # reliable on this one narrow question, so ask it.
    if ask_vision(image, "Are any teeth visible in this picture? Answer yes or no."
                  ).lower().startswith("y"):
        return False
    mouth = mouth_is_simple(image, geometry.get("eyes", []))
    return mouth.get("ok") is not False


def eye_geometry(image: Path) -> dict:
    """Measure the eyes instead of asking about them.

    A model will answer "yes, each eye has a pupil" for a pupil painted on the
    rim of the eye white, which reads as a wall-eyed stare. So the pupils are
    located: each eye white must contain a dark blob of real size, sitting away
    from the rim, and the two pupils must sit in roughly the same place within
    their eye, or the character is looking in two directions at once.
    """
    import numpy as np
    from PIL import Image as PILImage

    img = PILImage.open(image).convert("L")
    scale = 900 / img.width
    img = img.resize((900, round(img.height * scale)), PILImage.BILINEAR)
    a = np.asarray(img, dtype=np.uint8)
    h, w = a.shape
    white = a > 232
    dark = a < 90

    # label the white blobs with a simple flood fill; eyes are small and high
    seen = np.zeros_like(white)
    blobs = []
    from collections import deque
    for y in range(int(h * 0.05), int(h * 0.75)):
        for x in range(w):
            if not white[y, x] or seen[y, x]:
                continue
            q, pts = deque([(y, x)]), []
            seen[y, x] = True
            while q:
                cy, cx = q.popleft()
                pts.append((cy, cx))
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ny, nx = cy + dy, cx + dx
                    if 0 <= ny < h and 0 <= nx < w and white[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        q.append((ny, nx))
            if 60 <= len(pts) <= 4000:
                ys = np.array([p_[0] for p_ in pts]); xs = np.array([p_[1] for p_ in pts])
                blobs.append({"area": len(pts), "cy": ys.mean(), "cx": xs.mean(),
                              "y0": ys.min(), "y1": ys.max(), "x0": xs.min(), "x1": xs.max()})

    blobs.sort(key=lambda b: -b["area"])
    eyes = []
    for b in blobs[:8]:
        if len(eyes) == 2:
            break
        # eyes sit side by side at a similar height and similar size
        if eyes and (abs(b["cy"] - eyes[0]["cy"]) > 0.05 * h
                     or not 0.45 <= b["area"] / eyes[0]["area"] <= 2.2):
            continue
        eyes.append(b)
    if len(eyes) < 2:
        return {"eyes_found": len(eyes), "ok": None}

    offsets = []
    for eye in eyes:
        sub = dark[int(eye["y0"]):int(eye["y1"]) + 1, int(eye["x0"]):int(eye["x1"]) + 1]
        if sub.sum() < max(8, 0.04 * eye["area"]):
            return {"eyes_found": 2, "ok": False, "why": "an eye has no pupil"}
        ys, xs = np.nonzero(sub)
        py, px = ys.mean() + eye["y0"], xs.mean() + eye["x0"]
        half_w = max(1.0, (eye["x1"] - eye["x0"]) / 2)
        half_h = max(1.0, (eye["y1"] - eye["y0"]) / 2)
        offsets.append(((px - eye["cx"]) / half_w, (py - eye["cy"]) / half_h))

    for ox, oy in offsets:
        if abs(ox) > 0.55 or abs(oy) > 0.6:
            return {"eyes_found": 2, "ok": False, "why": "a pupil sits on the rim of the eye",
                    "offsets": offsets}
    if abs(offsets[0][0] - offsets[1][0]) > 0.5 or abs(offsets[0][1] - offsets[1][1]) > 0.4:
        # one pupil high and one low is the wall-eyed stare that started all this
        return {"eyes_found": 2, "ok": False, "why": "the two pupils do not match",
                "offsets": offsets}
    return {"eyes_found": 2, "ok": True, "offsets": offsets,
            "eyes": [(e["cy"], e["cx"], e["y1"] - e["y0"], e["x1"] - e["x0"]) for e in eyes]}


def mouth_is_simple(image: Path, eyes: list[tuple[float, float, float, float]]) -> dict:
    """Measures the biggest dark mark under the eyes.

    A family A mouth is one line or a small curve. Counting the marks in this
    band was useless - nose and jaw contours land in it too - but the SIZE of
    the largest mark separates a drawn line from a filled black hole.

    Below the eyes, inside a band the width of the face, the drawing should
    contain one dark mark. A grin full of teeth shows up as many small dark
    pieces, which is what "distorted" never catches.
    """
    from collections import deque

    import numpy as np
    from PIL import Image as PILImage

    if len(eyes) < 2:
        return {"ok": None}
    img = PILImage.open(image).convert("L")
    scale = 900 / img.width
    a = np.asarray(img.resize((900, round(img.height * scale)), PILImage.BILINEAR), dtype=np.uint8)
    h, w = a.shape

    (cy1, cx1, _, _), (cy2, cx2, _, _) = eyes[0], eyes[1]
    span = abs(cx1 - cx2)
    if span < 6:
        return {"ok": None}
    cx = (cx1 + cx2) / 2
    top = int(max(0, (cy1 + cy2) / 2 + span * 0.55))
    bottom = int(min(h, (cy1 + cy2) / 2 + span * 1.5))
    left = int(max(0, cx - span * 0.75))
    right = int(min(w, cx + span * 0.75))
    if bottom - top < 6 or right - left < 6:
        return {"ok": None}

    band = a[top:bottom, left:right] < 95
    seen = np.zeros_like(band)
    pieces = []
    for y in range(band.shape[0]):
        for x in range(band.shape[1]):
            if not band[y, x] or seen[y, x]:
                continue
            q, n = deque([(y, x)]), 0
            seen[y, x] = True
            while q:
                cy_, cx_ = q.popleft()
                n += 1
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)):
                    ny, nx = cy_ + dy, cx_ + dx
                    if 0 <= ny < band.shape[0] and 0 <= nx < band.shape[1] and band[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        q.append((ny, nx))
            if n >= max(6, 0.0006 * band.size):
                pieces.append(n)
    # note: piece COUNT is unreliable here (nose and jaw lines land in the band),
    # so only the size of the largest mark is used as a gate
    # a filled black mouth is the other failure: family A draws a line, not a hole
    biggest = max(pieces) if pieces else 0
    if biggest > 0.05 * span * span:
        return {"ok": False, "why": "the mouth is a filled dark shape, not a line",
                "biggest": biggest, "span": round(span, 1)}
    return {"ok": True, "pieces": len(pieces), "biggest": biggest}


def cut_out(image: Path, tolerance: int = 26) -> None:
    """Key the flat background out of a prop so it can be animated on its own.

    Family A props are drawn on an even paper field, so the background is the
    colour that fills the corners; everything connected to a corner in that
    colour becomes transparent. Anything enclosed by the drawing stays.
    """
    from collections import deque

    import numpy as np
    from PIL import Image as PILImage

    img = PILImage.open(image).convert("RGB")
    a = np.asarray(img).astype(np.int16)
    h, w = a.shape[:2]
    corners = np.array([a[0, 0], a[0, w - 1], a[h - 1, 0], a[h - 1, w - 1]])
    bg = np.median(corners, axis=0)
    near = (np.abs(a - bg).max(axis=2) <= tolerance)

    keep = np.zeros((h, w), dtype=bool)   # background pixels reachable from an edge
    queue = deque()
    for x in range(w):
        for y in (0, h - 1):
            if near[y, x]:
                queue.append((y, x)); keep[y, x] = True
    for y in range(h):
        for x in (0, w - 1):
            if near[y, x]:
                queue.append((y, x)); keep[y, x] = True
    while queue:
        y, x = queue.popleft()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and near[ny, nx] and not keep[ny, nx]:
                keep[ny, nx] = True
                queue.append((ny, nx))

    alpha = np.where(keep, 0, 255).astype(np.uint8)
    out = np.dstack([np.asarray(img), alpha])
    rgba = PILImage.fromarray(out, "RGBA")
    box = rgba.getbbox()
    if box:
        rgba = rgba.crop(box)
    rgba.save(image)


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
    ap.add_argument("--must-show", help="what the render has to show, checked before it is kept")
    ap.add_argument("--cutout", action="store_true",
                    help="key out the flat background so the result can be animated on its own")
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

    attempt_path = args.out.with_suffix(".attempt.png")
    attempts = []
    for seed in args.seeds:
        workflow = ComfyUIClient.patch_workflow(base, {
            "3": {"text": " ".join(prompt.split())},
            "4": {"text": " ".join(negative.split())},
            "6": {"seed": seed},
            "2": {"lora_name": LORA[args.family],
                  "strength_model": args.strength, "strength_clip": args.strength},
        })
        # render to a scratch file: a rejected attempt must never be left where
        # the accepted asset belongs, or a failed build silently ships its worst try
        client.generate(workflow, output_node="9", dest=attempt_path, timeout=900)
        problems = []
        if args.must_show and not shows(attempt_path, args.must_show):
            problems.append(f"does not show: {args.must_show}")
        if args.subjects is not None:
            seen = count_subjects(attempt_path, args.noun)
            if seen != args.subjects:
                problems.append(f"counted {seen} {args.noun}, wanted {args.subjects}")
        # the face check has no opt-out: a missing pupil is the first thing a
        # viewer sees and no other check can catch it
        if not face_is_whole(attempt_path):
            problems.append("a face is broken (missing pupil, eye or mouth)")
        if not args.allow_text and has_lettering(attempt_path):
            problems.append("lettering appeared")
        attempts.append({"seed": seed, "problems": problems})
        print(f"seed {seed}: " + ("accepted" if not problems else "; ".join(problems)))
        if not problems:
            attempt_path.replace(args.out)
            if args.cutout:
                cut_out(args.out)
            print(json.dumps({"accepted_seed": seed, "file": str(args.out), "attempts": attempts}))
            return

    attempt_path.unlink(missing_ok=True)
    print(json.dumps({"accepted_seed": None, "file": str(args.out), "attempts": attempts}))
    raise SystemExit(f"no seed passed the checks for: {args.description}")


if __name__ == "__main__":
    main()

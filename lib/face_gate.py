"""Face gate: every image that shows a person is checked before it reaches a page.

Two modes:
  * ``cartoon`` -- the original hand-drawn family gate (scripts/style_refs/generate_scene.face_is_whole):
    two eyes with real pupils, one simple mouth, no teeth.
  * ``photo`` -- photographs, realistic paintings and generations: natural eyes looking one way,
    no warped or doubled features, hands with the right fingers, natural teeth (teeth are allowed),
    no missing or extra limbs.
``auto`` asks the vision model which one the picture is. A failed image is never deleted: the
caller moves it to components/ and records why.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from lib import local_models as lm

# (question, the answer that PASSES)
# Small vision models answer "no" to most positive questions ("two normal eyes?") even on a
# sound face, so every check asks about the DEFECT, and eyes are also counted (see eye_count).
PHOTO_CHECKS: list[tuple[str, str, bool]] = [
    ("eyes", "Do the eyes of any person in this picture look wrong: missing, extra, misplaced, or mismatched? "
             "Answer yes or no.", False),
    ("warping", "Is any face in this picture warped, melted, smeared, doubled, or unnaturally asymmetric? "
                "Answer yes or no.", False),
    ("hands", "Look at every visible hand. Is any hand deformed: extra fingers, missing fingers, fused fingers, "
              "or fingers bent the wrong way? If no hands are visible, answer no. Answer yes or no.", False),
    ("teeth", "If teeth are visible, are any of them malformed: merged into one strip, too many, or misplaced? "
              "If no teeth are visible, answer no. Answer yes or no.", False),
    ("limbs", "Is any arm, leg or body part missing, duplicated, or bent in an impossible way? Answer yes or no.", False),
]


def _default_ask(p: Path, q: str) -> str:
    return lm.see(p, q)


def has_person(image: Path, ask: Callable[[Path, str], str]) -> bool:
    return lm.yes(ask(image, "Is there a person, a human face, or a human figure in this picture? Answer yes or no."))


def kind_of(image: Path, ask: Callable[[Path, str], str]) -> str:
    a = ask(image, "Is this picture a photograph or a realistic painting (answer: photo), or a cartoon, "
                   "flat illustration or simple drawing (answer: cartoon)? Answer with one word.").lower()
    return "cartoon" if "cartoon" in a or "drawing" in a or "illustration" in a else "photo"


def _num(ans: str) -> int | None:
    import re

    m = re.search(r"\d+", ans)
    return int(m.group(0)) if m else None


def eye_boxes(image: Path) -> list[list[float]]:
    """Ground every visible eye (qwen2.5-VL grounding), boxes in ORIGINAL image pixels."""
    import json
    import re

    from PIL import Image

    w, h = Image.open(image).size
    scale = max(w, h) / 1344 if max(w, h) > 1344 else 1.0  # lm.see sends the image at <= 1344 px
    ans = lm.see(image, 'Find each person\'s eyes. Output JSON [{"bbox_2d": [x1, y1, x2, y2], "label": "eye"}] '
                        "for every visible eye, and nothing else.", max_tokens=400)
    m = re.search(r"\[.*\]", ans, re.S)
    try:
        boxes = [b["bbox_2d"] for b in json.loads(m.group(0))] if m else []
    except (ValueError, KeyError, TypeError):
        boxes = []
    return [[v * scale for v in b] for b in boxes if isinstance(b, list) and len(b) == 4]


def zoom_on(image: Path, boxes: list[list[float]], out_dir: Path) -> Path:
    """Crop around the grounded eyes (wide enough to show whole faces) so counting is done up close."""
    from PIL import Image

    im = Image.open(image).convert("RGB")
    x1, y1 = min(b[0] for b in boxes), min(b[1] for b in boxes)
    x2, y2 = max(b[2] for b in boxes), max(b[3] for b in boxes)
    span = max(x2 - x1, y2 - y1, 0.12 * max(im.size))
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2 + 0.3 * span
    half = 1.6 * span
    box = (max(0, cx - half), max(0, cy - half * 1.1), min(im.width, cx + half), min(im.height, cy + half * 1.1))
    out = out_dir / f".facegate-{image.stem}.jpg"
    im.crop(tuple(round(v) for v in box)).save(out, quality=92)
    return out


def eye_count(image: Path, ask: Callable[[Path, str], str], grounded: list[list[float]] | None = None) -> dict[str, Any]:
    """Count faces and eyes up close: more than two per face fails; fewer passes only for a profile."""
    faces = _num(ask(image, "How many human faces are in this picture? Answer with one number.")) or 0
    target = image
    if grounded:
        import tempfile

        target = zoom_on(image, grounded, Path(tempfile.gettempdir()))
    eyes = _num(ask(target, "How many human eyes can you see in this picture in total? Answer with one number."))
    out: dict[str, Any] = {"faces": faces, "eyes": eyes, "grounded": len(grounded or []), "ok": True}
    if target != image:
        target.unlink(missing_ok=True)  # keep-media-ok: temporary zoomed crop of an image that stays on disk
    if not faces or eyes is None:
        return out  # nothing countable (a figure from behind, a tiny figure): the yes/no checks decide
    if eyes > 2 * faces:
        out.update(ok=False, why="extra eyes")
    elif eyes < 2 * faces:
        profile = lm.yes(ask(image, "Is any face in this picture turned into full side profile, so that only "
                                    "one of its eyes could be seen? Answer yes or no."))
        out["profile"] = profile
        if not profile:
            out.update(ok=False, why="missing eye")
    return out


def run_face_gate(image: str | Path, mode: str = "auto", ask: Callable[[Path, str], str] | None = None) -> dict[str, Any]:
    """Return {"pass", "mode", "person", "checks": {name: {"answer", "ok"}}, "failed": [...]}."""
    image = Path(image)
    ask = ask or _default_ask
    if not has_person(image, ask):
        return {"pass": True, "mode": mode, "person": False, "checks": {}, "failed": [], "image": str(image)}
    if mode == "auto":
        mode = kind_of(image, ask)
    if mode == "cartoon":
        from scripts.style_refs.generate_scene import face_is_whole

        ok = face_is_whole(image)
        return {"pass": ok, "mode": "cartoon", "person": True, "checks": {"face_is_whole": {"ok": ok}},
                "failed": [] if ok else ["face_is_whole"], "image": str(image)}
    checks, failed = {}, []
    try:
        grounded = eye_boxes(image) if ask is _default_ask else []
    except lm.LocalModelUnavailable:
        grounded = []
    ec = eye_count(image, ask, grounded)
    checks["eye_count"] = ec
    if not ec["ok"]:
        failed.append("eye_count")
    for name, q, want in PHOTO_CHECKS:
        ans = ask(image, q)
        ok = lm.yes(ans) == want
        checks[name] = {"answer": ans[:80], "ok": ok}
        if not ok:
            failed.append(name)
    return {"pass": not failed, "mode": "photo", "person": True, "checks": checks, "failed": failed,
            "image": str(image), "model": lm.detect().get("vision")}

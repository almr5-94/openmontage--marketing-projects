"""Realistic POV stills from the recurring world, gated for faces and text.

The gate is the inverse of scripts/style_refs/generate_scene.py::face_is_whole:
this account must never show a face, so a local vision model is asked, and then
OpenCV measures. Either says "face" and the still is rejected.
"""
from __future__ import annotations

import base64
import json
import urllib.request
from pathlib import Path

from .common import SERIES_DIR, read_json, run_tool, log
from . import budget

OLLAMA = "http://localhost:11434/api/generate"
VISION_MODEL = "qwen2.5vl:7b"
WORLD = SERIES_DIR / "world"


def world() -> dict:
    return read_json(WORLD / "world.json")


def constants() -> str:
    return (WORLD / "constants.txt").read_text(encoding="utf-8").strip()


def negative() -> str:
    return (WORLD / "negative.txt").read_text(encoding="utf-8").strip()


def accepted_settings() -> list[dict]:
    return [s for s in world()["settings"] if s.get("accepted_by_owner")]


def ask_vision(image: Path, question: str, timeout: int = 180, keep_alive: str = "5m") -> str:
    body = json.dumps({
        "model": VISION_MODEL, "prompt": question,
        "images": [base64.b64encode(image.read_bytes()).decode()],
        "stream": False, "keep_alive": keep_alive,
        "options": {"temperature": 0, "num_predict": 8, "seed": 7},
    }).encode()
    req = urllib.request.Request(OLLAMA, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())["response"].strip()


def unload_vision() -> None:
    """Free the GPU for Whisper / Qwen-Image after a batch of gate questions."""
    try:
        body = json.dumps({"model": VISION_MODEL, "prompt": "", "keep_alive": 0}).encode()
        urllib.request.urlopen(urllib.request.Request(OLLAMA, data=body, headers={"Content-Type": "application/json"}), timeout=30).read()
    except Exception:
        pass


def opencv_faces(image: Path) -> int:
    import cv2

    img = cv2.imread(str(image))
    if img is None:
        return 0
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    total = 0
    for name in ("haarcascade_frontalface_default.xml", "haarcascade_profileface.xml"):
        cascade = cv2.CascadeClassifier(cv2.data.haarcascades + name)
        total += len(cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=6, minSize=(60, 60)))
    return total


def is_faceless_and_textless(image: Path, check_text: bool = True) -> dict:
    """Ask, then measure. Returns {'ok': bool, 'face_answer', 'text_answer', 'opencv_faces'}."""
    face = ask_vision(image, "Is there a human face, or a reflection of a face, anywhere in this picture? Answer yes or no.")
    text = ask_vision(image, "Is there any readable text, letters, numbers, a logo or a brand mark in this picture? Answer yes or no.") if check_text else "n/a"
    n = opencv_faces(image)
    ok = face.lower().startswith("n") and (not check_text or text.lower().startswith("n")) and n == 0
    return {"ok": ok, "face_answer": face, "text_answer": text, "opencv_faces": n}


def generate_still(project_dir: Path, shot_id: str, setting: dict, prompt: str, seed: int) -> tuple[Path, dict]:
    """Qwen edit from the setting reference (+ the home desk anchor), gated; Imagen as last resort."""
    out_dir = project_dir / "assets" / "images"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{shot_id}.png"
    gate_path = out_dir / f"{shot_id}.gate.json"
    if out.exists() and gate_path.exists() and read_json(gate_path).get("ok"):
        return out, read_json(gate_path)
    refs = [str(WORLD / "refs" / setting["ref"])]
    anchor = WORLD / "refs" / "home_desk.png"
    if anchor.exists() and setting["ref"] != "home_desk.png":
        refs.append(str(anchor))
    full_prompt = (f"{prompt}. Keep exactly the same hands, watch, cufflinks, sleeves, phone, laptop and notebook as in "
                   f"the reference images; same real-photo phone-camera look. {constants()}")
    attempts = []
    for k, s in enumerate((seed, seed + 1000)):
        log(f"{shot_id}: qwen edit seed {s}")
        run_tool("qwen_image_edit_local", {
            "prompt": full_prompt, "image_paths": refs, "negative_prompt": negative(), "seed": s,
            "num_inference_steps": 40, "true_cfg_scale": 4.0, "quantization": "4bit", "offload": "two_phase",
            "output_path": str(out)})
        gate = is_faceless_and_textless(out)
        attempts.append({"tool": "qwen_image_edit_local", "seed": s, **gate})
        if gate["ok"]:
            break
    else:
        log(f"{shot_id}: qwen rejected twice, trying google_imagen")
        budget.assert_can_spend(project_dir, 0.05, f"google_imagen {shot_id}")
        run_tool("google_imagen", {"prompt": full_prompt + " Vertical 9:16 phone photo.", "aspect_ratio": "9:16",
                                   "model": "imagen-4.0-generate-001", "output_path": str(out)})
        gate = is_faceless_and_textless(out)
        attempts.append({"tool": "google_imagen", **gate})
        if not gate["ok"]:
            gate_path.write_text(json.dumps({"ok": False, "attempts": attempts}, indent=1))
            raise RuntimeError(f"{shot_id}: no faceless, text-free still after 3 attempts")
    result = {"ok": True, "attempts": attempts, "setting": setting["id"], "prompt": full_prompt}
    gate_path.write_text(json.dumps(result, ensure_ascii=False, indent=1))
    return out, result

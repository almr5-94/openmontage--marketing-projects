"""Realistic POV stills from the recurring world, gated for faces and text.

The gate is the inverse of scripts/style_refs/generate_scene.py::face_is_whole:
this account must never show a face, so a local vision model is asked, and then
OpenCV measures. Either says "face" and the still is rejected.
"""
from __future__ import annotations

import base64
import json
import os
import urllib.request
from pathlib import Path

from .common import SERIES_DIR, read_json, run_tool, log
from . import budget

OLLAMA = "http://localhost:11434/api/generate"
VISION_MODEL = "qwen2.5vl:7b"
GEMINI_IMAGE_MODEL = "gemini-2.5-flash-image"  # USD 0.039 per image; imagen-4.0-* return 404 on this key
WORLD = SERIES_DIR / "world"


def world() -> dict:
    return read_json(WORLD / "world.json")


def constants() -> str:
    return (WORLD / "constants.txt").read_text(encoding="utf-8").strip()


def negative() -> str:
    return (WORLD / "negative.txt").read_text(encoding="utf-8").strip()


def accepted_settings() -> list[dict]:
    from .voice import PROVISIONAL

    if PROVISIONAL["on"]:
        return [s for s in world()["settings"] if s.get("accepted_by_owner") or s.get("gate", {}).get("ok")]
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


def opencv_face_boxes(image: Path) -> list[tuple[int, int, int, int]]:
    """Haar candidates (frontal + profile). Candidates, not verdicts: the cascade fires on
    steering wheels and dashboards, so each box is shown to the vision model before it counts."""
    import cv2

    img = cv2.imread(str(image))
    if img is None:
        return []
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    boxes = []
    for name in ("haarcascade_frontalface_default.xml", "haarcascade_profileface.xml"):
        cascade = cv2.CascadeClassifier(cv2.data.haarcascades + name)
        for (x, y, w, h) in cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=6, minSize=(60, 60)):
            boxes.append((int(x), int(y), int(w), int(h)))
    return boxes


def confirmed_faces(image: Path) -> list[dict]:
    """Each Haar candidate, cropped with a margin and put to the vision model. Only a 'yes' counts."""
    import cv2

    boxes = opencv_face_boxes(image)
    if not boxes:
        return []
    img = cv2.imread(str(image))
    H, W = img.shape[:2]
    confirmed = []
    for i, (x, y, w, h) in enumerate(boxes):
        m = int(0.6 * max(w, h))
        crop = img[max(0, y - m):min(H, y + h + m), max(0, x - m):min(W, x + w + m)]
        tmp = image.with_suffix(f".facecand{i}.jpg")
        cv2.imwrite(str(tmp), crop)
        ans = ask_vision(tmp, "Is there a human face or part of a human face in this picture? Answer yes or no.")
        tmp.unlink(missing_ok=True)
        if ans.lower().startswith("y"):
            confirmed.append({"box": [x, y, w, h], "answer": ans})
    return confirmed


def is_faceless_and_textless(image: Path, check_text: bool = True) -> dict:
    """Ask, then measure, then ask again about anything measured.

    Returns {'ok', 'face_answer', 'text_answer', 'opencv_candidates', 'confirmed_faces'}.
    """
    face = ask_vision(image, "Is there a human face, or a reflection of a face, anywhere in this picture? Answer yes or no.")
    text = ask_vision(image, "Is there any readable text, letters, numbers, a logo or a brand mark in this picture? Answer yes or no.") if check_text else "n/a"
    cands = opencv_face_boxes(image)
    confirmed = confirmed_faces(image) if cands else []
    ok = face.lower().startswith("n") and (not check_text or text.lower().startswith("n")) and not confirmed
    return {"ok": ok, "face_answer": face, "text_answer": text, "opencv_candidates": len(cands), "confirmed_faces": confirmed}


def still_prompt_for(setting: dict, prompt: str) -> str:
    return (f"{prompt}. Keep exactly the same hands, watch, cufflinks, sleeves, phone, laptop and notebook as in "
            f"the reference images; same real-photo phone-camera look. {constants()}")


def render_still(out: Path, setting: dict, prompt: str, seed: int, tool_name: str = "qwen_image_edit_local") -> dict:
    """Render one still with Qwen (or Imagen as the last resort). No gate here — gates run in a batch."""
    out.parent.mkdir(parents=True, exist_ok=True)
    full_prompt = still_prompt_for(setting, prompt)
    refs = [str(WORLD / "refs" / setting["ref"])]
    anchor = WORLD / "refs" / "home_desk.png"
    if anchor.exists() and setting["ref"] != "home_desk.png":
        refs.append(str(anchor))
    if tool_name == "google_imagen":
        # this key has no Imagen models; the Gemini image model takes the same references
        run_tool("google_imagen", {"prompt": full_prompt + " Vertical 9:16 phone photo, same scene and hands as the reference images.",
                                   "aspect_ratio": "9:16", "model": GEMINI_IMAGE_MODEL, "reference_image_paths": refs, "output_path": str(out)})
        return {"tool": "google_imagen", "model": GEMINI_IMAGE_MODEL, "seed": None, "prompt": full_prompt}
    log(f"{out.stem}: qwen edit seed {seed}")
    qwen_edit_isolated({
        "prompt": full_prompt, "image_paths": refs, "negative_prompt": negative(), "seed": seed,
        "num_inference_steps": 40, "true_cfg_scale": 4.0, "quantization": "4bit", "offload": "two_phase",
        "output_path": str(out)})
    return {"tool": "qwen_image_edit_local", "seed": seed, "prompt": full_prompt}


def qwen_edit_isolated(inputs: dict, timeout: int = 1500) -> None:
    """Run the Qwen edit in a child process so an OOM kill loses one still, not the run. Raises on failure."""
    import json as _json
    import subprocess
    import tempfile

    from .common import OM_ROOT

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        _json.dump(inputs, f, ensure_ascii=False)
        spec = f.name
    r = subprocess.run([str(OM_ROOT / ".venv" / "bin" / "python"), str(Path(__file__).with_name("qwen_worker.py")), spec],
                       cwd=OM_ROOT, capture_output=True, text=True, timeout=timeout)
    Path(spec).unlink(missing_ok=True)
    tail = (r.stdout.strip().splitlines() or [""])[-1]
    if r.returncode != 0 or not tail.startswith("{"):
        raise RuntimeError(f"qwen worker exited {r.returncode} (killed={r.returncode < 0 or r.returncode == 137}): {(r.stderr or r.stdout)[-400:]}")
    if not _json.loads(tail).get("success"):
        raise RuntimeError("qwen worker reported failure")


def generate_stills(project_dir: Path, jobs: list[dict]) -> dict[str, dict]:
    """jobs: [{shot_id, setting, prompt, seed}]. Renders every still with the GPU to itself, then frees
    the card, then gates the batch with the vision model, then re-renders the failures (seed+1000,
    then Imagen). Returns shot_id -> gate record (also written to assets/images/<id>.gate.json)."""
    out_dir = project_dir / "assets" / "images"
    out_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, dict] = {}
    pending = []
    for j in jobs:
        gate_path = out_dir / f"{j['shot_id']}.gate.json"
        if (out_dir / f"{j['shot_id']}.png").exists() and gate_path.exists() and read_json(gate_path).get("ok"):
            results[j["shot_id"]] = read_json(gate_path)
        else:
            pending.append({**j, "attempts": []})
    rounds = (("qwen_image_edit_local", 0), ("qwen_image_edit_local", 1000), ("google_imagen", 0))
    if os.environ.get("KLI_IMAGEN_ONLY"):  # the machine cannot host the 20B editor: go straight to the reference-conditioned Gemini image model
        rounds = (("google_imagen", 0), ("google_imagen", 1000))
    for round_no, (tool_name, seed_shift) in enumerate(rounds):
        if not pending:
            break
        for j in pending:
            if tool_name == "google_imagen":
                budget.assert_can_spend(project_dir, 0.04, f"google_imagen {j['shot_id']}")
            try:
                j["last"] = render_still(out_dir / f"{j['shot_id']}.png", j["setting"], j["prompt"], j["seed"] + seed_shift, tool_name)
            except Exception as exc:  # a killed or failed render is a rejected attempt, not a crash
                log(f"{j['shot_id']}: render failed in round {round_no + 1}: {str(exc)[:200]}")
                j["last"] = {"tool": tool_name, "seed": j["seed"] + seed_shift, "prompt": still_prompt_for(j["setting"], j["prompt"]), "render_error": str(exc)[:200]}
        free_gpu()
        still_pending = []
        for j in pending:
            if j["last"].get("render_error") or not (out_dir / f"{j['shot_id']}.png").exists():
                j["attempts"].append({**j["last"], "ok": False})
                still_pending.append(j)
                continue
            gate = is_faceless_and_textless(out_dir / f"{j['shot_id']}.png")
            j["attempts"].append({**j["last"], **gate})
            if gate["ok"]:
                rec = {"ok": True, "attempts": j["attempts"], "setting": j["setting"]["id"], "prompt": j["last"]["prompt"]}
                (out_dir / f"{j['shot_id']}.gate.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1))
                results[j["shot_id"]] = rec
            else:
                log(f"{j['shot_id']}: rejected by the gate (round {round_no + 1}): {gate}")
                still_pending.append(j)
        unload_vision()
        pending = still_pending
    for j in pending:
        (out_dir / f"{j['shot_id']}.gate.json").write_text(json.dumps({"ok": False, "attempts": j["attempts"]}, ensure_ascii=False, indent=1))
    if pending:
        raise RuntimeError(f"no faceless, text-free still after 3 rounds for: {[j['shot_id'] for j in pending]}")
    return results


def free_gpu() -> None:
    """Drop the resident Qwen pipeline so Whisper and the vision model have the card."""
    try:
        from tools.graphics import _qwen_local

        _qwen_local._evict_other_pipelines(("", "", ""))
    except Exception as exc:  # never fail a stage over cleanup
        log(f"free_gpu: {exc}")

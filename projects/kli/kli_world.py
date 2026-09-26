#!/usr/bin/env python
"""Build (once) the recurring world: reference stills the owner accepts, plus their seeds.

    .venv/bin/python projects/kli/kli_world.py build      # generate/refresh references, write world.json
    .venv/bin/python projects/kli/kli_world.py gate       # re-run the no-face/no-text gate on every ref
    .venv/bin/python projects/kli/kli_world.py accept <setting_id> --by "<owner name>"

Nothing here is a production shot: these are the anchors every daily still is edited from.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from klilib.common import SERIES_DIR, run_tool, sha256_file, now_iso, log  # noqa: E402
from klilib import stills  # noqa: E402

WORLD = SERIES_DIR / "world"
REFS = WORLD / "refs"
SEED = 4242

SETTINGS = [
    {"id": "home_desk", "ref": "home_desk.png", "description": "home desk by a window, laptop, notebook, coffee cup, phone", "origin": "runway 2026-09-19"},
    {"id": "car", "ref": "car.png", "description": "passenger seat of a parked car in daylight, notebook on the lap, phone in hand", "origin": "runway 2026-09-19"},
    {"id": "office_desk", "ref": "office_desk.png", "description": "office desk, navy suit sleeve with white cuff, laptop and printed pages", "origin": "regenerated 2026-09-27 (logo)",
     "regen_from": "home_desk.png", "regen_prompt": "Move the scene to a clean office desk: same hands and watch, but the sleeve is now a navy suit jacket with a white shirt cuff; a matte grey laptop with no logo, a stack of printed A4 pages face-down, a black pen. Daylight from a window on the side."},
    {"id": "library", "ref": "library.png", "description": "university library table, open law book, notebook, pen", "origin": "generated 2026-09-27",
     "gen_prompt": "Vertical phone photo, first-person view looking down at a wooden university library table. A young man's hands with light-tan skin rest on an open thick book with blank-looking pages; a navy hardcover notebook with an elastic band and a black pen beside it; blurred bookshelves in the background. White dishdasha sleeve with a simple silver cufflink, plain black leather-strap watch on the left wrist. Natural daylight, moderately raw handheld look."},
    {"id": "cafe", "ref": "cafe.png", "description": "cafe table, small coffee cup, phone in hand, laptop half open", "origin": "generated 2026-09-27",
     "gen_prompt": "Vertical phone photo, first-person view of a small cafe table. A young man's hands with light-tan skin hold a black phone in a plain dark-green case above the table; a small coffee cup and a matte grey laptop with no logo, half open; soft daylight from a window, blurred cafe interior. White dishdasha sleeve with a simple silver cufflink, plain black leather-strap watch on the left wrist. Moderately raw handheld look."},
    {"id": "night_car", "ref": "night_car.png", "description": "parked car at night, dashboard glow, phone in hand", "origin": "generated 2026-09-27",
     "gen_prompt": "Vertical phone photo, first-person view inside a parked car at night. A young man's hands with light-tan skin hold a black phone in a plain dark-green case low over the lap; warm dashboard glow and street lights blurred through the windscreen; a navy hardcover notebook on the passenger seat. White dishdasha sleeve with a simple silver cufflink, plain black leather-strap watch on the left wrist. Moderately raw handheld look."},
]


def load() -> dict:
    p = WORLD / "world.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"version": "2026-09-27", "seed": SEED, "settings": []}


def save(w: dict) -> None:
    (WORLD / "world.json").write_text(json.dumps(w, ensure_ascii=False, indent=2), encoding="utf-8")


def build() -> None:
    w = load()
    existing = {s["id"]: s for s in w["settings"]}
    anchor = REFS / "home_desk.png"
    for i, spec in enumerate(SETTINGS):
        out = REFS / spec["ref"]
        s = existing.get(spec["id"], {})
        if s.get("accepted_by_owner"):
            log(f"{spec['id']}: accepted, untouched")
            continue
        seed = SEED + i
        if spec.get("regen_from"):
            log(f"{spec['id']}: regenerating from {spec['regen_from']}")
            run_tool("qwen_image_edit_local", {"prompt": spec["regen_prompt"] + " " + stills.constants(), "image_paths": [str(REFS / spec["regen_from"])],
                                               "negative_prompt": stills.negative(), "seed": seed, "quantization": "4bit", "offload": "two_phase", "output_path": str(out)})
        elif spec.get("gen_prompt") and not out.exists():
            log(f"{spec['id']}: imagen then one qwen pass against the anchor")
            raw = REFS / f"{spec['id']}.imagen.png"
            run_tool("google_imagen", {"prompt": spec["gen_prompt"], "aspect_ratio": "9:16", "model": "imagen-4.0-generate-001", "output_path": str(raw)})
            run_tool("qwen_image_edit_local", {"prompt": "Keep this scene exactly, but make the hands, the black leather watch on the left wrist, the silver cufflink and the phone case match the second image precisely. " + stills.constants(),
                                               "image_paths": [str(raw), str(anchor)], "negative_prompt": stills.negative(), "seed": seed, "quantization": "4bit", "offload": "two_phase", "output_path": str(out)})
        gate = stills.is_faceless_and_textless(out)
        log(f"{spec['id']}: gate {gate}")
        existing[spec["id"]] = {**{k: spec[k] for k in ("id", "ref", "description", "origin")}, "seed": seed, "sha256": sha256_file(out),
                                "gate": gate, "accepted_by_owner": False, "built_at": now_iso()}
    stills.unload_vision()
    w["settings"] = [existing[s["id"]] for s in SETTINGS if s["id"] in existing]
    save(w)
    log("world.json written; owner must accept each setting: kli_world.py accept <id> --by <name>")


def gate() -> None:
    w = load()
    for s in w["settings"]:
        s["gate"] = stills.is_faceless_and_textless(REFS / s["ref"])
        log(f"{s['id']}: {s['gate']}")
    stills.unload_vision()
    save(w)


def accept(setting_id: str, by: str) -> None:
    w = load()
    for s in w["settings"]:
        if s["id"] == setting_id:
            if not s.get("gate", {}).get("ok"):
                raise SystemExit(f"{setting_id} has not passed the no-face/no-text gate; cannot accept")
            s["accepted_by_owner"] = True
            s["accepted_by"] = by
            s["accepted_at"] = now_iso()
            s["sha256"] = sha256_file(REFS / s["ref"])
            save(w)
            log(f"{setting_id} accepted by {by}")
            return
    raise SystemExit(f"unknown setting {setting_id}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["build", "gate", "accept"])
    ap.add_argument("setting", nargs="?")
    ap.add_argument("--by", default="")
    a = ap.parse_args()
    {"build": build, "gate": gate}.get(a.command, lambda: accept(a.setting, a.by))()

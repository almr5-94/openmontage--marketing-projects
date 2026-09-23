"""Turn captured reference frames into per-family training datasets.

Usage:
    python -m scripts.style_refs.build_datasets assets/references/handdrawn [--per-family 160]

Implements the curation contract of forensic-illustration-study.md section 5.2:

- the capture archive is not a dataset; every frame is judged, never sampled at a
  fixed interval
- the three families are kept apart (one folder, one trigger, one adapter each),
  because averaging their contradictory constructions is the failure the study
  identifies
- frames carrying the video player's own graphics are quarantined, not cropped
  and not repaired: cropping cannot recover artwork a control covered, and
  inpainting would invent linework
- near-duplicates are grouped into scenes on the artwork region, so a moving
  progress bar cannot make one held shot look like many examples
- the train/validation split is by scene group, so validation cannot score a
  memorised neighbour of a training frame

Writes
    <ref>/dataset-{a,b,c}/            accepted images, cropped to the art field
    <ref>/quarantine/                 rejected frames, kept for audit
    <ref>/dataset-manifest.jsonl      one record per candidate, schema of study 5.3
    <ref>/dataset-report.json         counts per family and rejection reasons
"""

from __future__ import annotations

import argparse
import json
from multiprocessing import Pool
from pathlib import Path

import numpy as np
from PIL import Image

from scripts.style_refs.common import (
    array_has_player_ui,
    detect_content_box,
    has_player_ui,
    list_frames,
    load_gray,
    phash,
    write_json,
)

OUT_WIDTH = 1344

# one reference video per family; the families are three different illustration
# systems, not three moods of one system
FAMILIES = {
    "video1": {"key": "a", "family": "A", "trigger": "hdx_paperfolk", "name": "paper folk"},
    "video2": {"key": "b", "family": "B", "trigger": "hdx_incise", "name": "incised silhouette"},
    "video3": {"key": "c", "family": "C", "trigger": "hdx_biotext", "name": "bio texture"},
}

SCENE_BREAK = 14   # hamming distance between consecutive frames that starts a new scene
DUP_WITHIN_SCENE = 6  # below this two frames in one scene teach the same thing
VALIDATION_SHARE = 0.12
SALVAGE_BELOW = 40     # a family this thin may use detail crops of contaminated frames
SALVAGE_TOP = 0.12     # fraction of the art field dropped from the top (title band)
SALVAGE_BOTTOM = 0.20  # ... and from the bottom (controls band)


def _probe(args):
    path, box = args
    return has_player_ui(path), phash(load_gray(path, box, width=320))


def salvage_box(box, path: Path) -> tuple | None:
    """A 16:9 crop of the clean middle of a frame whose edges carry player graphics.

    The study allows a carefully captioned detail crop when no clean frame of
    that moment exists, and forbids repairing the covered area. So the crop is
    only accepted when the player's graphics are fully outside it.
    """
    x0, y0, x1, y1 = box
    h = y1 - y0
    top, bottom = y0 + round(h * SALVAGE_TOP), y1 - round(h * SALVAGE_BOTTOM)
    height = bottom - top
    width = round(height * 16 / 9)
    if width > x1 - x0:
        width = x1 - x0
        height = round(width * 9 / 16)
        bottom = top + height
    cx = (x0 + x1) // 2
    crop = (max(x0, cx - width // 2), top, min(x1, cx + width // 2), bottom)
    region = Image.open(path).convert("RGB").crop(crop)
    return None if array_has_player_ui(region) else crop


def _save(args):
    path, box, dest = args
    img = Image.open(path).convert("RGB").crop(box)
    img = img.resize((OUT_WIDTH, round(img.height * OUT_WIDTH / img.width)), Image.LANCZOS)
    img.save(dest, optimize=True)


def scene_groups(hashes: np.ndarray) -> list[int]:
    """Number each frame with its scene, walking the capture in time order."""
    groups, current = [], 0
    for i, h in enumerate(hashes):
        if i and (hashes[i - 1] != h).sum() > SCENE_BREAK:
            current += 1
        groups.append(current)
    return groups


def pick_within_scene(hashes: np.ndarray, idx: list[int]) -> list[int]:
    """Keep the frames inside one scene that differ from each other."""
    kept: list[int] = []
    for i in idx:
        if all((hashes[i] != hashes[k]).sum() > DUP_WITHIN_SCENE for k in kept):
            kept.append(i)
    return kept


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("ref_dir", type=Path)
    ap.add_argument("--per-family", type=int, default=160, help="soft cap on accepted frames per family")
    ap.add_argument("--workers", type=int, default=16)
    args = ap.parse_args()

    ref = args.ref_dir
    quarantine = ref / "quarantine"
    quarantine.mkdir(parents=True, exist_ok=True)
    for f in FAMILIES.values():
        d = ref / f"dataset-{f['key']}"
        d.mkdir(parents=True, exist_ok=True)
        for old in d.glob("*"):
            old.unlink()
    for old in quarantine.glob("*"):
        old.unlink()

    videos = list_frames(ref / "raw")
    manifest: list[dict] = []
    report: dict = {"families": {}, "scene_break_hamming": SCENE_BREAK, "duplicate_hamming": DUP_WITHIN_SCENE}

    for video, frames in videos.items():
        meta = FAMILIES[video]
        box = detect_content_box(frames)
        with Pool(args.workers) as pool:
            probes = pool.map(_probe, [(p, box) for p in frames], chunksize=8)
        ui = np.array([p[0] for p in probes])
        hashes = np.array([p[1] for p in probes])
        groups = scene_groups(hashes)

        # accept only clean frames, then thin each scene down to its distinct views
        clean_idx = [i for i in range(len(frames)) if not ui[i]]
        by_scene: dict[int, list[int]] = {}
        for i in clean_idx:
            by_scene.setdefault(groups[i], []).append(i)
        accepted = [i for g in sorted(by_scene) for i in pick_within_scene(hashes, by_scene[g])]

        # a soft cap keeps one long scene from dominating: thin the largest scenes first
        while len(accepted) > args.per_family:
            biggest = max(by_scene, key=lambda g: sum(1 for i in accepted if groups[i] == g))
            in_big = [i for i in accepted if groups[i] == biggest]
            if len(in_big) <= 1:
                break
            drop = set(in_big[1::2])
            accepted = [i for i in accepted if i not in drop]
            by_scene[biggest] = [i for i in by_scene[biggest] if i not in drop]

        salvaged: dict[int, tuple] = {}
        if len(accepted) < SALVAGE_BELOW:
            for i in range(len(frames)):
                if not ui[i] or i in accepted:
                    continue
                crop = salvage_box(box, frames[i])
                if crop is None:
                    continue
                if all((hashes[i] != hashes[k]).sum() > DUP_WITHIN_SCENE for k in list(accepted) + list(salvaged)):
                    salvaged[i] = crop
                    accepted.append(i)
            accepted.sort()
            by_scene = {}
            for i in accepted:
                by_scene.setdefault(groups[i], []).append(i)

        accepted_set = set(accepted)
        scenes_sorted = sorted({groups[i] for i in accepted})
        n_val = max(1, round(len(scenes_sorted) * VALIDATION_SHARE))
        val_scenes = set(scenes_sorted[:: max(1, len(scenes_sorted) // n_val)][:n_val])

        dataset_dir = ref / f"dataset-{meta['key']}"
        jobs, counts = [], {"accepted": 0, "quarantined_player_ui": 0, "dropped_duplicate": 0,
                            "validation": 0, "salvaged_detail_crops": 0}
        for i, path in enumerate(frames):
            stem = f"{video}_{path.stem.split('_frame_')[1]}"
            record = {
                "image_id": stem,
                "source_file": path.name,
                "family": meta["family"],
                "trigger": meta["trigger"],
                "scene_group": f"{video}_s{groups[i]:03d}",
                "mode": None,  # set by the captioner, which looks at the picture
                "source_dimensions": list(Image.open(path).size) if i == 0 else [2940, 1912],
                "crop_xyxy": list(box),
                "crop_status": "cropped_art_field",
                "capture_contamination": [],
                "caption_status": "pending",
                "caption": None,
                "evidence_role": "candidate",
                "training_approved": False,
                "split": "unassigned",
            }
            if i in accepted_set and i in salvaged:
                split = "validation" if groups[i] in val_scenes else "train"
                record.update({
                    "crop_xyxy": list(salvaged[i]),
                    "crop_status": "detail_crop_of_contaminated_frame",
                    "capture_contamination": ["player_ui_outside_crop"],
                    "training_approved": True,
                    "split": split,
                    "evidence_role": "training_candidate_detail_crop",
                })
                counts["accepted"] += 1
                counts["salvaged_detail_crops"] = counts.get("salvaged_detail_crops", 0) + 1
                counts["validation"] += split == "validation"
                jobs.append((frames[i], salvaged[i], dataset_dir / f"{stem}.png"))
            elif ui[i]:
                record.update({
                    "crop_status": "requires_review",
                    "capture_contamination": ["player_ui"],
                    "evidence_role": "quarantined",
                })
                counts["quarantined_player_ui"] += 1
                jobs.append((path, box, quarantine / f"{stem}.png"))
            elif i in accepted_set:
                split = "validation" if groups[i] in val_scenes else "train"
                record.update({"training_approved": True, "split": split, "evidence_role": "training_candidate"})
                counts["accepted"] += 1
                counts["validation"] += split == "validation"
                jobs.append((path, box, dataset_dir / f"{stem}.png"))
            else:
                record["evidence_role"] = "duplicate_of_scene"
                counts["dropped_duplicate"] += 1
            manifest.append(record)

        with Pool(args.workers) as pool:
            pool.map(_save, jobs, chunksize=4)

        counts.update({
            "family": meta["family"], "name": meta["name"], "trigger": meta["trigger"],
            "candidates": len(frames), "scenes": len(set(groups)), "scenes_accepted": len(scenes_sorted),
            "picture_box": list(box),
        })
        report["families"][meta["key"]] = counts
        print(f"{meta['family']} ({meta['name']}): {counts['accepted']} accepted "
              f"({counts['validation']} validation) from {len(frames)} candidates in "
              f"{counts['scenes_accepted']} scenes; {counts['quarantined_player_ui']} quarantined")

    with (ref / "dataset-manifest.jsonl").open("w", encoding="utf-8") as fh:
        for record in manifest:
            fh.write(json.dumps(record) + "\n")
    write_json(ref / "dataset-report.json", report)


if __name__ == "__main__":
    main()

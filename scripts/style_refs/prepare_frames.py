"""Turn screen-recorded reference frames into a clean, de-duplicated style set.

Usage:
    python -m scripts.style_refs.prepare_frames assets/references/ted-ed [--target 250]

Reads   <ref>/raw/<video>_frame_NNNN.png
Writes  <ref>/work/boxes.json            picture box found in each video
        <ref>/work/hashes.npz            perceptual hash of every frame (reused by motion_analysis)
        <ref>/clean/<video>_NNNN.png     distinct frames, cropped, 1344 px wide
        <ref>/clean/contact_NN.jpg       contact sheets for picking the board
        <ref>/prepare-report.json        counts and the dedupe threshold used
"""

from __future__ import annotations

import argparse
from multiprocessing import Pool
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from scripts.style_refs.common import detect_content_box, has_player_ui, list_frames, load_gray, phash, write_json

OUT_WIDTH = 1344


def _hash_one(args):
    path, box = args
    return phash(load_gray(path, box, width=320))


def _save_clean(args):
    path, box, dest = args
    img = Image.open(path).convert("RGB").crop(box)
    img = img.resize((OUT_WIDTH, round(img.height * OUT_WIDTH / img.width)), Image.LANCZOS)
    img.save(dest, optimize=True)
    return dest


def greedy_dedupe(hashes: np.ndarray, threshold: int) -> list[int]:
    kept: list[int] = []
    kept_h = np.zeros((0, hashes.shape[1]), dtype=bool)
    for i, h in enumerate(hashes):
        if len(kept) == 0 or (kept_h != h).sum(axis=1).min() > threshold:
            kept.append(i)
            kept_h = np.vstack([kept_h, h])
    return kept


def contact_sheets(paths: list[Path], out_dir: Path, per_sheet: int = 48, cols: int = 8) -> list[Path]:
    thumb_w, thumb_h = 320, 180
    sheets = []
    for s in range(0, len(paths), per_sheet):
        chunk = paths[s : s + per_sheet]
        rows = (len(chunk) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * thumb_w, rows * (thumb_h + 18)), "white")
        draw = ImageDraw.Draw(sheet)
        for i, p in enumerate(chunk):
            t = Image.open(p).convert("RGB")
            t.thumbnail((thumb_w, thumb_h))
            x, y = (i % cols) * thumb_w, (i // cols) * (thumb_h + 18)
            sheet.paste(t, (x, y))
            draw.text((x + 4, y + thumb_h + 3), p.stem, fill="black")
        dest = out_dir / f"contact_{s // per_sheet + 1:02d}.jpg"
        sheet.save(dest, quality=85)
        sheets.append(dest)
    return sheets


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("ref_dir", type=Path)
    ap.add_argument("--target", type=int, default=250, help="approximate number of distinct frames to keep")
    ap.add_argument("--workers", type=int, default=16)
    args = ap.parse_args()

    raw, work, clean = args.ref_dir / "raw", args.ref_dir / "work", args.ref_dir / "clean"
    work.mkdir(parents=True, exist_ok=True)
    clean.mkdir(parents=True, exist_ok=True)
    for old in clean.glob("*"):
        old.unlink()

    videos = list_frames(raw)
    boxes = {v: detect_content_box(frames) for v, frames in videos.items()}
    write_json(work / "boxes.json", boxes)

    all_paths, all_boxes, all_video = [], [], []
    for v, frames in videos.items():
        all_paths += frames
        all_boxes += [boxes[v]] * len(frames)
        all_video += [v] * len(frames)

    # frames with the player controls on top are not usable as clean art
    with Pool(args.workers) as pool:
        ui = pool.map(has_player_ui, all_paths, chunksize=16)
    ui_skipped = sum(ui)
    all_paths = [p for p, u in zip(all_paths, ui) if not u]
    all_boxes = [b for b, u in zip(all_boxes, ui) if not u]
    all_video = [v for v, u in zip(all_video, ui) if not u]

    with Pool(args.workers) as pool:
        hashes = np.array(pool.map(_hash_one, zip(all_paths, all_boxes), chunksize=16))
    np.savez_compressed(work / "hashes.npz", hashes=hashes, names=np.array([p.name for p in all_paths]))

    # Raise the distance threshold until the kept set is near the target size.
    threshold, kept = 4, list(range(len(all_paths)))
    while len(kept) > args.target and threshold < 40:
        threshold += 1
        kept = greedy_dedupe(hashes, threshold)

    jobs = []
    for i in kept:
        p = all_paths[i]
        idx = p.stem.split("_frame_")[1]
        jobs.append((p, all_boxes[i], clean / f"{all_video[i]}_{idx}.png"))
    with Pool(args.workers) as pool:
        saved = pool.map(_save_clean, jobs, chunksize=4)

    sheets = contact_sheets(sorted(saved), clean)
    per_video = {v: sum(1 for i in kept if all_video[i] == v) for v in videos}
    write_json(
        args.ref_dir / "prepare-report.json",
        {
            "raw_frames": len(all_paths),
            "raw_per_video": {v: len(f) for v, f in videos.items()},
            "skipped_player_ui": ui_skipped,
            "picture_boxes": boxes,
            "dedupe_hamming_threshold": threshold,
            "kept": len(kept),
            "kept_per_video": per_video,
            "contact_sheets": [s.name for s in sheets],
        },
    )
    print(f"kept {len(kept)} of {len(all_paths)} (threshold {threshold}); per video {per_video}; boxes {boxes}")


if __name__ == "__main__":
    main()

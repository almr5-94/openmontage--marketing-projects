"""Pick the reference board: the few frames that cover the whole style.

Usage:
    python -m scripts.style_refs.select_board assets/references/handdrawn --count 40

Takes the cleaned frames and keeps the most different ones (farthest-point
selection on their perceptual hashes), proportionally per video, so the board
spans characters, objects, backgrounds and colour moods instead of ten frames
of the same shot. These are the images handed to an image model as visual
references, and the ones a human looks at to judge the style.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import numpy as np

from scripts.style_refs.common import list_frames, load_gray, phash, write_json
from scripts.style_refs.prepare_frames import contact_sheets


def farthest_first(hashes: np.ndarray, count: int) -> list[int]:
    """Greedy: start from the most typical frame, then always add the frame
    least like everything picked so far."""
    dists = (hashes[:, None, :] != hashes[None, :, :]).sum(axis=2)
    picked = [int(dists.sum(axis=1).argmin())]
    while len(picked) < min(count, len(hashes)):
        d = dists[picked].min(axis=0)
        d[picked] = -1
        picked.append(int(d.argmax()))
    return picked


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("ref_dir", type=Path)
    ap.add_argument("--count", type=int, default=40)
    args = ap.parse_args()

    clean, board = args.ref_dir / "clean", args.ref_dir / "board"
    board.mkdir(parents=True, exist_ok=True)
    for old in board.glob("*"):
        old.unlink()

    frames = sorted(clean.glob("*.png"))
    groups: dict[str, list[Path]] = {}
    for p in frames:
        groups.setdefault(p.stem.rsplit("_", 1)[0], []).append(p)

    # An almost empty frame is the most "different" of all, so farthest-point
    # selection loves them. Drop frames with hardly any drawing in them first.
    def has_drawing(path: Path) -> bool:
        g = load_gray(path, width=320)
        return float(((g < 110) | (g > 245)).mean()) > 0.02 and float((g < 110).mean()) > 0.015

    groups = {v: [p for p in paths if has_drawing(p)] or paths for v, paths in groups.items()}
    frames = [p for paths in groups.values() for p in paths]

    chosen: list[Path] = []
    for video, paths in sorted(groups.items()):
        share = max(3, round(args.count * len(paths) / len(frames)))
        hashes = np.array([phash(load_gray(p, width=320)) for p in paths])
        chosen += [paths[i] for i in farthest_first(hashes, share)]

    for p in sorted(chosen):
        shutil.copy2(p, board / p.name)
    sheets = contact_sheets(sorted(board.glob("*.png")), board)
    write_json(args.ref_dir / "board-report.json", {
        "count": len(chosen),
        "per_video": {v: sum(1 for p in chosen if p.stem.rsplit("_", 1)[0] == v) for v in groups},
        "files": [p.name for p in sorted(chosen)],
        "contact_sheets": [s.name for s in sheets],
    })
    print(f"board: {len(chosen)} frames -> {board}")


if __name__ == "__main__":
    main()

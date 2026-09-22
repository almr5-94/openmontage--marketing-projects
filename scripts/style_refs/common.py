"""Shared helpers for the style-reference scripts (numpy + Pillow only)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
from PIL import Image

FRAME_RE = re.compile(r"^(?P<video>.+?)_frame_(?P<idx>\d+)\.png$")


def list_frames(raw_dir: Path) -> dict[str, list[Path]]:
    """Group frame files by video name, sorted by frame index."""
    groups: dict[str, list[tuple[int, Path]]] = {}
    for p in raw_dir.iterdir():
        m = FRAME_RE.match(p.name)
        if m:
            groups.setdefault(m["video"], []).append((int(m["idx"]), p))
    return {v: [p for _, p in sorted(items)] for v, items in sorted(groups.items())}


def load_gray(path: Path, box: tuple[int, int, int, int] | None = None, width: int | None = None) -> np.ndarray:
    img = Image.open(path).convert("L")
    if box:
        img = img.crop(box)
    if width:
        img = img.resize((width, round(img.height * width / img.width)), Image.BILINEAR)
    return np.asarray(img, dtype=np.float32)


def detect_content_box(frames: list[Path], samples: int = 60, inset: float = 0.035) -> tuple[int, int, int, int]:
    """Find the video picture inside a screen recording.

    The player draws an ambient glow around the picture that changes with it,
    so change-over-time cannot separate them. What stays put is the hard
    straight edge where the picture starts: for each row (and column) average
    the brightness jump to its neighbour over many frames and take the
    strongest jump in the outer quarter of each side. A side with no clear edge
    keeps the full frame. The inset then trims the channel logo burnt into the
    lower-right corner while keeping the aspect ratio.
    """
    step = max(1, len(frames) // samples)
    picked = frames[::step][:samples]
    full_w, full_h = Image.open(picked[0]).size
    scale = 4
    stack = np.stack([load_gray(p, width=full_w // scale) for p in picked])
    row_jump = np.abs(np.diff(stack, axis=1)).mean(axis=(0, 2))
    col_jump = np.abs(np.diff(stack, axis=2)).mean(axis=(0, 1))

    def edges(jump: np.ndarray, n: int) -> tuple[int, int]:
        q = n // 4
        # a real picture edge is one of the strongest straight lines in the whole frame
        floor = max(6 * float(np.median(jump)) + 0.5, 0.5 * float(jump.max()))
        lo = int(np.argmax(jump[:q]))
        hi = int(np.argmax(jump[-q:])) + len(jump) - q
        return (lo + 1 if jump[lo] > floor else 0, hi + 1 if jump[hi] > floor else n)

    top, bottom = (v * scale for v in edges(row_jump, stack.shape[1]))
    left, right = (v * scale for v in edges(col_jump, stack.shape[2]))
    bottom, right = min(bottom, full_h), min(right, full_w)
    w, h = right - left, bottom - top
    dx, dy = round(w * inset), round(h * inset)
    return (int(left + dx), int(top + dy), int(right - dx), int(bottom - dy))


def has_player_ui(path: Path) -> bool:
    """True when the YouTube player controls are drawn over the picture.

    Those frames carry the red progress bar near the bottom and the white
    video title near the top; either one means the frame is not clean art.
    """
    img = Image.open(path).convert("RGB")
    img = img.resize((img.width // 4, img.height // 4), Image.NEAREST)
    a = np.asarray(img).astype(np.int16)
    h = a.shape[0]
    band = a[int(h * 0.90) : int(h * 0.97)]
    red = ((band[..., 0] > 200) & (band[..., 1] < 70) & (band[..., 2] < 70)).sum()
    top = a[int(h * 0.03) : int(h * 0.085)]
    white = (top.min(axis=2) > 235).sum()
    return bool(red > 20 or white > 50)


def phash(gray: np.ndarray, size: int = 32, keep: int = 8) -> np.ndarray:
    """Perceptual hash: low-frequency DCT signs of a 32x32 thumbnail (64 bits)."""
    img = Image.fromarray(gray.astype(np.uint8)).resize((size, size), Image.BILINEAR)
    a = np.asarray(img, dtype=np.float64)
    n = np.arange(size)
    dct = np.cos(np.pi * (2 * n[None, :] + 1) * n[:, None] / (2 * size))
    coeffs = dct @ a @ dct.T
    low = coeffs[:keep, :keep].flatten()[1:]
    return low > np.median(low)


def _np_default(o):
    if isinstance(o, np.generic):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(type(o).__name__)


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=_np_default), encoding="utf-8")

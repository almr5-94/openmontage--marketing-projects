"""Measure how a hand-drawn reference keeps moving while a scene is "holding".

Usage:
    python -m scripts.style_refs.motion_analysis assets/references/ted-ed [--fps 24]
    python -m scripts.style_refs.motion_analysis <frames_dir> --flat --fps 30 --out <json>

The first form reads <ref>/raw/<video>_frame_NNNN.png and the picture boxes
from prepare_frames. --flat reads every PNG in a folder in name order (used to
measure one of our own renders the same way, for the side-by-side check).

For every consecutive pair of frames it measures:
  - global motion (sub-pixel pan and zoom) with phase correlation
  - line change: how much of the black linework moved after removing camera motion
  - background change: flicker in the flat paper areas
  - where the change is concentrated (a blink is local, a boil is everywhere)
and from those series derives the numbers the ted-ed-alive layer is driven by:
boil cadence and amplitude, grain flicker, drift speed and easing, hold lengths,
idle-motion rate and transition lengths. All pixel values are reported at a
1920 px wide frame so they can be used directly in a 1920x1080 composition.

Writes <ref>/motion-profile.json and, for the source set, <ref>/motion/ with
close-up GIFs and a timeline chart.
"""

from __future__ import annotations

import argparse
from multiprocessing import Pool
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from scripts.style_refs.common import detect_content_box, has_player_ui, list_frames, load_gray, write_json

W = 640            # analysis width
REF_W = 1920       # width that reported pixel values refer to
PX = REF_W / W
LINE_DARK = 90     # grey level below which a pixel counts as linework
CUT_MAD = 14.0     # mean abs diff above which a pair is a cut / transition frame
TRANSITION_MAD = 5.0
STATIC_MAD = 0.1   # pairs below this show no visible change at all


# ---------------------------------------------------------------- primitives
def _hann(h: int, w: int) -> np.ndarray:
    return np.outer(np.hanning(h), np.hanning(w)).astype(np.float32)


def phase_shift(a: np.ndarray, b: np.ndarray) -> tuple[float, float, float]:
    """Sub-pixel translation of b relative to a, plus peak strength (0..1)."""
    win = _hann(*a.shape)
    fa, fb = np.fft.fft2((a - a.mean()) * win), np.fft.fft2((b - b.mean()) * win)
    r = fb * np.conj(fa)
    r /= np.abs(r) + 1e-9
    corr = np.fft.ifft2(r).real
    peak = np.unravel_index(np.argmax(corr), corr.shape)
    h, w = corr.shape

    def sub(c_m, c_0, c_p):
        d = c_m - 2 * c_0 + c_p
        return 0.0 if abs(d) < 1e-9 else 0.5 * (c_m - c_p) / d

    py, px = peak
    dy = py + sub(corr[(py - 1) % h, px], corr[py, px], corr[(py + 1) % h, px])
    dx = px + sub(corr[py, (px - 1) % w], corr[py, px], corr[py, (px + 1) % w])
    dy = dy - h if dy > h / 2 else dy
    dx = dx - w if dx > w / 2 else dx
    return float(dx), float(dy), float(corr[py, px])


def dilate(mask: np.ndarray, r: int) -> np.ndarray:
    out = mask.copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if dx or dy:
                out |= np.roll(np.roll(mask, dy, 0), dx, 1)
    return out


def zoom_between(first: np.ndarray, second: np.ndarray) -> float:
    """Scale change from `first` to `second`, found by trying scales.

    Deriving zoom from how far the two halves of the frame move apart is
    fragile: the correlation peak follows whatever is most detailed, not the
    geometric centre. Scaling the first frame and keeping the best match is
    slower but reads a 7% push-in as 7%.
    """
    h, w = first.shape
    img = Image.fromarray(first.astype(np.uint8))

    def score(s: float) -> float:
        if abs(s - 1) < 1e-6:
            cand = first
        else:
            nw, nh = max(8, round(w * s)), max(8, round(h * s))
            r = np.asarray(img.resize((nw, nh), Image.BILINEAR), dtype=np.float32)
            if s > 1:  # crop back to the original frame around the centre
                x, y = (nw - w) // 2, (nh - h) // 2
                cand = r[y : y + h, x : x + w]
            else:      # pad back out with the frame's own mean
                cand = np.full((h, w), float(r.mean()), dtype=np.float32)
                x, y = (w - nw) // 2, (h - nh) // 2
                cand[y : y + nh, x : x + nw] = r
        return phase_shift(cand, second)[2]

    best, best_s = -1.0, 1.0
    for step, span in ((0.01, 0.12), (0.002, 0.012)):
        grid = np.arange(best_s - span, best_s + span + 1e-9, step)
        vals = [(score(float(s)), float(s)) for s in grid if 0.5 < s < 2]
        best, best_s = max(vals)
    return best_s - 1


def pair_stats(args) -> dict:
    pa, pb, box = args
    a, b = load_gray(pa, box, W), load_gray(pb, box, W)
    h, w = a.shape
    mad = float(np.abs(b - a).mean())
    dx, dy, strength = phase_shift(a, b)
    # zoom from opposite halves moving apart / together
    lx, _, _ = phase_shift(a[:, : w // 2], b[:, : w // 2])
    rx, _, _ = phase_shift(a[:, w // 2 :], b[:, w // 2 :])
    _, ty, _ = phase_shift(a[: h // 2], b[: h // 2])
    _, by, _ = phase_shift(a[h // 2 :], b[h // 2 :])
    zoom = ((rx - lx) / (w / 2) + (by - ty) / (h / 2)) / 2

    # remove the integer part of camera motion, then compare linework
    ib = np.roll(np.roll(b, -round(dy), 0), -round(dx), 1)
    m = 6  # ignore borders touched by the roll
    a_c, b_c = a[m:-m, m:-m], ib[m:-m, m:-m]
    la, lb = a_c < LINE_DARK, b_c < LINE_DARK
    n_lines = max(1, int(la.sum()))
    line_change = float((la ^ lb).sum() / n_lines)
    amp = None
    if lb.sum() > 50:
        for r in range(0, 5):
            if (lb & dilate(la, r)).sum() / lb.sum() >= 0.9:
                amp = r
                break
        else:
            amp = 5

    near_line = dilate(la | lb, 3)
    bg = ~near_line & (a_c > 40)
    diff = b_c - a_c
    bg_flicker = float(diff[bg].std()) if bg.sum() > 500 else None

    changed = np.abs(diff) > 25
    frac_changed = float(changed.mean())
    # concentration: share of changed pixels inside the busiest cell of a 6x6 grid
    gh, gw = changed.shape[0] // 6, changed.shape[1] // 6
    cells = changed[: gh * 6, : gw * 6].reshape(6, gh, 6, gw).sum(axis=(1, 3))
    concentration = float(cells.max() / max(1, cells.sum()))
    return {
        "ui": has_player_ui(pb),
        "mad": mad, "dx": dx, "dy": dy, "zoom": zoom, "strength": strength,
        "line_change": line_change, "line_amp": amp, "bg_flicker": bg_flicker,
        "changed": frac_changed, "concentration": concentration,
    }


# ---------------------------------------------------------------- analysis
def runs(flags: np.ndarray) -> list[tuple[int, int]]:
    """(start, length) of consecutive True runs."""
    out, start = [], None
    for i, f in enumerate(list(flags) + [False]):
        if f and start is None:
            start = i
        elif not f and start is not None:
            out.append((start, i - start))
            start = None
    return out


def pct(x, q):
    x = [v for v in x if v is not None]
    return round(float(np.percentile(x, q)), 4) if x else None


def analyse_series(stats: list[dict], fps: float) -> dict:
    # Frames are sampled at a fixed rate from the recording, so time is frames / fps.
    # Pairs with no visible change are kept: they are part of how long a hold lasts.
    live = stats
    eff_fps = fps

    lm = np.array([s["mad"] for s in live])
    cut = lm > CUT_MAD
    ui = np.array([s.get("ui", False) for s in live])
    trans = (lm > TRANSITION_MAD) | ui
    trans_runs = [(s, n) for s, n in runs(trans) if cut[s : s + n].any()]
    hard_cuts = sum(1 for _, n in trans_runs if n <= 1)
    soft = [n for _, n in trans_runs if n > 1]

    # shots = spans between transitions
    boundaries = sorted({0, len(live)} | {s for s, _ in trans_runs} | {s + n for s, n in trans_runs})
    shots = [(a, b) for a, b in zip(boundaries, boundaries[1:]) if b - a >= 6 and not trans[a:b].all()]

    # "holding" = inside a shot, little local change beyond boil and camera drift
    changed = np.array([s["changed"] for s in live])
    conc = np.array([s["concentration"] for s in live])
    line = np.array([s["line_change"] for s in live])
    hold = (changed < 0.01) & ~trans
    hold_runs = [n for _, n in runs(hold) if n >= 3]

    # boil: linework that changes on a beat while the shot holds
    hold_line = line[hold]
    boil_thr = max(0.02, float(np.percentile(hold_line, 75))) if hold_line.size else 0.02
    boil_ev = hold & (line > boil_thr)
    ev_idx = np.where(boil_ev)[0]
    gaps = np.diff(ev_idx)
    gaps = gaps[(gaps >= 1) & (gaps <= 12)]
    cadence = int(np.bincount(gaps).argmax()) if gaps.size else None
    ac = None
    if hold_line.size > 40:
        x = hold_line - hold_line.mean()
        ac_full = np.correlate(x, x, "full")[x.size - 1 :]
        ac_full /= ac_full[0] + 1e-9
        lag = int(np.argmax(ac_full[2:9]) + 2)
        ac = {"lag_frames": lag, "strength": round(float(ac_full[lag]), 3)}
    amps = [s["line_amp"] for s, e in zip(live, boil_ev) if e and s["line_amp"] is not None]

    # idle motion: small, concentrated change while holding (blinks, a hand, a nod)
    idle = (changed > 0.0005) & (changed < 0.03) & (conc > 0.5) & ~trans
    idle_events = len(runs(idle))
    minutes = len(live) / eff_fps / 60 if eff_fps else 0

    shot_secs = [(b - a) / eff_fps for a, b in shots]
    # Camera drift is measured end-to-end per shot by shot_drift(); adding up
    # per-frame estimates accumulates their noise into a fake zoom.
    return {
        "pairs": len(stats),
        "fps": eff_fps,
        "player_ui_share": round(float(ui.mean()), 3),
        "static_pair_share": round(float((lm < STATIC_MAD).mean()), 3),
        "shots": len(shots),
        "shot_seconds": {"p25": pct(shot_secs, 25), "median": pct(shot_secs, 50), "p75": pct(shot_secs, 75)},
        "transitions": {
            "hard_cuts": hard_cuts,
            "soft": len(soft),
            "soft_frames": {"median": pct(soft, 50), "p75": pct(soft, 75)},
        },
        "hold": {
            "share_of_time_holding": round(float(hold.mean()), 3),
            "hold_seconds": {"median": pct(np.array(hold_runs) / eff_fps, 50) if hold_runs else None,
                              "p75": pct(np.array(hold_runs) / eff_fps, 75) if hold_runs else None},
        },
        "line_boil": {
            "threshold_line_change": round(boil_thr, 4),
            "events_share_of_hold_frames": round(float(boil_ev.sum() / max(1, hold.sum())), 3),
            "cadence_frames_mode": cadence,
            "cadence_seconds": round(cadence / eff_fps, 3) if cadence else None,
            "autocorrelation": ac,
            "line_change_while_holding": {"median": pct(hold_line, 50), "p90": pct(hold_line, 90)},
            "amplitude_px_at_1920": {
                "median": round(float(np.median(amps)) * PX, 2) if amps else None,
                "p90": round(float(np.percentile(amps, 90)) * PX, 2) if amps else None,
            },
        },
        "paper_grain": {
            "bg_flicker_std_while_holding": pct([s["bg_flicker"] for s, h in zip(live, hold) if h], 50),
            "bg_flicker_std_p90": pct([s["bg_flicker"] for s, h in zip(live, hold) if h], 90),
        },
        "camera_drift": None,  # filled in by shot_drift()
        "idle_motion": {"events": idle_events, "per_minute": round(idle_events / minutes, 1) if minutes else None},
        "_shots": shots,
        "_series": {"mad": lm.round(3).tolist(), "line": line.round(4).tolist(),
                    "hold": hold.astype(int).tolist(), "boil": boil_ev.astype(int).tolist()},
    }


def shot_drift(frames: list[Path], box, shots: list[tuple[int, int]], fps: float) -> dict:
    """Measure each shot's camera move once, from its first frame to its last.

    Per-frame estimates are far below the noise floor of phase correlation, so
    summing them invents a zoom that is not there. Comparing the two ends of a
    shot (and its quarter points, for the easing) keeps the estimate above the
    noise.
    """
    moving = []
    for a, b in shots:
        if b - a < 8:
            continue
        idx = [a, a + (b - a) // 4, a + (b - a) // 2, a + 3 * (b - a) // 4, b - 1]
        imgs = [load_gray(frames[i], box, W) for i in idx]
        legs = []
        for first, second in zip(imgs, imgs[1:]):
            dx, dy, _ = phase_shift(first, second)
            legs.append((dx, dy, zoom_between(first, second)))
        dur = (b - a) / fps
        pan = float(np.hypot(sum(l[0] for l in legs), sum(l[1] for l in legs))) * PX
        zoom_total = float(np.prod([1 + l[2] for l in legs]) - 1)
        if pan < 6 and abs(zoom_total) < 0.01:
            continue
        speed = [abs(l[0]) + abs(l[1]) + abs(l[2]) * W for l in legs]
        easing = ("ease-in-out" if max(speed[1], speed[2]) > 1.3 * max(speed[0], speed[3])
                  else "ease-out" if speed[0] > 1.3 * speed[3]
                  else "ease-in" if speed[3] > 1.3 * speed[0] else "linear")
        moving.append({
            "seconds": round(dur, 2),
            "pan_px_per_s": round(pan / dur, 2),
            "zoom_pct_per_s": round(100 * zoom_total / dur, 3),
            "direction": "push-in" if zoom_total > 0.005 else ("pull-out" if zoom_total < -0.005 else "pan"),
            "easing": easing,
        })
    n_shots = sum(1 for a, b in shots if b - a >= 8)
    return {
        "shots_measured": n_shots,
        "share_of_shots_moving": round(len(moving) / max(1, n_shots), 3),
        "pan_px_per_s": {"median": pct([m["pan_px_per_s"] for m in moving], 50),
                         "p75": pct([m["pan_px_per_s"] for m in moving], 75)},
        "zoom_pct_per_s": {"median": pct([m["zoom_pct_per_s"] for m in moving], 50),
                           "p75": pct([m["zoom_pct_per_s"] for m in moving], 75)},
        "directions": {k: sum(1 for m in moving if m["direction"] == k) for k in ("push-in", "pull-out", "pan")},
        "easing": {k: sum(1 for m in moving if m["easing"] == k)
                   for k in ("linear", "ease-in", "ease-out", "ease-in-out")},
    }


# ---------------------------------------------------------------- visuals
def timeline_png(series: dict, dest: Path, title: str) -> None:
    mad, line = np.array(series["mad"]), np.array(series["line"])
    n = min(len(mad), 1600)
    w, h = 1600, 360
    img = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(img)
    d.text((8, 6), title + "  (grey = holding, red = boil event; top: picture change, bottom: line change)", fill="black")
    for i in range(n):
        x = int(i * w / n)
        if series["hold"][i]:
            d.line([(x, 30), (x, h)], fill=(235, 235, 235))
        if series["boil"][i]:
            d.line([(x, h - 10), (x, h)], fill=(220, 40, 40))
    for arr, top, bot, col in ((mad, 30, 190, (40, 40, 40)), (line, 200, 340, (30, 90, 200))):
        v = np.clip(arr[:n] / (np.percentile(arr[:n], 98) + 1e-9), 0, 1)
        pts = [(int(i * w / n), int(bot - v[i] * (bot - top))) for i in range(n)]
        d.line(pts, fill=col, width=1)
    img.save(dest)


def closeup_gif(frames: list[Path], box, start: int, count: int, fps: float, dest: Path) -> None:
    """3x close-up of the most line-dense tile, so the boil is visible."""
    imgs = [Image.open(p).convert("RGB").crop(box) for p in frames[start : start + count]]
    g = np.asarray(imgs[0].convert("L"), dtype=np.float32)
    th, tw = g.shape[0] // 4, g.shape[1] // 4
    best, best_xy = -1, (0, 0)
    for y in range(0, g.shape[0] - th, th // 2):
        for x in range(0, g.shape[1] - tw, tw // 2):
            s = (g[y : y + th, x : x + tw] < LINE_DARK).mean()
            if s > best:
                best, best_xy = s, (x, y)
    x, y = best_xy
    tiles = [im.crop((x, y, x + tw, y + th)).resize((min(960, tw * 3), min(540, th * 3)), Image.NEAREST) for im in imgs]
    tiles[0].save(dest, save_all=True, append_images=tiles[1:], duration=int(1000 / fps), loop=0)


def full_gif(frames: list[Path], box, start: int, count: int, fps: float, dest: Path) -> None:
    imgs = []
    for p in frames[start : start + count]:
        im = Image.open(p).convert("RGB").crop(box)
        imgs.append(im.resize((640, round(im.height * 640 / im.width)), Image.LANCZOS))
    imgs[0].save(dest, save_all=True, append_images=imgs[1:], duration=int(1000 / fps), loop=0)


def strip_private(d: dict) -> dict:
    return {k: v for k, v in d.items() if not k.startswith("_")}


# ---------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("src", type=Path)
    ap.add_argument("--fps", type=float, default=24.0, help="frame rate the frames were extracted at")
    ap.add_argument("--flat", action="store_true", help="src is a plain folder of frames (our own render)")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--workers", type=int, default=16)
    args = ap.parse_args()

    if args.flat:
        frames = sorted(args.src.glob("*.png"))
        w, h = Image.open(frames[0]).size
        videos, boxes = {"render": frames}, {"render": (0, 0, w, h)}
        out = args.out or args.src / "motion-profile.json"
        vis_dir = None
    else:
        import json
        videos = list_frames(args.src / "raw")
        box_file = args.src / "work" / "boxes.json"
        if box_file.exists():
            boxes = {k: tuple(v) for k, v in json.loads(box_file.read_text()).items()}
        else:
            boxes = {k: detect_content_box(f) for k, f in videos.items()}
            write_json(box_file, boxes)
        out = args.out or args.src / "motion-profile.json"
        vis_dir = args.src / "motion"
        vis_dir.mkdir(exist_ok=True)

    result = {"fps_assumed": args.fps, "pixel_reference_width": REF_W, "videos": {}}
    with Pool(args.workers) as pool:
        for v, frames in videos.items():
            jobs = [(frames[i], frames[i + 1], boxes[v]) for i in range(len(frames) - 1)]
            stats = pool.map(pair_stats, jobs, chunksize=8)
            a = analyse_series(stats, args.fps)
            a["camera_drift"] = shot_drift(frames, boxes[v], a["_shots"], args.fps)
            result["videos"][v] = strip_private(a)
            print(v, {k: a[k] for k in ("static_pair_share", "shots", "line_boil", "paper_grain", "camera_drift")})
            if vis_dir:
                timeline_png(a["_series"], vis_dir / f"{v}_timeline.png", v)
                # longest held stretch -> boil close-up; longest shot -> full view
                hold_runs = runs(np.array(a["_series"]["hold"], dtype=bool))
                if hold_runs:
                    s, n = max(hold_runs, key=lambda r: r[1])
                    closeup_gif(frames, boxes[v], s, min(n, 72), args.fps, vis_dir / f"{v}_boil_closeup.gif")
                    full_gif(frames, boxes[v], s, min(n, 96), args.fps, vis_dir / f"{v}_hold_full.gif")

    # pooled numbers weighted by length, which is what the HyperFrames layer reads
    # A video that shows the player controls most of the time was mostly
    # recorded while scrubbing; its timing is not the animation's timing.
    vids = [v for v in result["videos"].values() if v["player_ui_share"] <= 0.5]
    result["pooled_from"] = [k for k, v in result["videos"].items() if v["player_ui_share"] <= 0.5]
    total = sum(v["pairs"] for v in vids)

    def wavg(get):
        vals = [(get(v), v["pairs"] * (1 - v["player_ui_share"])) for v in vids if get(v) is not None]
        return round(sum(x * n for x, n in vals) / sum(n for _, n in vals), 4) if vals else None

    result["pooled"] = {
        "boil_cadence_seconds": wavg(lambda v: v["line_boil"]["cadence_seconds"]),
        "boil_amplitude_px": wavg(lambda v: v["line_boil"]["amplitude_px_at_1920"]["median"]),
        "line_change_while_holding_median": wavg(lambda v: v["line_boil"]["line_change_while_holding"]["median"]),
        "boil_share_of_hold_frames": wavg(lambda v: v["line_boil"]["events_share_of_hold_frames"]),
        "grain_flicker_std": wavg(lambda v: v["paper_grain"]["bg_flicker_std_while_holding"]),
        "drift_pan_px_per_s": wavg(lambda v: v["camera_drift"]["pan_px_per_s"]["median"]),
        "drift_zoom_pct_per_s": wavg(lambda v: v["camera_drift"]["zoom_pct_per_s"]["median"]),
        "share_of_shots_moving": wavg(lambda v: v["camera_drift"]["share_of_shots_moving"]),
        "shot_seconds_median": wavg(lambda v: v["shot_seconds"]["median"]),
        "soft_transition_seconds": wavg(lambda v: v["transitions"]["soft_frames"]["median"] / v["fps"]
                                         if v["transitions"]["soft_frames"]["median"] else None),
        "idle_events_per_minute": wavg(lambda v: v["idle_motion"]["per_minute"]),
        "fps": wavg(lambda v: v["fps"]),
        "pairs": total,
    }
    write_json(out, result)
    print("pooled", result["pooled"])
    print("wrote", out)


if __name__ == "__main__":
    main()

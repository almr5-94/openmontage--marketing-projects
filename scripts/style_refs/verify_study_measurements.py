"""Re-measure the forensic study's colour samples on the same pixels.

Usage:
    python -m scripts.style_refs.verify_study_measurements \
        assets/references/handdrawn/work/study/image-measurements.json \
        assets/references/handdrawn/work/anchors \
        docs/handdrawn-palette-verification.md

The style playbooks quote hex values from the study. Before a number is used as
a design rule it is re-read from the original frame at the study's own box, so a
mistyped value or a mismatched frame cannot enter the pipeline unnoticed. Each
row reports the study's value, the re-measured value, and the distance between
them; anything above the tolerance is flagged and must be labelled in the
playbook rather than used silently.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image

TOL = 3  # per-channel levels; captured PNGs are lossless so a match should be exact


def hexof(rgb) -> str:
    return "#%02X%02X%02X" % tuple(int(v) for v in rgb)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("measurements", type=Path)
    ap.add_argument("frames_dir", type=Path)
    ap.add_argument("out_md", type=Path)
    args = ap.parse_args()

    data = json.loads(args.measurements.read_text(encoding="utf-8"))
    rows, flagged, missing = [], 0, 0

    for anchor in data["anchors"]:
        path = args.frames_dir / anchor["file"]
        if not path.exists():
            rows.append((anchor["id"], anchor["file"], "-", "-", "-", "-", "frame not available"))
            missing += 1
            continue
        arr = np.asarray(Image.open(path).convert("RGB"), dtype=np.int16)
        for name, roi in anchor["rois"].items():
            x0, y0, x1, y1 = roi["box_xyxy"]
            patch = arr[y0:y1, x0:x1]
            med = np.median(patch.reshape(-1, 3), axis=0)
            luma = patch.mean(axis=2)
            got_hex, want_hex = hexof(med), roi.get("hex", "-")
            delta = max(abs(int(med[i]) - int(roi["median_rgb"][i])) for i in range(3)) if roi.get("median_rgb") else None
            sd_got = float(luma.std())
            sd_want = roi.get("luma_sd")
            ok = delta is not None and delta <= TOL
            if not ok:
                flagged += 1
            rows.append((
                anchor["id"], f'{anchor["file"]}:{name}', want_hex, got_hex,
                f"{delta}" if delta is not None else "-",
                f"{sd_want:.3f} / {sd_got:.3f}" if sd_want is not None else f"- / {sd_got:.3f}",
                "match" if ok else "FLAG",
            ))

    checked = sum(1 for r in rows if r[6] in ("match", "FLAG"))
    lines = [
        "# Palette verification — the study's samples re-measured",
        "",
        f"Source: `{args.measurements}` (companion to forensic-illustration-study.md).",
        f"Frames re-read from `{args.frames_dir}` at the study's own `box_xyxy` boxes.",
        "",
        f"**{checked - flagged} of {checked} samples reproduce within {TOL} levels per channel.** "
        f"{flagged} flagged, {missing} anchors unavailable.",
        "",
        "A flagged row means the playbook must not quote that value as measured.",
        "The `luma sd` column is the study's value against the re-measured one; it uses the",
        "study's definition (arithmetic channel mean, not calibrated luminance).",
        "",
        "| Anchor | Frame : region | Study hex | Re-measured | Max channel delta | luma sd study / now | Result |",
        "|---|---|---|---|---|---|---|",
    ]
    lines += [f"| {r[0]} | `{r[1]}` | {r[2]} | {r[3]} | {r[4]} | {r[5]} | {r[6]} |" for r in rows]
    lines.append("")
    args.out_md.parent.mkdir(parents=True, exist_ok=True)
    args.out_md.write_text("\n".join(lines), encoding="utf-8")
    print(f"{checked - flagged}/{checked} samples match within {TOL}; {flagged} flagged; {missing} anchors missing")
    for r in rows:
        if r[6] == "FLAG":
            print("  FLAG", r[1], "study", r[2], "now", r[3], "delta", r[4])


if __name__ == "__main__":
    main()

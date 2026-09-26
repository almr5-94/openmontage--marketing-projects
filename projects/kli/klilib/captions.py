"""Fill the HyperFrames composition from the narration timeline and the fitted shots."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from lib.arabic_captions import assert_caption_safe, to_latin_digits

from .common import SERIES_DIR

TEMPLATE = SERIES_DIR / "composition" / "index.tpl.html"
ASSETS = SERIES_DIR / "composition" / "assets"


def build_composition(project_dir: Path, comp_id: str, title: str, shots: list[dict], chunks: list[list],
                      takeaway: str, source_line: str, total: float, end_at: float) -> Path:
    """shots: [{id, start, duration, path}] with path relative to the project. Returns composition dir."""
    comp = project_dir / "composition"
    (comp / "assets").mkdir(parents=True, exist_ok=True)
    for f in ASSETS.iterdir():
        dst = comp / "assets" / f.name
        if not dst.exists():
            shutil.copy2(f, dst)
    slots = []
    for i, s in enumerate(shots):
        src = Path(s["path"])
        dst = comp / "assets" / src.name
        if not dst.exists() or dst.stat().st_size != src.stat().st_size:
            shutil.copy2(src, dst)
        slots.append(
            f'  <div class="vw" id="w{s["id"]}"><video id="v{s["id"]}" class="vid" src="assets/{src.name}" muted playsinline '
            f'data-start="{s["start"]:.2f}" data-duration="{s["duration"]:.2f}" data-track-index="{i + 2}"></video></div>')
    safe_chunks = []
    for txt, st, en, head in chunks:
        txt = to_latin_digits(txt)
        assert_caption_safe(txt)
        safe_chunks.append([txt, st, en, bool(head)])
    html = (TEMPLATE.read_text(encoding="utf-8")
            .replace("__TITLE__", title)
            .replace("__COMP_ID__", comp_id)
            .replace("__DURATION__", f"{total:.2f}")
            .replace("__VIDEO_SLOTS__", "\n".join(slots))
            .replace("__TAKEAWAY__", to_latin_digits(takeaway))
            .replace("__SOURCE__", to_latin_digits(source_line))
            .replace("__SHOTS__", json.dumps([{"id": s["id"], "start": round(s["start"], 2), "duration": round(s["duration"], 2)} for s in shots]))
            .replace("__CHUNKS__", json.dumps(safe_chunks, ensure_ascii=False))
            .replace("__END_AT__", f"{end_at:.2f}"))
    (comp / "index.html").write_text(html, encoding="utf-8")
    return comp

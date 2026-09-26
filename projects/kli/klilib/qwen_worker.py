"""Run one Qwen-Image-Edit call in a child process.

The 20B editor holds ~10 GB of RAM as well as the card; when another job on the
machine bursts, the kernel OOM-killer takes the biggest process. Rendering in a
child means a kill costs one still, not the whole reel: the parent sees a non-zero
exit and falls back to Imagen.

    .venv/bin/python projects/kli/klilib/qwen_worker.py <inputs.json>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from klilib.common import run_tool  # noqa: E402

if __name__ == "__main__":
    inputs = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    r = run_tool("qwen_image_edit_local", inputs)
    print(json.dumps({"success": r.success, "cost_usd": r.cost_usd, "seed": r.seed}))

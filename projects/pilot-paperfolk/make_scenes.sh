#!/usr/bin/env bash
# Generate every scene still for the pilot, each one checked before it is accepted.
set -euo pipefail
P=/home/abood/work/openmontage--marketing-projects
cd "$P"
export COMFYUI_SERVER_URL="${COMFYUI_SERVER_URL:-http://127.0.0.1:8188}"
OUT="$P/projects/pilot-paperfolk/scenes"
mkdir -p "$OUT"
.venv/bin/python - "$OUT" <<'PY'
import json, subprocess, sys
from pathlib import Path
out = Path(sys.argv[1])
script = json.loads(Path("projects/pilot-paperfolk/script.json").read_text())
for scene in script["scenes"]:
    dest = out / f'{scene["id"]}.png'
    cmd = [".venv/bin/python", "-m", "scripts.style_refs.generate_scene", script["family"],
           scene["prompt"], "--out", str(dest)]
    if scene["subjects"]:
        cmd += ["--subjects", str(scene["subjects"]), "--noun", "people"]
    print("==", scene["id"], scene["line"], flush=True)
    subprocess.run(cmd, check=True)
PY
echo SCENES-DONE
ls -la "$OUT"

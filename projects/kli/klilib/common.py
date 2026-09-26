"""Paths, registry access and small helpers shared by every KLI script.

Every script runs from the OpenMontage repo root with the repo's venv:
    .venv/bin/python projects/kli/kli_daily.py run
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

OM_ROOT = Path(__file__).resolve().parents[3]
SERIES_DIR = OM_ROOT / "projects" / "kli"
PROJECTS_DIR = OM_ROOT / "projects"
KUWAIT_TZ = "Asia/Kuwait"

if str(OM_ROOT) not in sys.path:
    sys.path.insert(0, str(OM_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(OM_ROOT / ".env")

_registry = None


def registry():
    """The OpenMontage tool registry, discovered once per process."""
    global _registry
    if _registry is None:
        from tools.tool_registry import registry as reg

        reg.discover()
        _registry = reg
    return _registry


def tool(name: str):
    t = registry()._tools.get(name)
    if t is None:
        raise RuntimeError(f"OpenMontage tool not found: {name}")
    return t


def run_tool(name: str, inputs: dict[str, Any]):
    """Execute a registry tool and raise on failure so a stage cannot half-succeed silently."""
    r = tool(name).execute(inputs)
    if not r.success:
        raise RuntimeError(f"{name} failed: {r.error}")
    return r


def read_json(path: Path, default: Any = None) -> Any:
    if not Path(path).exists():
        if default is not None:
            return default
        raise FileNotFoundError(path)
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def kuwait_now() -> datetime:
    from zoneinfo import ZoneInfo

    return datetime.now(ZoneInfo(KUWAIT_TZ))


def ffprobe(path: Path) -> dict[str, Any]:
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path)],
        text=True,
    )
    return json.loads(out)


def media_duration(path: Path) -> float:
    return float(ffprobe(path)["format"]["duration"])


def sh(cmd: list[str], cwd: Path | None = None, timeout: int = 1800) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(cwd or OM_ROOT), text=True, capture_output=True, timeout=timeout)


def project_dir(project_id: str) -> Path:
    return PROJECTS_DIR / project_id


def reel_id(date_str: str) -> str:
    return "kli-" + date_str.replace("-", "")


def series_config() -> dict[str, Any]:
    return read_json(SERIES_DIR / "project.json")


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

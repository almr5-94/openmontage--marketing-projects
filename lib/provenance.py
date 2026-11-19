"""Provenance ledger: where every imported, cropped or generated picture came from.

Hard rule (editorial art stack): source art must be CC0 / public domain, licensed stock
(Pexels, Pixabay), supplied by the user, or generated in this session. Every asset placed
in a project gets a record in ``projects/<id>/assets/PROVENANCE.json``:

    source, URL, licence, object ID, date fetched, the crop applied, the parent asset.

Records are append-only. A crop or a collage points at its parent(s), so the chain from a
finished page back to the museum object is always recoverable. ``check_complete`` is the
blocking gate the review stages run: every image a layout uses must have a record whose
licence is on the allowed list.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

PROVENANCE_FILE = "PROVENANCE.json"

# Licence classes that may appear in a publication. Anything else is refused.
ALLOWED_LICENCES = {
    "CC0",
    "public-domain",
    "pexels-license",
    "pixabay-license",
    "user-supplied",
    "generated-in-session",
    "derived",  # a crop/collage/edit of assets that are themselves allowed (checked via parents)
}

KINDS = {"museum", "stock", "user", "generated", "generative_art", "fragment", "collage", "render"}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def project_root(project_dir: str | Path) -> Path:
    return Path(project_dir).resolve()


def ledger_path(project_dir: str | Path) -> Path:
    return project_root(project_dir) / "assets" / PROVENANCE_FILE


def load(project_dir: str | Path) -> dict[str, Any]:
    p = ledger_path(project_dir)
    if not p.exists():
        return {"version": "1.0", "assets": []}
    return json.loads(p.read_text(encoding="utf-8"))


def _save(project_dir: str | Path, data: dict[str, Any]) -> None:
    p = ledger_path(project_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=".prov-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, p)


def rel(project_dir: str | Path, path: str | Path) -> str:
    """Path of an asset relative to the project folder (how records store it)."""
    try:
        return str(Path(path).resolve().relative_to(project_root(project_dir)))
    except ValueError:
        return str(Path(path).resolve())


def record(
    project_dir: str | Path,
    path: str | Path,
    *,
    kind: str,
    source: str,
    licence: str,
    source_url: Optional[str] = None,
    image_url: Optional[str] = None,
    object_id: Optional[str] = None,
    title: Optional[str] = None,
    creator: Optional[str] = None,
    crop: Optional[dict[str, Any]] = None,
    parents: Iterable[str] = (),
    tool: Optional[str] = None,
    seed: Optional[int] = None,
    notes: Optional[str] = None,
) -> dict[str, Any]:
    """Append one record. Returns it. Raises ValueError on a disallowed licence."""
    if kind not in KINDS:
        raise ValueError(f"unknown provenance kind {kind!r}; one of {sorted(KINDS)}")
    if licence not in ALLOWED_LICENCES:
        raise ValueError(
            f"licence {licence!r} is not allowed in a publication "
            f"(allowed: {sorted(ALLOWED_LICENCES)})"
        )
    data = load(project_dir)
    rp = rel(project_dir, path)
    rec = {
        "asset_id": f"{kind}:{Path(rp).stem}",
        "path": rp,
        "kind": kind,
        "source": source,
        "source_url": source_url,
        "image_url": image_url,
        "licence": licence,
        "object_id": None if object_id is None else str(object_id),
        "title": title,
        "creator": creator,
        "date_fetched": _now(),
        "sha256": sha256_file(path) if Path(path).exists() else None,
        "crop": crop,
        "parents": list(parents),
        "tool": tool,
        "seed": seed,
        "notes": notes,
    }
    # One live record per path: a re-import of the same file replaces its record
    # (the old one is kept under "superseded" so history is never lost).
    keep = []
    for a in data["assets"]:
        if a["path"] == rp:
            data.setdefault("superseded", []).append(a)
        else:
            keep.append(a)
    keep.append(rec)
    data["assets"] = keep
    _save(project_dir, data)
    return rec


def find(project_dir: str | Path, path: str | Path) -> Optional[dict[str, Any]]:
    rp = rel(project_dir, path)
    for a in load(project_dir)["assets"]:
        if a["path"] == rp:
            return a
    return None


def lineage(project_dir: str | Path, path: str | Path) -> list[dict[str, Any]]:
    """The record for ``path`` followed by every ancestor (breadth-first)."""
    data = {a["path"]: a for a in load(project_dir)["assets"]}
    start = data.get(rel(project_dir, path))
    if not start:
        return []
    out, queue, seen = [], [start], set()
    while queue:
        a = queue.pop(0)
        if a["path"] in seen:
            continue
        seen.add(a["path"])
        out.append(a)
        queue.extend(data[p] for p in a.get("parents", []) if p in data)
    return out


def check_complete(project_dir: str | Path, used_images: Iterable[str | Path]) -> dict[str, Any]:
    """Blocking gate: every used image has a record and an allowed licence chain.

    Returns {"pass": bool, "missing": [...], "bad_licence": [...], "broken_chain": [...]}.
    """
    missing, bad, broken = [], [], []
    records = {a["path"]: a for a in load(project_dir)["assets"]}
    for img in used_images:
        rp = rel(project_dir, img)
        rec = records.get(rp)
        if rec is None:
            missing.append(rp)
            continue
        if rec["licence"] not in ALLOWED_LICENCES:
            bad.append(rp)
        if rec["licence"] == "derived":
            if not rec.get("parents"):
                broken.append(rp)
            for parent in rec.get("parents", []):
                if parent not in records:
                    broken.append(f"{rp} -> {parent}")
    return {
        "pass": not (missing or bad or broken),
        "missing": missing,
        "bad_licence": bad,
        "broken_chain": broken,
    }

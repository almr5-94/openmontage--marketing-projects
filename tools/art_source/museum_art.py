"""Open-access museum art: the Met, Art Institute of Chicago, Cleveland, Rijksmuseum.

Free, no keys. Always option one in any "source art" menu (Rule Zero still logs the choice).

Common contract for every tool in this module::

    {"operation": "search", "query": "brass astrolabe", "limit": 10}
        -> data["results"] = [{object_id, title, creator, date, public_domain,
                               image_url, source_url, preview_url}]
    {"operation": "fetch", "object_id": "451699", "project_dir": "projects/x"}
        -> downloads into projects/x/assets/art/<source>-<id>.jpg, writes PROVENANCE
           (licence CC0/public-domain), or fails with "not public domain" and downloads nothing.

The public-domain flag is checked on the object record fetched at download time, never on a
cached search hit, so a later change by the museum is respected.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
import urllib.error
from abc import abstractmethod
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Optional

from lib import provenance
from tools.base_tool import (
    BaseTool,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    ToolResult,
    ToolRuntime,
    ToolStability,
    ToolStatus,
    ToolTier,
)

USER_AGENT = "OpenMontage/1.0 (art_source; open-access museum client)"


def _get(url: str, *, accept: str = "application/json", timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        # Some museum CDNs (the Art Institute's IIIF server) sit behind a bot filter that
        # rejects Python's TLS client but serves curl. Retry once through curl, arguments
        # passed as a list (no shell).
        if e.code != 403 or not shutil.which("curl"):
            raise
        out = subprocess.run(
            ["curl", "-sfL", "--max-time", str(timeout), "-A", USER_AGENT, "-H", f"Accept: {accept}", url],
            capture_output=True, timeout=timeout + 10,
        )
        if out.returncode != 0 or not out.stdout:
            raise
        return out.stdout


def _get_json(url: str, **kw: Any) -> Any:
    return json.loads(_get(url, **kw).decode("utf-8"))


class NotPublicDomain(Exception):
    pass


class MuseumArt(BaseTool):
    """Shared behaviour. Subclasses implement _search, _object and _image_urls."""

    version = "0.1.0"
    tier = ToolTier.SOURCE
    capability = "art_source"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC
    runtime = ToolRuntime.API
    dependencies: list[str] = []
    install_instructions = "No key needed. Needs internet access to the museum's open API."
    capabilities = ["search_public_domain_art", "download_cc0_image", "record_provenance"]
    resource_profile = ResourceProfile(cpu_cores=1, ram_mb=256, vram_mb=0, disk_mb=500, network_required=True)
    side_effects = ["downloads an image into projects/<id>/assets/art/", "appends to assets/PROVENANCE.json"]
    best_for = [
        "real art for editorial pages (old masters, objects, prints, textiles)",
        "archive material for archive/contemporary spreads",
        "source fragments for crops and collage",
    ]
    not_good_for = ["contemporary photography (use pexels_image / pixabay_image)", "anything not public domain"]
    museum = ""
    licence = "CC0"
    agent_skills = ["art-sourcing"]

    input_schema = {
        "type": "object",
        "required": ["operation"],
        "properties": {
            "operation": {"type": "string", "enum": ["search", "fetch"]},
            "query": {"type": "string"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
            "object_id": {"type": "string"},
            "project_dir": {"type": "string", "description": "projects/<id>"},
            "out_name": {"type": "string", "description": "optional file stem"},
        },
    }

    def get_status(self) -> ToolStatus:
        return ToolStatus.AVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        return 0.0

    # --- subclass hooks -------------------------------------------------------------
    @abstractmethod
    def _search(self, query: str, limit: int) -> list[dict[str, Any]]:  # pragma: no cover
        raise NotImplementedError

    @abstractmethod
    def _object(self, object_id: str) -> dict[str, Any]:  # pragma: no cover
        """Normalised record; MUST set public_domain from the museum's own flag."""
        raise NotImplementedError

    # --- shared ---------------------------------------------------------------------
    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        start = time.time()
        op = inputs.get("operation")
        try:
            if op == "search":
                q = (inputs.get("query") or "").strip()
                if not q:
                    return ToolResult(success=False, error="search needs a query")
                results = self._search(q, int(inputs.get("limit", 10)))
                return ToolResult(success=True, data={"museum": self.museum, "results": results},
                                  duration_seconds=time.time() - start)
            if op == "fetch":
                return self._fetch(inputs, start)
            return ToolResult(success=False, error=f"unknown operation {op!r}")
        except NotPublicDomain as e:
            return ToolResult(success=False, error=f"refused: not public domain ({e})")
        except Exception as e:  # network or API shape
            return ToolResult(success=False, error=f"{self.museum}: {type(e).__name__}: {e}")

    def _fetch(self, inputs: dict[str, Any], start: float) -> ToolResult:
        oid = str(inputs.get("object_id") or "").strip()
        project_dir = inputs.get("project_dir")
        if not oid or not project_dir:
            return ToolResult(success=False, error="fetch needs object_id and project_dir")
        obj = self._object(oid)
        if obj.get("public_domain") is not True:
            raise NotPublicDomain(f"{self.museum} object {oid}")
        urls = [u for u in obj.get("image_urls", []) if u]
        if not urls:
            return ToolResult(success=False, error=f"{self.museum} object {oid} has no open-access image")
        out_dir = Path(project_dir) / "assets" / "art"
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = inputs.get("out_name") or f"{self.name.replace('_art', '')}-{oid}"
        last_err: Optional[Exception] = None
        for url in urls:  # largest first; fall back to smaller renditions
            try:
                blob = _get(url, accept="image/*", timeout=120)
                if len(blob) < 2048:
                    raise ValueError("image response too small")
                out = out_dir / f"{stem}.jpg"
                out.write_bytes(blob)
                rec = provenance.record(
                    project_dir, out, kind="museum", source=self.museum, licence=self.licence,
                    source_url=obj.get("source_url"), image_url=url, object_id=oid,
                    title=obj.get("title"), creator=obj.get("creator"), tool=self.name,
                    notes=obj.get("credit"),
                )
                size = _image_size(out)
                return ToolResult(
                    success=True,
                    data={"path": str(out), "object": obj, "provenance": rec, "width": size[0], "height": size[1]},
                    artifacts=[str(out)], duration_seconds=time.time() - start,
                )
            except Exception as e:
                last_err = e
        return ToolResult(success=False, error=f"download failed for every rendition: {last_err}")


def _image_size(path: Path) -> tuple[int, int]:
    try:
        from PIL import Image

        with Image.open(path) as im:
            return im.size
    except Exception:
        return (0, 0)


# ------------------------------------------------------------------------------------
class MetArt(MuseumArt):
    name = "met_art"
    provider = "metmuseum"
    museum = "The Metropolitan Museum of Art"
    licence = "CC0"
    API = "https://collectionapi.metmuseum.org/public/collection"

    def _search(self, query: str, limit: int) -> list[dict[str, Any]]:
        # v1/search was retired 2026-10-01; v1.1 is paginated.
        q = urllib.parse.urlencode({"q": query, "isPublicDomain": "true", "hasImages": "true",
                                    "limit": limit, "offset": 0})
        ids = (_get_json(f"{self.API}/v1.1/search?{q}").get("objectIDs") or [])[:limit]
        out = []
        for oid in ids:
            try:
                out.append(self._object(str(oid), small=True))
            except Exception:
                continue
        return out

    def _object(self, object_id: str, small: bool = False) -> dict[str, Any]:
        d = _get_json(f"{self.API}/v1/objects/{urllib.parse.quote(object_id)}")
        return {
            "object_id": str(d.get("objectID", object_id)),
            "title": d.get("title"),
            "creator": d.get("artistDisplayName") or None,
            "date": d.get("objectDate"),
            "medium": d.get("medium"),
            "public_domain": d.get("isPublicDomain") is True,
            "source_url": d.get("objectURL"),
            "preview_url": d.get("primaryImageSmall"),
            "image_urls": [d.get("primaryImage"), d.get("primaryImageSmall")],
            "credit": d.get("creditLine"),
        }


class AicArt(MuseumArt):
    name = "aic_art"
    provider = "artic"
    museum = "Art Institute of Chicago"
    licence = "CC0"
    API = "https://api.artic.edu/api/v1"
    IIIF = "https://www.artic.edu/iiif/2"
    FIELDS = "id,title,artist_display,date_display,medium_display,image_id,is_public_domain,credit_line"

    def _norm(self, d: dict[str, Any]) -> dict[str, Any]:
        img = d.get("image_id")
        sizes = [3000, 1686, 843]
        return {
            "object_id": str(d.get("id")),
            "title": d.get("title"),
            "creator": (d.get("artist_display") or "").split("\n")[0] or None,
            "date": d.get("date_display"),
            "medium": d.get("medium_display"),
            "public_domain": d.get("is_public_domain") is True,
            "source_url": f"https://www.artic.edu/artworks/{d.get('id')}",
            "preview_url": f"{self.IIIF}/{img}/full/400,/0/default.jpg" if img else None,
            "image_urls": [f"{self.IIIF}/{img}/full/{s},/0/default.jpg" for s in sizes] if img else [],
            "credit": d.get("credit_line"),
        }

    def _search(self, query: str, limit: int) -> list[dict[str, Any]]:
        q = urllib.parse.urlencode({"q": query, "query[term][is_public_domain]": "true",
                                    "fields": self.FIELDS, "limit": limit})
        return [self._norm(d) for d in _get_json(f"{self.API}/artworks/search?{q}").get("data", [])
                if d.get("image_id")]

    def _object(self, object_id: str) -> dict[str, Any]:
        d = _get_json(f"{self.API}/artworks/{urllib.parse.quote(object_id)}?fields={self.FIELDS}")["data"]
        return self._norm(d)


class ClevelandArt(MuseumArt):
    name = "cleveland_art"
    provider = "clevelandart"
    museum = "Cleveland Museum of Art"
    licence = "CC0"
    API = "https://openaccess-api.clevelandart.org/api/artworks"

    def _norm(self, d: dict[str, Any]) -> dict[str, Any]:
        imgs = d.get("images") or {}
        url = lambda k: (imgs.get(k) or {}).get("url")  # noqa: E731
        creators = d.get("creators") or []
        return {
            "object_id": str(d.get("id")),
            "accession_number": d.get("accession_number"),
            "title": d.get("title"),
            "creator": creators[0].get("description") if creators else None,
            "date": d.get("creation_date"),
            "medium": d.get("technique"),
            "public_domain": d.get("share_license_status") == "CC0",
            "source_url": d.get("url"),
            "preview_url": url("web"),
            "image_urls": [url("print"), url("web")],  # the .tif "full" is skipped: huge, not web-safe
            "credit": d.get("creditline"),
        }

    def _search(self, query: str, limit: int) -> list[dict[str, Any]]:
        q = urllib.parse.urlencode({"q": query, "cc0": 1, "has_image": 1, "limit": limit})
        return [self._norm(d) for d in _get_json(f"{self.API}/?{q}").get("data", [])]

    def _object(self, object_id: str) -> dict[str, Any]:
        return self._norm(_get_json(f"{self.API}/{urllib.parse.quote(object_id)}")["data"])


class RijksArt(MuseumArt):
    name = "rijks_art"
    provider = "rijksmuseum"
    museum = "Rijksmuseum"
    licence = "public-domain"
    SEARCH = "https://data.rijksmuseum.nl/search/collection"

    def _search(self, query: str, limit: int) -> list[dict[str, Any]]:
        q = urllib.parse.urlencode({"description": query, "imageAvailable": "true"})
        items = _get_json(f"{self.SEARCH}?{q}", accept="application/ld+json").get("orderedItems", [])[:limit]
        out = []
        for it in items:
            try:
                out.append(self._object(it["id"].rsplit("/", 1)[-1]))
            except Exception:
                continue
        return out

    def _object(self, object_id: str) -> dict[str, Any]:
        d = _get_json(f"https://id.rijksmuseum.nl/{urllib.parse.quote(object_id)}",
                      accept="application/ld+json")
        title, number = None, None
        for ident in d.get("identified_by", []):
            if ident.get("type") == "Name" and not title:
                title = ident.get("content")
            if ident.get("type") == "Identifier" and not number:
                number = ident.get("content")
        image, licence_label = None, ""
        for subj in d.get("subject_of", []):
            for carrier in subj.get("digitally_carried_by", []):
                for ap in carrier.get("access_point", []):
                    image = image or ap.get("id")
                for ref in carrier.get("referred_to_by", []):
                    licence_label = licence_label or (ref.get("_label") or ref.get("content") or "")
        pd = "public domain" in licence_label.lower() or "cc0" in licence_label.lower()
        creator = None
        try:
            creator = d["produced_by"]["part"][0]["carried_out_by"][0].get("_label")
        except (KeyError, IndexError, TypeError):
            pass
        return {
            "object_id": object_id,
            "accession_number": number,
            "title": title,
            "creator": creator,
            "date": None,
            "public_domain": pd,
            "licence_label": licence_label,
            "source_url": f"https://id.rijksmuseum.nl/{object_id}",
            "preview_url": image.replace("/full/max/", "/full/400,/") if image else None,
            "image_urls": [image],
            "credit": "Rijksmuseum, Amsterdam (public domain)",
        }

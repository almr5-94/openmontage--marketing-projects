"""art_source: public-domain gate and provenance, with the museum APIs faked (no network)."""

from __future__ import annotations

import io
import json

import pytest
from PIL import Image

from lib import provenance
from tools.art_source import museum_art
from tools.art_source.museum_art import AicArt, ClevelandArt, MetArt, RijksArt


def _jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), (120, 90, 60)).save(buf, "JPEG", quality=95)
    data = buf.getvalue()
    return data + b"\0" * max(0, 4096 - len(data))


def _fake_met(public: bool):
    obj = {"objectID": 1, "isPublicDomain": public, "title": "Astrolabe",
           "artistDisplayName": "Muhammad Zaman", "objectDate": "1654",
           "primaryImage": "https://images.metmuseum.org/x.jpg", "primaryImageSmall": "",
           "objectURL": "https://www.metmuseum.org/art/collection/search/1", "creditLine": "Fund"}

    def get(url, **kw):
        if "image" in kw.get("accept", "") or url.endswith(".jpg"):
            return _jpeg()
        if "search" in url:
            return json.dumps({"objectIDs": [1]}).encode()
        return json.dumps(obj).encode()

    return get


def test_met_fetch_downloads_and_records_cc0(tmp_path, monkeypatch):
    monkeypatch.setattr(museum_art, "_get", _fake_met(True))
    r = MetArt().execute({"operation": "fetch", "object_id": "1", "project_dir": str(tmp_path)})
    assert r.success, r.error
    rec = provenance.find(tmp_path, r.data["path"])
    assert rec["licence"] == "CC0" and rec["object_id"] == "1" and rec["sha256"]
    assert rec["source"] == "The Metropolitan Museum of Art"
    assert rec["image_url"] == "https://images.metmuseum.org/x.jpg"


def test_not_public_domain_is_refused_and_nothing_written(tmp_path, monkeypatch):
    monkeypatch.setattr(museum_art, "_get", _fake_met(False))
    r = MetArt().execute({"operation": "fetch", "object_id": "1", "project_dir": str(tmp_path)})
    assert not r.success and "not public domain" in r.error
    assert not (tmp_path / "assets" / "art").exists()
    assert provenance.load(tmp_path)["assets"] == []


def test_search_uses_public_domain_filter(monkeypatch):
    seen = []

    def get(url, **kw):
        seen.append(url)
        return _fake_met(True)(url, **kw)

    monkeypatch.setattr(museum_art, "_get", get)
    r = MetArt().execute({"operation": "search", "query": "astrolabe", "limit": 1})
    assert r.success and r.data["results"][0]["public_domain"] is True
    assert "isPublicDomain=true" in seen[0] and "/v1.1/search" in seen[0]


def test_cleveland_flag_is_share_license_status():
    t = ClevelandArt()
    assert t._norm({"id": 1, "share_license_status": "CC0", "images": {}})["public_domain"] is True
    assert t._norm({"id": 1, "share_license_status": "Copyrighted", "images": {}})["public_domain"] is False


def test_aic_flag_and_iiif_urls():
    n = AicArt()._norm({"id": 9, "is_public_domain": True, "image_id": "abc"})
    assert n["public_domain"] is True and n["image_urls"][0].endswith("/abc/full/3000,/0/default.jpg")
    assert AicArt()._norm({"id": 9, "is_public_domain": False, "image_id": "abc"})["public_domain"] is False


def test_rijks_licence_read_from_linked_art(monkeypatch):
    doc = {"identified_by": [{"type": "Name", "content": "Navigatie"}],
           "subject_of": [{"digitally_carried_by": [{"access_point": [{"id": "https://iiif.micr.io/a/full/max/0/default.jpg"}],
                                                      "referred_to_by": [{"_label": "Public Domain"}]}]}]}
    monkeypatch.setattr(museum_art, "_get", lambda url, **kw: json.dumps(doc).encode())
    o = RijksArt()._object("200415868")
    assert o["public_domain"] is True and o["title"] == "Navigatie"
    doc["subject_of"][0]["digitally_carried_by"][0]["referred_to_by"][0]["_label"] = "In copyright"
    assert RijksArt()._object("1")["public_domain"] is False


def test_all_four_registered_free():
    from tools.tool_registry import registry

    registry.discover()
    names = {t["name"] for t in registry.capability_catalog()["art_source"]}
    assert {"met_art", "aic_art", "cleveland_art", "rijks_art"} <= names
    assert all(registry.get(n).estimate_cost({}) == 0.0 for n in names)


# ---------- provenance ledger ----------

def test_provenance_refuses_unknown_licence(tmp_path):
    f = tmp_path / "a.jpg"
    f.write_bytes(b"x")
    with pytest.raises(ValueError):
        provenance.record(tmp_path, f, kind="stock", source="somewhere", licence="all-rights-reserved")


def test_provenance_chain_and_gate(tmp_path):
    src = tmp_path / "assets" / "art" / "met-1.jpg"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"x")
    crop = tmp_path / "assets" / "fragments" / "met-1-circle.png"
    crop.parent.mkdir(parents=True)
    crop.write_bytes(b"y")
    stray = tmp_path / "assets" / "images" / "stray.png"
    stray.parent.mkdir(parents=True)
    stray.write_bytes(b"z")
    provenance.record(tmp_path, src, kind="museum", source="Met", licence="CC0", object_id="1")
    provenance.record(tmp_path, crop, kind="fragment", source="image_crop", licence="derived",
                      parents=["assets/art/met-1.jpg"], crop={"mask": "circle"})
    assert [a["path"] for a in provenance.lineage(tmp_path, crop)] == [
        "assets/fragments/met-1-circle.png", "assets/art/met-1.jpg"]
    ok = provenance.check_complete(tmp_path, [crop])
    assert ok["pass"], ok
    bad = provenance.check_complete(tmp_path, [crop, stray])
    assert not bad["pass"] and bad["missing"] == ["assets/images/stray.png"]

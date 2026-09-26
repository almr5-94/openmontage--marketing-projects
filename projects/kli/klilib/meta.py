"""Instagram Graph API for the one authorised account. The token value is never printed."""
from __future__ import annotations

import json
import os
import stat
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .common import read_json
from . import kli_repo

GRAPH = "https://graph.facebook.com/v25.0"
SECRET = Path.home() / ".config/kuwait-legal-insider/meta-token.verified.json"


def _boundary() -> dict:
    return read_json(kli_repo.root() / "_INTERNAL" / "account_boundary.json")


def identity() -> tuple[str, str]:
    """(instagram_id, username) after the KLI boundary guard and the credential checks."""
    sys.path.insert(0, str(kli_repo.root() / "_INTERNAL"))
    from account_boundary import require_account  # the KLI repo's own guard

    rule = _boundary()
    ig = require_account(rule.get("allowed_instagram_id"), rule.get("allowed_username"))
    fd = os.open(SECRET, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd) as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
            raise RuntimeError("Credential file must be private and owner-controlled")
        cred = json.load(stream)
    if cred.get("verified") is not True or cred.get("instagram_id") != ig or cred.get("username") != "kwlegalinsider":
        raise RuntimeError("Credential identity mismatch")
    return ig, cred["username"]


def _token() -> str:
    fd = os.open(SECRET, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd) as stream:
        return json.load(stream)["access_token"]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise RuntimeError("Redirect refused")


def call(method: str, path: str, params: dict | None = None, timeout: int = 30) -> dict:
    """One Graph call. Denies any path that names a forbidden id. Raises with the API error body."""
    rule = _boundary()
    denied = {str(x) for x in rule.get("forbidden_instagram_ids", []) + rule.get("forbidden_page_ids", [])}
    for d in denied:
        if d and d in path:
            raise RuntimeError("Owner-prohibited account in request path")
    params = dict(params or {})
    url = GRAPH + path
    data = None
    if method == "GET":
        url += "?" + urllib.parse.urlencode(params)
    else:
        data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(url, data=data, method=method, headers={"Authorization": "Bearer " + _token()})
    try:
        with urllib.request.build_opener(_NoRedirect).open(req, timeout=timeout) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")[:600]
        raise RuntimeError(f"Graph {method} {path} -> HTTP {exc.code}: {body}")

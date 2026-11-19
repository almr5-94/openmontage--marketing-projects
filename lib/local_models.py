"""Local LLM client (Ollama / LM Studio) through their OpenAI-compatible endpoints.

Reads config/local_models.yaml, detects which runtime answers and which candidate models are
installed, and exposes ``chat`` (planner) and ``see`` (vision). Never pulls a model.
"""

from __future__ import annotations

import base64
import io
import json
import time
import urllib.error
import urllib.request
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import yaml

from lib.paths import REPO_ROOT

CONFIG = REPO_ROOT / "config" / "local_models.yaml"


class LocalModelUnavailable(RuntimeError):
    pass


def config() -> dict[str, Any]:
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))


def _get_json(url: str, timeout: float = 3) -> Optional[dict[str, Any]]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read())
    except (urllib.error.URLError, OSError, ValueError):
        return None


def installed(runtime: str) -> list[str]:
    rt = config()["runtimes"][runtime]
    data = _get_json(rt["models_url"])
    if not data:
        return []
    if "models" in data:  # ollama /api/tags
        return [m["name"] for m in data["models"]]
    return [m["id"] for m in data.get("data", [])]  # openai /v1/models


@lru_cache(maxsize=None)
def detect() -> dict[str, Any]:
    """{"runtime", "base_url", "planner", "vision", "installed"} -- or runtime None when offline."""
    cfg = config()
    for rt in cfg.get("prefer", list(cfg["runtimes"])):
        models = installed(rt)
        if not models:
            continue
        pick = {role: next((m for m in spec["candidates"] if m in models), None) for role, spec in cfg["roles"].items()}
        return {"runtime": rt, "base_url": cfg["runtimes"][rt]["base_url"], "installed": models, **pick}
    return {"runtime": None, "base_url": None, "installed": [], "planner": None, "vision": None}


def _post(messages: list[dict[str, Any]], role: str, **kw: Any) -> str:
    d = detect()
    model = kw.pop("model", None) or d.get(role)
    if not d["runtime"] or not model:
        raise LocalModelUnavailable(f"no local {role} model: start Ollama or LM Studio and install one of "
                                    f"{config()['roles'][role]['candidates']}")
    spec = config()["roles"][role]
    body = {"model": model, "messages": messages, "temperature": kw.get("temperature", spec["temperature"]),
            "max_tokens": kw.get("max_tokens", spec["max_tokens"]), "stream": False}
    if kw.get("seed") is not None:
        body["seed"] = kw["seed"]
    data = json.dumps(body).encode()
    last: Exception | None = None
    for attempt in range(3):  # Ollama answers 400/503 while it swaps models in VRAM
        req = urllib.request.Request(d["base_url"] + "/chat/completions", data=data,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=config()["timeouts_s"][role]) as r:
                out = json.loads(r.read())
            return out["choices"][0]["message"]["content"].strip()
        except urllib.error.HTTPError as e:
            last = e
            if e.code not in (400, 500, 502, 503):
                raise
            time.sleep(2 + 4 * attempt)
    raise LocalModelUnavailable(f"local {role} model kept failing: {last}")


def chat(prompt: str, system: Optional[str] = None, **kw: Any) -> str:
    msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
    return _post(msgs, "planner", **kw)


def _encode(image: str | Path, max_side: int = 1344) -> str:
    """JPEG, longest side <= max_side: the vision model does not need print resolution."""
    from PIL import Image

    im = Image.open(image)
    im = im.convert("RGBA") if im.mode in ("P", "LA") else im
    if im.mode == "RGBA":
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.getchannel("A"))
        im = bg
    im = im.convert("RGB")
    im.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=90)
    return base64.b64encode(buf.getvalue()).decode()


def see(image: str | Path, question: str, **kw: Any) -> str:
    data = _encode(image)
    mime = "image/jpeg"
    msgs = [{"role": "user", "content": [{"type": "text", "text": question},
                                         {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{data}"}}]}]
    return _post(msgs, "vision", **{"seed": 7, **kw})


def yes(answer: str) -> bool:
    return answer.strip().strip("*\"' ").lower().startswith("y")

"""Gemini access for the creative and judging stages, with cost written to the ledger.

The registry does not meter LLM calls, so every call here emits a 'finish'
event with an estimated cost into the reel's events.jsonl — the same file the
budget guard reads. Prices are the public list prices; they are estimates.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types

from .common import OM_ROOT

PRO = "gemini-2.5-pro"
FLASH = "gemini-2.5-flash"
# USD per 1M tokens (input, output)
PRICES = {PRO: (1.25, 10.0), FLASH: (0.30, 2.50)}

_client = None


def client() -> genai.Client:
    global _client
    if _client is None:
        key = os.environ.get("GOOGLE_API_KEY")
        if not key:
            raise RuntimeError("GOOGLE_API_KEY is not set in the OpenMontage .env")
        _client = genai.Client(api_key=key)
    return _client


def _emit(project_dir: Path | None, model: str, usage, purpose: str) -> float:
    from lib.events import emit_event

    pin, pout = PRICES.get(model, (1.25, 10.0))
    i = getattr(usage, "prompt_token_count", 0) or 0
    o = getattr(usage, "candidates_token_count", 0) or 0
    cost = round(i / 1e6 * pin + o / 1e6 * pout, 4)
    if project_dir is not None:
        emit_event(project_dir, {"tool": "gemini", "event": "finish", "model": model, "purpose": purpose,
                                 "success": True, "cost_usd": cost, "input_tokens": i, "output_tokens": o})
    return cost


def _extract_json(text: str) -> Any:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S)
    return json.loads(text)


def ask_json(prompt: str, *, model: str = PRO, project_dir: Path | None = None, purpose: str = "",
             files: list[Path] | None = None, temperature: float = 0.4, retries: int = 2) -> Any:
    """Send a prompt (optionally with uploaded files) and parse a JSON reply."""
    c = client()
    contents: list[Any] = []
    for f in files or []:
        up = c.files.upload(file=str(f))
        while c.files.get(name=up.name).state.name != "ACTIVE":
            time.sleep(3)
        contents.append(up)
    contents.append(prompt)
    last_err = None
    for attempt in range(retries + 1):
        resp = c.models.generate_content(
            model=model, contents=contents,
            config=types.GenerateContentConfig(response_mime_type="application/json", temperature=temperature),
        )
        _emit(project_dir, model, resp.usage_metadata, purpose)
        try:
            return _extract_json(resp.text)
        except (ValueError, TypeError) as exc:  # malformed JSON: ask again
            last_err = exc
            time.sleep(2)
    raise RuntimeError(f"Gemini returned no parseable JSON for {purpose}: {last_err}")


def read_text_prompt(name: str) -> str:
    return (OM_ROOT / "projects" / "kli" / "prompts" / name).read_text(encoding="utf-8")


def ask_grounded(prompt: str, *, model: str = FLASH, project_dir: Path | None = None, purpose: str = "research") -> str:
    """Plain-text answer with Google Search grounding (JSON mode cannot be combined with tools)."""
    c = client()
    resp = c.models.generate_content(
        model=model, contents=[prompt],
        config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())], temperature=0.2),
    )
    _emit(project_dir, model, resp.usage_metadata, purpose)
    return resp.text or ""

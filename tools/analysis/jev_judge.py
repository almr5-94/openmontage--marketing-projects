"""Fast typed judgments from TypeSafe's Jev model (System One API).

Jev does not generate anything. It answers narrow questions about text with
typed answers and probabilities, so the pipeline can gate, rank and route
without a full LLM call. Three operations:

  script_check  flag script lines that promise legal outcomes, give legal
                advice, make unverifiable claims or name competitors
  rank_assets   score candidate images/clips against a scene description
  route_brief   pick the best pipeline in pipeline_defs/ for a request

Thresholds are starting points. Tune them on real scripts before relying on them.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

from tools.base_tool import (
    BaseTool,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    RetryPolicy,
    ToolResult,
    ToolRuntime,
    ToolStability,
    ToolTier,
)

# One question per risk, so several can fire on the same line.
SCRIPT_RISKS: dict[str, str] = {
    "promises_outcome": (
        "Does `line` promise, guarantee or strongly imply a specific legal "
        "result for the viewer, such as winning a case, getting compensation "
        "or avoiding a penalty?"
    ),
    "legal_advice": (
        "Does `line` tell the viewer what they should legally do in their own "
        "situation, as opposed to describing a product or general information?"
    ),
    "unverifiable_claim": (
        "Does `line` make a factual or superlative claim that would need proof, "
        "such as numbers, rankings, 'the best', 'the only' or 'guaranteed'?"
    ),
    "names_competitor": (
        "Does `line` name or clearly point to a specific competing company, "
        "firm or product?"
    ),
}

RELEVANCE_LEVELS = [
    "unrelated to the scene",
    "loosely related but shows the wrong subject or mood",
    "matches the subject but misses important details or mood",
    "matches the scene's subject, details and mood closely",
]

PIPELINES_DIR = Path(__file__).resolve().parent.parent.parent / "pipeline_defs"


def _default_client():
    from typesafe_sdk import TypeSafeClient

    return TypeSafeClient()


def _pipeline_catalog() -> dict[str, str]:
    import yaml

    catalog: dict[str, str] = {}
    for path in sorted(PIPELINES_DIR.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        name = data.get("name") or path.stem
        if name == "framework-smoke":
            continue
        catalog[name] = " ".join(str(data.get("description", "")).split())
    return catalog


class JevJudge(BaseTool):
    name = "jev_judge"
    version = "0.1.0"
    tier = ToolTier.ANALYZE
    capability = "analysis"
    provider = "typesafe"
    stability = ToolStability.EXPERIMENTAL
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC
    runtime = ToolRuntime.API

    dependencies = ["env:TYPESAFE_API_KEY", "python:typesafe_sdk"]
    install_instructions = (
        "pip install typesafe-sdk, then set TYPESAFE_API_KEY in .env "
        "(key from https://console.typesafe.ai/)"
    )

    capabilities = ["script_check", "rank_assets", "route_brief"]
    best_for = [
        "flagging risky claims in a marketing script before voiceover",
        "choosing the best stock clip or generated image for a scene",
        "routing a free-text brief to a pipeline",
    ]
    not_good_for = ["writing or rewriting copy", "anything that needs reasoning explanations"]

    input_schema = {
        "type": "object",
        "required": ["operation"],
        "properties": {
            "operation": {"type": "string", "enum": ["script_check", "rank_assets", "route_brief"]},
            "lines": {"type": "array", "items": {"type": "string"},
                      "description": "script_check: script lines in order"},
            "context": {"type": "string",
                        "description": "script_check: what is being advertised, and to whom"},
            "threshold": {"type": "number", "default": 0.5,
                          "description": "script_check: probability at or above which a risk is flagged"},
            "scene": {"type": "string", "description": "rank_assets: the scene description"},
            "candidates": {"type": "array",
                           "items": {"type": "object", "required": ["id", "description"],
                                     "properties": {"id": {"type": "string"},
                                                    "description": {"type": "string"}}},
                           "description": "rank_assets: candidate assets with text descriptions"},
            "brief": {"type": "string", "description": "route_brief: the user's request"},
        },
    }

    resource_profile = ResourceProfile(cpu_cores=1, ram_mb=128, vram_mb=0, disk_mb=0, network_required=True)
    retry_policy = RetryPolicy(max_retries=2, retryable_errors=["TypeSafeRateLimitError", "TypeSafeAPITimeoutError"])
    idempotency_key_fields = ["operation", "lines", "scene", "candidates", "brief"]
    side_effects = ["calls TypeSafe API (billed per token)"]

    # Tests replace this to avoid the network.
    client_factory: Callable[[], Any] = staticmethod(_default_client)

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        return 0.0  # TypeSafe pricing not published in the SDK; usage tokens are reported instead

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        op = inputs.get("operation")
        handlers = {
            "script_check": self._script_check,
            "rank_assets": self._rank_assets,
            "route_brief": self._route_brief,
        }
        if op not in handlers:
            return ToolResult(success=False, error=f"Unknown operation: {op!r}")
        start = time.time()
        try:
            with self.client_factory() as client:
                data, model, usage = handlers[op](client, inputs)
        except ValueError as exc:
            return ToolResult(success=False, error=str(exc))
        except Exception as exc:  # SDK/network errors
            return ToolResult(success=False, error=f"{type(exc).__name__}: {exc}")
        data["usage"] = usage
        return ToolResult(success=True, data=data, model=model,
                          duration_seconds=round(time.time() - start, 2))

    @staticmethod
    def _usage(resp) -> dict[str, Any]:
        return {"input_tokens": resp.usage.input_tokens, "output_tokens": resp.usage.output_tokens}

    def _script_check(self, client, inputs):
        from typesafe_sdk import Noul

        lines = [str(line) for line in inputs.get("lines") or [] if str(line).strip()]
        if not lines:
            raise ValueError("script_check needs a non-empty 'lines' list")
        threshold = float(inputs.get("threshold", 0.5))
        context = inputs.get("context") or "a marketing video"
        questions = {name: Noul(instructions=text) for name, text in SCRIPT_RISKS.items()}

        results, flagged = [], []
        in_tok = out_tok = 0
        model = None
        for index, line in enumerate(lines):
            resp = client.system_one(state={"advertising": context, "line": line}, questions=questions)
            model = resp.model
            in_tok += resp.usage.input_tokens or 0
            out_tok += resp.usage.output_tokens or 0
            probs = {name: round(resp.answers[name].noul, 3) for name in SCRIPT_RISKS}
            risks = sorted((n for n, p in probs.items() if p >= threshold), key=lambda n: -probs[n])
            row = {"index": index, "line": line, "probabilities": probs, "flags": risks}
            results.append(row)
            if risks:
                flagged.append(index)
        data = {"lines": results, "flagged_indices": flagged, "passed": not flagged, "threshold": threshold}
        return data, model, {"input_tokens": in_tok, "output_tokens": out_tok}

    def _rank_assets(self, client, inputs):
        from typesafe_sdk import Score

        scene = (inputs.get("scene") or "").strip()
        candidates = inputs.get("candidates") or []
        if not scene or not candidates:
            raise ValueError("rank_assets needs 'scene' and a non-empty 'candidates' list")
        # Independent per-item Scores over shared state run in parallel in one request.
        state = {"scene": scene, "candidates": [c["description"] for c in candidates]}
        questions = {
            f"c{i}": Score(
                instructions=f"How well does `candidates[{i}]` fit `scene` as footage or an image for it?",
                criteria=RELEVANCE_LEVELS,
            )
            for i in range(len(candidates))
        }
        resp = client.system_one(state=state, questions=questions)
        top = len(RELEVANCE_LEVELS) - 1
        ranked = []
        for i, cand in enumerate(candidates):
            ans = resp.answers[f"c{i}"]
            ranked.append({"id": cand["id"], "relevance": round(ans.score / top, 3),
                           "confidence": round(ans.confidence, 3)})
        ranked.sort(key=lambda r: -r["relevance"])
        return {"ranked": ranked, "best_id": ranked[0]["id"]}, resp.model, self._usage(resp)

    def _route_brief(self, client, inputs):
        from typesafe_sdk import Choice

        brief = (inputs.get("brief") or "").strip()
        if not brief:
            raise ValueError("route_brief needs 'brief'")
        catalog = _pipeline_catalog()
        question = Choice(
            instructions="Which production pipeline best fits the video requested in `brief`?",
            criteria=catalog,
        )
        resp = client.system_one(state={"brief": brief}, questions={"pipeline": question})
        ans = resp.answers["pipeline"]
        alternatives = sorted(ans.probabilities.items(), key=lambda kv: -kv[1])[:3]
        data = {"pipeline": ans.choice, "confidence": round(ans.confidence, 3),
                "top3": [{"pipeline": k, "probability": round(v, 3)} for k, v in alternatives]}
        return data, resp.model, self._usage(resp)

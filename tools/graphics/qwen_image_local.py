"""Qwen-Image-2.1 text-to-image, running locally on this machine's GPU.

Weights live in the shared Hugging Face cache (`Qwen/Qwen-Image-2.1`), so a run
costs nothing, needs no API key and works offline. Qwen-Image is the open model
with the strongest text rendering inside the image — English and Chinese
signage, posters, UI mockups and captions come out legible where most
open models smear them.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from tools.base_tool import (
    BaseTool,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    RetryPolicy,
    ToolResult,
    ToolRuntime,
    ToolStability,
    ToolStatus,
    ToolTier,
)
from tools.graphics import _qwen_local


class QwenImageLocal(BaseTool):
    """Local text-to-image generation with Qwen-Image-2.1 via diffusers."""

    name = "qwen_image_local"
    version = "0.1.0"
    tier = ToolTier.GENERATE
    capability = "image_generation"
    provider = "qwen_local"
    stability = ToolStability.EXPERIMENTAL
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.SEEDED
    runtime = ToolRuntime.LOCAL_GPU

    dependencies = ["python:diffusers", "python:torch", "python:transformers", "gpu"]
    install_instructions = _qwen_local.INSTALL_INSTRUCTIONS
    agent_skills = ["visual-style"]

    capabilities = ["generate_image", "text_to_image", "generate_illustration"]
    supports = {
        "negative_prompt": True,
        "seed": True,
        "offline": True,
        "custom_size": True,
        "text_in_image": True,
        "image_edit": False,
    }
    best_for = [
        "text inside the image (posters, signage, UI, captions) in English or Chinese",
        "free generation with no API key and no per-image cost",
        "offline or privacy-sensitive work — nothing leaves this machine",
        "long batches where API spend would add up",
    ]
    not_good_for = [
        "machines without an NVIDIA GPU (a run takes minutes on CPU, if it fits at all)",
        "the fastest possible turnaround — a hosted API answers sooner",
        "editing an existing image (use qwen_image_edit_local)",
    ]
    fallback_tools = ["flux_image", "dashscope_image", "openai_image", "local_diffusion"]

    input_schema = {
        "type": "object",
        "required": ["prompt"],
        "properties": {
            "prompt": {
                "type": "string",
                "description": (
                    "What to draw. Quote any text that must appear in the image "
                    "exactly as it should be rendered."
                ),
            },
            "negative_prompt": {"type": "string", "default": ""},
            "width": {"type": "integer", "default": 1328},
            "height": {"type": "integer", "default": 1328},
            "num_inference_steps": {"type": "integer", "default": 40},
            "true_cfg_scale": {
                "type": "number",
                "default": 4.0,
                "description": "Prompt adherence. Qwen-Image's guidance control.",
            },
            "seed": {"type": "integer"},
            "quantization": {
                "type": "string",
                "enum": list(_qwen_local.QUANTIZATION_CHOICES),
                "default": "4bit",
                "description": (
                    "4bit fits this machine's 16 GB card. 'none' needs ~33 GB of "
                    "combined VRAM and RAM."
                ),
            },
            "offload": {
                "type": "string",
                "enum": list(_qwen_local.OFFLOAD_CHOICES),
                "default": "model",
            },
            "output_path": {"type": "string", "default": "qwen_image.png"},
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=4, ram_mb=16000, vram_mb=15000, disk_mb=34000, network_required=False
    )
    retry_policy = RetryPolicy(max_retries=1)
    idempotency_key_fields = ["prompt", "width", "height", "seed", "num_inference_steps"]
    side_effects = ["writes an image file to output_path", "holds the GPU for the duration of the run"]
    user_visible_verification = [
        "Open the image and check any rendered text is spelled correctly",
        "Check the aspect ratio matches the shot it was generated for",
    ]

    def get_status(self) -> ToolStatus:
        if not _qwen_local.diffusers_available():
            return ToolStatus.UNAVAILABLE
        if not _qwen_local.weights_cached(_qwen_local.TEXT_TO_IMAGE_REPO):
            return ToolStatus.UNAVAILABLE
        return ToolStatus.AVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        return 0.0

    def estimate_runtime(self, inputs: dict[str, Any]) -> float:
        steps = inputs.get("num_inference_steps", 40)
        # ~2.5 s per step on this card once the weights are resident, plus load.
        return 60.0 + 2.5 * float(steps)

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        if not _qwen_local.diffusers_available():
            return ToolResult(
                success=False,
                error="diffusers/torch not installed. " + self.install_instructions,
            )
        if not _qwen_local.weights_cached(_qwen_local.TEXT_TO_IMAGE_REPO):
            return ToolResult(
                success=False,
                error=(
                    f"{_qwen_local.TEXT_TO_IMAGE_REPO} is not in the local Hugging Face "
                    "cache. " + self.install_instructions
                ),
            )

        start = time.time()
        prompt = inputs["prompt"]
        seed = inputs.get("seed")
        quantization = inputs.get("quantization", "4bit")
        offload = inputs.get("offload", "model")

        try:
            pipe, placement = _qwen_local.load_pipeline(
                _qwen_local.TEXT_TO_IMAGE_REPO,
                quantization=quantization,
                offload=offload,
            )
        except Exception as exc:
            return ToolResult(success=False, error=f"Could not load Qwen-Image-2.1: {exc}")

        call_kwargs = _qwen_local.supported_call_kwargs(
            pipe,
            {
                "prompt": prompt,
                "negative_prompt": inputs.get("negative_prompt") or None,
                "width": inputs.get("width", 1328),
                "height": inputs.get("height", 1328),
                "num_inference_steps": inputs.get("num_inference_steps", 40),
                "true_cfg_scale": inputs.get("true_cfg_scale", 4.0),
                "generator": _qwen_local.make_generator(seed),
            },
        )

        try:
            image = pipe(**call_kwargs).images[0]
            output_path = Path(inputs.get("output_path", "qwen_image.png"))
            output_path.parent.mkdir(parents=True, exist_ok=True)
            image.save(str(output_path))
        except Exception as exc:
            return ToolResult(success=False, error=f"Qwen-Image-2.1 generation failed: {exc}")

        return ToolResult(
            success=True,
            data={
                "provider": self.provider,
                "model": _qwen_local.TEXT_TO_IMAGE_REPO,
                "prompt": prompt,
                "placement": placement,
                "quantization": quantization,
                "output": str(output_path),
            },
            artifacts=[str(output_path)],
            cost_usd=0.0,
            duration_seconds=round(time.time() - start, 2),
            seed=seed,
            model=_qwen_local.TEXT_TO_IMAGE_REPO,
        )

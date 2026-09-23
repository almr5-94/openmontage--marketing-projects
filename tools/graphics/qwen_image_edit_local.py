"""Qwen-Image-Edit-2511 instruction image editing, on this machine's GPU.

Weights live in the shared Hugging Face cache (`Qwen/Qwen-Image-Edit-2511`), so
an edit costs nothing and needs no API key. The 2511 release takes up to three
input images at once, which is what makes it useful in a montage: put a product
shot, a character sheet and a background in, and ask for one composed frame —
or hand it a single frame and describe the change in plain language.
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


class QwenImageEditLocal(BaseTool):
    """Local instruction-driven image editing with Qwen-Image-Edit-2511."""

    name = "qwen_image_edit_local"
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

    capabilities = ["edit_image", "image_to_image", "multi_image_edit", "generate_image"]
    supports = {
        "negative_prompt": True,
        "seed": True,
        "offline": True,
        "image_edit": True,
        "multi_image_input": True,
        "text_in_image": True,
    }
    best_for = [
        "changing one thing in an existing frame while the rest stays put",
        "composing up to three reference images into one frame",
        "keeping a character or product consistent across shots",
        "free editing with no API key and no per-image cost",
    ]
    not_good_for = [
        "machines without an NVIDIA GPU",
        "text-to-image from nothing (use qwen_image_local)",
        "the fastest possible turnaround — this is a 20B model on one card",
    ]
    fallback_tools = ["dashscope_image", "grok_image", "kling_official_image"]

    input_schema = {
        "type": "object",
        "required": ["prompt", "image_paths"],
        "properties": {
            "prompt": {
                "type": "string",
                "description": (
                    "The edit, in plain language. Say what changes and what must "
                    "stay the same."
                ),
            },
            "image_paths": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "maxItems": 3,
                "description": "Local paths to the input images (1-3).",
            },
            "negative_prompt": {"type": "string", "default": ""},
            "num_inference_steps": {"type": "integer", "default": 40},
            "true_cfg_scale": {"type": "number", "default": 4.0},
            "seed": {"type": "integer"},
            "quantization": {
                "type": "string",
                "enum": list(_qwen_local.QUANTIZATION_CHOICES),
                "default": "4bit",
                "description": (
                    "4bit fits this machine's 16 GB card. 'none' needs ~58 GB of "
                    "combined VRAM and RAM."
                ),
            },
            "offload": {
                "type": "string",
                "enum": list(_qwen_local.OFFLOAD_CHOICES),
                "default": "two_phase",
                "description": (
                    "two_phase encodes the prompt, frees the encoder, then "
                    "denoises — peak VRAM ~11.5 GB, which is what fits a 16 GB "
                    "card. The other modes need the whole model resident."
                ),
            },
            "output_path": {"type": "string", "default": "qwen_image_edit.png"},
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=4, ram_mb=20000, vram_mb=15500, disk_mb=58000, network_required=False
    )
    retry_policy = RetryPolicy(max_retries=1)
    idempotency_key_fields = ["prompt", "image_paths", "seed", "num_inference_steps"]
    side_effects = ["writes an image file to output_path", "holds the GPU for the duration of the run"]
    user_visible_verification = [
        "Compare the output against the input and confirm only the asked-for change moved",
        "Check any rendered text is spelled correctly",
    ]

    def get_status(self) -> ToolStatus:
        if not _qwen_local.diffusers_available():
            return ToolStatus.UNAVAILABLE
        if not _qwen_local.weights_cached(_qwen_local.IMAGE_EDIT_REPO):
            return ToolStatus.UNAVAILABLE
        return ToolStatus.AVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        return 0.0

    def estimate_runtime(self, inputs: dict[str, Any]) -> float:
        steps = inputs.get("num_inference_steps", 40)
        # A 20B transformer offloaded to a 16 GB card: slower per step than 2.1.
        return 120.0 + 5.0 * float(steps)

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        if not _qwen_local.diffusers_available():
            return ToolResult(
                success=False,
                error="diffusers/torch not installed. " + self.install_instructions,
            )
        if not _qwen_local.weights_cached(_qwen_local.IMAGE_EDIT_REPO):
            return ToolResult(
                success=False,
                error=(
                    f"{_qwen_local.IMAGE_EDIT_REPO} is not in the local Hugging Face "
                    "cache. " + self.install_instructions
                ),
            )

        raw_paths = inputs.get("image_paths") or []
        if isinstance(raw_paths, str):
            raw_paths = [raw_paths]
        if not raw_paths:
            return ToolResult(success=False, error="image_paths is required (1-3 local image paths)")

        from PIL import Image

        images = []
        for raw in raw_paths[:3]:
            path = Path(raw)
            if not path.is_file():
                return ToolResult(success=False, error=f"Input image not found: {path}")
            images.append(Image.open(path).convert("RGB"))

        start = time.time()
        seed = inputs.get("seed")
        quantization = inputs.get("quantization", "4bit")
        offload = inputs.get("offload", "two_phase")

        placement = offload
        try:
            if offload == "two_phase":
                result = _qwen_local.run_two_phase_edit(
                    _qwen_local.IMAGE_EDIT_REPO,
                    images,
                    inputs["prompt"],
                    quantization=quantization,
                    num_inference_steps=inputs.get("num_inference_steps", 40),
                    generator=_qwen_local.make_generator(seed),
                )
            else:
                pipe, placement = _qwen_local.load_pipeline(
                    _qwen_local.IMAGE_EDIT_REPO,
                    quantization=quantization,
                    offload=offload,
                )
                call_kwargs = _qwen_local.supported_call_kwargs(
                    pipe,
                    {
                        "image": images,
                        "prompt": inputs["prompt"],
                        "negative_prompt": inputs.get("negative_prompt") or None,
                        "num_inference_steps": inputs.get("num_inference_steps", 40),
                        "true_cfg_scale": inputs.get("true_cfg_scale", 4.0),
                        "generator": _qwen_local.make_generator(seed),
                    },
                )
                result = pipe(**call_kwargs).images[0]

            output_path = Path(inputs.get("output_path", "qwen_image_edit.png"))
            output_path.parent.mkdir(parents=True, exist_ok=True)
            result.save(str(output_path))
        except Exception as exc:
            return ToolResult(success=False, error=f"Qwen-Image-Edit-2511 edit failed: {exc}")

        return ToolResult(
            success=True,
            data={
                "provider": self.provider,
                "model": _qwen_local.IMAGE_EDIT_REPO,
                "prompt": inputs["prompt"],
                "inputs": [str(p) for p in raw_paths[:3]],
                "placement": placement,
                "quantization": quantization,
                "output": str(output_path),
            },
            artifacts=[str(output_path)],
            cost_usd=0.0,
            duration_seconds=round(time.time() - start, 2),
            seed=seed,
            model=_qwen_local.IMAGE_EDIT_REPO,
        )

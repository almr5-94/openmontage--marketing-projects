"""Shared loader for the Qwen-Image models held in this machine's HF cache.

Two tools sit on top of this module — `qwen_image_local` (text to image) and
`qwen_image_edit_local` (instruction image editing). Both run entirely on the
local GPU from weights already in the Hugging Face cache, cost nothing, and
never touch the network at generation time.

Everything heavy (torch, diffusers, transformers) is imported lazily inside the
functions so that tool discovery still works on a machine without them.

Hardware note: this box has 16 GB of VRAM and shares its RAM with other
services, while Qwen-Image-2.1 is ~33 GB and Qwen-Image-Edit-2511 ~58 GB in
bfloat16. The default load therefore quantizes the transformer and the text
encoder to 4-bit NF4 (bitsandbytes) and leaves CPU offload on. Pass
``quantization="none"`` only on a machine that can actually hold the full
weights.
"""

from __future__ import annotations

import gc
import inspect
import os
from typing import Any

# Repo ids as they appear in the Hugging Face cache.
TEXT_TO_IMAGE_REPO = "Qwen/Qwen-Image-2.1"
IMAGE_EDIT_REPO = "Qwen/Qwen-Image-Edit-2511"

QUANTIZATION_CHOICES = ("4bit", "8bit", "none")
OFFLOAD_CHOICES = ("two_phase", "balanced", "model", "sequential", "none")

INSTALL_INSTRUCTIONS = (
    "Install the local diffusion stack into the OpenMontage venv:\n"
    "  uv pip install --python .venv/bin/python --index-strategy unsafe-best-match \\\n"
    "    --extra-index-url https://download.pytorch.org/whl/cu128 \\\n"
    "    torch torchvision 'transformers>=5.0' accelerate bitsandbytes\n"
    "  uv pip install --python .venv/bin/python --no-deps \\\n"
    "    git+https://github.com/huggingface/diffusers.git@main\n"
    "    # Qwen-Image-2.1 needs QwenImage21Pipeline, which is on main, not in\n"
    "    # the 0.40.0 release. Qwen-Image-Edit-2511 works on 0.40.0 too.\n"
    "Then fetch the weights on this machine (HF_HUB_DISABLE_XET=1 — the Xet\n"
    "backend discards partial files when the link drops):\n"
    "  HF_HUB_DISABLE_XET=1 hf download Qwen/Qwen-Image-2.1\n"
    "  HF_HUB_DISABLE_XET=1 hf download Qwen/Qwen-Image-Edit-2511"
)

# One loaded pipeline per (repo, quantization, offload) so a batch of shots in
# the same run does not pay the load cost twice. Only ONE entry is ever kept:
# on a 16 GB card the 20B edit model needs ~9.5 GB in a single allocation, and
# a Qwen-Image-2.1 pipeline left resident from an earlier call is enough to
# make that fail. Generating and then editing in one process is the normal
# shape of a montage run, so the cache evicts rather than accumulates.
_PIPELINE_CACHE: dict[tuple[str, str, str], Any] = {}


def _vram_note(tag: str) -> None:
    """Print VRAM at a step when QWEN_VRAM_DEBUG is set. Silent otherwise."""
    if not os.environ.get("QWEN_VRAM_DEBUG"):
        return
    try:
        import torch

        if torch.cuda.is_available():
            print(f"[qwen vram] {tag}: {int(torch.cuda.memory_allocated() / 1e6)} MB", flush=True)
    except Exception:
        pass


def _free_pipeline(pipe: Any) -> None:
    """Release a pipeline's weights from the GPU.

    Deleting the Python reference is not enough. `enable_model_cpu_offload`
    installs accelerate hooks that hold their own references, and a pipeline
    keeps its components in attributes, so both have to be let go before the
    allocator will give the memory back.
    """
    if pipe is None:
        return
    for teardown in ("remove_all_hooks", "maybe_free_model_hooks"):
        fn = getattr(pipe, teardown, None)
        if callable(fn):
            try:
                fn()
            except Exception:
                pass
    try:
        for name in list(getattr(pipe, "components", {})):
            try:
                setattr(pipe, name, None)
            except Exception:
                pass
    except Exception:
        pass


def _reclaim_vram() -> None:
    """Collect and hand the freed blocks back to the driver."""
    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
    except Exception:
        pass


def _evict_other_pipelines(keep: tuple[str, str, str]) -> None:
    """Drop every cached pipeline except `keep` and hand the VRAM back.

    Dropping the dict entry is not enough: `enable_model_cpu_offload` installs
    accelerate hooks that keep their own references to every component, so the
    weights stay on the card until the hooks are removed. Without this the card
    still held 14.8 GB when the next model asked for room.
    """
    for key in [k for k in _PIPELINE_CACHE if k != keep]:
        entry = _PIPELINE_CACHE.pop(key, None)
        if entry is None:
            continue
        pipe = entry[0] if isinstance(entry, tuple) else entry
        _free_pipeline(pipe)
        del pipe, entry
    _reclaim_vram()


def diffusers_available() -> bool:
    """True when the local diffusion stack can be imported."""
    try:
        import diffusers  # noqa: F401
        import torch  # noqa: F401
        import transformers  # noqa: F401
    except Exception:
        return False
    return True


def weights_cached(repo_id: str) -> bool:
    """True when every file of `repo_id` is already in the local HF cache."""
    try:
        from huggingface_hub import snapshot_download
    except Exception:
        return False
    try:
        snapshot_download(repo_id, local_files_only=True)
    except Exception:
        return False
    return True


def snapshot_path(repo_id: str) -> str | None:
    """Local cache path for `repo_id`, or None when it is not fully cached."""
    try:
        from huggingface_hub import snapshot_download

        return snapshot_download(repo_id, local_files_only=True)
    except Exception:
        return None


def _quantization_config(quantization: str) -> Any:
    """Build a pipeline-level bitsandbytes config, or None for full precision."""
    if quantization == "none":
        return None

    import torch

    try:
        from diffusers import PipelineQuantizationConfig
    except ImportError:  # older layout
        from diffusers.quantizers import PipelineQuantizationConfig  # type: ignore

    if quantization == "8bit":
        return PipelineQuantizationConfig(
            quant_backend="bitsandbytes_8bit",
            quant_kwargs={"load_in_8bit": True},
            components_to_quantize=["transformer", "text_encoder"],
        )
    return PipelineQuantizationConfig(
        quant_backend="bitsandbytes_4bit",
        quant_kwargs={
            "load_in_4bit": True,
            "bnb_4bit_quant_type": "nf4",
            "bnb_4bit_compute_dtype": torch.bfloat16,
        },
        components_to_quantize=["transformer", "text_encoder"],
    )


def _max_memory_budget() -> dict[Any, str]:
    """How much of each device a balanced load may use.

    Qwen-Image-Edit-2511 at 4-bit is a ~10.7 GB transformer plus a ~5.2 GB text
    encoder. Both together overflow a 16 GB card, and the overflow happens
    during `from_pretrained`, before any offload hook exists — so the ceiling
    has to be declared up front and accelerate keeps the text encoder on the
    CPU. Three GB of headroom leaves room for activations and the VAE decode.
    """
    import torch

    if not torch.cuda.is_available():
        return {"cpu": "24GiB"}
    total_gib = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
    return {0: f"{max(4, int(total_gib) - 3)}GiB", "cpu": "18GiB"}


def _apply_placement(pipe: Any, offload: str) -> str:
    """Put the pipeline somewhere it fits. Returns the placement actually used."""
    import torch

    if not torch.cuda.is_available():
        return "cpu"

    if offload == "sequential":
        try:
            pipe.enable_sequential_cpu_offload()
            return "sequential_cpu_offload"
        except Exception:
            offload = "model"

    if offload == "model":
        try:
            pipe.enable_model_cpu_offload()
            return "model_cpu_offload"
        except Exception:
            pass

    try:
        pipe.to("cuda")
        return "cuda"
    except Exception:
        # Quantized weights are already pinned to the GPU by bitsandbytes.
        return "cuda_preplaced"


def load_pipeline(
    repo_id: str,
    quantization: str = "4bit",
    offload: str = "model",
) -> tuple[Any, str]:
    """Load (and memoize) a Qwen-Image pipeline from the local cache.

    Returns the pipeline and the placement string describing where it ran.
    """
    if quantization not in QUANTIZATION_CHOICES:
        raise ValueError(f"quantization must be one of {QUANTIZATION_CHOICES}")
    if offload not in OFFLOAD_CHOICES:
        raise ValueError(f"offload must be one of {OFFLOAD_CHOICES}")

    key = (repo_id, quantization, offload)
    cached = _PIPELINE_CACHE.get(key)
    if cached is not None:
        return cached

    # A pipeline held from an earlier call is the usual reason the next load
    # runs out of VRAM, so free it before asking for more.
    _evict_other_pipelines(key)

    import torch
    from diffusers import DiffusionPipeline

    # Generation is an offline operation: the weights are already here.
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    # A 9.5 GB single allocation on a 16 GB card fails on a fragmented heap.
    os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

    kwargs: dict[str, Any] = {
        "dtype": torch.bfloat16,
        "local_files_only": True,
    }
    quant_config = _quantization_config(quantization)
    if quant_config is not None:
        kwargs["quantization_config"] = quant_config
    if offload == "balanced":
        kwargs["device_map"] = "balanced"
        kwargs["max_memory"] = _max_memory_budget()

    pipe = DiffusionPipeline.from_pretrained(repo_id, **kwargs)

    # The VAE decode is the other place a 16 GB card runs out of room.
    for enable in ("enable_tiling", "enable_slicing"):
        fn = getattr(getattr(pipe, "vae", None), enable, None)
        if callable(fn):
            try:
                fn()
            except Exception:
                pass

    # A balanced load has already been placed by accelerate; touching it again
    # would undo the CPU offload that made it fit.
    placement = "balanced_device_map" if offload == "balanced" else _apply_placement(pipe, offload)
    _PIPELINE_CACHE[key] = (pipe, placement)
    return pipe, placement


def supported_call_kwargs(pipe: Any, candidate: dict[str, Any]) -> dict[str, Any]:
    """Drop any kwarg this pipeline's __call__ does not accept.

    Qwen-Image-2.1 and Qwen-Image-Edit-2511 do not take the same arguments, and
    diffusers renames things between releases; filtering by signature keeps both
    tools working without pinning to one version's argument list.
    """
    try:
        params = inspect.signature(pipe.__call__).parameters
    except (TypeError, ValueError):
        return {k: v for k, v in candidate.items() if v is not None}
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return {k: v for k, v in candidate.items() if v is not None}
    return {k: v for k, v in candidate.items() if v is not None and k in params}


def make_generator(seed: int | None) -> Any:
    """A seeded torch generator on the right device, or None for a random run."""
    if seed is None:
        return None
    import torch

    device = "cuda" if torch.cuda.is_available() else "cpu"
    return torch.Generator(device=device).manual_seed(int(seed))


def _condition_images(images: list[Any]) -> list[Any]:
    """Shrink the reference images to the size the text encoder expects.

    QwenImageEditPlusPipeline.__call__ resizes every condition image to about
    384x384 before it reaches the vision-language encoder, and only the VAE
    sees the full-resolution frame. Calling `encode_prompt` directly skips that
    step, and a 1024x1024 frame then drove the encoder to 14.8 GB and out of
    memory. This reproduces the pipeline's own preprocessing.
    """
    try:
        from diffusers.pipelines.qwenimage.pipeline_qwenimage_edit_plus import (
            CONDITION_IMAGE_SIZE,
            calculate_dimensions,
        )
    except Exception:
        CONDITION_IMAGE_SIZE = 384 * 384

        def calculate_dimensions(target_area, ratio):  # type: ignore[misc]
            import math

            width = int(round(math.sqrt(target_area * ratio)))
            height = int(round(math.sqrt(target_area / ratio)))
            return max(width - width % 32, 32), max(height - height % 32, 32)

    resized = []
    for img in images:
        width, height = img.size
        cond_w, cond_h = calculate_dimensions(CONDITION_IMAGE_SIZE, width / height)
        resized.append(img.resize((cond_w, cond_h)))
    return resized


def run_two_phase_edit(
    repo_id: str,
    images: list[Any],
    prompt: str,
    quantization: str = "4bit",
    **call_kwargs: Any,
) -> Any:
    """Encode the prompt, free the encoder, then denoise. Returns a PIL image.

    Why this exists: abood has 16 GB of VRAM, and with its other services up,
    only a few GB of free RAM. Qwen-Image-Edit-2511 at 4-bit is an ~11.5 GB
    transformer plus a ~5.2 GB text encoder. They do not fit on the card
    together, and parking either in CPU RAM got the process killed by the
    kernel OOM killer (2026-09-23 16:57). Loading each one, using it, and
    dropping it keeps peak VRAM at ~11.5 GB and peak RAM small.

    Classifier-free guidance is off (true_cfg_scale=1.0) because a negative
    prompt would need a second pass through the encoder.
    """
    import gc

    import torch
    from diffusers import DiffusionPipeline

    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

    # Generating a frame and then editing it is one process, so a text-to-image
    # pipeline from the earlier call is usually still resident. 6 GB of it plus
    # an 11.5 GB transformer overflows the card, so clear the cache first.
    _PIPELINE_CACHE.clear()
    _evict_other_pipelines(("", "", ""))

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    def _quant(components: list[str]) -> Any:
        config = _quantization_config(quantization)
        if config is None:
            return None
        config.components_to_quantize = components
        return config

    base = {"dtype": torch.bfloat16, "local_files_only": True}

    # --- phase 1: the text encoder, on its own --------------------------------
    encoder_kwargs = dict(base, transformer=None, vae=None)
    quant_encoder = _quant(["text_encoder"])
    if quant_encoder is not None:
        encoder_kwargs["quantization_config"] = quant_encoder
    encoder = DiffusionPipeline.from_pretrained(repo_id, **encoder_kwargs)
    _vram_note("encoder loaded")
    prompt_embeds, prompt_embeds_mask = encoder.encode_prompt(
        image=_condition_images(images),
        prompt=[prompt],
        device=device,
        num_images_per_prompt=1,
    )
    # encode_prompt returns a None mask when every token is real — keep that.
    prompt_embeds = prompt_embeds.detach().clone()
    if prompt_embeds_mask is not None:
        prompt_embeds_mask = prompt_embeds_mask.detach().clone()
    _vram_note("after encode")
    _free_pipeline(encoder)
    del encoder
    _reclaim_vram()
    _vram_note("encoder freed")

    # --- phase 2: the transformer and the VAE ---------------------------------
    denoiser_kwargs = dict(base, text_encoder=None)
    quant_denoiser = _quant(["transformer"])
    if quant_denoiser is not None:
        denoiser_kwargs["quantization_config"] = quant_denoiser
    denoiser = DiffusionPipeline.from_pretrained(repo_id, **denoiser_kwargs)
    _vram_note("denoiser loaded")
    for enable in ("enable_tiling", "enable_slicing"):
        fn = getattr(getattr(denoiser, "vae", None), enable, None)
        if callable(fn):
            try:
                fn()
            except Exception:
                pass
    _apply_placement(denoiser, "model")

    kwargs = supported_call_kwargs(
        denoiser,
        dict(
            call_kwargs,
            image=images,
            prompt_embeds=prompt_embeds,
            prompt_embeds_mask=prompt_embeds_mask,
            true_cfg_scale=1.0,
        ),
    )
    image = denoiser(**kwargs).images[0]

    _free_pipeline(denoiser)
    del denoiser
    _reclaim_vram()
    return image

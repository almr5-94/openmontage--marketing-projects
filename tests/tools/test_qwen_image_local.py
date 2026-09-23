"""Unit tests for the local Qwen-Image tools (generation and editing).

These never load the 33 GB / 58 GB weights — they check the contract the
registry and the image selector rely on, and the two guard paths that keep a
half-installed machine from producing a confusing crash.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.base_tool import ToolStatus


# ---------------------------------------------------------------------------
# Tool discovery & metadata
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tool_name,expected_caps",
    [
        ("qwen_image_local", "text_to_image"),
        ("qwen_image_edit_local", "edit_image"),
    ],
)
def test_qwen_tools_are_discovered_by_registry(tool_name, expected_caps):
    from tools.tool_registry import ToolRegistry

    registry = ToolRegistry()
    registry.discover()

    tool = registry.get(tool_name)
    assert tool is not None
    assert tool.provider == "qwen_local"
    assert tool.capability == "image_generation"
    assert expected_caps in tool.capabilities


def test_generation_tool_metadata():
    from tools.graphics.qwen_image_local import QwenImageLocal

    info = QwenImageLocal().get_info()

    assert info["tier"] == "generate"
    assert info["runtime"] == "local_gpu"
    assert info["supports"]["offline"] is True
    assert info["supports"]["seed"] is True
    assert info["resource_profile"]["network_required"] is False


def test_edit_tool_advertises_image_editing():
    """image_selector routes an edit only to tools that claim image_edit."""
    from tools.graphics.qwen_image_edit_local import QwenImageEditLocal

    tool = QwenImageEditLocal()

    assert tool.supports["image_edit"] is True
    assert "image_paths" in tool.input_schema["properties"]
    assert tool.input_schema["properties"]["image_paths"]["maxItems"] == 3


def test_both_tools_are_free():
    from tools.graphics.qwen_image_edit_local import QwenImageEditLocal
    from tools.graphics.qwen_image_local import QwenImageLocal

    assert QwenImageLocal().estimate_cost({"prompt": "x"}) == 0.0
    assert QwenImageEditLocal().estimate_cost({"prompt": "x"}) == 0.0


# ---------------------------------------------------------------------------
# Availability guards
# ---------------------------------------------------------------------------


def test_status_is_unavailable_without_the_diffusion_stack():
    from tools.graphics.qwen_image_local import QwenImageLocal

    with patch("tools.graphics._qwen_local.diffusers_available", return_value=False):
        assert QwenImageLocal().get_status() == ToolStatus.UNAVAILABLE


def test_status_is_unavailable_when_weights_are_not_cached():
    from tools.graphics.qwen_image_local import QwenImageLocal

    with patch("tools.graphics._qwen_local.diffusers_available", return_value=True), \
            patch("tools.graphics._qwen_local.weights_cached", return_value=False):
        assert QwenImageLocal().get_status() == ToolStatus.UNAVAILABLE


def test_execute_reports_missing_weights_instead_of_crashing():
    from tools.graphics.qwen_image_local import QwenImageLocal

    with patch("tools.graphics._qwen_local.diffusers_available", return_value=True), \
            patch("tools.graphics._qwen_local.weights_cached", return_value=False):
        result = QwenImageLocal().execute({"prompt": "a red bicycle"})

    assert result.success is False
    assert "Qwen/Qwen-Image-2.1" in result.error


def test_edit_execute_rejects_a_missing_input_image():
    from tools.graphics.qwen_image_edit_local import QwenImageEditLocal

    with patch("tools.graphics._qwen_local.diffusers_available", return_value=True), \
            patch("tools.graphics._qwen_local.weights_cached", return_value=True):
        result = QwenImageEditLocal().execute(
            {"prompt": "make the sky green", "image_paths": ["/nope/missing.png"]}
        )

    assert result.success is False
    assert "not found" in result.error


# ---------------------------------------------------------------------------
# Pipeline argument filtering
# ---------------------------------------------------------------------------


def test_unsupported_kwargs_are_dropped_before_the_pipeline_is_called():
    """Qwen-Image-2.1 and Qwen-Image-Edit-2511 do not share an argument list."""
    from tools.graphics import _qwen_local

    class FakePipe:
        def __call__(self, prompt, num_inference_steps=40):  # noqa: D401
            return None

    kept = _qwen_local.supported_call_kwargs(
        FakePipe(),
        {"prompt": "x", "num_inference_steps": 8, "true_cfg_scale": 4.0, "generator": None},
    )

    assert kept == {"prompt": "x", "num_inference_steps": 8}


def test_quantization_and_offload_choices_are_validated():
    from tools.graphics import _qwen_local

    with pytest.raises(ValueError):
        _qwen_local.load_pipeline(_qwen_local.TEXT_TO_IMAGE_REPO, quantization="2bit")
    with pytest.raises(ValueError):
        _qwen_local.load_pipeline(_qwen_local.TEXT_TO_IMAGE_REPO, offload="disk")

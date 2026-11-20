"""Real-ESRGAN's base library (basicsr 1.4.2) imports a torchvision module that
torchvision 0.17+ removed. The upscale tool registers the old name first, so the
tool reports AVAILABLE once realesrgan and torch are installed."""
import sys
import types

from tools.enhancement import upscale


def test_old_functional_tensor_name_points_at_functional(monkeypatch):
    fake_tv = types.ModuleType("torchvision")
    fake_tf = types.ModuleType("torchvision.transforms")
    fake_f = types.ModuleType("torchvision.transforms.functional")
    fake_f.rgb_to_grayscale = lambda x: x
    fake_tv.transforms = fake_tf
    fake_tf.functional = fake_f
    monkeypatch.setitem(sys.modules, "torchvision", fake_tv)
    monkeypatch.setitem(sys.modules, "torchvision.transforms", fake_tf)
    monkeypatch.setitem(sys.modules, "torchvision.transforms.functional", fake_f)
    monkeypatch.delitem(sys.modules, "torchvision.transforms.functional_tensor", raising=False)

    upscale._torchvision_compat()

    assert sys.modules["torchvision.transforms.functional_tensor"] is fake_f
    from torchvision.transforms.functional_tensor import rgb_to_grayscale  # noqa: F401


def test_compat_is_a_no_op_without_torchvision(monkeypatch):
    monkeypatch.setitem(sys.modules, "torchvision", None)
    monkeypatch.delitem(sys.modules, "torchvision.transforms.functional_tensor", raising=False)
    upscale._torchvision_compat()
    assert "torchvision.transforms.functional_tensor" not in sys.modules

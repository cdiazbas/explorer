"""scripts/types_intel.py: mypy with the Intel Mac's types. What it reads of pyproject and uv.lock, and what it keeps
of numpy's wheel, without the network; the run itself is scripts/check.sh's."""
import importlib.util
import tomllib
from pathlib import Path

ROOT = Path(__file__).parents[2]
_spec = importlib.util.spec_from_file_location("types_intel", ROOT / "scripts" / "types_intel.py")
ti = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ti)


def test_the_intel_pins_and_wheel_come_from_pyproject_and_uv_lock():
    pyproject = (ROOT / "pyproject.toml").read_text()
    version = ti.intel_pin(pyproject, "numpy")
    w = ti.intel_wheel(tomllib.loads((ROOT / "uv.lock").read_text()), "numpy", version)
    name = w["url"].rsplit("/", 1)[-1]
    assert name.startswith(f"numpy-{version}-cp312-cp312-macosx") and name.endswith("_x86_64.whl")
    assert w["hash"].startswith("sha256:") and len(w["hash"]) == len("sha256:") + 64


def test_a_missing_pin_or_wheel_says_so():
    import pytest

    with pytest.raises(SystemExit, match="no numpy pin"):
        ti.intel_pin('"numpy==2.5.3"', "numpy")
    with pytest.raises(SystemExit, match="no numpy 9.9 wheel"):
        ti.intel_wheel({"package": [{"name": "numpy", "version": "9.9", "wheels": []}]}, "numpy", "9.9")


def test_only_python_and_stub_files_are_kept():
    assert ti.kept("numpy/__init__.pyi") and ti.kept("numpy/_core/numeric.py") and ti.kept("numpy/py.typed")
    assert not ti.kept("numpy/_core/_multiarray_umath.cpython-312-darwin.so") and not ti.kept("numpy/LICENSE.txt")

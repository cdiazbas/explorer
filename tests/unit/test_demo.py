"""`explorer demo` runs headless on a given cube, and writes its synthetic cube once."""
import pytest

from explorer import demo
from explorer.testing import synth


@pytest.fixture
def headless(monkeypatch, tmp_path):
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("LD_LIBRARY_PATH", raising=False)
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    return tmp_path


def test_demo_on_a_given_cube(headless):
    cube = synth.write_stokes_cube(headless / "c_im.fits", shape=(2, 1, 3, 32, 32))
    assert demo.main([str(cube), "--no-window"]) == 0


def test_synthetic_cube_is_written_once(headless, monkeypatch):
    calls = []
    monkeypatch.setattr(synth, "write_stokes_cube", lambda p, **k: (calls.append(p), p.write_bytes(b"x"))[0])
    first, second = demo.synthetic_cube(), demo.synthetic_cube()
    assert first == second and len(calls) == 1 and not list((headless / "cache" / "explorer" / "demo").glob("*.tmp*"))

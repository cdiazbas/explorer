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
    assert demo.main([str(cube), "--no-window", "--moves", "2"]) == 0


def test_cursor_walk_with_and_without_the_per_pixel_file(headless, capsys):
    paths = synth.write_dataset(headless / "d", "c", shape=(3, 4, 5, 48, 40), icube=False)
    with_sp = demo.cursor_walk(paths["im"], moves=3)
    without = demo.cursor_walk(paths["im"], no_sp=True, moves=3)
    out = capsys.readouterr().out
    assert "per-pixel file (sp.fits)" in out and "no per-pixel file" in out
    assert sum(line.startswith("  move ") for line in out.splitlines()) == 6
    assert set(with_sp) == set(without) == {"spectrum", "lambda_t"}
    assert set(demo.cursor_walk(paths["im"], no_sp=True, moves=5, drag=True)) == {"spectrum", "lambda_t"}


def test_synthetic_cube_is_written_once_with_its_per_pixel_file(headless, monkeypatch):
    calls = []

    def fake(directory, name, **k):                        # no 84 MB cubes in unit tests
        calls.append(name)
        directory.mkdir(parents=True, exist_ok=True)
        paths = {"im": directory / f"{name}_im.fits", "sp": directory / f"{name}_sp.fits"}
        for p in paths.values():
            p.write_bytes(b"x")
        return {k: str(v) for k, v in paths.items()}

    demo_dir = headless / "cache" / "explorer" / "demo"
    demo_dir.mkdir(parents=True)
    (demo_dir / "synth_stokes_v1_im.fits").write_bytes(b"old")        # a cube of an older version
    monkeypatch.setattr(synth, "write_dataset", fake)
    first, second = demo.synthetic_cube(), demo.synthetic_cube()
    assert first == second and len(calls) == 1
    names = sorted(p.name for p in demo_dir.iterdir())
    v = synth.SYNTH_VERSION
    assert names == [f"synth_stokes_v{v}_im.fits", f"synth_stokes_v{v}_sp.fits"]      # old one gone, no temp left

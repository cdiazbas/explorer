"""ui.app.start(): the window as `explorer cube` shows it, shared by run() and the self-test (ROADMAP E0.15). The
self-test built its own window (no title bar, no display attachment of explorer's, never the bridge), so it measured
a window nobody sees."""
import json
import os
import subprocess
import sys

import pytest

from explorer.testing import synth

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def headless(monkeypatch, tmp_path):
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    return tmp_path


def test_start_without_the_saved_layout_reads_and_writes_none(qapp, headless):
    from explorer.ui.app import start

    cube = synth.write_dataset(headless / "d", "c", shape=(2, 4, 3, 32, 24), icube=False)["im"]
    s = start(cube, saved_layout=False)
    assert s is not None
    try:
        assert s.shell.window_ops is not None and s.shell.layout_store is None
        assert s.app_ready >= s.t0 and s.theme
    finally:
        s.shell.close()
        s.close()
    config = headless / "config"
    assert not config.exists() or not any(config.rglob("*")), list(config.rglob("*"))


def test_a_linked_cube_that_cannot_open_is_left_out_and_the_first_opens(qapp, headless, capsys):
    """A linked cube whose WCS-TAB holds 2 times for its 3 frames in t (Dataset.open refuses it): not linked, with
    the reason, as the plan's other refusals; the first cube opens alone. Planned as linked, its opening made the
    start return None, the first cube included."""
    from astropy.io import fits

    from explorer.ui.app import start

    shape = (3, 1, 5, 16, 12)
    main = synth.write_stokes_cube(headless / "x_im.fits", shape=shape)
    other = synth.write_stokes_cube(headless / "y_im.fits", shape=(2,) + shape[1:])
    with fits.open(main) as a, fits.open(other) as b:
        fits.HDUList([fits.PrimaryHDU(a[0].data, a[0].header), b["WCS-TAB"].copy()]).writeto(headless / "z_im.fits")
    s = start(main, no_sp=True, saved_layout=False, linked=[headless / "z_im.fits"])
    err = capsys.readouterr().err
    print(err)
    assert s is not None, err
    try:
        assert s.ds.path == str(main) and s.linked == []
        assert "not linked: z_im.fits" in err and "2 times for 3 steps along its t" in err
    finally:
        s.shell.close()
        s.close()


def test_the_self_test_goes_through_start(headless):
    cube = synth.write_dataset(headless / "d", "c", shape=(2, 4, 3, 32, 24), icube=False)["im"]
    out = headless / "r.json"
    p = subprocess.run([sys.executable, os.path.join(ROOT, "bench", "explorer_selftest.py"), str(cube), "--x11", "auto",
                        "--out", str(out)], env=dict(os.environ), capture_output=True, text=True, timeout=300)
    assert p.returncode == 0, p.stderr[-2000:]
    r = json.loads(out.read_text())
    assert r["bridge"] is False and r["platform"] == "offscreen" and r["open_to_first_frame_s"] >= 0
    assert {"step in t", "step in λ", "change Stokes"} <= set(r["actions"])


def test_the_theme_switched_with_t_is_the_next_starts(qapp, headless, monkeypatch):
    """Without --theme a start takes the theme in use at the last close (ROADMAP E5.24); --theme wins over it."""
    from PySide6 import QtGui, QtWidgets

    from explorer.ui import style
    from explorer.ui.app import start

    name, pal = qapp.style().name(), QtGui.QPalette(qapp.palette())
    monkeypatch.setenv("EXPLORER_LAYOUT", str(headless / "layout.ini"))
    cube = synth.write_dataset(headless / "d", "c", shape=(2, 4, 3, 32, 24), icube=False)["im"]
    try:
        for given, want, switch in (("dark", "dark", True), (None, "light", True), (None, "dark", False),
                                    ("light", "light", False)):
            s = start(cube, theme=given)
            assert s is not None
            try:
                assert s.theme == want and style.is_light() == (want == "light"), (given, want, s.theme)
                if switch:
                    s.shell.toggle_theme()              # T: the other one, kept at the close
            finally:
                s.shell.close()
                s.close()
    finally:
        qapp.setStyle(QtWidgets.QStyleFactory.create(name or "Fusion"))
        qapp.setPalette(pal)
        qapp.setProperty("explorer_light", False)

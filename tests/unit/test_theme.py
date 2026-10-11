"""A switch of theme while the window runs (T, Shell.set_theme), offscreen: every part as in a window started in that
theme, in each look and in the 2x2 view, both ways; glass switches in place, its panels where they are and the image's
region kept; T is in the key table. The application's switch alone (style.apply_theme) left the image, the spectra
and the window's own background in the old theme."""
import time

import numpy as np
import pytest

from explorer.testing import synth

SHAPE = (3, 4, 9, 64, 80)


def spin(qapp, until=lambda: False, timeout=1.0):
    end = time.perf_counter() + timeout
    while not until() and time.perf_counter() < end:
        qapp.processEvents()
        time.sleep(0.002)
    return until()


@pytest.fixture(scope="module")
def cube(tmp_path_factory):
    return synth.write_dataset(tmp_path_factory.mktemp("theme"), "c", shape=SHAPE, icube=False)["im"]


@pytest.fixture
def restore(qapp):
    from PySide6 import QtGui, QtWidgets

    name, pal = qapp.style().name(), QtGui.QPalette(qapp.palette())
    yield qapp
    qapp.setStyle(QtWidgets.QStyleFactory.create(name or "Fusion"))
    qapp.setPalette(pal)
    qapp.setProperty("explorer_light", False)
    import pyqtgraph as pg

    pg.setConfigOptions(background="k", foreground="d")


def window(qapp, cube, look, grid=False):
    from explorer.data.dataset import Dataset
    from explorer.look import get_look
    from explorer.ui.shell import Shell

    ds = Dataset.open(cube)
    w = Shell(ds, title="c_im.fits", look=get_look(look))
    w.setGeometry(60, 50, 1000, 700)
    w.show()
    assert spin(qapp, lambda: w.first_image_s is not None and "lambda_t" in w.last, 10.0)
    if grid:
        w.set_grid(True)
    spin(qapp, timeout=0.5)
    return w, ds


def parts(w):
    out = dict(window=w, image=w.view.widget, spectra=w.spectra.w, lambda_t=w.lambda_t.w, toolbar=w.nav.tb,
               status=w.statusBar(), image_lock=w.image_lock, spec_lock=w.spec_lock, colour_key=w.colour_key,
               spec_dock=w.spec_dock, lt_dock=w.lt_dock, grid=w.grid)
    if w.glass is not None:
        # shown in both and kept: the autohide's timing is not compared. Its timer runs from the window's making, the
        # first window's ~2 s before the capture: hidden in the spin before it, 15 % of that window's pixels differed
        w.glass.autohide.stop()
        w.glass.bar.show()
        out["bar"] = w.glass.bar
    return {k: v for k, v in out.items() if v is not None and v.isVisible()}


def pixels(widget):
    from PySide6 import QtGui

    im = widget.grab().toImage().convertToFormat(QtGui.QImage.Format.Format_RGB888)
    a = np.frombuffer(im.constBits(), np.uint8).reshape(im.height(), im.bytesPerLine())[:, :im.width() * 3]
    return a.reshape(im.height(), im.width(), 3).astype(int)


@pytest.mark.parametrize("look, grid", [("classic", False), ("modern", False), ("glass", False), ("modern", True)])
@pytest.mark.parametrize("first, then", [("dark", "light"), ("light", "dark")])
def test_switched_every_part_is_as_in_a_window_started_in_that_theme(restore, cube, look, grid, first, then):
    from explorer.ui import style

    qapp = restore
    style.apply_theme(qapp, first)
    a, da = window(qapp, cube, look, grid)
    b = db = None
    try:
        a.set_theme(then)
        assert style.is_light() == (then == "light")
        b, db = window(qapp, cube, look, grid)          # the application is in the new theme now
        pa, pb = parts(a), parts(b)
        spin(qapp, timeout=0.3)
        assert set(pa) == set(pb)
        off = {}
        for k in pa:
            x, y = pixels(pa[k]), pixels(pb[k])
            assert x.shape == y.shape, k
            d = np.abs(x - y).max(axis=2)
            if (d > 24).mean() > 0.002:
                off[k] = round(float((d > 24).mean()), 3)
        assert not off, off                              # the share of each part's pixels that differ
    finally:
        for w, ds in ((a, da), (b, db)):
            if w is not None:
                w.close()
                ds.close()


def test_glass_switches_in_place(restore, cube):
    """Taking glass off and on again would put the panels back beside the window and show the whole image."""
    from PySide6 import QtCore

    from explorer.ui import style

    qapp = restore
    style.apply_theme(qapp, "dark")
    w, ds = window(qapp, cube, "glass")
    try:
        spin(qapp, timeout=0.3)
        w.view.vb.setRange(QtCore.QRectF(10, 12, 30, 24), padding=0)
        w.spec_dock.move(w.spec_dock.x() + 37, w.spec_dock.y() + 21)
        spin(qapp, timeout=0.3)
        region, where = w.view.vb.viewRect(), w.spec_dock.geometry()
        w.set_theme("light")
        spin(qapp, timeout=0.5)
        assert w.glass is not None and w.view.vb.viewRect() == region and w.spec_dock.geometry() == where
    finally:
        w.close()
        ds.close()


def test_t_switches_the_theme(restore, cube):
    from explorer.ui import style

    qapp = restore
    style.apply_theme(qapp, "dark")
    w, ds = window(qapp, cube, "classic")
    try:
        assert "T" in " ".join(k for k, _w, _b in w.key_table()).split()
        w.toggle_theme()
        assert style.is_light() and "light theme" in w.statusBar().currentMessage()
        w.toggle_theme()
        assert not style.is_light()
    finally:
        w.close()
        ds.close()

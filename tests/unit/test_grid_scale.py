"""The scale in the 2x2 view (ROADMAP E5.33), offscreen, in classic, modern and glass: each panel has its own padlock,
for that panel's Stokes, as the single image has one for the Stokes it shows. The padlock over a panel fixes or
releases that panel's Stokes, a right click on it fixes the levels to that panel's frame, and it shows whether that
Stokes is fixed; the single image's padlock is not over the panels."""
import contextlib
import time

import pytest

from explorer.core.levels import rule_levels
from explorer.testing import synth

SHAPE = (3, 4, 5, 96, 80)


def spin(qapp, until=lambda: False, timeout=10.0):
    end = time.perf_counter() + timeout
    while not until() and time.perf_counter() < end:
        qapp.processEvents()
        time.sleep(0.002)
    return until()


@pytest.fixture(scope="module")
def cube(tmp_path_factory):
    return synth.write_dataset(tmp_path_factory.mktemp("gridscale"), "c", shape=SHAPE, icube=False)["im"]


@contextlib.contextmanager
def made(qapp, cube, look):
    from PySide6 import QtGui, QtWidgets

    from explorer.data.dataset import Dataset
    from explorer.look import get_look
    from explorer.ui import style
    from explorer.ui.shell import Shell

    name, pal = qapp.style().name(), QtGui.QPalette(qapp.palette())
    style.apply_theme(qapp, "dark")
    ds = Dataset.open(cube)
    w = Shell(ds, title="c_im.fits", look=get_look(look, {}))
    w.setGeometry(60, 50, 1100, 760)
    w.show()
    try:
        assert spin(qapp, lambda: w.first_image_s is not None and "lambda_t" in w.last)
        w.set_grid(True)
        assert spin(qapp, lambda: all(v._full is not None for v in w.grid.views))
        spin(qapp, timeout=0.2)
        yield w
    finally:
        for m in w.findChildren(QtWidgets.QMenu):
            m.close()
        w.close()
        ds.close()
        qapp.setStyle(QtWidgets.QStyleFactory.create(name or "Fusion"))
        qapp.setPalette(pal)
        qapp.setProperty("explorer_light", False)


@pytest.fixture(params=["classic", "modern", "glass"])
def grid(request, qapp, cube):
    with made(qapp, cube, request.param) as w:
        yield w, qapp


def global_rect(widget):
    from PySide6 import QtCore

    return QtCore.QRect(widget.mapToGlobal(QtCore.QPoint(0, 0)), widget.size())


def lock_over(w, s):
    """The padlock shown over panel s of the 2x2 view (its centre on that panel), or None."""
    from explorer.ui.padlock import PanelLock

    panel = global_rect(w.grid.views[s].widget)
    over = [p for p in w.findChildren(PanelLock) if p.isVisible() and panel.contains(global_rect(p).center())]
    assert len(over) <= 1, over
    return over[0] if over else None


def panel_drawn(qapp, w, s):
    qapp.processEvents()
    return tuple(w.grid.views[s]._lim)


# ---------------------------------------------------------------------------------------------- the padlocks
def test_the_padlock_over_each_panel_fixes_that_panel_s_stokes(grid):
    w, qapp = grid
    sess = w.session
    assert sess.state.s == 0
    for s in range(4):
        lock = lock_over(w, s)
        assert lock is not None and not lock.isChecked(), (s, lock)
    lock_over(w, 1).click()                             # Q's, while the session's Stokes is I
    qapp.processEvents()
    want = rule_levels(w.grid.views[1]._full, True, "p1")
    assert sess.scale(0, 1) == ("fixed", *want), sess.state.scale
    assert all(sess.scale(0, s)[0] == "p1" for s in (0, 2, 3)), sess.state.scale
    assert spin(qapp, lambda: panel_drawn(qapp, w, 1) == want)
    assert lock_over(w, 1).isChecked() and not any(lock_over(w, s).isChecked() for s in (0, 2, 3))
    lock_over(w, 1).click()                             # open: Q automatic again, the others untouched
    qapp.processEvents()
    assert all(sess.scale(0, s)[0] == "p1" for s in range(4)) and not lock_over(w, 1).isChecked()


def test_each_panel_s_padlock_shows_its_stokes_and_its_right_click_fits_its_frame(grid):
    w, qapp = grid
    sess = w.session
    sess.set_scale(0, 2, "fixed", 0.1, 0.5)             # U fixed by anything else (the menu, the layout)
    qapp.processEvents()
    assert [lock_over(w, s).isChecked() for s in range(4)] == [False, False, True, False]
    lock_over(w, 3).refit.emit()                        # V's right click: fixed to V's frame now
    qapp.processEvents()
    assert sess.scale(0, 3) == ("fixed", *rule_levels(w.grid.views[3]._full, True, "p1"))
    assert lock_over(w, 3).isChecked() and sess.scale(0, 2) == ("fixed", -0.5, 0.5)
    assert sess.scale(0, 0)[0] == "p1"
    w.set_grid(False)                                   # the single image: its own padlock, for its Stokes (I)
    qapp.processEvents()
    assert w.image_lock.isVisible() and not w.image_lock.isChecked()
    w.set_grid(True)
    qapp.processEvents()
    assert not w.image_lock.isVisible()
    assert [lock_over(w, s).isChecked() for s in range(4)] == [False, False, True, True]

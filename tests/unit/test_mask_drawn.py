"""The mask's outline on every image (ROADMAP E8.2, ui.mask), offscreen: on the main cube's image, a linked cube's
and the 2x2 view's four, the outline of the mask's frame at the session's t, following t on all of them; in the
look's accent in every look; drawn (pixels of that colour on the image); nothing of it without a mask. Hidden and
shown again by Panels → Mask and by H, in step, on every image; hidden, the t steps read nothing of the mask; without
a mask, no entry, no H and no row on the ? sheet. Each test prints what it measured."""
import time

import numpy as np
import pytest

from explorer.testing import synth

SHAPE = (4, 4, 5, 48, 40)                               # t, s, lambda, y, x


def spin(qapp, until, timeout=10.0):
    end = time.perf_counter() + timeout
    while not until() and time.perf_counter() < end:
        qapp.processEvents()
        time.sleep(0.002)
    return until()


@pytest.fixture(scope="module")
def cubes(tmp_path_factory):
    from astropy.io import fits

    d = tmp_path_factory.mktemp("mask_drawn")
    main = synth.write_dataset(d, "main", shape=SHAPE, icube=False)["im"]
    blos = d / "Blos.map.fcube"
    synth.write_lp(blos, np.random.default_rng(1).normal(size=(SHAPE[0], SHAPE[3], SHAPE[4])))
    m = np.zeros((SHAPE[0], SHAPE[3], SHAPE[4]), np.uint8)
    for k in range(SHAPE[0]):                           # a box moving right by 3 px per t
        m[k, 10:30, 5 + 3 * k:20 + 3 * k] = 1
    per_t = d / "per_t_mask.fits"
    fits.PrimaryHDU(m).writeto(per_t)
    return {"main": main, "map": blos, "per_t": per_t, "boxes": m}


@pytest.fixture
def window(qapp, cubes):
    from explorer.data.dataset import Dataset
    from explorer.data.mask import Mask
    from explorer.ui.shell import Shell

    ds = Dataset.open(cubes["main"])
    linked = Dataset.open(cubes["map"], axes="t", executors=ds.executors)
    mask = Mask.open(cubes["per_t"], ds)
    w = Shell(ds, linked=[linked], mask=mask)
    w.resize(1400, 600)
    w.show()
    assert spin(qapp, lambda: w.first_image_s is not None and all(c.scheduler.img is not None for c in w.linked)
                and w.mask_outlines.frame is not None)      # the outline comes from a worker (ui.mask)
    yield w
    w.close()
    for c in (mask, linked, ds):
        c.close()


def images(w):
    """Every image view of the window: the main cube's, the linked ones', the 2x2 view's once made."""
    return [w.view, *(c.view for c in w.linked), *(w.grid.views if w.grid is not None else [])]


def drawn(w):
    """The segments each image's outline holds: [(x, y) pairs as (n, 2, 2)] per image, in images()'s order."""
    out = []
    for v in images(w):
        items = [it for it in w.mask_outlines.items if it.getViewBox() is v.vb]
        assert len(items) == 1
        x, y = items[0].getData()
        out.append(np.stack([x, y], -1).reshape(-1, 2, 2))
    return out


def test_on_every_image_following_t(qapp, window, cubes):
    from explorer.data.mask import outline

    w = window
    w.set_grid(True)
    assert spin(qapp, lambda: w.grid is not None and w.grid.isVisible())
    assert len(images(w)) == 6
    for t in (0, 2, 3, 1):
        w.session.set_index("t", t)
        assert spin(qapp, lambda t=t: w.mask_outlines.frame == t)
        qapp.processEvents()
        want = outline(cubes["boxes"][t] >= 1)
        got = drawn(w)
        print(f"t {t}: {len(want)} segments; leftmost x per image", [float(g[:, :, 0].min()) for g in got])
        for g in got:
            np.testing.assert_array_equal(g, want)
        assert float(got[0][:, :, 0].min()) == 5 + 3 * t


def test_outline_computed_off_the_ui_thread_and_ahead(qapp, window, cubes, monkeypatch):
    """A step in t to a frame whose outline is not kept: set_index returns without reading or outlining it on the UI
    thread; the outline comes from a worker and is drawn, and the next t's (2 and 3 after 1, AHEAD) are kept."""
    import threading

    from explorer.data import mask as dm

    w = window
    mo = w.mask_outlines
    assert spin(qapp, lambda: not getattr(mo, "_busy", set()))
    mo.mask._kept.clear()
    threads = []
    real = dm.outline

    def recorded(m):
        threads.append(threading.current_thread() is threading.main_thread())
        return real(m)
    monkeypatch.setattr(dm, "outline", recorded)
    w.session.set_index("t", 1)
    on_ui = list(threads)
    assert spin(qapp, lambda: mo.frame == 1 and not getattr(mo, "_busy", set()))
    print("outlines computed during set_index:", len(on_ui), "on the UI thread:", sum(on_ui),
          "| then:", len(threads), "in all, on the UI thread:", sum(threads), "| kept:", sorted(mo.mask._kept))
    assert not any(threads)
    np.testing.assert_array_equal(drawn(w)[0], real(cubes["boxes"][1] >= 1))
    assert {1, 2, 3} <= set(mo.mask._kept)


def test_in_the_looks_accent(qapp, window):
    from explorer.look import get_look
    from explorer.ui import glass, style

    w = window
    for name in ("classic", "modern", "glass", "classic"):
        w.set_look(get_look(name))
        qapp.processEvents()
        want = (glass.accent() if name == "glass" else style.accent()).name()
        got = {it.opts["pen"].color().name() for it in w.mask_outlines.items}
        print(name, want, got)
        assert got == {want}


def accent_pixels(w, colour):
    from PySide6 import QtGui

    img = w.view.widget.grab().toImage().convertToFormat(QtGui.QImage.Format.Format_RGB32)
    a = np.frombuffer(img.constBits(), np.uint8).reshape(img.height(), img.bytesPerLine())[:, :img.width() * 4]
    a = a.reshape(img.height(), img.width(), 4).copy()
    bgr = np.array([colour.blue(), colour.green(), colour.red()])
    return int((np.abs(a[:, :, :3].astype(int) - bgr).max(-1) <= 8).sum())


def test_drawn_on_the_image(qapp, window):
    from explorer.ui.glass import look_accent

    w = window
    n = accent_pixels(w, look_accent(w.look))
    print("pixels in the outline's colour:", n)
    assert n > 50


def test_nothing_without_a_mask(qapp, cubes):
    from explorer.data.dataset import Dataset
    from explorer.ui.glass import look_accent
    from explorer.ui.shell import Shell

    ds = Dataset.open(cubes["main"])
    w = Shell(ds)
    w.resize(900, 600)
    w.show()
    try:
        assert spin(qapp, lambda: w.first_image_s is not None)
        w.set_grid(True)
        qapp.processEvents()
        # ui.mask's items are the only curves drawn as pairs of points
        curves = [it for v in images(w) for it in v.vb.allChildren()
                  if type(it).__name__ == "PlotCurveItem" and it.opts.get("connect") == "pairs"]
        n = accent_pixels(w, look_accent(w.look))
        print("outlines:", w.mask_outlines, "curves:", len(curves), "pixels in the accent:", n)
        assert w.mask_outlines is None and not curves
    finally:
        w.close()
        ds.close()


def mask_entry(w):
    """The Panels menu's Mask entry, as the menu makes it when it opens (ui.toolbar); None when it has none."""
    menu = w.nav.panels.menu()
    menu.aboutToShow.emit()
    hits = [a for a in menu.actions() if a.text() == "Mask"]
    assert len(hits) <= 1
    return hits[0] if hits else None


def fire(w, seq):
    from PySide6 import QtGui

    ks = QtGui.QKeySequence(seq)
    hits = [sc for sc in w.findChildren(QtGui.QShortcut) if sc.key() == ks]
    assert len(hits) == 1, seq
    hits[0].activated.emit()


def test_hidden_and_shown_by_the_menu_and_by_h_on_every_image(qapp, window):
    """Panels → Mask and H (the window's shortcut and the terminal's key, ui.termkeys) hide and show the outline on
    the main image, the linked one and the 2x2 view's four; the menu's tick follows either; the sheet has H's row."""
    from PySide6 import QtCore

    from explorer.ui import termkeys as T
    from explorer.ui.glass import look_accent

    w = window
    w.set_grid(True)
    assert spin(qapp, lambda: w.grid is not None and w.grid.isVisible())
    mo, entry = w.mask_outlines, mask_entry(w)
    assert entry is not None and entry.isCheckable() and entry.isChecked()
    assert ("H", "mask: hide · show") in [(k, what) for k, what, _b in w.action_registry.rows]
    assert "mask: hide · show" in w.sheet.text()
    w.set_grid(False)
    qapp.processEvents()
    colour = look_accent(w.look)

    def state(how):
        qapp.processEvents()
        n = accent_pixels(w, colour)
        shown = [it.isVisible() for it in mo.items]
        print(f"{how}: menu ticked {entry.isChecked()}, items shown {shown}, pixels in the accent {n}")
        return entry.isChecked(), set(shown), n

    on = state("at start")
    assert on[:2] == (True, {True}) and on[2] > 50 and len(mo.items) == 6
    terminal_h = T.actions_of(w)[T.combined(QtCore.Qt.Key.Key_H, QtCore.Qt.KeyboardModifier.NoModifier)]
    for how, act, ticked in (("menu, off", lambda: entry.trigger(), False), ("menu, on", lambda: entry.trigger(), True),
                             ("H, off", lambda: fire(w, "H"), False), ("H, on", lambda: fire(w, "H"), True),
                             ("terminal h, off", terminal_h, False), ("menu, on again", lambda: entry.trigger(), True)):
        act()
        got = state(how)
        assert got[:2] == (ticked, {ticked}) and mo.visible == ticked
        assert got[2] > 50 if ticked else got[2] == 0


def test_hidden_t_steps_read_nothing_and_shown_it_is_at_the_t_then(qapp, window, cubes, monkeypatch):
    """Hidden, four steps in t call nothing of the mask (its frame, its kept outlines, its reading, its outline); shown
    again two t from the one hidden, the outline drawn is that t's, read then (the kept ones emptied first), never
    the frame hidden."""
    from explorer.data.mask import outline

    w = window
    mo = w.mask_outlines
    assert spin(qapp, lambda: not mo._busy)
    calls: list[str] = []
    for name in ("frame_at", "kept", "outline", "inside"):
        real = getattr(mo.mask, name)
        monkeypatch.setattr(mo.mask, name, lambda *a, name=name, real=real: (calls.append(name), real(*a))[1])
    hidden = mo.frame
    end = (w.session.state.t + 2) % SHAPE[0]
    w.set_mask_shown(False)
    for t in (end + 1, end + 3, end + 2, end):
        w.session.set_index("t", t % SHAPE[0])
        qapp.processEvents()
    assert spin(qapp, lambda: not mo._busy)
    print("hidden, the mask's calls over four t steps:", calls, "| frame drawn:", mo.frame)
    assert calls == [] and mo.frame == hidden != end
    mo.mask._kept.clear()
    w.set_mask_shown(True)
    first = drawn(w)[0]
    assert len(first) == 0 or np.array_equal(first, outline(cubes["boxes"][end] >= 1))
    assert spin(qapp, lambda: mo.frame == end)
    qapp.processEvents()
    print(f"shown at t {end}: segments at once", len(first), "| calls", sorted(set(calls)), "| frame drawn", mo.frame)
    assert "inside" in calls and w.mask_action.isChecked()
    for g in drawn(w):
        np.testing.assert_array_equal(g, outline(cubes["boxes"][end] >= 1))


def test_without_a_mask_no_entry_no_h_and_no_row(qapp, cubes):
    from PySide6 import QtCore, QtGui

    from explorer.data.dataset import Dataset
    from explorer.ui import termkeys as T
    from explorer.ui.shell import Shell

    ds = Dataset.open(cubes["main"])
    w = Shell(ds)
    w.resize(900, 600)
    w.show()
    try:
        assert spin(qapp, lambda: w.first_image_s is not None)
        h = QtGui.QKeySequence("H")
        keys = [k for k, _w, _b in w.action_registry.rows]
        bound = [sc for sc in w.findChildren(QtGui.QShortcut) if sc.key() == h]
        term = T.combined(QtCore.Qt.Key.Key_H, QtCore.Qt.KeyboardModifier.NoModifier) in T.actions_of(w)
        print("entry:", mask_entry(w), "| H shortcuts:", len(bound), "| terminal H:", term, "| H row:", "H" in keys)
        assert mask_entry(w) is None and w.mask_action is None and not bound and not term and "H" not in keys
        assert "mask" not in w.sheet.text()
        w.set_mask_shown(False)                         # what H would call: nothing to do
        assert w.mask_outlines is None
    finally:
        w.close()
        ds.close()

"""Gamma in the window, offscreen: G / Shift+G / Ctrl+G act on the image under the pointer (its cube, its Stokes; a
panel of the 2x2 view: that panel's Stokes), its image is reduced through the gamma table, its lambda-t and the slit's
slices of that cube follow, the colour key says it, and gamma back to 1 gives today's bytes again."""
import time

import numpy as np
import pytest

from explorer.testing import synth

SHAPE = (3, 4, 5, 90, 80)


def spin(qapp, until, timeout=10.0):
    end = time.perf_counter() + timeout
    while not until() and time.perf_counter() < end:
        qapp.processEvents()
        time.sleep(0.002)
    return until()


@pytest.fixture(scope="module")
def cubes(tmp_path_factory):
    d = tmp_path_factory.mktemp("gamma")
    main = synth.write_dataset(d, "main", shape=SHAPE, icube=False)["im"]
    other = synth.write_dataset(d, "other", shape=(SHAPE[0], SHAPE[1], 7, SHAPE[3], SHAPE[4]), seed=4, icube=False,
                                sp=False)["im"]
    return main, other


@pytest.fixture
def window(qapp, cubes):
    from explorer.data.dataset import Dataset
    from explorer.ui.shell import Shell

    ds = Dataset.open(cubes[0])
    linked = [Dataset.open(cubes[1], executors=ds.executors)]
    w = Shell(ds, linked=linked)
    w.resize(1400, 600)
    w.show()
    assert spin(qapp, lambda: w.first_image_s is not None and "lambda_t" in w.last
                and all(c.scheduler.img is not None for c in w.linked))
    yield w, qapp
    w.close()
    for d in linked:
        d.close()
    ds.close()


def fire(w, seq):
    from PySide6 import QtGui

    ks = QtGui.QKeySequence(seq)
    hits = [sc for sc in w.findChildren(QtGui.QShortcut) if sc.key() == ks]
    assert len(hits) == 1, seq
    hits[0].activated.emit()


def shown(view):
    return None if view.img.image is None else view.img.image.copy()


def test_the_keys_act_on_the_image_under_the_pointer_and_gamma_1_gives_today_s_bytes(window):
    w, qapp = window
    s = w.session
    s.set_index("s", 1)                                 # Q on the main cube (the linked one follows: same Stokes)
    assert spin(qapp, lambda: w.main.scheduler.img_idx is not None and w.main.scheduler.img_idx[1] == 1
                and w.linked[0].scheduler.img is not None)
    qapp.processEvents()
    before, other_before = shown(w.view), shown(w.linked[0].view)
    w.main._hover(10, 10)
    fire(w, "G")
    qapp.processEvents()
    assert s.gamma(0, 1) == pytest.approx(10 ** -0.1)
    assert (s.gamma(0, 0), s.gamma(0, 3), s.gamma(1, 1)) == (1.0, 1.0, 1.0)
    assert not np.array_equal(shown(w.view), before)
    assert np.array_equal(shown(w.linked[0].view), other_before)       # the other cube's image as it was
    assert "γ = 0.79" in w.statusBar().currentMessage()
    fire(w, "Shift+G")
    fire(w, "Shift+G")
    assert s.gamma(0, 1) == pytest.approx(10 ** 0.1)
    fire(w, "Ctrl+G")
    qapp.processEvents()
    assert s.gamma(0, 1) == 1.0 and s.state.gamma == ()
    assert np.array_equal(shown(w.view), before)       # gamma 1: the same bytes as before any gamma
    w.linked[0]._hover(10, 10)                          # now over the linked cube's image
    fire(w, "G")
    qapp.processEvents()
    assert s.gamma(1, 1) == pytest.approx(10 ** -0.1) and s.gamma(0, 1) == 1.0
    assert not np.array_equal(shown(w.linked[0].view), other_before)
    assert np.array_equal(shown(w.view), before)


def test_the_image_is_reduced_through_the_table_of_its_stokes_symmetric_for_v(window):
    from explorer.core.levels import symmetric_levels
    from explorer.data.kernels import gamma_table, reduce_u8_table_serial

    w, qapp = window
    w.pick_stokes(3)
    assert spin(qapp, lambda: w.main.scheduler.img_idx is not None and w.main.scheduler.img_idx[1] == 3)
    w.session.set_gamma(0, 3, 0.5)
    qapp.processEvents()
    v = w.view
    lo, hi = v._lim
    assert symmetric_levels(v._lim)
    y0, y1, x0, x1 = v.last_render["region"]
    f, (h, wd) = v.last_render["factor"], v.last_render["shape"]
    want = np.empty((h, wd), np.uint8)
    reduce_u8_table_serial(v._full, y0, x0, f, lo, hi, gamma_table(0.5, True), want)
    assert np.array_equal(shown(v), want)


def test_lambda_t_and_the_slit_follow_their_cube_s_gamma_at_the_stokes_they_show(window):
    from explorer.core.levels import gamma_panel

    w, qapp = window
    w.session.set_index("s", 2)
    w.main._hover(30, 30)
    assert spin(qapp, lambda: "lambda_t" in w.last and w.last["lambda_t"][2] == 2)
    w.session.store.set(path=((10.5, 10.5), (60.5, 70.5)))
    w.session.show("slit")
    assert spin(qapp, lambda: w.slit_panel._raw[0][0] is not None and w.slit_panel._raw[1][0] is not None)
    lt, _p, _s, lv = w.last["lambda_t"]
    assert np.array_equal(w.lambda_t.img.image, lt, equal_nan=True)            # gamma 1: as the core gave it
    w.session.set_gamma(0, 2, 0.5)
    qapp.processEvents()
    want, _ = gamma_panel(lt, lv, 0.5)
    assert np.array_equal(w.lambda_t.img.image, want, equal_nan=True)
    (ts, tlv), (sl, slv) = w.slit_panel._raw
    assert np.array_equal(w.slit_panel.ts_img.image, gamma_panel(ts, tlv, 0.5)[0], equal_nan=True)
    assert np.array_equal(w.slit_panel.sl_img.image, gamma_panel(sl, slv, 0.5)[0], equal_nan=True)
    w.session.set_gamma(0, 1, 2.0)                      # another Stokes's: nothing of these changes
    qapp.processEvents()
    assert np.array_equal(w.lambda_t.img.image, want, equal_nan=True)
    w.session.set_gamma(0, 2, 1.0)
    qapp.processEvents()
    assert np.array_equal(w.lambda_t.img.image, lt, equal_nan=True)
    assert np.array_equal(w.slit_panel.ts_img.image, ts, equal_nan=True)


def test_a_panel_of_the_2x2_view_is_its_stokes_and_the_key_at_rest_never_says_gamma(window):
    from explorer.look import get_look

    w, qapp = window
    w.set_grid(True)
    assert spin(qapp, lambda: all(v._full is not None for v in w.grid.views))
    w.grid._hovered(3, 20, 20)                          # the mouse over the V panel
    fire(w, "G")
    qapp.processEvents()
    assert w.session.gamma(0, 3) == pytest.approx(10 ** -0.1) and w.session.gamma(0, w.session.state.s) == 1.0
    assert w.grid.views[3]._gamma == pytest.approx(10 ** -0.1) and w.grid.views[0]._gamma == 1.0
    w.set_grid(False)
    w.set_look(get_look("modern"))
    w.session.set_gamma(0, w.session.state.s, 0.5)
    qapp.processEvents()
    assert "γ" not in w.colour_key.state[0]            # the hot key only (the user, 2026-10-11)
    w.session.set_gamma(0, w.session.state.s, 1.0)
    qapp.processEvents()
    assert "γ" not in w.colour_key.state[0]


def test_the_keys_are_on_the_sheet(window):
    w, _ = window
    keys = [k for k, _what, _b in w.action_registry.rows]
    assert "G  ⇧G" in keys and any(k.endswith("G") and k != "G  ⇧G" for k in keys)


def test_in_glass_the_key_at_rest_does_not_say_the_new_gamma(window):
    """Gamma is written on the hot key only (the user, 2026-10-11: "only when I pass the mouse over the new panel"):
    G in glass leaves the key at rest as it was, main and linked."""
    from explorer.look import get_look

    w, qapp = window
    w.set_look(get_look("glass"))
    spin(qapp, lambda: False, timeout=0.4)
    assert not w.statusBar().isVisible()
    w.main._hover(10, 10)
    fire(w, "G")
    qapp.processEvents()
    main_note = w.main.key.note
    w.linked[0]._hover(10, 10)
    fire(w, "Shift+G")
    qapp.processEvents()
    print("glass: main key", main_note, "linked key", w.linked[0].key.note)
    assert main_note is None and w.linked[0].key.note is None
    assert w.session.gamma(0, w.session.state.s) == pytest.approx(10 ** -0.1)
    w.set_look(get_look("classic"))
    spin(qapp, lambda: False, timeout=0.4)              # glass's deferred calls done before the window closes

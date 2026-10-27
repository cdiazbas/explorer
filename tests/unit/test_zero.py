"""Key Z (the author's decision of 2026-10-27): a signed plane between -m..m and limits of its own on each side of 0,
0 the map's middle in both, each half stretched to its own limit; a plane that is not signed stays as it is. The
image, the lambda-t and the slit's slices, the keys, the layout. Files built as test_bifrost's (the real header),
small. Each test prints what it measured."""
import numpy as np
import pytest
from test_bifrost import NX, NY, NZ, bifrost, open_window, spin


@pytest.fixture(scope="module")
def files(tmp_path_factory):
    d = tmp_path_factory.mktemp("zero")
    z, y, x = np.mgrid[0:NZ, 0:NY, 0:NX]
    # mostly positive, a negative tail: -m..m and its own sides differ
    return {"bz": bifrost(d / "BIFROST_en024048_hion_bz_385.fits", "bz", True,
                          0.08 + 0.3 * np.sin((x + y) / 5.0) * np.exp(-z / 9.0)),
            "lgtg": bifrost(d / "BIFROST_en024048_hion_lgtg_385.fits")}


def test_the_image_table_puts_0_at_the_middle_byte():
    """kernels.centred_table: 0's place is byte 128, the limits 1 and 255, rising; with 0 at the table's middle, the
    symmetric gamma table to the byte (Q U V drawn as before)."""
    from explorer.data.kernels import TABLE_N, centred_table, gamma_table

    same = [np.array_equal(centred_table(g, (TABLE_N - 1) // 2), gamma_table(g, True)) for g in (0.5, 1.0, 2.0)]
    t = centred_table(0.7, 20000)
    print("as symmetric", same, "| ends", t[0], t[-1], "| at 0", t[20000])
    assert all(same) and (t[0], t[-1], t[20000]) == (1, 255, 128)
    assert np.all(np.diff(t.astype(int)) >= 0)


def test_a_panel_and_a_key_bend_each_side_by_its_own_limit():
    """levels.gamma_panel (lambda-t, slit) and scalekey.transfer (the open key): with limits of its own on each side
    (-1, 3), -1 -> -1 and 0, 0 -> 0 and 0.5, 3 -> 1 and 1, at gamma 1 too; -m..m and an unsigned plane as before."""
    from explorer.core.levels import gamma_panel
    from explorer.ui.scalekey import transfer

    a = np.array([-1.0, -0.5, 0.0, 1.5, 3.0], np.float32)
    got, lv = gamma_panel(a, (-1.0, 3.0), 1.0, centred=True)
    t = transfer(a, -1.0, 3.0, 1.0, True)
    print("panel", got.tolist(), lv, "| key", t.tolist())
    np.testing.assert_allclose(got, [-1, -0.5, 0, 0.5, 1]) and lv == (-1.0, 1.0)
    np.testing.assert_allclose(t, [0, 0.25, 0.5, 0.75, 1])
    assert gamma_panel(a, (-3.0, 3.0), 1.0, centred=True)[0] is a        # -m..m at gamma 1: as given
    assert gamma_panel(a, (-1.0, 3.0), 1.0, centred=False)[0] is a       # not signed: as given
    np.testing.assert_allclose(transfer(a, -3.0, 3.0, 1.0, True), 0.5 + a / 6)


def test_the_session_keeps_z_per_cube_and_plane(files):
    """Session.set_zero: a signed plane's levels of its own on each side (symmetric False, centred True), a fixed
    pair kept as given; an unsigned plane refused (False) and nothing set."""
    from explorer.core.loop import ManualLoop
    from explorer.core.session import Session
    from explorer.data.dataset import Dataset

    ds = Dataset.open(files["bz"])
    try:
        s = Session(ManualLoop(), ds)
        assert s.symmetric(0, 0) and s.centred(0, 0) and not s.zero(0, 0)
        assert s.set_zero(0, 0, True) and s.zero(0, 0) and not s.symmetric(0, 0) and s.centred(0, 0)
        s.set_scale(0, 0, "fixed", -0.1, 0.4)
        print("fixed", s.scale(0, 0), "| zero", s.state.zero)
        assert s.scale(0, 0) == ("fixed", -0.1, 0.4)
        s.set_zero(0, 0, False)
        s.set_scale(0, 0, "fixed", -0.1, 0.4)
        assert s.scale(0, 0) == ("fixed", -0.4, 0.4) and s.state.zero == ()
    finally:
        ds.close()
    ds = Dataset.open(files["lgtg"])
    try:
        s = Session(ManualLoop(), ds)
        assert s.set_zero(0, 0, True) is False and s.state.zero == () and not s.centred(0, 0)
    finally:
        ds.close()


def blocks(view):
    """The image's frame as drawn last (its region and factor): each drawn pixel's mean, and its byte."""
    r = view.last_render
    y0, y1, x0, x1 = r["region"]
    f, (h, w) = r["factor"], r["shape"]
    a = view._full[y0:y0 + h * f, x0:x0 + w * f].reshape(h, f, w, f).mean(axis=(1, 3))
    return a, view.img.image.astype(int)


def test_z_gives_bz_its_own_sides_with_0_at_the_map_s_middle(qapp, files):
    """bz alone: -m..m at start; Z, levels of its own on each side (lo != -hi), every drawn pixel below 0 under byte
    128 and above 0 over it, the lambda-t's levels its own too; Z again, -m..m. Before: no Z."""
    w, close = open_window(qapp, files["bz"])
    try:
        w.session.set_index("l", 0)                     # the bottom: both signs (higher up, positive alone)
        assert spin(qapp, lambda: w.main.scheduler.img_idx is not None and w.main.scheduler.img_idx[-1] == 0)
        for _ in range(20):
            qapp.processEvents()
        lo0, hi0 = w.view._lim
        assert np.isclose(lo0, -hi0)
        w.toggle_zero()
        assert spin(qapp, lambda: not np.isclose(w.view._lim[0], -w.view._lim[1]))
        qapp.processEvents()
        lo, hi = w.view._lim
        a, b = blocks(w.view)
        neg, pos = b[a < 0], b[a > 0]
        print(f"Z: {lo0:.4f}..{hi0:.4f} -> {lo:.4f}..{hi:.4f}; below 0 max byte {neg.max()}, above 0 min byte "
              f"{pos.min()} ({neg.size} and {pos.size} pixels) | {w.statusBar().currentMessage()!r}")
        assert lo < 0 < hi and neg.size and pos.size and neg.max() <= 128 <= pos.min()
        assert "each side of 0" in w.statusBar().currentMessage()
        assert w.session.state.zero == ((0, 0),)
        w.toggle_zero()
        assert spin(qapp, lambda: np.isclose(w.view._lim[0], -w.view._lim[1]))
        assert w.session.state.zero == ()
    finally:
        close()


def test_z_leaves_an_unsigned_plane_as_it_is(qapp, files):
    """log10(tg): Z changes nothing, and the status line says why."""
    w, close = open_window(qapp, files["lgtg"])
    try:
        before = w.view._lim
        w.toggle_zero()
        for _ in range(20):
            qapp.processEvents()
        print(w.view._lim, repr(w.statusBar().currentMessage()))
        assert w.session.state.zero == () and w.view._lim == before
        assert "not signed" in w.statusBar().currentMessage()
    finally:
        close()


def test_the_layout_keeps_z_and_reads_what_it_kept_before(qapp, files, tmp_path):
    """scale_settings has Z's planes; LayoutStore keeps them (" zero" after the four words) and reads an entry of
    four words as before Z; restore_scale gives Z back. Z is on the ? sheet."""
    from PySide6 import QtCore

    from explorer.ui.layout import LayoutStore

    path = str(tmp_path / "layout.ini")
    w, close = open_window(qapp, files["bz"])
    try:
        assert any(r[0].endswith("· Z") for r in w.key_table())             # in C's row
        w.toggle_zero()
        kept = w.scale_settings()
        LayoutStore("x11", path).save_scale(kept)
    finally:
        close()
    back = LayoutStore("bridge", path).scale()
    print("kept", kept, "| back", back)
    assert back == kept and list(back.values())[0][4] is True
    st = QtCore.QSettings(path, QtCore.QSettings.Format.IniFormat)
    key = [k for k in st.allKeys() if k.startswith(LayoutStore.SCALE_GROUP)][0]
    st.setValue(key, "p05 0.0 0.0 0.5")                                  # as kept before Z
    st.sync()
    assert list(LayoutStore("bridge", path).scale().values())[0] == ("p05", 0.0, 0.0, 0.5, False)
    w, close = open_window(qapp, files["bz"])
    try:
        w.restore_scale(back)
        assert w.session.zero(0, 0)
    finally:
        close()

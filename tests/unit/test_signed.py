"""Signed quantities and the colour key's name (the author's decisions of 2026-10-27, points 31 and 32), offscreen:
a plane whose quantity is signed about 0 (a Bifrost field component, a Blos map) has its levels symmetric about 0
and the diverging maps, as Q U V; one of log₁₀(tg) does not. The key of a cube of one plane says what it shows with
its unit, never the unit alone. Files built as test_bifrost's (the real header), small. Each test prints what it
measured."""
import numpy as np
import pytest
from test_bifrost import NX, NY, NZ, bifrost, open_window, spin
from test_snapshot import snapshot


@pytest.fixture(scope="module")
def files(tmp_path_factory):
    d = tmp_path_factory.mktemp("signed")
    z, y, x = np.mgrid[0:NZ, 0:NY, 0:NX]
    return {"lgtg": bifrost(d / "BIFROST_en024048_hion_lgtg_385.fits"),
            # mostly positive: its own levels would not be symmetric
            "bz": bifrost(d / "BIFROST_en024048_hion_bz_385.fits", "bz", True,
                          0.08 + 0.3 * np.sin((x + y) / 5.0) * np.exp(-z / 9.0)),
            "six": snapshot(tmp_path_factory.mktemp("signed6"))}


def test_a_quantity_is_signed_by_its_name():
    """SIGNED: the components of a vector and the line-of-sight field and velocities; not a modulus, an angle, a log
    or a temperature."""
    from explorer.data.axes import is_signed

    yes = ["bz", "bx", "Blos", "Vlos", "ux", "Br", "Doppler", " BZ "]
    no = ["log₁₀(tg)", "Bstr", "Binc", "Bazi", "Btr", "Intensity", "T", "Quantity", "tg", "b"]
    print("signed", [n for n in yes + no if is_signed(n)])
    assert all(is_signed(n) for n in yes) and not any(is_signed(n) for n in no)


def test_the_roles_say_which_planes_are_signed(files, tmp_path):
    """axes.read: a cube of one plane by what it shows (names.quantity: BTYPE "bz", a Blos map by its file name); a
    snapshot's variables each by its name; Stokes as before (Q U V, never I). Before: only Q U V."""
    from explorer.data import axes
    from explorer.data.dataset import Dataset

    got = {}
    for k in ("bz", "lgtg"):
        ds = Dataset.open(files[k])
        got[k] = (ds.roles.signs, axes.signed(ds.roles, 0))
        ds.close()
    ds = Dataset.open(None, variables=files["six"])
    got["six"] = tuple(axes.signed(ds.roles, s) for s in range(ds.roles.ns))
    ds.close()
    print(got)
    assert got["bz"] == ((True,), True) and got["lgtg"] == ((False,), False)
    assert got["six"] == (True, True, True, False, False, False)          # bx by bz, then the logs
    r = axes.Roles(0, 1, 2, 5, 4, 7)
    assert [axes.signed(r, s) for s in range(4)] == [False, True, True, True]


def test_a_signed_plane_wears_the_diverging_maps():
    """ColormapRegistry: per plane, the signed ones step through the diverging maps (Q U V's), the others the
    sequential ones (I's); a bool keeps its meaning (Q U V after the first)."""
    from explorer.look import colormaps as cm

    reg = cm.ColormapRegistry(3, colour=True, signed=(True, False, True))
    got = [reg.names_for(s) is cm.SEQUENTIAL for s in range(3)]
    print("sequential", got)
    assert got == [False, True, False]
    assert [cm.ColormapRegistry(4, signed=True).names_for(s) is cm.SEQUENTIAL for s in range(4)] == \
        [True, False, False, False]


def test_a_signed_cube_s_image_and_key_are_centred_on_0(qapp, files):
    """bz alone in the window: its image's levels -m..m (mostly positive values: its own would not be), its key
    symmetric, named "bz [T]". Before: lo != -hi."""
    w, close = open_window(qapp, files["bz"])
    try:
        assert spin(qapp, lambda: w.colour_key is not None and w.colour_key.state is not None)
        lo, hi = w.view._lim
        print("bz levels", (round(lo, 4), round(hi, 4)), "| key symmetric", w.colour_key.symmetric())
        assert np.isclose(lo, -hi) and hi > 0 and w.colour_key.symmetric()
    finally:
        close()


def test_the_key_of_one_plane_names_its_quantity(qapp, files):
    """A cube of one plane: its key's top row is what it shows with its unit ("log₁₀(tg)   [K]"), as the status line
    names it. Before: "[K]" alone."""
    from PySide6 import QtGui

    w, close = open_window(qapp, files["lgtg"])
    try:
        assert spin(qapp, lambda: w.colour_key is not None and w.colour_key.state is not None)
        key = w.colour_key
        fm = QtGui.QFontMetrics(QtGui.QFont())
        title = key.title(fm, 1e4)
        print("key title", repr(title), "| name", repr(key.state[0]))
        assert key.state[0] == "log₁₀(tg)" and title.startswith("log₁₀(tg)") and "K]" in title
    finally:
        close()

"""A Bifrost snapshot's variables, a file each, as one cube with a variable selector (the author's "A", 2026-10-27),
offscreen: detected only when the files are one snapshot's (Bifrost, one shape, OBJECT and ISNAP, the same heights,
each its own BTYPE); each variable a plane with its name, unit, levels and γ; z moves them all; the profile panel one
plot per variable; side by side three columns for six. Files built as test_bifrost's (the real header), small. Each
test prints what it measured."""
import time

import numpy as np
import pytest
from astropy.io import fits
from test_bifrost import NX, NY, NZ, Z, bifrost

z_, y_, x_ = np.mgrid[0:NZ, 0:NY, 0:NX]
# the six of en024048_hion snapshot 385, each in its own range and unit
VARS = {"bx": ("bx", True, 0.2 * np.sin(x_ / 4.0) * np.exp(-z_ / 12.0)),
        "by": ("by", True, 0.1 * np.cos(y_ / 3.0) + 0.01 * z_ / NZ),
        "bz": ("bz", True, 0.08 + 0.3 * np.sin((x_ + y_) / 5.0) * np.exp(-z_ / 9.0)),
        "lgne": ("lg(ne)", "m^(-3)", 21.0 - 4.0 * z_ / NZ + 0.1 * np.sin(x_ / 3.0)),
        "lgp": ("lg(p)", "N m^(-2)", 4.0 - 5.0 * z_ / NZ + 0.05 * np.cos(y_ / 2.0)),
        "lgtg": ("lg(tg)", "K", 3.6 + 2.5 * z_ / NZ + 0.05 * np.sin(x_ / 3.0) * np.cos(y_ / 4.0))}
NAMES = ["bx", "by", "bz", "log₁₀(ne)", "log₁₀(p)", "log₁₀(tg)"]
UNITS = ["T", "T", "T", "m^(-3)", "N m^(-2)", "K"]       # as the real files' BUNIT


def spin(qapp, until, timeout=10.0):
    end = time.perf_counter() + timeout
    while not until() and time.perf_counter() < end:
        qapp.processEvents()
        time.sleep(0.002)
    return until()


def snapshot(d, keys=tuple(VARS), **change):
    """The variables' files of one snapshot (ISNAP 385); change: {key: {card: value}} to make one differ."""
    out = []
    for k in keys:
        b, u, a = VARS[k]
        p = bifrost(d / f"BIFROST_en024048_hion_{k}_385.fits", b, u, a)
        with fits.open(p, mode="update") as h:
            h[0].header["ISNAP"] = 385
            for card, v in change.get(k, {}).items():
                h[0].header[card] = v
        out.append(p)
    return out


@pytest.fixture(scope="module")
def six(tmp_path_factory):
    return snapshot(tmp_path_factory.mktemp("snap6"))


def test_one_snapshot_s_variables_are_detected_and_nothing_else(six, tmp_path):
    """Detection: six Bifrost files of one snapshot are one cube (6, z, y, x); not when one is of another snapshot
    (ISNAP), another run (OBJECT), not Bifrost (INSTRUME), the same variable twice (BTYPE), another shape, or other
    heights. Before: no such cube (the first file alone, the others refused for linking)."""
    from explorer.data.formats import variables_layout

    lay = variables_layout(six)
    print("six:", lay.shape if lay else None, lay.btypes if lay else None)
    assert lay is not None and lay.shape == (6, NZ, NY, NX) and lay.kind == "variables"
    no = {}
    for what, change in (("ISNAP", {"bz": {"ISNAP": 386}}), ("OBJECT", {"bz": {"OBJECT": "other_run"}}),
                         ("INSTRUME", {"bz": {"INSTRUME": "MURaM"}}), ("BTYPE", {"bz": {"BTYPE": "bx"}})):
        d = tmp_path / what
        d.mkdir()
        no[what] = variables_layout(snapshot(d, ("bx", "bz", "lgtg"), **change))
    d = tmp_path / "shape"
    d.mkdir()
    other = bifrost(d / "BIFROST_en024048_hion_lgp_385.fits", "lg(p)", "N m^(-2)", np.zeros((NZ, NY, NX + 2)))
    no["shape"] = variables_layout([*snapshot(d, ("bx", "lgtg")), other])
    d = tmp_path / "heights"
    d.mkdir()
    a, b = snapshot(d, ("bx", "lgtg"))
    with fits.open(b, mode="update") as h:
        h[1].data = h[1].data + 0.5
    no["heights"] = variables_layout([a, b])
    no["one file"] = variables_layout(six[:1])
    print("not one snapshot:", no)
    assert all(v is None for v in no.values())


def test_each_variable_is_a_plane_with_its_name_unit_and_frames(six):
    """Names and units per plane (log₁₀(x), tesla for BUNIT = T); frame (v, z) is file v's frame z, a profile file
    v's values along z, read where they are. Before: no variables cube."""
    from explorer.data.dataset import Dataset

    ds = Dataset.open(None, variables=six)
    try:
        r = ds.roles
        print(r, ds.axes.plane_units)
        assert (r.t, r.s, r.l, r.ns, r.nl) == (None, 0, 1, 6, NZ) and list(r.planes) == NAMES
        assert list(ds.axes.plane_units) == UNITS and ds.pixel is None
        np.testing.assert_allclose(ds.axes.lead_coord(1)[0], Z, rtol=1e-6)
        for v, k in enumerate(VARS):
            np.testing.assert_allclose(ds.image((v, 7)).result(), VARS[k][2][7], rtol=1e-6)
            np.testing.assert_allclose(ds.read_series(5, 6, (v, 0), [1]), VARS[k][2][:, 5, 6], rtol=1e-6)
    finally:
        ds.close()


def open_window(qapp, paths):
    from PySide6 import QtGui

    from explorer.data.dataset import Dataset
    from explorer.ui import style
    from explorer.ui.shell import Shell

    name, pal = qapp.style().name(), QtGui.QPalette(qapp.palette())
    style.apply_theme(qapp, "dark")
    ds = Dataset.open(None, variables=paths)
    w = Shell(ds)
    w.resize(1200, 760)
    w.show()
    assert spin(qapp, lambda: w.first_image_s is not None)
    qapp.processEvents()

    def close():
        from PySide6 import QtWidgets

        w.close()
        ds.close()
        qapp.setStyle(QtWidgets.QStyleFactory.create(name or "Fusion"))
        qapp.setPalette(pal)
        qapp.setProperty("explorer_light", False)
    return w, close


def test_the_window_picks_a_variable_and_z_moves_them_all(qapp, six):
    """The toolbar picks the variable by name (keys 1-6, All); z moves every one; each image its own levels (bz's not
    symmetric about 0 as Q's), its own scale and γ; the image and its key say which and in what unit; the status
    line the variable's value with its unit. Before: no variables cube."""
    from explorer.data.axes import unit_text

    w, close = open_window(qapp, six)
    try:
        items = [w.nav.stokes.itemText(i) for i in range(w.nav.stokes.count())]
        keys = [r for r in w.key_table() if r[0].startswith("1–")]
        print("toolbar", items, "| keys", [r[:2] for r in keys])
        assert items == [*NAMES, "All"] and keys and keys[0][0] == "1–6 · 7"
        w.session.set_index("l", 9)
        w.session.hover(5, 6)
        got = {}
        for v, k in enumerate(VARS):
            w.pick_stokes(v)
            assert spin(qapp, lambda v=v: w.main.scheduler.img_idx == (v, 9))
            qapp.processEvents()
            np.testing.assert_allclose(w.main.scheduler.img, VARS[k][2][9], rtol=1e-6)
            got[k] = (w.view.stokes.toPlainText(), w.main.key.unit, tuple(round(x, 3) for x in w.view._lim),
                      w.status.text().split("   ·   ")[-1])
            print(k, got[k])
            assert got[k][0] == NAMES[v] and got[k][1] == unit_text(UNITS[v])
            assert got[k][3].startswith(f"{NAMES[v]} ")
        lo, hi = got["bz"][2]
        assert not np.isclose(lo, -hi)                  # its own levels, not Q's -m..m
        w.session.set_scale(0, 5, "fixed", 4.0, 5.0)
        w.session.set_gamma(0, 3, 0.5)
        assert w.session.scale(0, 0)[0] != "fixed" and w.session.scale(0, 5)[0] == "fixed"
        assert w.session.gamma(0, 3) == 0.5 and w.session.gamma(0, 5) == 1.0
    finally:
        close()


def test_the_profile_panel_has_a_plot_per_variable_along_z(qapp, six):
    """The profile panel: one plot per variable, stacked, each its own y axis "name [unit]" and its own profile at
    the cursor, all along z [Mm] at the heights; "Profile". Side by side: three columns of two, each panel's key
    named by its variable in its unit. Before: no variables cube."""
    from explorer.data.axes import unit_text

    w, close = open_window(qapp, six)
    try:
        w.session.hover(5, 6)
        w.session.lock(True)
        sp = w.spectra
        want = [VARS[k][2][:, 5, 6] for k in VARS]       # the cursor's pixel's, once its read came
        assert spin(qapp, lambda: all(c.yData is not None and np.allclose(c.yData, wv, rtol=1e-5)
                                      for c, wv in zip(sp.curves, want, strict=True)))
        labels = [p.getAxis("left").labelText for p in sp.plots]
        rows = [p.vb.sceneBoundingRect().height() for p in sp.plots]
        print("dock", w.spec_dock.windowTitle(), "| labels", labels, "| plot heights", [round(h) for h in rows])
        assert w.spec_dock.windowTitle() == "Profile" and len(sp.plots) == 6
        assert labels == [f"{n} [{unit_text(u)}]" for n, u in zip(NAMES, UNITS, strict=True)]
        assert sp.plots[-1].getAxis("bottom").labelText == "z [Mm]"
        for v, k in enumerate(VARS):
            np.testing.assert_allclose(sp.curves[v].xData, Z, rtol=1e-6)
            np.testing.assert_allclose(sp.curves[v].yData, VARS[k][2][:, 5, 6], rtol=1e-5)
        w.set_grid(True)
        assert spin(qapp, lambda: all(v._full is not None for v in w.grid.views))
        qapp.processEvents()
        lay = w.grid.layout()
        cells = [lay.getItemPosition(lay.indexOf(v.widget))[:2] for v in w.grid.views]
        keys = [(k.state[0], k.unit) for k in w.grid_keys]
        print("grid cells", cells, "| keys", keys)
        assert cells == [(0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2)]
        assert keys == [(n, unit_text(u)) for n, u in zip(NAMES, UNITS, strict=True)]
    finally:
        close()

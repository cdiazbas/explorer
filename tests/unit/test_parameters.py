"""An inversion's parameters picked as Stokes are (ROADMAP E8.8), offscreen: the planes of an inversion's file are on
s (data.axes.by_parameter), never lambda; each is its own image with its own levels and gamma, none symmetric about
0; the main cube's are picked in the toolbar, named "Quantity 1", "Quantity 2", ...; a linked cube's own over its
image (ui.linked.PlanePicker). The cubes are built like the meinv LP (106 t x 3 planes, split by its per-pixel file)
and a headerless FITS [t, 3, y, x]. Each test prints what it measured."""
import time

import numpy as np
import pytest

from explorer.testing import synth

NT, NP, NY, NX = 5, 3, 48, 40


def spin(qapp, until, timeout=10.0):
    end = time.perf_counter() + timeout
    while not until() and time.perf_counter() < end:
        qapp.processEvents()
        time.sleep(0.002)
    return until()


def planes():
    """(t, parameter, y, x): parameter k around 1000 k, all positive, each plane its own range."""
    y, x = np.mgrid[0:NY, 0:NX]
    return np.stack([np.stack([1000.0 * k + 10 * (k + 1) * (np.sin(x / 5 + t) + 2) + y for k in range(NP)])
                     for t in range(NT)]).astype(np.float32)


def meinv_lp(d, a):
    """An LP pair as the meinv one: frames (t * ns + s) * nl + l with ns = 1, its NP planes where the layout puts
    lambda, and its per-pixel file (y, x, s, t, l) whose sizes split them."""
    nt, npar, ny, nx = a.shape
    im = synth.write_lp(str(d / "inversion_6173_im.fcube"), a.reshape(nt * npar, ny, nx), head="stokes=[I], ns=1 :  ")
    sp = a.transpose(2, 3, 0, 1)[:, :, None]                                    # (y, x, 1, t, l)
    head = f"stokes=[I], ns=1 :  datatype=4 (float), dims=3, nx={npar}, ny={nt}, nt={ny * nx}, endian=l"
    with open(d / "inversion_6173_sp.fcube", "wb") as f:
        f.write(head.encode().ljust(512, b"\0"))
        f.write(np.ascontiguousarray(sp).astype("<f4").tobytes())
    return im


@pytest.fixture(scope="module")
def cubes(tmp_path_factory):
    from astropy.io import fits

    d = tmp_path_factory.mktemp("parameters")
    a = planes()
    fits.PrimaryHDU(a.astype(">f4")).writeto(d / "WFA_inversion_8542.fits")
    spec = synth.write_dataset(d, "spec", shape=(NT, 4, 7, NY, NX), sp=False, icube=False)["im"]
    return {"lp": meinv_lp(d, a), "fits": str(d / "WFA_inversion_8542.fits"), "spec": spec, "a": a}


def open_window(qapp, main, linked=()):
    from explorer.data.dataset import Dataset
    from explorer.ui.shell import Shell

    ds = Dataset.open(main)
    lks = [Dataset.open(p, executors=ds.executors) for p in linked]
    w = Shell(ds, linked=lks)
    w.resize(1200, 640)
    w.show()
    assert spin(qapp, lambda: w.first_image_s is not None and all(c.scheduler.img is not None for c in w.linked))
    qapp.processEvents()

    def close():
        w.close()
        for x in lks:
            x.close()
        ds.close()
    return w, close


def test_an_inversion_s_planes_are_on_s_not_lambda(cubes):
    """The meinv-like LP (its pair layout calls the planes WAVE) and the headerless FITS [t, 3, y, x] ("default (t,
    lambda)"): their parameters on s, planes "parameter", no lambda; the LP's series from its frames, not its
    per-pixel file (whose blocks keep them along WAVE). --axes still says what the axes are. Before: l = 1 or 2,
    nl = 3, no s."""
    from explorer.data.dataset import Dataset

    for key, s in (("lp", 2), ("fits", 1)):
        ds = Dataset.open(cubes[key])
        try:
            r = ds.roles
            print(key, r, "pixel:", ds.pixel)
            assert (r.t, r.s, r.l, r.ns, r.planes, r.how) == (0, s, None, NP, "parameter", "inversion")
            assert ds.pixel is None
        finally:
            ds.close()
    ds = Dataset.open(cubes["fits"], axes="t,l")
    try:
        print("--axes t,l", ds.roles)
        assert (ds.roles.l, ds.roles.planes) == (1, "stokes")
    finally:
        ds.close()


def test_each_parameter_has_its_own_scale_none_symmetric(cubes):
    """Session.scale and Session.gamma per (cube, plane): a parameter's fixed levels stay as given (Q U V's are made
    symmetric about 0), another parameter keeps the default rule. Before: one plane only (s clipped to 0)."""
    from explorer.core.loop import ManualLoop
    from explorer.core.session import Session
    from explorer.data.dataset import Dataset

    ds = Dataset.open(cubes["lp"])
    try:
        sess = Session(ManualLoop(), ds)
        sess.set_scale(0, 1, "fixed", 1000.0, 1100.0)
        sess.set_gamma(0, 2, 0.5)
        got = [(sess.scale(0, s), sess.gamma(0, s)) for s in range(NP)]
        print(got)
        assert got[1] == (("fixed", 1000.0, 1100.0), 1.0)
        assert got[0][0][0] != "fixed" and got[2][1] == 0.5 and got[0][1] == 1.0
    finally:
        ds.close()


def test_the_main_cube_picks_its_parameters_as_stokes(qapp, cubes):
    """An inversion as the main cube: the toolbar picks "Quantity 1".."Quantity 3" (and All), the image says which,
    each plane comes with its own levels, none symmetric about 0; lambda-t is the cursor's value against t, named by
    the cube, the plane shown at its top left; the status line names the plane. Before: no plane to pick, the three
    side by side along "λ index" under one scale."""
    w, close = open_window(qapp, cubes["lp"])
    try:
        nav = w.nav
        items = [nav.stokes.itemText(i) for i in range(nav.stokes.count())] if nav.stokes is not None else None
        print("toolbar", items, "| lambda-t", type(w.lambda_t).__name__, w.lt_dock.windowTitle())
        assert items == ["Quantity 1", "Quantity 2", "Quantity 3", "All"]
        assert w.lt_dock.windowTitle() == "Fe I 617.3 inversion–t" and w.spectra is None
        a = cubes["a"]
        seen = {}
        for s in range(NP):
            w.pick_stokes(s)
            assert spin(qapp, lambda s=s: w.main.scheduler.img_idx is not None and w.main.scheduler.img_idx[2] == s)
            qapp.processEvents()
            seen[s] = (w.view.stokes.toPlainText(), tuple(float(v) for v in w.view._lim))
            w.session.hover(NY // 2, NX // 2)
            qapp.processEvents()
            print(s, seen[s], "| status", w.status.text().split("   ·   ")[-1])
            assert seen[s][0] == f"Quantity {s + 1}"
            lo, hi = seen[s][1]
            assert a[0, s].min() - 1 <= lo < hi <= a[0, s].max() + 1         # its own range: not -m..m
            assert w.status.text().split("   ·   ")[-1].startswith(f"Quantity {s + 1} ")
        assert len({v[1] for v in seen.values()}) == NP
    finally:
        close()


def test_a_linked_inversion_picks_its_own_parameters_over_its_image(qapp, cubes):
    """A Stokes cube with an inversion linked: the inversion's planes are its own (not the main cube's I Q U V),
    picked over its image's top left; a pick changes its plane, not the main cube's. Before: no picker, its planes
    along "λ index"."""
    w, close = open_window(qapp, cubes["spec"], [cubes["lp"]])
    try:
        lk = w.linked[0]
        assert lk.picker is not None
        texts = [b.text() for b in lk.picker.group.buttons()]
        print("picker", texts, "at", lk.picker.geometry().topLeft().toTuple())
        assert texts == ["Quantity 1", "Quantity 2", "Quantity 3"]
        lk.picker.group.button(2).click()
        assert spin(qapp, lambda: lk.scheduler.img_idx is not None and lk.scheduler.img_idx[2] == 2)
        print("linked s", w.session.member_state(lk.k).s, "main s", w.session.state.s)
        assert (w.session.member_state(lk.k).s, w.session.state.s) == (2, 0)
        assert lk.picker.group.checkedId() == 2
        # a plane not picked is legible over the image, in the window as grabbed: light ink on a dark card
        from PySide6 import QtCore, QtGui

        qapp.processEvents()
        b = lk.picker.group.button(0)
        img = w.grab(QtCore.QRect(b.mapTo(w, QtCore.QPoint(0, 0)), b.size())).toImage()
        img = img.convertToFormat(QtGui.QImage.Format.Format_RGB32)
        a = np.frombuffer(img.constBits(), np.uint8).reshape(img.height(), img.bytesPerLine() // 4, 4)
        lum = a[:, :img.width(), :3].mean(axis=2)
        print(f"unpicked plane: {np.mean(lum > 180):.3f} of its pixels light, median {np.median(lum):.0f}")
        assert np.mean(lum > 180) > 0.01 and np.median(lum) < 90
    finally:
        close()


def test_parameters_start_in_a_sequential_map():
    """Every parameter in a sequential map, as Stokes I (Q U V start in a diverging one with the colour part)."""
    from explorer.look.colormaps import SEQUENTIAL, ColormapRegistry

    cols = ColormapRegistry(NP, colour=True, signed=False)
    print(cols.maps)
    assert all(m == SEQUENTIAL[0] for m in cols.maps) and cols.names_for(1) == SEQUENTIAL


def test_in_the_2x2_view_each_panel_s_key_is_named_by_its_parameter(qapp, cubes):
    """An inversion side by side (All, key 4): each panel's key (ui.scalekey, the 2x2 view's names since E5.33) says
    its parameter, "Quantity 1" .. "Quantity 3", in its title, hot or not, wide or narrow (the short rule, not Q U V's
    |x| forms), and its scale menu's head; "Stokes" nowhere. Before (main a75208b): the planes along lambda, no 2x2
    view at all."""
    from PySide6 import QtGui, QtWidgets

    from explorer.ui import style
    from explorer.ui.scalekey import ScaleKey, scale_menu

    name, pal = qapp.style().name(), QtGui.QPalette(qapp.palette())
    style.apply_theme(qapp, "dark")
    w, close = open_window(qapp, cubes["lp"])
    try:
        w.set_grid(True)
        assert w.grid is not None and len(w.grid.views) == NP
        assert spin(qapp, lambda: all(v._full is not None for v in w.grid.views))
        spin(qapp, lambda: False, timeout=0.3)
        texts = []
        for s, v in enumerate(w.grid.views):
            keys = [k for k in v.widget.findChildren(ScaleKey) if k.isVisible()]
            assert len(keys) == 1, (s, keys)
            key = keys[0]
            f = QtGui.QFont(key.font())
            f.setPixelSize(key.TEXT_PX)
            fm = QtGui.QFontMetrics(f)
            wide, narrow = key.hot_title(fm, 1000.0), key.hot_title(fm, 10.0)
            menu = scale_menu(w, 0, s)
            head = menu.actions()[0].text()
            menu.close()
            got = (key.state[0], key.title(fm, 10.0), wide, narrow, head)
            print(s, got, "| levels", tuple(round(x, 1) for x in v._lim))
            texts += list(got)
            want = f"Quantity {s + 1}"
            assert key.state[0] == want and head == want
            assert wide.startswith(want) and wide.endswith("auto 1–99 %") and narrow == f"{want}   1–99 %"
            assert v._lim[0] >= 0                       # its own levels, not -m..m
        texts += [w.nav.stokes.itemText(i) for i in range(w.nav.stokes.count())] + [w.status.text()]
        assert not any("Stokes" in t for t in texts), texts
    finally:
        for m in w.findChildren(QtWidgets.QMenu):
            m.close()
        close()
        qapp.setStyle(QtWidgets.QStyleFactory.create(name or "Fusion"))
        qapp.setPalette(pal)
        qapp.setProperty("explorer_light", False)


def test_a_saved_slit_of_an_inversion_is_never_named_by_a_stokes():
    """The saved time slice's STOKES card and file name (data.slitfits.stokes_name): I Q U V only for the four
    Stokes, 's<k>' for an inversion's parameters even when it has four. Before: a 4-parameter inversion's plane 1
    saved as Q."""
    from explorer.data.slitfits import stokes_name

    got = [stokes_name(s, 4, "parameter") for s in range(4)], [stokes_name(s, 4) for s in range(4)]
    print(got)
    assert got == (["s0", "s1", "s2", "s3"], ["I", "Q", "U", "V"])

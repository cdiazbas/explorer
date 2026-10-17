"""The slit's time slice to a FITS file (data.slitfits, the save button in the slit's title): the writer read back
with astropy, HDU by HDU and card by card; a plain reader (fits.getdata) on every HDU; never over an existing file;
the button in the slit's title in each kind of title (ours, the Mac's stand-in under the macos style, glass's), after
the number and clear of the name, and not in lambda-t's; no key for it. Through the window offscreen, a click writes
the slice the slit tab in front shows (at the 100-step cap and at "all", per-pixel file or not), at the pixels of the
slit drawn, named after its cube, a linked cube's too. Each test prints what it measured."""
import datetime as dt
import os
import sys
import time
import warnings

import numpy as np
import pytest
from astropy.io import fits

from explorer.data.slits import slit_path, slit_pixels
from explorer.testing import synth

NT, NS, NL, NY, NX = 250, 4, 3, 24, 20
PTS = ((3.5, 6.5), (16.5, 18.5), (9.2, 21.7))
DRAWN = ((3.5, 6.5), (16.5, 18.5), (9.5, 21.5))       # PTS as the slit tool takes clicks: at pixel centres
WHEN = dt.datetime(2026, 10, 15, 9, 8, 7, tzinfo=dt.UTC)


def steps(nt, cap):
    """The steps the panel shows, computed here: the centres of `cap` equal bins of [0, nt)."""
    return np.floor((np.arange(cap) + 0.5) * nt / cap).astype(int)


def pixels(pts):
    return slit_pixels(slit_path(np.asarray(pts, float)), NY, NX)


@pytest.fixture(scope="module")
def cube(tmp_path_factory):
    d = synth.write_dataset(tmp_path_factory.mktemp("slitfits"), "c", shape=(NT, NS, NL, NY, NX), icube=False)
    return d["im"], fits.getdata(d["im"]).astype(np.float32)


# ---------------------------------------------------------------- the writer
def write(folder, axes, values, t, **kw):
    """write_time_slice with every warning an error: a card astropy cuts or wraps fails the test."""
    from explorer.data.slitfits import write_time_slice

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        return write_time_slice(folder, values, t=t, pix=pixels(PTS), pts=PTS, axes=axes,
                                **{"source": "/data/c_im.fits", "s": 2, "ns": NS, "l": 1, "nt": NT, "when": WHEN, **kw})


def test_the_file_read_back_hdu_by_hdu(tmp_path, cube):
    from explorer import __version__
    from explorer.data.axes import from_fits
    from explorer.data.slitfits import COMMENTS

    ax = from_fits(cube[0])
    iy, ix = pixels(PTS)
    t = steps(NT, 100)
    values = cube[1][t, 2, 1][:, iy, ix]
    values[:, 3] = np.nan                               # a point not read yet
    path = write(tmp_path, ax, values, t)
    print(path)
    with fits.open(path) as h:
        h.info()
        assert [x.name for x in h] == ["PRIMARY", "SLIT", "TIME", "VERTICES"]
        h.verify("exception")
        hd = h[0].header
        print(repr(hd))
        assert h[0].data.dtype == np.dtype(">f4") and h[0].data.shape == (100, len(ix))
        np.testing.assert_array_equal(h[0].data, values)
        assert (hd["NAXIS1"], hd["NAXIS2"]) == (len(ix), 100)
        want = {"DATE": "2026-10-15T09:08:07", "FILENAME": "c_im_slit_U_l01_20261015T090807.fits",
                "PARENT": "c_im.fits", "CREATOR": "explorer", "VERS_SW": __version__,
                "BUNIT": "W m^-2 Hz^-1 sr^-1", "STOKES": "U", "STOKESIX": 2, "LAMIDX": 1,
                "WAVELNTH": float(ax.lam_nm[1]), "WAVEUNIT": -9, "WAVEBAND": ax.line,
                "LAMBDA0": float(ax.lam0_nm), "DLAMBDA": float(ax.dlam_A(1)),
                "DATEREF": str(np.datetime64(ax.dateref, "ms")), "TIMESYS": "UTC", "NTCUBE": NT, "TSTEPS": "100",
                "IDXBASE": 0}
        assert {k: hd.get(k) for k in want} == want
        assert "/" not in hd["PARENT"] and "BTYPE" not in hd and "LONGSTRN" not in hd
        assert list(hd["COMMENT"]) == list(COMMENTS)  # each line whole, none wrapped

        slit = h["SLIT"].data
        path_xy = slit_path(np.asarray(PTS, float))
        assert slit.columns.names == ["X", "Y", "XPOS", "YPOS", "DIST"] and len(slit) == len(ix)
        np.testing.assert_array_equal(slit["X"], ix)
        np.testing.assert_array_equal(slit["Y"], iy)
        np.testing.assert_allclose(slit["XPOS"], path_xy[:, 0] - 0.5, rtol=0, atol=1e-12)
        np.testing.assert_allclose(slit["YPOS"], path_xy[:, 1] - 0.5, rtol=0, atol=1e-12)
        np.testing.assert_array_equal(np.floor(slit["XPOS"] + 0.5).astype(int), ix)
        d = slit["DIST"]
        np.testing.assert_array_equal(d[:-1], np.arange(len(d) - 1))    # a point every pixel along the curve
        assert len(d) - 2 < d[-1] <= len(d) - 1
        assert [h["SLIT"].header[f"TUNIT{i}"] for i in range(1, 6)] == ["pixel"] * 5

        tim = h["TIME"].data
        assert tim.columns.names == ["TINDEX", "TSEC", "UTC"] and len(tim) == 100
        np.testing.assert_array_equal(tim["TINDEX"], t)
        np.testing.assert_allclose(tim["TSEC"], ax.t_sec[t], rtol=0, atol=1e-9)
        assert list(tim["UTC"]) == [str(ax.utc(k)) for k in t]
        assert h["TIME"].header["DATEREF"] == hd["DATEREF"] and h["TIME"].header["TUNIT2"] == "s"
        print("TIME", tim[:2], "SLIT", slit[:2])

        vert = h["VERTICES"].data
        assert vert.columns.names == ["XPOS", "YPOS"]
        np.testing.assert_array_equal(np.c_[vert["XPOS"], vert["YPOS"]], np.asarray(PTS) - 0.5)


def test_a_plain_reader_sees_every_hdu(tmp_path, cube):
    from explorer.data.axes import from_fits

    path = write(tmp_path, from_fits(cube[0]), np.zeros((NT, len(pixels(PTS)[0])), np.float32), np.arange(NT))
    got = [fits.getdata(path, k) for k in range(4)] + [fits.getdata(path, n) for n in ("SLIT", "TIME", "VERTICES")]
    print([getattr(g, "shape", None) for g in got])
    assert got[0].shape == (NT, len(pixels(PTS)[0])) and fits.getheader(path)["TSTEPS"] == "all"
    assert [len(g) for g in got[1:4]] == [len(pixels(PTS)[0]), NT, len(PTS)]
    assert all(np.array_equal(a, b) for a, b in zip(got[1:4], got[4:], strict=True))


def test_never_over_a_file_and_a_long_sst_name(tmp_path, cube):
    from explorer.data.axes import from_fits

    ax, n = from_fits(cube[0]), len(pixels(PTS)[0])
    src = "/data/cube_6173_2020-08-07T08:22:14_scans=0-185_stokes_corrected_with_a_long_name_im.fits"
    paths = [write(tmp_path, ax, np.full((3, n), k, np.float32), [0, 1, 2], source=src) for k in range(3)]
    print(*paths, sep="\n")
    names = [p.rsplit("/", 1)[1] for p in paths]
    stem = "cube_6173_2020-08-07T08-22-14_scans=0-185_stokes_corrected_with_a_long_name_im_slit_U_l01_20261015T090807"
    assert names == [f"{stem}.fits", f"{stem}_2.fits", f"{stem}_3.fits"]
    assert [float(fits.getdata(p)[0, 0]) for p in paths] == [0.0, 1.0, 2.0]
    hd = fits.getheader(paths[0])
    assert hd["PARENT"] == src.rsplit("/", 1)[1] and hd["FILENAME"] == names[0] and hd["LONGSTRN"] == "OGIP 1.0"


def test_without_times_stokes_or_lambda(tmp_path):
    """A map without a header: TSEC NaN and UTC blank, the same columns; no Stokes nor lambda in the name or cards. A
    time of day without its day (an LP cube's): TSEC from midnight, UTC hh:mm:ss.sss, no DATEREF."""
    from explorer.data.axes import Axes

    n = len(pixels(PTS)[0])
    p = write(tmp_path, Axes(), np.ones((2, n), np.float32), [0, 1], source="/d/Blos.map.fcube", s=None, l=None, nt=2)
    with fits.open(p) as h:
        print(p.rsplit("/", 1)[1], h["TIME"].data)
        assert p.endswith("/Blos.map_slit_20261015T090807.fits")
        assert not {"STOKES", "STOKESIX", "LAMIDX", "WAVELNTH", "DATEREF", "BUNIT"} & set(h[0].header)
        assert np.isnan(h["TIME"].data["TSEC"]).all() and list(h["TIME"].data["UTC"]) == ["", ""]
    lp = Axes()
    lp.t_sec, lp.time_of_day = np.array([30134.25, 30154.5]), True
    p = write(tmp_path, lp, np.ones((2, n), np.float32), [0, 1], source="/d/x.icube", s=0, ns=1, l=None, nt=2)
    tim = fits.getdata(p, "TIME")
    print(tim)
    assert list(tim["UTC"]) == ["08:22:14.250", "08:22:34.500"] and "DATEREF" not in fits.getheader(p)
    assert fits.getheader(p)["STOKES"] == "s0"


def test_a_slice_that_does_not_match_its_slit_is_refused(tmp_path):
    from explorer.data.axes import Axes

    with pytest.raises(ValueError, match="points along the slit"):
        write(tmp_path, Axes(), np.ones((2, 5), np.float32), [0, 1])
    assert not list(tmp_path.iterdir())               # nothing left behind


# ---------------------------------------------------------------- through the window
def spin(qapp, until, timeout=10.0):
    end = time.perf_counter() + timeout
    while not until() and time.perf_counter() < end:
        qapp.processEvents()
        time.sleep(0.002)
    return until()


@pytest.fixture(params=["per-pixel", "frames"])
def shell(request, qapp, cube):
    from explorer.data.dataset import Dataset
    from explorer.ui.shell import Shell

    ds = Dataset.open(cube[0], no_sp=request.param == "frames")
    w = Shell(ds, title="c_im.fits")
    w.resize(1100, 700)
    w.show()
    assert spin(qapp, lambda: w.first_image_s is not None)
    yield w
    w.close()
    ds.close()


def draw(w, pts):
    w.set_slit_mode(True)
    for x, y in pts:
        w.slit_tool.add(x, y)
    w.slit_tool.finish()
    assert w.session.state.path == DRAWN


def shown(qapp, panel, reads, want):
    """Until the panel's time slice is want, whole, and the reads have it."""
    def done():
        a = panel._raw[0][0]
        return (a is not None and a.shape == want.shape and np.array_equal(a, want, equal_nan=True)
                and reads.time_slice is not None and reads.time_slice.values is a)
    return spin(qapp, done)


def said(w) -> list:
    """The status line's messages from now on: a hover in the offscreen window can take one off it before it is
    read."""
    got: list[str] = []
    w.statusBar().messageChanged.connect(got.append)
    return got


def save_button(w):
    from explorer.ui.titlebar import SaveButton

    return w.slit_dock.titleBarWidget().findChild(SaveButton, "save_slit")


def click_save(qapp, w, folder, monkeypatch):
    """A click on the slit title's save button, in folder as the working directory: the path of the one file it
    wrote."""
    from PySide6 import QtCore
    from PySide6.QtTest import QTest

    monkeypatch.chdir(folder)
    before = set(folder.iterdir())
    b = save_button(w)
    QTest.mouseClick(b, QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier, b.rect().center())
    qapp.processEvents()
    new = sorted(set(folder.iterdir()) - before)
    assert len(new) == 1, new
    return str(new[0])


def test_a_click_saves_the_time_slice_the_panel_shows(qapp, shell, cube, tmp_path, monkeypatch):
    from explorer.ui import shell as shell_module

    w, data = shell, cube[1]
    w.session.set_index("s", 3)
    w.session.set_index("l", 2)
    draw(w, PTS)
    iy, ix = pixels(DRAWN)
    said_, bar = [], said(w)
    # what the shell prints to the terminal, taken at its print: pytest put its own sys.stderr back in the middle of
    # this test in 2 runs of 18 (offscreen, Mac), and the line went there
    terminal: list[str] = []
    monkeypatch.setattr(shell_module, "print",
                        lambda *a, file=None: terminal.append(" ".join(map(str, a))) if file is sys.stderr else None,
                        raising=False)
    for cap, t in ((100, steps(NT, 100)), (None, np.arange(NT))):
        w.session.set_t_cap(cap)
        want = data[t, 3, 2][:, iy, ix]
        assert shown(qapp, w.slit_panel, w.scheduler.slit, want), f"cap {cap}: the panel never showed the slice"
        path = click_save(qapp, w, tmp_path, monkeypatch)
        err = "\n".join(terminal)
        terminal.clear()
        said_.append(f"cap {cap}: {path.rsplit('/', 1)[1]} {fits.getdata(path).shape} | terminal: {err.strip()}")
        with fits.open(path) as h:
            np.testing.assert_array_equal(h[0].data, w.slit_panel._raw[0][0])     # what the panel has
            np.testing.assert_array_equal(h[0].data, want)                       # the cube's values there
            np.testing.assert_array_equal(h["TIME"].data["TINDEX"], t)
            np.testing.assert_array_equal(h["SLIT"].data["X"], ix)
            np.testing.assert_array_equal(h["SLIT"].data["Y"], iy)
            np.testing.assert_array_equal(np.c_[h["VERTICES"].data["XPOS"], h["VERTICES"].data["YPOS"]],
                                          np.asarray(DRAWN) - 0.5)
            hd = h[0].header
            assert (hd["STOKES"], hd["LAMIDX"], hd["TSTEPS"], hd["PARENT"]) == ("V", 2, "100" if cap else "all",
                                                                              "c_im.fits")
        assert path.rsplit("/", 1)[1].startswith("c_im_slit_V_l02_")
        assert f"slit saved: {path}" in err and f"slit saved: {path}" == bar[-1], (err, bar)
        assert "not read yet" not in err                # the slice was whole: its NaN are the cube's padding
    print(*said_, sep="\n")


def test_a_click_without_a_finished_slit_writes_nothing_and_says_why(qapp, shell, tmp_path, monkeypatch):
    from PySide6 import QtCore
    from PySide6.QtTest import QTest

    monkeypatch.chdir(tmp_path)
    bar = said(w := shell)
    b = save_button(w)
    assert b is not None and b.isEnabled()
    def click():
        w.statusBar().clearMessage()                    # the same message twice is said twice
        qapp.processEvents()
        QTest.mouseClick(b, QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier,
                         b.rect().center())

    click()                                             # S off
    w.set_slit_mode(True)
    click()                                             # S on, no point yet
    w.slit_tool.add(*PTS[0])
    click()                                             # one point
    w.slit_tool.add(*PTS[1])
    click()                                             # two, not finished
    print(" | ".join(bar))
    assert [m for m in bar if m.startswith("slit not saved")] == [
        "slit not saved: no slit (S draws one)",
        "slit not saved: no slit yet: click points, double click to finish",
        "slit not saved: the slit is being drawn: finish it first (double click)",
        "slit not saved: the slit is being drawn: finish it first (double click)"]
    assert not list(tmp_path.iterdir())


def test_the_button_is_in_the_slit_s_title_alone_and_no_key_saves(qapp, shell):
    """After the number in the slit's title, as high, before the name; not in lambda-t's; its tooltip. No E key: not
    in the shortcuts, the terminal's keys (the same table) nor the ? sheet."""
    from PySide6 import QtGui

    from explorer.ui.titlebar import SAVE_TIP, SaveButton

    w = shell
    t, lt = w.slit_dock.titleBarWidget(), w.lt_dock.titleBarWidget()
    b = save_button(w)
    print(type(t).__name__, "steps", t.steps_button.geometry().getRect(), "save", b.geometry().getRect(),
          "left end", t.left_end(), "width", t.width())
    assert b is t.save_button and b.toolTip() == SAVE_TIP
    assert lt.findChild(SaveButton) is None and lt.save_button is None and lt.steps_button is not None
    s = t.steps_button.geometry()
    assert s.right() < b.x() <= s.right() + 4 and b.geometry().center().y() == s.center().y()
    assert t.left_end() == b.geometry().right() and t.rect().contains(b.geometry())
    seqs = [QtGui.QKeySequence(seq) for seq, _fn in w.action_registry.binds()]
    assert QtGui.QKeySequence("E") not in seqs
    assert all(fn is not w.save_slit for _k, _w, binds in w.action_registry.rows for _s, fn in binds)
    assert "save" not in w.sheet.text().lower() and "FITS" not in w.sheet.text()


def test_the_button_in_glass_s_title_and_under_the_macos_style(qapp, cube):
    """Glass's PanelTitle has it in the glass's ink, the name clear of it; under Qt's macos style (a Mac only) the
    stand-in title has it after the number, as high as Qt's marks, the name clear of it."""
    import pyqtgraph as pg
    from PySide6 import QtGui, QtWidgets

    from explorer.data.dataset import Dataset
    from explorer.ui import glass
    from explorer.ui.shell import Shell
    from explorer.ui.titlebar import SaveButton

    ds = Dataset.open(cube[0], no_sp=True)
    w = Shell(ds)
    try:
        w.resize(1100, 600)
        w.show()
        assert spin(qapp, lambda: w.first_image_s is not None)
        g = glass.PanelTitle(w.slit_dock)
        g.resize(300, 20)
        g.layout().activate()
        g.grab()                                         # a paint: the glass's ink set
        print("glass:", g.steps_button.geometry().getRect(), g.save_button.geometry().getRect(), g.left_end())
        assert g.save_button is not None and g.left_end() == g.save_button.geometry().right()
        assert g.save_button.x() > g.steps_button.geometry().right()
        assert g.save_button.ink == glass.INK[glass._mode()]
        assert glass.PanelTitle(w.lt_dock).findChild(SaveButton) is None
        g.deleteLater()
    finally:
        w.close()
        ds.close()
    if "macos" not in [k.lower() for k in QtWidgets.QStyleFactory.keys()]:
        print("no macos style here: its title not built")
        return
    name, pal = qapp.style().name(), QtGui.QPalette(qapp.palette())
    qapp.setStyle(QtWidgets.QStyleFactory.create("macos"))
    ds = Dataset.open(cube[0], no_sp=True)
    w = Shell(ds)
    try:
        w.resize(1100, 600)
        w.show()
        assert spin(qapp, lambda: w.first_image_s is not None)
        draw(w, PTS)                                     # the slit's panel shown, its title laid out
        t = w.slit_dock.titleBarWidget()
        assert t.qt_marks and spin(qapp, lambda: t.isVisible() and t.button.x() > 0)
        b, s, f = t.save_button, t.steps_button.geometry(), t.button.geometry()
        print("macos: float", f.getRect(), "steps", s.getRect(), "save", b.geometry().getRect(), "width", t.width())
        assert b is not None and s.right() < b.x() <= s.right() + 4
        assert b.height() == f.height() and b.y() == f.y() and t.rect().contains(b.geometry())
        assert w.lt_dock.titleBarWidget().save_button is None
    finally:
        w.close()
        ds.close()
        qapp.setStyle(QtWidgets.QStyleFactory.create(name or "Fusion"))
        qapp.setPalette(pal)
        qapp.setProperty("explorer_light", False)
        pg.setConfigOptions(background="k", foreground="d")


@pytest.fixture
def linked(qapp, cube, tmp_path_factory):
    from explorer.data.dataset import Dataset
    from explorer.ui.shell import Shell

    other = synth.write_dataset(tmp_path_factory.mktemp("slitfits_o"), "o", shape=(NT, NS, 7, NY, NX), seed=4,
                                icube=False, sp=False)["im"]
    ds = Dataset.open(cube[0])
    lk = Dataset.open(other, executors=ds.executors)
    w = Shell(ds, linked=[lk])
    w.resize(1400, 700)
    w.show()
    assert spin(qapp, lambda: w.first_image_s is not None and all(c.scheduler.img is not None for c in w.linked))
    yield w, fits.getdata(other).astype(np.float32)
    w.close()
    lk.close()
    ds.close()


def test_a_click_saves_the_tab_in_front_named_after_its_cube(qapp, linked, tmp_path, monkeypatch):
    w, data = linked
    o = w.linked[0]
    assert w.session.state.slit_tabs
    draw(w, PTS)
    assert spin(qapp, lambda: w.scheduler.slit.time_slice is not None)  # the drawn-on cube's tab, in front
    w.slit_tabs.setCurrentIndex(w.slit_tabs.keys.index("slit:1"))     # then the linked cube's
    iy, ix = pixels(DRAWN)
    st = w.session.member_state(1)
    want = data[steps(NT, 100), st.s, st.l][:, iy, ix]
    assert shown(qapp, o.slit_panel, o.scheduler.slit, want), "the linked tab never showed its slice"
    assert w.slit_tabs.keys[w.slit_tabs.currentIndex()] == "slit:1"
    path = click_save(qapp, w, tmp_path, monkeypatch)
    print(path.rsplit("/", 1)[1], "lambda", st.l, "of 7, Stokes", st.s)
    with fits.open(path) as h:
        np.testing.assert_array_equal(h[0].data, o.slit_panel._raw[0][0])
        np.testing.assert_array_equal(h[0].data, want)
        assert h[0].header["PARENT"] == "o_im.fits" and h[0].header["LAMIDX"] == st.l
        np.testing.assert_array_equal(h["SLIT"].data["X"], ix)
    assert path.rsplit("/", 1)[1].startswith(f"o_im_slit_I_l{st.l:02d}_")


def _toast_wait(qapp, ms):
    end = time.perf_counter() + ms / 1e3
    while time.perf_counter() < end:
        qapp.processEvents()
        time.sleep(0.005)


def test_a_save_says_its_file_in_a_note_above_the_x_axis_that_goes(qapp, shell, tmp_path, monkeypatch):
    """After a click, the file's name in a note over the slit panel, its foot above the time slice's x axis (the
    axis and its label stay readable), gone by itself after TOAST_MS; a click with no finished slit says why the
    same way."""
    from explorer.ui import shell as shell_module

    monkeypatch.setattr(shell_module, "TOAST_MS", 300)
    monkeypatch.setattr(shell_module, "FADE_MS", 100)
    w = shell
    draw(w, DRAWN)
    assert spin(qapp, lambda: w.cubes[0].scheduler.slit.time_slice is not None)
    path = click_save(qapp, w, tmp_path, monkeypatch)
    t = w._toast
    assert t.isVisible() and t.text() == f"saved {os.path.basename(path)}"
    panel, host = w.slit_panel, w.slit_dock.widget()
    vb = panel.ts.vb
    axis_top = panel.w.mapTo(host, panel.w.mapFromScene(vb.mapRectToScene(vb.boundingRect()).bottomLeft())).y()
    assert t.geometry().bottom() < axis_top
    assert t.geometry().top() > panel.w.mapTo(host, panel.w.mapFromScene(vb.mapRectToScene(vb.boundingRect())
                                                                         .topLeft())).y()
    _toast_wait(qapp, 500)
    assert not t.isVisible()
    w.clear_slit()                                              # no slit: its panel goes; S shows it, drawing
    w.set_slit_mode(True)
    assert spin(qapp, lambda: w.slit_dock.isVisible())
    assert w.save_slit(str(tmp_path)) is None
    assert t.isVisible() and t.text() == "not saved: no slit yet: click points, double click to finish"


def test_through_the_bridge_the_note_goes_at_once(qapp):
    """fade_ms 0 (the X11 bridge: each step of a fade is a repaint on the link): shown for ms, then hidden at once,
    no fade run; with a fade, it fades out over its last fade_ms."""
    from PySide6 import QtCore, QtWidgets

    from explorer.ui.overlays import Toast

    host = QtWidgets.QWidget()
    host.resize(400, 200)
    host.show()
    t = Toast(host)
    t.say("saved x.fits", 150, 0, bottom=150)
    assert t.isVisible() and t.geometry().bottom() < 150
    _toast_wait(qapp, 250)
    assert not t.isVisible() and t._anim.state() == QtCore.QAbstractAnimation.State.Stopped
    t.say("saved y.fits", 200, 120)
    _toast_wait(qapp, 130)
    assert t.isVisible() and t._anim.state() == QtCore.QAbstractAnimation.State.Running
    _toast_wait(qapp, 250)
    assert not t.isVisible()
    host.close()

"""The temporal panels at most 100 t steps (ViewState.t_cap, data.tsample): lambda-t (and the value against t of a
cube without lambda) and the slit's time slice read and show only the t steps evenly spread over the cube's t; a cube
with nt <= the cap, or the cap off ("all"), as before; the number in their titles changes it; the current t's line
and a click stay in the cube's own t, a click picking the nearest t shown. Each test prints what it measured.

The behaviour tests use only what existed before the cap (the Driver, the Store, Dataset): on the code before it they
fail on their assertions, not on an import."""
import time

import numpy as np
import pytest
from astropy.io import fits

from explorer.data.dataset import Dataset
from explorer.data.io import SeriesReader
from explorer.testing import synth
from explorer.testing.driver import Driver

NT, NS, NL, NY, NX = 250, 4, 3, 24, 20
Y, X = 14, 8                                            # not the centre, where the cursor starts
SLIT = ((3.5, 6.5), (16.5, 18.5))


def steps(nt, cap):
    """The steps the panels must show, computed here: the centres of `cap` equal bins of [0, nt)."""
    return np.floor((np.arange(cap) + 0.5) * nt / cap).astype(int)


@pytest.fixture(scope="module")
def cube(tmp_path_factory):
    d = synth.write_dataset(tmp_path_factory.mktemp("tcap"), "c", shape=(NT, NS, NL, NY, NX), icube=False)
    return d["im"], fits.getdata(d["im"]).astype(np.float32)


@pytest.fixture(scope="module")
def small(tmp_path_factory):
    d = synth.write_dataset(tmp_path_factory.mktemp("tcap_small"), "s", shape=(5, NS, NL, NY, NX), icube=False)
    return d["im"], fits.getdata(d["im"]).astype(np.float32)


@pytest.fixture(params=["per-pixel", "frames"])
def drv(request, cube):
    d = Driver.open(cube[0], no_sp=request.param == "frames")
    yield d
    d.close()


def frames_read(ds, monkeypatch):
    """The number of frames each series read of ds asks for (FrameReader.series_frames), in order."""
    got: list[int] = []
    orig = ds.frames.series_frames

    def spy(*a, **kw):
        sizes, fn = orig(*a, **kw)
        got.append(int(fn.size))
        return sizes, fn
    monkeypatch.setattr(ds.frames, "series_frames", spy)
    return got


# ---------------------------------------------------------------- the steps
def test_the_steps_are_bin_centres_and_every_t_within_the_cap():
    from explorer.data.tsample import nearest_sample, time_samples

    for nt, cap in ((250, 100), (300, 100), (3900, 100), (101, 100), (7, 3)):
        ts = time_samples(nt, cap)
        print(nt, cap, "->", ts[:4], "...", ts[-2:])
        assert len(ts) == cap and np.array_equal(ts, steps(nt, cap)) and (np.diff(ts) > 0).all()
        j = np.arange(cap)
        assert ((ts + 1 > j * nt / cap) & (ts < (j + 1) * nt / cap)).all()   # each row drawn over its t's cell
    for nt, cap in ((5, 100), (100, 100), (250, None)):
        assert np.array_equal(time_samples(nt, cap), np.arange(nt))
    ts = time_samples(250, 100)                                          # 1, 3, 6, 8, 11, ...
    assert nearest_sample(ts, 3.4) == 3 and nearest_sample(ts, 5.0) == 3 and nearest_sample(ts, 6.2) == 6
    assert nearest_sample(ts, 0.0) == 1 and nearest_sample(ts, 250.0) == ts[-1]


# ---------------------------------------------------------------- lambda-t
def test_lambda_t_reads_and_shows_100_of_250_t(drv, cube, monkeypatch):
    data = cube[1]
    reads = frames_read(drv.dataset, monkeypatch)
    drv.hover(Y, X)
    drv.wait_idle()
    lt, ts = drv.shown.lambda_t, steps(NT, 100)
    print("lambda-t", None if lt is None else lt.shape, "frames per series read", reads)
    assert lt is not None and lt.shape == (100, NL)
    assert np.allclose(lt, data[ts, 0, :, Y, X], rtol=1e-5, atol=0, equal_nan=True)
    if drv.dataset.pixel is None:                   # without a per-pixel file only the steps are read
        assert reads and max(reads) == 100 * NL


def test_the_cap_off_reads_every_t(drv, cube):
    drv.hover(Y, X)
    drv.wait_idle()
    drv.session.store.set(t_cap=None)               # "all"
    drv.wait_idle()
    lt = drv.shown.lambda_t
    print("cap off: lambda-t", lt.shape)
    assert lt.shape == (NT, NL) and np.allclose(lt, cube[1][:, 0, :, Y, X], rtol=1e-5, atol=0, equal_nan=True)
    drv.session.store.set(t_cap=50)
    drv.wait_idle()
    print("cap 50: lambda-t", drv.shown.lambda_t.shape)
    assert np.allclose(drv.shown.lambda_t, cube[1][steps(NT, 50), 0, :, Y, X], rtol=1e-5, atol=0, equal_nan=True)


@pytest.mark.parametrize("no_sp", [False, True])
def test_a_cube_within_the_cap_is_as_before(small, no_sp):
    """nt = 5: every t, the same arrays as before the cap (this one passes before and after)."""
    with Driver.open(small[0], no_sp=no_sp) as d:
        d.hover(Y, X)
        d.show("slit")
        d.set_slit(SLIT)
        d.wait_idle()
        iy, ix = d.shown.slit_pix
        print("nt 5: lambda-t", d.shown.lambda_t.shape, "time slice", d.shown.slit_ts.shape)
        assert np.allclose(d.shown.lambda_t, small[1][:, 0, :, Y, X], rtol=1e-5, atol=0, equal_nan=True)
        lam = d.state().l                               # the tuning the session starts at
        assert np.allclose(d.shown.slit_ts, small[1][:, 0, lam][:, iy, ix], rtol=1e-5, atol=0, equal_nan=True)


# ---------------------------------------------------------------- the slit's time slice
def test_the_slits_time_slice_reads_and_shows_100_of_250_t(drv, cube):
    drv.show("slit")
    drv.set_slit(SLIT)
    drv.wait_idle()
    iy, ix = drv.shown.slit_pix
    a, ts, lam = drv.shown.slit_ts, steps(NT, 100), drv.state().l
    frames = [r["frames"] for r in drv.scheduler.slit.reads if r.get("kind") == "ts"]
    print("time slice", a.shape, "frames read for it", frames)
    assert a.shape == (100, len(iy)) and np.allclose(a, cube[1][ts, 0, lam][:, iy, ix], rtol=1e-5, atol=0,
                                                               equal_nan=True)
    if drv.dataset.pixel is None:
        assert frames == [100]
    drv.session.store.set(t_cap=None)
    drv.wait_idle()
    assert drv.shown.slit_ts.shape == (NT, len(iy))


# ---------------------------------------------------------------- a file series: one file read per step
def test_a_series_reads_one_file_per_step_shown(tmp_path, monkeypatch):
    n, ny, nx = 150, 6, 5
    rng = np.random.default_rng(1)
    imgs = rng.integers(0, 3000, (n, ny, nx)).astype(np.int16)
    t0 = np.datetime64("2026-06-07T06:52:00.000", "ms")
    paths = []
    for k in range(n):
        h = fits.Header()
        h["T_OBS"] = str(t0 + np.timedelta64(12000 * k, "ms")) + "Z"
        h["WAVELNTH"], h["INSTRUME"], h["BUNIT"] = 171, "AIA_3", "DN"
        p = str(tmp_path / f"aia_{k:03d}.fits")
        fits.PrimaryHDU(imgs[k], h).writeto(p)
        paths.append(p)
    calls: list[int] = []
    orig = SeriesReader._pixel_raw

    def spy(self, t, y, x):
        calls.append(int(t))
        return orig(self, t, y, x)
    monkeypatch.setattr(SeriesReader, "_pixel_raw", spy)
    with Driver(Dataset.open(None, series=paths), own=True) as d:
        q = time.perf_counter()
        d.hover(3, 2)
        d.wait_idle()
        ts = steps(n, 100)
        print(f"series of {n}: files read {len(calls)}, curve {d.shown.lambda_t.shape}, "
              f"{(time.perf_counter() - q) * 1e3:.0f} ms")
        assert sorted(set(calls)) == ts.tolist() and len(calls) == 100
        assert np.array_equal(d.shown.lambda_t.reshape(-1), imgs[ts, 3, 2].astype(np.float32))


# ---------------------------------------------------------------- the panels: drawn in the cube's own t
def spin(qapp, until, timeout=20.0):
    end = time.perf_counter() + timeout
    while not until() and time.perf_counter() < end:
        qapp.processEvents()
        time.sleep(0.002)
    return until()


def window(qapp, path, **kw):
    """A window on path, shown, its first image in; the panels inside it (bare pyqtgraph widgets left to the collector
    crashed the run's teardown)."""
    from explorer.ui.shell import Shell

    ds = Dataset.open(path, **kw)
    w = Shell(ds)
    w.resize(1200, 640)
    w.show()
    assert spin(qapp, lambda: w.first_image_s is not None)

    def close():
        w.close()
        ds.close()
    return w, close


def test_the_panels_draw_the_steps_at_their_t_and_a_click_picks_the_nearest(qapp, cube, tmp_path):
    from PySide6 import QtCore

    ts = steps(NT, 100)
    w, close = window(qapp, cube[0], no_sp=True)
    try:
        w.session.hover(Y, X)
        p = w.lambda_t
        assert spin(qapp, lambda: w.last.get("lambda_t") is not None and w.last["lambda_t"][1] == (Y, X))
        r = p.img.mapRectToParent(p.img.boundingRect())
        print("lambda-t rows 100, image height", r.height(), "pick y 5.0 ->", p.pick(QtCore.QPointF(1.5, 5.0)))
        assert np.array_equal(p.steps, ts) and r.height() == pytest.approx(NT)
        assert p.pick(QtCore.QPointF(1.5, 5.0)) == {"l": 1, "t": 3}
        p.show(np.ones((NT, NL), np.float32), (0.0, 2.0))         # every t: as before
        assert p.steps is None and p.pick(QtCore.QPointF(1.5, 5.0)) == {"l": 1, "t": 5}
        w.session.set_path([(3.5, 6.5), (16.5, 18.5)], cube=0)
        w._slit_shown(True)
        sp = w.slit_panel
        assert spin(qapp, lambda: sp._raw[0][0] is not None and sp._raw[0][0].shape[0] == 100)
        r = sp.ts_img.mapRectToParent(sp.ts_img.boundingRect())
        print("time slice rows 100, image height", r.height())
        assert np.array_equal(sp.steps, ts) and r.height() == pytest.approx(NT)
    finally:
        close()

    path = tmp_path / "blos_t.fits"
    h = fits.Header()
    h["CTYPE1"], h["CTYPE2"], h["CTYPE3"], h["BTYPE"], h["BUNIT"] = "HPLN-TAN", "HPLT-TAN", "UTC", "Blos", "G"
    values = np.random.default_rng(2).normal(size=(NT, NY, NX)).astype(">f4")
    fits.PrimaryHDU(values, h).writeto(path)
    w, close = window(qapp, str(path))
    try:
        w.session.hover(Y, X)
        c = w.lambda_t
        assert spin(qapp, lambda: w.last.get("lambda_t") is not None and w.last["lambda_t"][1] == (Y, X))
        print("curve x", np.asarray(c.curve.xData)[:4], "pick 5.0 ->", c.pick(QtCore.QPointF(5.0, 0)))
        assert np.allclose(c.curve.xData, ts + 0.5) and np.allclose(c.curve.yData, values[ts, Y, X])
        assert c.pick(QtCore.QPointF(5.0, 0)) == {"t": 3} and c.pick(QtCore.QPointF(6.4, 0)) == {"t": 6}
        w.session.set_index("t", 4)
        assert spin(qapp, lambda: c.t_line.value() == 4.5)      # the current t where it is, between the steps
        c.show(np.arange(NT, dtype=np.float32))                  # every t: as before
        assert np.allclose(c.curve.xData, np.arange(NT) + 0.5) and c.pick(QtCore.QPointF(5.0, 0)) == {"t": 5}
    finally:
        close()


# ---------------------------------------------------------------- the number in the titles
def test_the_number_in_the_titles_changes_the_steps(qapp, cube):
    from PySide6 import QtCore, QtGui

    from explorer.ui import glass
    from explorer.ui.shell import Shell
    from explorer.ui.titlebar import StepsButton

    ds = Dataset.open(cube[0], no_sp=True)
    w = Shell(ds)
    try:
        w.resize(1200, 640)
        w.show()
        assert spin(qapp, lambda: w.first_image_s is not None)
        w.session.hover(Y, X)
        assert spin(qapp, lambda: w.last.get("lambda_t") is not None and len(w.last["lambda_t"][0]) == 100)
        buttons = [d.titleBarWidget().findChild(StepsButton, "time_steps") for d in (w.lt_dock, w.slit_dock)]
        assert all(b is not None for b in buttons)
        b = buttons[0]

        def wheel(up):
            pos = QtCore.QPointF(b.rect().center())
            e = QtGui.QWheelEvent(pos, b.mapToGlobal(pos), QtCore.QPoint(), QtCore.QPoint(0, 120 if up else -120),
                                  QtCore.Qt.MouseButton.NoButton, QtCore.Qt.KeyboardModifier.NoModifier,
                                  QtCore.Qt.ScrollPhase.NoScrollPhase, False)
            QtCore.QCoreApplication.sendEvent(b, e)
            qapp.processEvents()

        wheel(True)                                     # past 100 only "all"
        assert spin(qapp, lambda: w.session.state.t_cap is None and len(w.last["lambda_t"][0]) == NT)
        wheel(True)                                     # "all" is the end
        assert w.session.state.t_cap is None and w.t_steps.value is None
        for _ in range(3):
            wheel(False)
        assert spin(qapp, lambda: w.session.state.t_cap == 25 and len(w.last["lambda_t"][0]) == 25)
        print("wheel: 100 -> all -> all -> 100 -> 50 -> 25; lambda-t rows", len(w.last["lambda_t"][0]))
        b.choose()                                      # the menu of choices: 50 picked
        acts = [a for a in b.findChildren(QtGui.QAction) if a.text() == "50"]
        assert acts and [a.text() for a in b.findChildren(QtGui.QAction)][-4:] == ["25", "50", "100", "all"]
        acts[-1].trigger()
        assert spin(qapp, lambda: w.session.state.t_cap == 50 and w.t_steps.value == 50)
        img = b.grab().toImage()
        assert not img.isNull() and w.t_steps.value == 50
        g = glass.PanelTitle(w.lt_dock)                 # the glass look's title: the number there too
        g.resize(300, 20)
        g.layout().activate()
        assert g.steps_button is not None and g.left_end() > g.buttons[-1].geometry().right()
        g.deleteLater()
        print("titles with the number:", [type(d.titleBarWidget()).__name__ for d in (w.lt_dock, w.slit_dock)])
    finally:
        w.close()
        ds.close()


def test_titles_replaced_by_another_look_leave_no_button_behind(qapp, cube, monkeypatch):
    """Changing the look replaces the panels' titles and their step buttons; a change of the steps after it repaints
    the buttons shown, and none of the deleted ones (it raised "Internal C++ object (StepsButton) already deleted",
    once per deleted button and change)."""
    import sys

    from explorer.look import get_look
    from explorer.ui.shell import Shell
    from explorer.ui.titlebar import StepsButton

    raised: list = []
    monkeypatch.setattr(sys, "excepthook", lambda *a: raised.append(a[1]))
    ds = Dataset.open(cube[0], no_sp=True)
    w = Shell(ds)
    try:
        w.resize(1200, 640)
        w.show()
        assert spin(qapp, lambda: w.first_image_s is not None)
        for name in ("glass", "classic", "glass"):
            w.set_look(get_look(name))
            qapp.processEvents()
        for _ in range(3):                                          # the deleted titles go at the next event loop
            deferred_deletes(qapp)
        for v in (50, 25, None):
            w.t_steps.update(v)
            qapp.processEvents()
        assert raised == [], raised
        shown = [d.titleBarWidget().findChild(StepsButton, "time_steps") for d in (w.lt_dock, w.slit_dock)]
        assert all(b is not None for b in shown)
    finally:
        w.close()
        ds.close()


def deferred_deletes(qapp):
    """The titles deleted later (deleteLater) deleted now."""
    from PySide6 import QtCore

    QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
    qapp.processEvents()


def test_the_number_in_the_titles_has_a_glyph_that_says_t_steps(qapp, cube):
    """Before the number, the glyph icons.STEPS (a lambda-t cut in rows) in the number's ink, as high as its digits;
    the tooltip says what the number is: t steps shown at most."""
    from PySide6 import QtGui

    from explorer.ui import icons
    from explorer.ui.shell import Shell
    from explorer.ui.titlebar import StepsButton

    ds = Dataset.open(cube[0], no_sp=True)
    w = Shell(ds)
    try:
        w.resize(1200, 640)
        w.show()
        assert spin(qapp, lambda: w.first_image_s is not None)
        b = w.lt_dock.titleBarWidget().findChild(StepsButton, "time_steps")
        assert b is not None
        print("tooltip:", repr(b.toolTip()))
        assert b.toolTip().startswith("t steps shown at most")
        assert icons.STEPS in icons.GLYPHS
        img = b.grab().toImage()
        dpr = img.devicePixelRatio()
        fm = QtGui.QFontMetrics(b.font())
        tw = fm.horizontalAdvance("100")
        x0 = round((b.width() - (b.glyph + b.GAP + tw)) / 2)
        bg = QtGui.QColor(img.pixel(0, 0)).lightness()

        def ink(x_from, x_to):
            return [(x, y) for x in range(int(x_from * dpr), int(x_to * dpr)) for y in range(img.height())
                    if abs(QtGui.QColor(img.pixel(x, y)).lightness() - bg) > 60]

        glyph, text = ink(x0, x0 + b.glyph), ink(x0 + b.glyph + b.GAP, b.width())
        per_row: dict[int, int] = {}
        for _, y in glyph:
            per_row[y] = per_row.get(y, 0) + 1
        full = sorted(y for y, n in per_row.items() if n >= 0.7 * b.glyph * dpr)      # strokes across the glyph
        runs = sum(1 for k, y in enumerate(full) if k == 0 or y != full[k - 1] + 1)
        print(f"glyph {icons.STEPS!r} {b.glyph} px: {len(glyph)} ink px, rows across it {full} ({runs} apart); "
              f"number {len(text)} ink px")
        assert glyph and text and runs >= 3                                 # rows, apart
    finally:
        w.close()
        ds.close()


def test_the_sheet_says_what_the_number_in_the_titles_does(qapp, small):
    """The ? sheet has a row for the number in the titles of lambda-t and the slit: what it is and how it changes."""
    w, close = window(qapp, small[0], no_sp=True)
    try:
        rows = [(g, what) for g, what in w.action_registry.mouse if "t steps" in what]
        print("rows on the t steps", rows)
        assert len(rows) == 1 and "number" in rows[0][0] and "25, 50, 100, all" in rows[0][1]
        assert "wheel" in rows[0][0] and "t steps: 25, 50, 100, all" in w.sheet.text()
    finally:
        close()


def test_under_the_macos_style_the_numbered_titles_have_qt_s_own_close_and_float(qapp, cube):
    """On a local Mac the spectra keep Qt's own title; lambda-t's and the slit's are ours, for the number, standing in
    for Qt's (Shell.give_steps). Under the native macOS style their close and float are Qt's own: where Qt puts them
    in the spectra's title (the same width), the same pixels; the title as high, so the panels' contents start at
    the same height; the number after the float mark, as high. Qt's macos style, which exists only on a Mac: the
    application's for this test (a faked name would mix it with another style's sizes, as no Mac does)."""
    import pyqtgraph as pg
    from PySide6 import QtCore, QtGui, QtWidgets

    from explorer.ui.shell import Shell
    from explorer.ui.titlebar import StepsButton

    if "macos" not in [k.lower() for k in QtWidgets.QStyleFactory.keys()]:
        pytest.skip("Qt's macos style exists only on a Mac")
    name, pal = qapp.style().name(), QtGui.QPalette(qapp.palette())
    qapp.setStyle(QtWidgets.QStyleFactory.create("macos"))
    ds = Dataset.open(cube[0], no_sp=True)
    w = Shell(ds)
    try:
        w.resize(1200, 640)
        w.show()
        assert spin(qapp, lambda: w.first_image_s is not None)
        spec, lt = w.spec_dock, w.lt_dock
        assert spec.titleBarWidget() is None and spec.width() == lt.width()
        assert type(w.slit_dock.titleBarWidget()) is type(lt.titleBarWidget())
        t = lt.titleBarWidget()
        F = QtCore.Qt.FindChildOption.FindDirectChildrenOnly
        for b_name in ("qt_dockwidget_closebutton", "qt_dockwidget_floatbutton"):
            qt_b = spec.findChild(QtWidgets.QAbstractButton, b_name, F)
            ours = t.findChild(QtWidgets.QAbstractButton, b_name)
            print(f"{b_name}: Qt's {qt_b.geometry().getRect()}, ours {ours.geometry().getRect()}")
            assert ours.geometry() == qt_b.geometry()
            assert ours.grab().toImage() == qt_b.grab().toImage()
        print(f"contents at y: spectra {spec.widget().y()}, lambda-t {lt.widget().y()}")
        assert lt.widget().y() == spec.widget().y()
        b, f = t.findChild(StepsButton, "time_steps"), t.button.geometry()
        print(f"number at {b.geometry().getRect()}, float mark at {f.getRect()}")
        assert f.right() < b.x() <= f.right() + 8 and b.geometry().center().y() == f.center().y()
        assert t.rect().contains(b.geometry())
    finally:
        w.close()
        ds.close()
        qapp.setStyle(QtWidgets.QStyleFactory.create(name or "Fusion"))
        qapp.setPalette(pal)
        qapp.setProperty("explorer_light", False)
        pg.setConfigOptions(background="k", foreground="d")


def test_away_from_the_macos_style_the_numbered_titles_keep_their_marks(qapp, cube):
    """Away from the macOS style (Linux, the Mac's dark and light themes, the chrome's titles) the titles of lambda-t
    and the slit keep the tool buttons they had, at the left: unchanged by the stand-in's Qt marks."""
    from PySide6 import QtWidgets

    w, close = window(qapp, cube[0], no_sp=True)
    try:
        for d in (w.lt_dock, w.slit_dock):
            t = d.titleBarWidget()
            assert [type(b) for b in t.buttons] == [QtWidgets.QToolButton] * 2
            assert t.buttons[0].x() < t.buttons[1].x() < t.steps_button.x() < t.width() // 2
    finally:
        close()

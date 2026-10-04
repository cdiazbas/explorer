"""The interface's details, offscreen, one test per detail; each prints what it measured, so a failure says what was
drawn. The plots' lines keep their width on a Retina screen (ui.pens); the spectra: one level of ticks that fit
their labels, no grid from the velocity axis, the x values once on the outer edges, the velocity ticks out and in
the frame's alpha, the box closed, the padlock clear of the plots and without its square, the lambda line 2 px at
1x, dots and a ring on the value read, the velocity title in Unicode; lambda-t: seconds when the minutes repeat,
ticks out of the image; the colour key's contrast, hairline, ticks and text size; the locked crosshair readable in
the light theme; the readout's numbers and units; the Panels arrow level with its label; play and pause drawn;
the interface's font; the glass look: its panels never too short, its title in whole fields, its bar's room."""
import time

import numpy as np
import pytest

from explorer.testing import synth

SHAPE = (6, 4, 21, 96, 80)


def spin(qapp, until, timeout=10.0):
    end = time.perf_counter() + timeout
    while not until() and time.perf_counter() < end:
        qapp.processEvents()
        time.sleep(0.002)
    return until()


@pytest.fixture(scope="module")
def cube(tmp_path_factory):
    return synth.write_dataset(tmp_path_factory.mktemp("polish"), "c", shape=SHAPE, icube=False)["im"]


@pytest.fixture
def axes(cube):
    from explorer.data.dataset import Dataset

    ds = Dataset.open(cube)
    yield ds.axes
    ds.close()


@pytest.fixture
def panel(qapp, axes):
    """The spectra of I Q U V, shown at 600 x 373 px (the prototype's dock at a 1400 x 900 window)."""
    from explorer.ui.spectra import SpectraPanel

    p = SpectraPanel(4, SHAPE[2], axes)
    p.widget.resize(600, 373)
    p.widget.show()
    spec = np.stack([np.sin(np.linspace(0, 3, SHAPE[2])) + k for k in range(4)])
    p.show(spec)
    for k in range(4):
        p.set_range(k, (float(spec[k].min()) - 0.2, float(spec[k].max()) + 0.2))
    p.set_lambda(4)
    assert spin(qapp, lambda: p.plots[0].vb.width() > 50)
    yield p
    p.widget.close()


@pytest.fixture
def shell(qapp, cube):
    from PySide6 import QtGui, QtWidgets

    from explorer.data.dataset import Dataset
    from explorer.ui import style
    from explorer.ui.shell import Shell

    name, pal, font = qapp.style().name(), QtGui.QPalette(qapp.palette()), QtGui.QFont(qapp.font())
    style.apply_theme(qapp, "dark")
    ds = Dataset.open(cube)
    w = Shell(ds, title="c_im.fits")
    w.setGeometry(60, 50, 1000, 700)
    w.show()
    assert spin(qapp, lambda: w.first_image_s is not None and "lambda_t" in w.last)
    yield w
    w.close()
    ds.close()
    qapp.setStyle(QtWidgets.QStyleFactory.create(name or "Fusion"))
    qapp.setPalette(pal)
    qapp.setFont(font)


def _columns(pen, dpr=2, x=10.25):
    """Device columns a vertical line drawn with pen at x lights on a QImage at dpr (the raster engine every backing
    store uses)."""
    from PySide6 import QtCore, QtGui

    img = QtGui.QImage(40 * dpr, 10 * dpr, QtGui.QImage.Format.Format_ARGB32_Premultiplied)
    img.setDevicePixelRatio(dpr)
    img.fill(QtGui.QColor(0, 0, 0))
    p = QtGui.QPainter(img)
    p.setPen(pen)
    p.drawLine(QtCore.QPointF(x, 1), QtCore.QPointF(x, 9))
    p.end()
    return sum(1 for x in range(img.width()) if QtGui.QColor(img.pixel(x, 5 * dpr)).red() > 20)


def test_plot_lines_keep_their_width_on_a_retina_screen(qapp, panel):
    import pyqtgraph as pg

    from explorer.ui import pens

    def widths():
        return (panel.lines[0].pen.widthF(), panel.curves[0].opts["pen"].widthF(), panel.rings[0].opts["pen"].widthF())

    at1 = _columns(pg.mkPen((255, 0, 0), width=1.5))
    held1 = widths()
    pens.set_ratio(2.0, panel.w)
    try:
        at2 = _columns(pg.mkPen((255, 0, 0), width=1.5))
        held2 = widths()
    finally:
        pens.set_ratio(1.0, panel.w)
    back = widths()
    print(f"a 1.5 line at ratio 2: {at1} device columns made at ratio 1, {at2} made at ratio 2; "
          f"the panel's (lambda, curve, ring) widths {held1} -> {held2} -> {back}")
    assert at1 == 1 and at2 == 3                         # 1.5 logical px: 3 device columns at ratio 2
    assert held2 == tuple(2 * w for w in held1) and back == held1


def test_a_pen_made_after_the_ratio_is_known_is_scaled_once(qapp):
    """The theme sets the ratio before the views make their pens (ui.style.apply_theme, then the imports of
    ui.imageview and ui.spectra): such a pen comes out of mkPen scaled already, and keep() must not scale it again
    (it did: on Retina the spectra's lambda line was 8 device px for 4)."""
    import pyqtgraph as pg

    from explorer.ui import pens

    pens.set_ratio(2.0)
    try:
        pen = pg.mkPen((255, 0, 0), width=1.5)
        made = pen.widthF()
        pens.keep(pen)
        kept = pen.widthF()
        pens.set_ratio(1.0)
        back = pen.widthF()
    finally:
        pens.set_ratio(1.0)
        if pen in pens._kept:
            pens._kept.remove(pen)
    print(f"width 1.5 made at ratio 2: {made}, after keep(): {kept}, back at ratio 1: {back}")
    assert (made, kept, back) == (3.0, 3.0, 1.5)


def test_the_velocity_axis_draws_no_grid(panel):
    tops = [p.getAxis("top") for p in panel.plots]
    print("grid of the top axes:", [a.grid for a in tops], "bottom:", [p.getAxis("bottom").grid for p in panel.plots])
    assert all(a.grid is False for a in tops)
    assert all(p.getAxis("bottom").grid is not False for p in panel.plots)


def test_one_level_of_ticks_that_fit_their_labels(qapp, panel):
    from PySide6 import QtGui

    ax = panel.plots[2].getAxis("bottom")
    lo, hi, size = -0.392, 0.742, 190
    fm = QtGui.QFontMetrics(ax.style.get("tickFont") or ax.font())

    def least_gap(step):
        first = np.ceil(lo / step - 1e-9) * step
        vals = [round(float(v), 12) for v in np.arange(first, hi + step * 1e-9, step)]
        w = [fm.horizontalAdvance(t) for t in ax.fmt(vals, step)]
        return min(step / (hi - lo) * size - (a + b) / 2 for a, b in zip(w, w[1:], strict=False))

    levels = ax.tickValues(lo, hi, size)
    labels = ax.tickStrings(levels[0][1], 1, levels[0][0]) if levels else []
    print(f"{size}-px delta-lambda axis in {fm.horizontalAdvance('+0.6')}-px-wide labels:", levels, labels)
    assert len(levels) == 1                              # one level: pyqtgraph's two were labelled apart
    step = levels[0][0]
    finer = {0.5: 0.2, 0.2: 0.1, 0.1: 0.05, 1.0: 0.5}.get(round(step, 6))
    print(f"least gap at step {step}: {least_gap(step):.1f} px; at the next finer, {finer}: "
          f"{least_gap(finer) if finer else float('nan'):.1f} px (needed {ax.GAP[1]})")
    assert least_gap(step) >= ax.GAP[1] and (finer is None or least_gap(finer) < ax.GAP[1])


def test_the_x_values_once_on_the_outer_edges(panel):
    shown = [(p.getAxis("bottom").style["showValues"], p.getAxis("top").style["showValues"]) for p in panel.plots]
    print("(bottom, top) values shown per plot I Q U V:", shown)
    assert shown == [(False, True), (False, True), (True, False), (True, False)]
    assert all(p.getAxis("top").tickValues(-0.3, 0.3, 200) == [] for p in panel.plots[2:])    # bare edges


def test_the_velocity_ticks_point_out_in_the_frames_alpha(panel):
    from PySide6 import QtGui

    top = panel.plots[0].getAxis("top")
    top.setPen(QtGui.QColor(255, 255, 255, 60))
    print("velocity tick length:", top.style["tickLength"], "tick alpha:", top.style["tickAlpha"])
    assert top.style["tickLength"] > 0 and top.style["tickAlpha"] == 60


def test_the_box_is_closed_without_grid_or_ticks_of_its_own(panel):
    for p in panel.plots:
        p.showGrid(x=True, y=True, alpha=0.2)            # as a look does
    right = [p.getAxis("right") for p in panel.plots]
    print("right axes visible:", [a.isVisible() for a in right], "grid:", [a.grid for a in right],
          "ticks:", [a.tickValues(0, 1, 100) for a in right])
    assert all(a.isVisible() and a.grid is False and a.tickValues(0, 1, 100) == [] for a in right)


def _plot_lock(view):
    """The spectra's padlock as the shell puts it on (without a square where that exists)."""
    from explorer.ui.padlock import PanelLock

    try:
        return PanelLock(view, "y", backed=False)
    except TypeError:                                    # a PanelLock that always has its square
        return PanelLock(view, "y")


def test_the_padlock_is_clear_of_the_plots_and_their_titles(qapp, panel):
    from PySide6 import QtCore

    lock = _plot_lock(panel.w)
    qapp.processEvents()
    r = QtCore.QRectF(lock.geometry())
    hits = []
    for k, p in enumerate(panel.plots):
        for name in ("top", "right"):
            a = p.getAxis(name)
            rect = panel.w.mapFromScene(a.mapRectToScene(a.boundingRect())).boundingRect()
            label = panel.w.mapFromScene(a.label.mapRectToScene(a.label.boundingRect())).boundingRect() \
                if a.label.isVisible() else QtCore.QRect()
            if QtCore.QRectF(label).intersects(r) or (name == "top" and QtCore.QRectF(rect).intersects(r)):
                hits.append((k, name, rect, label))
    print("padlock at", r, "overlaps:", hits)
    assert not hits


def test_the_spectra_padlock_has_no_square_of_its_own(qapp):
    from PySide6 import QtGui, QtWidgets

    from explorer.ui.padlock import PanelLock

    host = QtWidgets.QWidget()
    host.resize(80, 60)
    host.setAutoFillBackground(True)
    pal = host.palette()
    pal.setColor(QtGui.QPalette.ColorRole.Window, QtGui.QColor(200, 30, 30))
    host.setPalette(pal)
    _plot_lock(host)
    bare = host.grab().toImage()
    lock_corner = QtGui.QColor(bare.pixel(80 - PanelLock.MARGIN - PanelLock.SIZE + 3, PanelLock.MARGIN + 3))
    print("pixel inside the padlock's corner over a red panel:", lock_corner.getRgb())
    assert lock_corner.getRgb()[:3] == (200, 30, 30)


def test_the_lambda_line_reads_in_its_colour_at_1x(panel):
    from explorer.ui import spectra

    mark_w = getattr(spectra, "MARK_W", None)
    w = [ln.pen.widthF() for ln in panel.lines]
    cols = sorted({_columns(panel.lines[0].pen, dpr=1, x=10 + i / 20) for i in range(20)})
    print("lambda line widths:", w, "modern:", mark_w, "columns lit at 1x over 20 subpixel places:", cols)
    assert cols == [2] and mark_w is not None and mark_w >= 2


def test_dots_and_a_ring_on_the_value_read(qapp, panel):
    rings = getattr(panel, "rings", None)
    c = panel.curves[1]
    print("curve antialiased:", c.opts["antialias"], "dot size:", c.opts["symbolSize"], "rings:", rings is not None)
    assert c.opts["antialias"] and c.opts["symbolSize"] >= 4 and rings is not None
    ring = rings[1]
    x, y = ring.getData()
    want = (float(panel.xl[4]), float(panel._y[1][4]))
    print("curve antialiased:", c.opts["antialias"], "dot size:", c.opts["symbolSize"],
          "ring at", list(zip(x, y, strict=True)), "value read", want)
    assert c.opts["antialias"] and c.opts["symbolSize"] >= 4
    assert len(x) == 1 and (x[0], y[0]) == pytest.approx(want)
    spec = np.full((4, SHAPE[2]), np.nan)                # padding: no ring
    panel.show(spec)
    assert len(panel.rings[1].getData()[0]) == 0


def test_the_velocity_title_is_unicode(panel):
    text = panel.plots[0].getAxis("top").labelText
    print("velocity title:", repr(text))
    assert "⁻¹" in text and "<sup>" not in text


def test_lambda_t_times_get_seconds_when_minutes_repeat(qapp, axes):
    from explorer.ui.lambda_t import LambdaTPanel

    lt = LambdaTPanel(SHAPE[0], SHAPE[2], axes)
    ax = lt.w.getAxis("left")
    labels = ax.tickStrings([i + 0.5 for i in range(SHAPE[0])], 1, 1)
    print("time labels:", labels)
    shown = [x for x in labels if x]
    assert len(set(shown)) == len(shown)


def test_lambda_t_ticks_point_out_of_the_image(qapp, axes):
    from explorer.ui.lambda_t import LambdaTPanel

    lt = LambdaTPanel(SHAPE[0], SHAPE[2], axes)
    lengths = {n: lt.w.getAxis(n).style["tickLength"] for n in ("left", "bottom")}
    print("lambda-t tick lengths (positive: out, to the labels):", lengths)
    assert all(v > 0 for v in lengths.values())


def test_the_colour_key(qapp):
    from PySide6 import QtGui, QtWidgets

    from explorer.ui.overlays import ColourKey

    host = QtWidgets.QWidget()
    host.resize(300, 120)
    host.setAutoFillBackground(True)
    pal = host.palette()
    pal.setColor(QtGui.QPalette.ColorRole.Window, QtGui.QColor(255, 255, 255))
    host.setPalette(pal)
    key = ColourKey(host, "W m⁻² Hz⁻¹ sr⁻¹")
    key.set("Q", (-2.0, 3.0), None)
    img = key.grab().toImage()
    bg = QtGui.QColor(img.pixel(key.W - 30, 12)).red()     # the key over white, away from text and bar
    tick = QtGui.QColor(img.pixel(12, 22 + 6 + 2)).red()     # under the bar's left end
    beside = QtGui.QColor(img.pixel(20, 22 + 6 + 2)).red()
    px = getattr(key, "TEXT_PX", None)
    print(f"key over white: background {bg} (alpha 185: ~70), tick {tick} beside it {beside}, text {px} px")
    assert bg <= 75 and tick > beside + 30 and px is not None and px >= 11


def test_the_locked_crosshair_reads_on_a_white_image(qapp):
    from explorer.ui.imageview import ImageView

    def lum(c):
        def f(u):
            u /= 255
            return u / 12.92 if u <= 0.04045 else ((u + 0.055) / 1.055) ** 2.4
        return 0.2126 * f(c.red()) + 0.7152 * f(c.green()) + 0.0722 * f(c.blue())

    v = ImageView(light=True)
    v.set_locked(True)
    c = v.hl.pen.color()
    ratio = 1.05 / (lum(c) + 0.05)
    print("locked crosshair in light:", c.getRgb(), f"contrast on white {ratio:.2f}:1")
    assert ratio >= 3.0


def test_the_readout_numbers_and_units():
    from explorer.ui.status import pixel_text

    class Ax:
        corners = None
        t_sec = None
        bunit = "W m^-2 Hz^-1 sr^-1"

        def dlam_A(self):
            return None

    text = pixel_text(Ax(), 1, 3, 4, 0, 2, 0, 1.2345e-5, None, None, False, present=("l",))
    print("readout:", repr(text))
    assert "e-" not in text and "× 10⁻⁵" in text and "\u00a0W" in text
    from explorer.data.axes import fmt_sig

    print("fmt_sig:", fmt_sig(1.2345e-5), fmt_sig(0.012345), fmt_sig(-12345.6))
    assert fmt_sig(0.012345) == "0.01235" and fmt_sig(-12345.6) == "−1.235 × 10⁴"


def test_the_panels_arrow_is_level_with_its_label(qapp, shell):
    from PySide6 import QtGui

    b = shell.nav.panels
    img = b.grab().toImage()
    dpr = img.devicePixelRatio()
    W, H = img.width(), img.height()
    bg = QtGui.QColor(img.pixel(1, H // 2))
    tw = b.fontMetrics().horizontalAdvance(b.text())
    text_right = ((b.width() - getattr(b, "ARROW", 0)) / 2 + tw / 2) * dpr
    ink = [(x, y) for x in range(W) for y in range(H)
           if x > text_right + 1 and abs(QtGui.QColor(img.pixel(x, y)).lightness() - bg.lightness()) > 60]
    ys = [y for _x, y in ink]
    mid = (min(ys) + max(ys)) / 2 if ys else None
    print(f"button {b.width()}x{b.height()}, text right edge {text_right / dpr:.1f}, arrow pixels {len(ink)}, "
          f"arrow middle {mid} of {H} device rows")
    assert ink and abs(mid - H / 2) <= 2 * dpr


def test_play_and_pause_are_drawn_glyphs(qapp, shell):
    play = shell.nav.play
    first = play.icon().cacheKey()
    shell.set_playing(True)
    playing = play.icon().cacheKey()
    shell.set_playing(False)
    print("play text:", repr(play.text()), "icon null:", play.icon().isNull(), "keys", first, playing)
    assert play.text() == "t" and not play.icon().isNull() and playing != first


def test_the_interface_font(qapp):
    import sys

    from PySide6 import QtGui, QtWidgets

    from explorer.ui import style

    name, pal, was = qapp.style().name(), QtGui.QPalette(qapp.palette()), QtGui.QFont(qapp.font())
    try:
        style.apply_theme(qapp, "dark")
        f = qapp.font()
        tnum = f.featureValue(QtGui.QFont.Tag("tnum")) if hasattr(f, "featureValue") else 1
        print("font:", f.families(), f.pixelSize(), QtGui.QFontInfo(f).family(), "tnum", tnum)
        if sys.platform != "darwin":
            assert f.families()[:1] == ["Noto Sans"] and f.pixelSize() == 12
        assert tnum == 1
    finally:
        qapp.setStyle(QtWidgets.QStyleFactory.create(name or "Fusion"))
        qapp.setPalette(pal)
        qapp.setFont(was)


def wear(qapp, w, name):
    from explorer.look import get_look

    w.set_look(get_look(name))
    for _ in range(5):
        qapp.processEvents()


def test_glass_panels_are_never_too_short(qapp, shell):
    from explorer.ui import glass

    wear(qapp, shell, "glass")
    shell.resize(700, 420)
    qapp.processEvents()
    shell.glass.place_panels()
    qapp.processEvents()
    least = getattr(glass, "FLOAT_MIN_H", {"spectrum": 380, "lambda_t": 240})
    h = {d.objectName(): d.height() for d in shell.glass.docks() if d.isVisible()}
    print("floating panel heights in a 420-px window:", h, "least:", least)
    assert h and all(h[n] >= m for n, m in least.items() if n in h)


def test_glass_title_is_whole_fields(qapp, shell):
    from PySide6 import QtGui

    from explorer.ui.status import SEP

    wear(qapp, shell, "glass")
    shell.resize(480, 600)
    shell.session.lock(True)
    qapp.processEvents()
    shell.update_status()
    title, full = shell.windowTitle(), shell.status.text()
    fm = QtGui.QFontMetrics(shell.font())
    print(f"title {fm.horizontalAdvance(title)} px in a {shell.width()}-px window: {title!r}")
    assert full.startswith(title) and (title == full or full[len(title):].startswith(SEP))
    assert fm.horizontalAdvance(title) <= max(120, shell.width() - 180)


def test_glass_bar_fits_a_narrow_window(qapp, shell):
    wear(qapp, shell, "glass")
    shell.resize(480, 600)
    qapp.processEvents()
    shell.glass.place_bar()
    bar, view = shell.glass.bar, shell.view.widget
    need = bar.minimumSizeHint().width()
    print(f"glass bar needs {need} px, has {bar.width()} px, view {view.width()} px")
    assert need <= bar.width()

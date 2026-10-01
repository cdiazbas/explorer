"""The window's theme (ROADMAP E5.1), offscreen: dark and light install their style, palette and plot colours; the
light image has white padding; native leaves the style alone; the main window's separators are 8 px; every styled
widget paints without a Python exception; the slider's track is filled with the accent up to its knob."""
import sys

import numpy as np
import pytest


@pytest.fixture
def restore(qapp):
    """Each test leaves the shared application as it found it."""
    from PySide6 import QtGui, QtWidgets

    name, pal = qapp.style().name(), QtGui.QPalette(qapp.palette())
    yield qapp
    qapp.setStyle(QtWidgets.QStyleFactory.create(name or "Fusion"))
    qapp.setPalette(pal)
    qapp.setProperty("explorer_light", False)
    import pyqtgraph as pg

    pg.setConfigOptions(background="k", foreground="d")


@pytest.mark.parametrize("theme, window, cls",
                         [("dark", "#2d2d2d", "MacDarkStyle"), ("light", "#ececec", "MacLightStyle")])
def test_dark_and_light_install_their_style_and_colours(restore, theme, window, cls):
    import pyqtgraph as pg
    from PySide6 import QtGui

    from explorer.ui import style

    assert style.apply_theme(restore, theme) == theme
    assert type(restore.style()).__name__ == cls and restore.style().THEME == theme
    assert restore.palette().color(QtGui.QPalette.ColorRole.Window).name() == window
    assert style.is_light() == (theme == "light")
    assert pg.getConfigOption("background") == ("w" if theme == "light" else "k")


def test_auto_is_native_on_a_mac_and_dark_elsewhere(restore, monkeypatch):
    from explorer.ui import style

    monkeypatch.setattr(sys, "platform", "linux")
    assert style.apply_theme(restore, "auto") == "dark"
    monkeypatch.setattr(sys, "platform", "darwin")
    name = restore.style().name()
    assert style.apply_theme(restore, "auto") == "native"
    assert restore.style().name() == name                # native: the style is left as it was


def test_the_style_switch_keeps_plain_fusion_with_the_palette(restore, monkeypatch):
    from PySide6 import QtGui

    from explorer.ui import style

    monkeypatch.setenv("EXPLORER_STYLE", "0")
    style.apply_theme(restore, "dark")
    assert not isinstance(restore.style(), style.MacDarkStyle)
    assert restore.palette().color(QtGui.QPalette.ColorRole.Window).name() == "#2d2d2d"


def test_an_unknown_theme_is_refused(restore):
    from explorer.ui import style

    with pytest.raises(ValueError):
        style.apply_theme(restore, "sepia")


def test_the_light_image_has_white_padding_and_surround(restore):
    from explorer.ui.imageview import ImageView

    v = ImageView(light=True)
    lut = v.img.lut
    assert lut is not None and tuple(lut[0]) == (255, 255, 255) and tuple(lut[1]) == (0, 0, 0)
    assert tuple(lut[255]) == (255, 255, 255)
    assert ImageView().img.lut is None                  # dark: pyqtgraph's grey, padding black


def test_separators_are_8_px_to_grab(restore):
    from PySide6 import QtWidgets

    from explorer.ui import style

    style.apply_theme(restore, "dark")
    w = QtWidgets.QMainWindow()
    assert style.separators(w) is not None
    assert w.style().pixelMetric(QtWidgets.QStyle.PixelMetric.PM_DockWidgetSeparatorExtent) == style.SEPARATOR_GRAB


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_every_styled_widget_paints_without_an_exception(restore, theme):
    from PySide6 import QtCore, QtWidgets

    from explorer.ui import style

    style.apply_theme(restore, theme)
    errors = []
    hook, sys.excepthook = sys.excepthook, lambda t, e, tb: errors.append(f"{t.__name__}: {e}")
    try:
        win = QtWidgets.QMainWindow()
        tb = win.addToolBar("t")
        slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        slider.setValue(40)
        combo = QtWidgets.QComboBox()
        combo.addItems(["I", "Q", "U", "V"])
        spin = QtWidgets.QSpinBox()
        check = QtWidgets.QCheckBox("fixed")
        check.setChecked(True)
        play = QtWidgets.QToolButton()
        play.setText("▶ t")
        play.setCheckable(True)
        play.setChecked(True)
        for w in (slider, combo, spin, check, play):
            tb.addWidget(w)
        tb.addSeparator()
        dock = QtWidgets.QDockWidget("Spectrum", win)
        dock.setWidget(QtWidgets.QLabel("x"))
        win.addDockWidget(QtCore.Qt.DockWidgetArea.RightDockWidgetArea, dock)
        win.statusBar().showMessage("status")
        win.setCentralWidget(QtWidgets.QLabel("image"))
        style.separators(win)
        win.resize(700, 400)
        win.show()
        restore.processEvents()
        assert not win.grab().isNull()
        menu = QtWidgets.QMenu()
        menu.addAction("a").setCheckable(True)
        menu.addSeparator()
        menu.addAction("b")
        menu.resize(menu.sizeHint())
        assert not menu.grab().isNull()
        win.close()
    finally:
        sys.excepthook = hook
    assert errors == []


def test_the_slider_track_is_filled_with_the_accent_up_to_the_knob(restore):
    from PySide6 import QtCore, QtGui, QtWidgets

    from explorer.ui import style

    style.apply_theme(restore, "dark")
    s = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
    s.setRange(0, 100)
    s.setValue(80)
    s.resize(200, 24)
    img = s.grab().toImage().convertToFormat(QtGui.QImage.Format.Format_RGB32)
    row = img.height() // 2
    px = np.array([QtGui.QColor(img.pixel(x, row)).getRgb()[:3] for x in range(img.width())])
    accent = np.array(QtGui.QColor(style.ACCENT).getRgb()[:3])
    near = np.abs(px - accent).sum(1) < 30
    assert near[img.width() // 4: img.width() // 2].all()   # filled well before the knob (at 80 %)
    assert not near[int(img.width() * 0.92):].any()         # and not after it

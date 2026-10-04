"""The glass look (ROADMAP E5.12), offscreen: the controls in a glass bar over the image, the panels floating beside
the window as smoked glass with their own titles, the status line hidden, the readout in the title, the markers in
the accent, the image to the window's edges; I hides and shows the panels, the bar's 2x2 button and key 5 agree, the
bar hides when idle and comes back on a move; the bar's glass is the image under it, blurred, and takes the new
image once it rests; the window is as wide as the image; out of it, everything as it was."""
import time

import numpy as np
import pytest

from explorer.testing import synth
from explorer.ui.status import SEP

SHAPE = (6, 4, 21, 96, 80)


def spin(qapp, until, timeout=10.0):
    end = time.perf_counter() + timeout
    while not until() and time.perf_counter() < end:
        qapp.processEvents()
        time.sleep(0.002)
    return until()


@pytest.fixture(scope="module")
def cube(tmp_path_factory):
    return synth.write_dataset(tmp_path_factory.mktemp("glass"), "c", shape=SHAPE, icube=False)["im"]


@pytest.fixture
def shell(qapp, cube):
    from PySide6 import QtGui, QtWidgets

    from explorer.data.dataset import Dataset
    from explorer.ui import style
    from explorer.ui.shell import Shell

    name, pal = qapp.style().name(), QtGui.QPalette(qapp.palette())
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


def wear(qapp, w, name):
    from explorer.look import get_look

    w.set_look(get_look(name))                          # not through M: an exception in a shortcut is only printed
    for _ in range(5):
        qapp.processEvents()


def test_in_glass(qapp, shell):
    from explorer.ui import glass
    from explorer.ui.glass import PanelTitle

    w = shell
    wear(qapp, w, "glass")
    g = w.glass
    assert g is not None and not w.nav.tb.isVisible() and g.bar.isVisible()
    inside = g.bar.findChildren(type(w.nav.sliders["t"]))
    assert set(inside) == set(w.nav.sliders.values())
    for x in (w.nav.play, w.nav.fps, w.nav.panels, w.nav.reset, w.nav.help, w.nav.drop):
        assert g.bar.isAncestorOf(x) and x.isVisible()
    assert not w.statusBar().isVisible()
    assert w.centralWidget().layout().contentsMargins().left() == 0
    assert spin(qapp, lambda: all(d.isFloating() for d in g.docks()))
    assert all(isinstance(d.titleBarWidget(), PanelTitle) for d in g.docks())
    assert w.colour_key.pos().y() == glass.MARGIN                          # the key at the top: the bar is below
    acc = glass.accent()
    assert qapp.style().SLIDER == acc and w.view.reticle.colour == acc
    assert w.spectra.lines[0].pen.color() == acc and w.lambda_t.t_line.pen.color() == acc


def test_the_readout_is_the_title_while_locked(qapp, shell):
    w = shell
    wear(qapp, w, "glass")
    w.session.lock(True)

    def whole_fields():                                 # the readout's first fields, as many as the title has room for
        t, full = w.windowTitle(), w.status.text()
        return bool(full) and full.startswith(t) and (t == full or full[len(t):].startswith(SEP))
    assert spin(qapp, whole_fields), (w.windowTitle(), w.status.text())
    w.session.lock(False)
    assert spin(qapp, lambda: w.windowTitle() == "c_im.fits")


def test_i_hides_and_shows_the_panels_and_all_agrees_with_key_5(qapp, shell):
    from PySide6 import QtWidgets

    w = shell
    wear(qapp, w, "glass")
    g = w.glass
    assert spin(qapp, lambda: all(d.isFloating() for d in g.docks()))
    w.toggle_panels()
    assert all(d.isHidden() for d in g.docks())
    w.toggle_panels()
    assert not any(d.isHidden() for d in g.docks())
    # one name and one control for the four Stokes: All in the Stokes control, as outside glass (no 2x2 button)
    texts = [b.text() for b in g.bar.findChildren(QtWidgets.QAbstractButton)]
    assert not [t for t in texts if "2" in t and "×" in t], f"the bar's buttons: {texts}"
    w.nav.drop.segments.group.button(w.session.sizes["s"]).click()
    seen = dict(grid=w.grid is not None and w.grid.isVisible(), drop=w.nav.drop.text())
    assert seen == dict(grid=True, drop="Stokes All ▾"), seen
    w.toggle_grid()                                      # key 5
    seen = dict(grid=w.grid.isVisible(), drop=w.nav.drop.text())
    assert not seen["grid"] and seen["drop"] != "Stokes All ▾", seen


def test_the_bar_hides_when_idle_and_comes_back(qapp, shell, monkeypatch):
    from PySide6 import QtCore, QtGui, QtWidgets

    from explorer.ui import glass

    monkeypatch.setattr(glass, "HIDE_MS", 150)
    w = shell
    wear(qapp, w, "glass")
    bar = w.glass.bar
    assert spin(qapp, lambda: not bar.isVisible(), timeout=3)
    vp = w.view.widget.viewport()
    p = QtCore.QPointF(vp.width() / 2, vp.height() / 2)
    ev = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseMove, p, vp.mapToGlobal(p), QtCore.Qt.MouseButton.NoButton,
                           QtCore.Qt.MouseButton.NoButton, QtCore.Qt.KeyboardModifier.NoModifier)
    QtWidgets.QApplication.sendEvent(vp, ev)
    assert bar.isVisible()


def grey(pm):
    """A pixmap's pixels in grey levels, as floats."""
    from PySide6 import QtGui

    img = pm.toImage().convertToFormat(QtGui.QImage.Format.Format_Grayscale8)
    a = np.frombuffer(img.constBits(), np.uint8).reshape(img.height(), img.bytesPerLine())[:, :img.width()]
    return a.astype(float)


def under(w, bar):
    """What the image view shows under the bar (its viewport, so not the bar), blurred as the glass blurs it."""
    from PySide6 import QtCore

    vp = w.view.widget.viewport()
    r = QtCore.QRect(vp.mapFrom(w.view.widget, bar.pos()), bar.size())
    S, A = QtCore.Qt.TransformationMode.SmoothTransformation, QtCore.Qt.AspectRatioMode.IgnoreAspectRatio
    return grey(vp.grab(r).scaled(max(1, r.width() // 8), max(1, r.height() // 8), A, S).scaled(r.size(), A, S))


def test_the_bar_is_the_image_under_it_and_follows_it_once_it_rests(qapp, shell, monkeypatch):
    """QWidget.render(view) paints the window's background only, the image living in the viewport: the first glass
    was a flat grey patch (grey 45, deviation 0 against 52.7 for the image). The scene is rendered instead, and drawn
    again once the image has rested REST_MS (the prototype's F78, app/look_glass.py:102-111 and 127-135)."""
    from explorer.ui import glass

    monkeypatch.setattr(glass, "HIDE_MS", 60000)         # shown all along: a hidden bar paints nothing
    w = shell
    wear(qapp, w, "glass")
    g = w.glass
    bar = g.bar
    assert spin(qapp, lambda: all(d.isFloating() for d in g.docks()))
    assert spin(qapp, lambda: bar._backdrop is not None and not g.changing), dict(changing=g.changing)
    first = bar._backdrop
    a0 = grey(first)
    seen = dict(std=round(float(a0.std()), 2), off=round(float(np.abs(a0 - under(w, bar)).mean()), 2))
    assert seen["std"] > 5 and seen["off"] < 1, seen       # measured: std 33, off 0.0
    t = (w.scheduler.img_idx[0] + 3) % SHAPE[0]
    w.session.set_index("t", t)
    assert spin(qapp, lambda: w.scheduler.img_idx[0] == t and not g.changing and bar._backdrop is not None
                and bar._backdrop is not first, timeout=3), dict(t=w.scheduler.img_idx, changing=g.changing,
                                                                  same=bar._backdrop is first)
    a1 = grey(bar._backdrop)
    seen = dict(moved=round(float(np.abs(a1 - a0).mean()), 2), off=round(float(np.abs(a1 - under(w, bar)).mean()), 2))
    assert seen["moved"] > 1 and seen["off"] < 1, seen     # measured: moved 4.5, off 0.0


def test_the_window_is_as_wide_as_the_image(qapp, shell):
    """At the image's height, the window as wide as the image: before, a 1100-px window held a 762-px image between
    black bands. Here the screen (800 x 800 offscreen) leaves no room for the panels beside it, so the window is
    narrowed to the least width and lowered to keep the image's shape (the prototype's F86,
    app/look_glass.py:511-531)."""
    from PySide6 import QtCore

    w = shell
    wear(qapp, w, "glass")
    assert spin(qapp, lambda: all(d.isFloating() for d in w.glass.docks()))

    def seen():
        view = w.view.widget
        img = view.mapFromScene(w.view.img.sceneBoundingRect()).boundingRect()
        return dict(view=view.size(), image=img.size(), window=w.geometry())

    def fits():
        s = seen()
        return abs(s["image"].width() - s["view"].width()) <= 2 and abs(s["image"].height() - s["view"].height()) <= 2
    assert spin(qapp, fits, timeout=3), dict(seen(), screen=qapp.primaryScreen().availableGeometry(),
                                              was=QtCore.QSize(1000, 700))


def test_out_of_glass_everything_as_it_was(qapp, shell):
    w = shell
    tb = w.nav.tb
    def shown():                                        # the toolbar's visible actions, in order (a separator's
        return [a for a in tb.actions() if a.isVisible()]   # widget is made anew when its action comes back)
    before = dict(actions=shown(), geometry=w.geometry(),
                  titles=[d.titleBarWidget() for d in (w.spec_dock, w.lt_dock)],
                  panels=[d.geometry() for d in (w.spec_dock, w.lt_dock)], image=w.view.widget.size(),
                  margins=w.centralWidget().layout().contentsMargins(), title=w.windowTitle(),
                  widths={a: (s.minimumWidth(), s.maximumWidth()) for a, s in w.nav.sliders.items()})
    wear(qapp, w, "glass")
    assert spin(qapp, lambda: all(d.isFloating() for d in w.glass.docks()))
    w.session.lock(True)
    qapp.processEvents()
    wear(qapp, w, "classic")
    assert w.glass is None and tb.isVisible() and w.statusBar().isVisible()
    assert shown() == before["actions"]                 # (the modern look's Stokes drop-down stays, hidden)
    assert all(tb.isAncestorOf(s) for s in w.nav.sliders.values())
    assert spin(qapp, lambda: {a: (s.minimumWidth(), s.maximumWidth()) for a, s in w.nav.sliders.items()}
                == before["widths"])
    assert spin(qapp, lambda: not w.spec_dock.isFloating() and not w.lt_dock.isFloating())
    assert [d.titleBarWidget() for d in (w.spec_dock, w.lt_dock)] == before["titles"]
    assert w.centralWidget().layout().contentsMargins() == before["margins"]
    assert w.windowTitle() == before["title"] and w.geometry() == before["geometry"]
    # the panels as they were, not laid out again in glass's narrow window (414x245 where 520x343 had been)
    assert spin(qapp, lambda: [d.geometry() for d in (w.spec_dock, w.lt_dock)] == before["panels"])
    assert w.view.widget.size() == before["image"]
    assert w.colour_key.pos().y() > w.view.widget.height() // 2            # back at its own corner


def test_the_2x2_view_stays_under_the_bar_with_its_reticles_in_the_accent(qapp, shell):
    from explorer.ui import glass

    w = shell
    wear(qapp, w, "glass")
    w.toggle_grid()                                      # made in glass: its reticles too in the accent
    assert w.grid is not None and w.grid.isVisible()
    bar = w.glass.bar
    bar.show()
    hit = w.view.widget.childAt(bar.geometry().center())
    assert hit is bar or bar.isAncestorOf(hit)           # look_glass.py:887, the bar raised over the grid
    assert all(v.reticle.colour == glass.accent() for v in w.grid.views)


def test_what_is_on_takes_the_accent_with_white_text_readable(qapp, shell):
    from explorer.ui import glass, style

    w = shell
    st = qapp.style()
    wear(qapp, w, "modern")                              # the Stokes drop-down is made by the modern look
    before = (style.selected().name(), w.nav.drop.segments.styleSheet())
    wear(qapp, w, "glass")
    sel = style.selected()
    assert st.ACC == glass.accent() and sel != glass.accent()
    assert glass.contrast_white(sel) >= 4.5 and sel.hue() == glass.accent().hue()
    assert f"background: {sel.name()};" in w.nav.drop.segments.styleSheet()
    wear(qapp, w, "modern")
    assert (style.selected().name(), w.nav.drop.segments.styleSheet()) == before


def test_started_in_glass_classic_comes_as_at_a_fresh_start(qapp, cube):
    """The last session closed in glass, so this one starts in it: out of it, classic as a fresh classic start (the
    prototype starts every look from its own layout), not the window as it was before its first show (640x480,
    the image 62 px wide beside 560-px panels)."""
    from PySide6 import QtCore, QtGui, QtWidgets

    from explorer.data.dataset import Dataset
    from explorer.look import get_look
    from explorer.ui import docks, style
    from explorer.ui.shell import Shell

    name, pal = qapp.style().name(), QtGui.QPalette(qapp.palette())
    style.apply_theme(qapp, "dark")
    first = docks.first_geometry(qapp)
    seen = {}
    try:
        for look in ("classic", "glass"):
            ds = Dataset.open(cube)
            w = Shell(ds, title="c_im.fits", look=get_look(look))
            w.setGeometry(first if look == "classic" else QtCore.QRect(60, 50, 700, 600))
            w.show()
            assert spin(qapp, lambda w=w: "lambda_t" in w.last)
            if look == "glass":
                assert spin(qapp, lambda w=w: all(d.isFloating() for d in w.glass.docks()))
                wear(qapp, w, "classic")
            spin(qapp, lambda: False, timeout=0.5)
            seen[look] = (w.geometry(), [d.geometry() for d in (w.spec_dock, w.lt_dock)], w.view.widget.size())
            w.close()
            ds.close()
    finally:
        qapp.setStyle(QtWidgets.QStyleFactory.create(name or "Fusion"))
        qapp.setPalette(pal)
    assert seen["glass"] == seen["classic"], seen



def test_the_bar_buttons_are_flat_whatever_the_style_and_given_back(qapp, shell):
    """Out of a toolbar a Mac's native style drew every button of the bar in a grey box (seen by the user): in glass
    they carry a sheet of their own, flat; out of it, the sheet they had."""
    w = shell
    wear(qapp, w, "modern")
    nav = w.nav
    buttons = [nav.play, nav.panels, nav.reset, nav.help, nav.drop]
    before = [b.styleSheet() for b in buttons]
    wear(qapp, w, "glass")
    for b in buttons:
        assert "border: none" in b.styleSheet() and "background: transparent" in b.styleSheet()
    assert nav.drop.segments.styleSheet().count("QToolButton {") == 1     # the segments keep their own
    wear(qapp, w, "modern")
    assert [b.styleSheet() for b in buttons] == before


def test_started_in_glass_its_panel_titles_survive_the_chrome(qapp, cube, monkeypatch):
    """The window wears its look when it is made, and the chrome (app.py) puts the dock titles on after: on Linux and
    through the bridge they replaced glass's titles, a grey bar under the manager's (seen by the user). The
    prototype puts the titles on first (startup.py:145), then the look. Out of glass, the chrome's titles."""
    from PySide6 import QtGui, QtWidgets

    from explorer.data.dataset import Dataset
    from explorer.look import get_look
    from explorer.ui import app as appmod
    from explorer.ui import style, titlebar
    from explorer.ui.glass import PanelTitle
    from explorer.ui.shell import Shell

    monkeypatch.setenv(titlebar.ENV, "wm")             # the bridge with the manager's frames: dock titles, no bar
    name, pal = qapp.style().name(), QtGui.QPalette(qapp.palette())
    style.apply_theme(qapp, "dark")
    ds = Dataset.open(cube)
    w = Shell(ds, title="c_im.fits", look=get_look("glass"))
    try:
        appmod.chrome(qapp, w, None, lambda d: None, bridge=True)
        assert all(isinstance(d.titleBarWidget(), PanelTitle) for d in w.glass.docks())
        w.show()
        assert spin(qapp, lambda: "lambda_t" in w.last)
        wear(qapp, w, "classic")
        assert all(type(d.titleBarWidget()) is titlebar.DockTitle for d in (w.spec_dock, w.lt_dock))
    finally:
        w.close()
        ds.close()
        qapp.setStyle(QtWidgets.QStyleFactory.create(name or "Fusion"))
        qapp.setPalette(pal)


def _chrome(qapp, w, monkeypatch):
    """Our title bar and edges on the shell, as ui.app.start puts them on (app.chrome), wherever the test runs."""
    from explorer.platform.display import Display
    from explorer.platform.plan import DisplayPlan
    from explorer.ui import app, titlebar

    monkeypatch.setattr(titlebar, "wanted", lambda *a, **k: True)          # a local Mac keeps its own
    disp = Display(DisplayPlan("offscreen"))
    shown = w.isVisible()
    bar = app.chrome(qapp, w, disp.ops(w), disp.ops, bridge=False)
    if shown:                                            # frameless now: a change of flags hides a shown window (the
        w.show()                                         # app puts the bar on before showing it)
    qapp.processEvents()
    return bar


def _rows(widget):
    """The widget's column of pixels 40 px from its right edge, as (r, g, b) from top to bottom."""
    from PySide6 import QtGui

    img = widget.grab().toImage()
    x = img.width() - int(40 * img.devicePixelRatio())
    return [QtGui.QColor(img.pixel(x, y)).getRgb()[:3] for y in range(img.height())]


def test_the_title_bar_and_edge_take_the_glass_light_and_give_it_back(qapp, shell, monkeypatch):
    from PySide6 import QtGui

    from explorer.ui import glass

    w = shell
    bar = _chrome(qapp, w, monkeypatch)
    before = bar.palette().color(QtGui.QPalette.ColorRole.Window).name()
    wear(qapp, w, "glass")
    rows = _rows(bar)
    print("title bar in glass, top to bottom:", [r[0] for r in rows], "edge hud:", bar.corners.line.hud)
    assert bar.hud == glass.accent() and bar.corners.line.hud == glass.accent()
    assert rows[0][0] > rows[-1][0] and rows[-1] == (0, 0, 0)     # light from above, down to the image's black
    wear(qapp, w, "classic")
    after = bar.palette().color(QtGui.QPalette.ColorRole.Window).name()
    print("title bar colour before glass, after it:", before, after)
    assert bar.hud is None and bar.corners.line.hud is None and after == before


def test_started_in_glass_its_title_bar_takes_the_light(qapp, cube, monkeypatch):
    """The title bar is made after the look when the window starts in glass (ui.app.start): the shell has it before
    glass is told the titles changed."""
    from PySide6 import QtGui, QtWidgets

    from explorer.data.dataset import Dataset
    from explorer.look import get_look
    from explorer.ui import glass, style
    from explorer.ui.shell import Shell

    name, pal = qapp.style().name(), QtGui.QPalette(qapp.palette())
    style.apply_theme(qapp, "dark")
    ds = Dataset.open(cube)
    w = Shell(ds, title="c_im.fits", look=get_look("glass"))
    try:
        bar = _chrome(qapp, w, monkeypatch)
        colour = bar.palette().color(QtGui.QPalette.ColorRole.Window)
        print("started in glass: title bar hud", bar.hud, "colour", colour.name())
        assert bar.hud == glass.accent()
        assert colour == glass.TITLE["dark"]
    finally:
        w.close()
        ds.close()
        qapp.setStyle(QtWidgets.QStyleFactory.create(name or "Fusion"))
        qapp.setPalette(pal)


def _panel_pixels(qapp, w):
    from PySide6 import QtGui

    from explorer.ui import glass

    floating = spin(qapp, lambda: all(d.isFloating() for d in w.glass.docks()))
    print("panels:", [(d.objectName(), d.isFloating(), d.isVisible(), d.geometry().getRect()) for d in w.glass.docks()],
          "window visible:", w.isVisible(), "glass on:", w.glass.on)
    assert floating
    d = w.spec_dock
    img = d.grab().toImage()
    k = img.devicePixelRatio()
    top = QtGui.QColor(img.pixel(img.width() // 2, int(1.75 * k))).getRgb()[:3]       # the accent's light
    body = QtGui.QColor(img.pixel(int((glass.RADIUS_PANEL + 4) * k), img.height() - int(8 * k))).getRgb()[:3]
    return top, body


def test_the_panels_are_the_images_colour_with_the_accent_light(qapp, shell):
    w = shell
    wear(qapp, w, "glass")
    top, body = _panel_pixels(qapp, w)
    print("dark panel: top edge", top, "body near the bottom", body)
    assert max(body) <= 12                               # near-black, as the image
    assert top[0] > 150 and top[0] > top[2] + 80         # orange along the top edge


def test_the_light_theme_has_the_same_on_white(qapp, cube, monkeypatch):
    from PySide6 import QtGui, QtWidgets

    from explorer.data.dataset import Dataset
    from explorer.ui import style
    from explorer.ui.shell import Shell

    name, pal = qapp.style().name(), QtGui.QPalette(qapp.palette())
    style.apply_theme(qapp, "light")
    ds = Dataset.open(cube)
    w = Shell(ds, title="c_im.fits")
    try:
        w.setGeometry(60, 50, 1000, 700)
        w.show()
        assert spin(qapp, lambda: w.first_image_s is not None)
        bar = _chrome(qapp, w, monkeypatch)
        wear(qapp, w, "glass")
        top, body = _panel_pixels(qapp, w)
        rows = _rows(bar)
        print("light panel: top edge", top, "body", body, "| title bar top to bottom:", [r[0] for r in rows])
        assert min(body) >= 243 and top[0] > 120 and top[2] < 90
        assert rows[0][0] < rows[-1][0] and rows[-1] == (255, 255, 255)   # a shade from above, down to white
    finally:
        w.close()
        ds.close()
        qapp.setStyle(QtWidgets.QStyleFactory.create(name or "Fusion"))
        qapp.setPalette(pal)

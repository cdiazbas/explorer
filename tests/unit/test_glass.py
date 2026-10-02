"""The glass look (ROADMAP E5.12), offscreen: the controls in a glass bar over the image, the panels floating beside
the window as smoked glass with their own titles, the status line hidden, the readout in the title, the markers in
the accent, the image to the window's edges; I hides and shows the panels, the bar's 2x2 button and key 5 agree, the
bar hides when idle and comes back on a move; out of it, everything as it was."""
import time

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
    assert spin(qapp, lambda: w.windowTitle() == w.status.text() and w.status.text())
    w.session.lock(False)
    assert spin(qapp, lambda: w.windowTitle() == "c_im.fits")


def test_i_hides_and_shows_the_panels_and_2x2_agrees_with_key_5(qapp, shell):
    w = shell
    wear(qapp, w, "glass")
    g = w.glass
    assert spin(qapp, lambda: all(d.isFloating() for d in g.docks()))
    w.toggle_panels()
    assert all(d.isHidden() for d in g.docks())
    w.toggle_panels()
    assert not any(d.isHidden() for d in g.docks())
    g.grid_btn.click()
    assert w.grid is not None and w.grid.isVisible()
    w.toggle_grid()                                      # key 5
    assert not w.grid.isVisible() and not g.grid_btn.isChecked()


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


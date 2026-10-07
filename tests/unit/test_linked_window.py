"""Linked cubes in the window, offscreen (ROADMAP E8.1): the images side by side, the same size, showing the same
region; a tab per cube in the spectra and lambda-t panels, named as the cube, only the one in front read; its image
and panels following the cursor and t at its own lambda; a map with no lambda has an image and no tabs; the start's
plan says why a cube is left out. Each test prints what it measured."""
import time

import numpy as np
import pytest

from explorer.testing import synth

SHAPE = (3, 4, 5, 48, 40)


def spin(qapp, until, timeout=10.0):
    end = time.perf_counter() + timeout
    while not until() and time.perf_counter() < end:
        qapp.processEvents()
        time.sleep(0.002)
    return until()


def lp_map(path, n, ny=SHAPE[3], nx=SHAPE[4]):
    with open(path, "wb") as f:
        f.write(f"datatype=4 (float), dims=3, nx={nx}, ny={ny}, nt={n}, endian=l".encode().ljust(512, b"\0"))
        f.write(np.random.default_rng(n).normal(size=(n, ny, nx)).astype("<f4").tobytes())
    return path


@pytest.fixture(scope="module")
def cubes(tmp_path_factory):
    d = tmp_path_factory.mktemp("linked")
    main = synth.write_dataset(d, "main", shape=SHAPE, icube=False)["im"]
    other = synth.write_dataset(d, "other", shape=(SHAPE[0], SHAPE[1], 7, SHAPE[3], SHAPE[4]), seed=4, icube=False,
                                sp=False)["im"]
    return main, other, lp_map(d / "Blos.map.fcube", SHAPE[0])


@pytest.fixture
def window(qapp, cubes):
    from explorer.data.dataset import Dataset
    from explorer.ui.shell import Shell

    main, other, blos = cubes
    ds = Dataset.open(main)
    linked = [Dataset.open(other, executors=ds.executors), Dataset.open(blos, axes="t", executors=ds.executors)]
    w = Shell(ds, linked=linked)
    w.resize(1400, 600)
    w.show()
    assert spin(qapp, lambda: w.first_image_s is not None and all(c.scheduler.img is not None for c in w.linked))
    w.reset_sizes()
    qapp.processEvents()
    yield w, qapp
    w.close()
    for d in linked:
        d.close()
    ds.close()


def test_the_images_are_side_by_side_the_same_size_and_region(window):
    from PySide6 import QtCore

    w, qapp = window
    views = [w.view] + [c.view for c in w.linked]
    sizes = [(v.widget.width(), v.widget.height()) for v in views]
    print("image sizes", sizes, "names", [c.name for c in w.linked], "main", w.image_title.text)
    assert max(s[0] for s in sizes) - min(s[0] for s in sizes) <= 1 and len({s[1] for s in sizes}) == 1
    w.view.vb.setRange(QtCore.QRectF(5, 6, 10, 10), padding=0)          # zoom the main image
    qapp.processEvents()
    rects = [v.vb.viewRect() for v in views]
    print("regions", [(round(r.x(), 2), round(r.y(), 2), round(r.width(), 2)) for r in rects])
    for r in rects[1:]:
        assert abs(r.x() - rects[0].x()) < 1e-6 and abs(r.width() - rects[0].width()) < 1e-6


def test_the_linked_panels_are_tabs_named_in_english_and_only_the_front_one_reads(window):
    w, qapp = window
    tabs = {"spectra": w.spec_tabs, "lambda_t": w.lt_tabs}
    names = {k: [t.tabText(i) for i in range(t.count())] for k, t in tabs.items()}
    print("docks", w.spec_dock.windowTitle(), w.lt_dock.windowTitle(), "tabs", names,
          "panels", sorted(w.session.state.panels))
    assert names == {"spectra": ["main_im", "other_im"], "lambda_t": ["main_im", "other_im"]}   # the map has none
    assert w.linked[1].name == "Blos.map" and w.linked[1].spectra is None
    assert {"spectra", "lambda_t"} <= w.session.state.panels and "spectra:1" not in w.session.state.panels
    w.spec_tabs.setCurrentIndex(1)                      # the linked cube's spectra in front: only they are read
    qapp.processEvents()
    print("after the tab", sorted(w.session.state.panels))
    assert "spectra:1" in w.session.state.panels and "spectra" not in w.session.state.panels
    w.spec_dock.close()                                 # the panel closed: neither
    qapp.processEvents()
    assert not {"spectra", "spectra:1"} & w.session.state.panels
    w.spec_dock.show()
    qapp.processEvents()
    assert "spectra:1" in w.session.state.panels


def test_the_linked_cube_follows_cursor_and_t_at_its_own_lambda(window):
    from PySide6 import QtCore

    w, qapp = window
    other, blos = w.linked
    w.spec_tabs.setCurrentIndex(1)                      # its spectrum in front: read for the cursor
    qapp.processEvents()
    w.view._moved(w.view.vb.mapViewToScene(QtCore.QPointF(15.5, 22.5)))
    assert spin(qapp, lambda: other.view.hl.value() == 22.5 and other.view.vl.value() == 15.5)
    w.session.set_index("t", 2)
    w.session.set_index("l", 1)                         # the main cube's lambda
    assert spin(qapp, lambda: other.scheduler.img_idx == (2, 0, 3) and blos.scheduler.img_idx == (2,))
    p = other.spectra.plots[0]
    x = float(other.spectra.xl[5])
    other.spectrum_pick(p.vb.mapViewToScene(QtCore.QPointF(x, 0)))  # its own lambda, on its own spectrum
    assert spin(qapp, lambda: other.scheduler.img_idx == (2, 0, 5))
    print("main", w.scheduler.img_idx, "linked", other.scheduler.img_idx, "map", blos.scheduler.img_idx,
          "own", w.session.state.own)
    assert w.session.state.l == 1 and w.scheduler.img_idx == (2, 0, 1)
    assert spin(qapp, lambda: other.spectra._l == 5 and w.spectra._l == 1)      # each its own marker


def test_the_start_leaves_out_what_cannot_be_linked_and_says_why(cubes, tmp_path, capsys):
    from explorer.ui.app import plan_links

    main, other, blos = cubes
    wide = lp_map(tmp_path / "wide.fcube", SHAPE[0], nx=SHAPE[4] + 2)
    links = plan_links(main, [other, wide, blos])
    err = capsys.readouterr().err
    print(err)
    assert [lk.path for lk in links] == [str(other), str(blos)] and [lk.axes for lk in links] == [None, "t"]
    assert "not linked: wide.fcube" in err and "pixels" in err


def test_after_glass_and_back_every_image_shows_the_same_region(window):
    """Glass takes the image's margins off and gives them back: taken from the main image only, with the views
    linked by pyqtgraph (setXLink, setYLink), a linked image was left on another region (real cubes, bellatrix: Blos
    57-1974 in x against 0-2031, the locked cursor 18 rows lower)."""
    from PySide6 import QtCore

    from explorer.look import get_look

    w, qapp = window
    w.session.hover(30, 25)
    w.session.lock(True)
    views = [w.view] + [c.view for c in w.linked]
    for look in ("glass", "classic"):
        w.set_look(get_look(look))
        spin(qapp, lambda: False, timeout=0.5)
        sizes = [(v.widget.width(), v.widget.height()) for v in views]
        print(look, "image sizes", sizes)
        # glass fits the window: Qt kept the panels' widths and the main image took the change (80 against 527 px)
        assert max(s[0] for s in sizes) - min(s[0] for s in sizes) <= 1 and len({s[1] for s in sizes}) == 1
    got = []
    for v in views:
        r = v.vb.viewRect()
        p = v.vb.mapViewToScene(QtCore.QPointF(25.5, 30.5))
        got.append(((round(r.x(), 2), round(r.y(), 2), round(r.width(), 2)), (round(p.x(), 1), round(p.y(), 1)),
                    (v.vb.width(), v.vb.height())))
    print("region, cursor on screen, box:", got)
    assert len({g[2] for g in got}) == 1                                # the same box (margins)
    for g in got[1:]:
        assert abs(g[1][0] - got[0][1][0]) <= 1 and abs(g[1][1] - got[0][1][1]) <= 1


def test_a_linked_image_is_a_panel_that_floats_docks_and_closes_reading_nothing(window):
    """Its image could not be taken out of the window (the user, 2026-10-06): a panel of its own, titled with its
    name as the main image is; floated it shows the same region; closed, no image is read for it."""
    from PySide6 import QtCore

    w, qapp = window
    other, blos = w.linked
    titles = [w.image_title.text] + [c.title.text for c in w.linked]
    heights = [w.image_title.height()] + [c.title.height() for c in w.linked]
    print("titles", titles, "heights", heights, "docks", [c.dock.objectName() for c in w.linked])
    assert titles == ["main_im", "other_im", "Blos.map"] and len(set(heights)) == 1
    assert all(not b.isVisible() for c in w.linked for b in c.title.buttons)       # nothing at rest
    blos.dock.setFloating(True)
    spin(qapp, lambda: False, timeout=0.3)
    w.view.vb.setRange(QtCore.QRectF(4, 6, 12, 12), padding=0)
    spin(qapp, lambda: False, timeout=0.3)
    r0, r1 = w.view.vb.viewRect(), blos.view.vb.viewRect()
    print("floating: main", r0.getRect(), "blos", r1.getRect())
    assert abs(r0.center().x() - r1.center().x()) < 0.5 and abs(r0.center().y() - r1.center().y()) < 0.5
    blos.dock.setFloating(False)
    blos.dock.close()
    spin(qapp, lambda: False, timeout=0.2)
    assert "image:2" not in w.session.state.panels
    idx = blos.scheduler.img_idx
    w.session.set_index("t", (w.session.state.t + 1) % 3)
    assert spin(qapp, lambda: w.scheduler.img_idx[0] == w.session.state.t)
    spin(qapp, lambda: False, timeout=0.3)
    print("closed: blos image", idx, "->", blos.scheduler.img_idx, "main", w.scheduler.img_idx)
    assert blos.scheduler.img_idx == idx                                # nothing read while closed
    blos.dock.show()
    assert spin(qapp, lambda: blos.scheduler.img_idx == (w.session.state.t,))      # shown: the image of now


def test_the_slit_is_on_every_image_and_can_be_drawn_on_any(window):
    """A slit drawn on the main image showed on it alone (the user, 2026-10-06): it is on every image, as on the 2x2
    view's panels, and a click on a linked image in the slit mode adds a point there."""
    from PySide6 import QtCore

    w, qapp = window
    tool = w.slit_tool
    w.session.store.set(path=((5.5, 6.5), (30.5, 40.5)))
    spin(qapp, lambda: False, timeout=0.2)
    drawn = [m.line.getData()[0] is not None and len(m.line.getData()[0]) > 0 for m in tool.marks]
    print("slit drawn on", len(tool.marks), "images:", drawn)
    assert len(tool.marks) == 3 and all(drawn)

    class Click:                                        # pyqtgraph's scene click, as the slit tool reads it
        def __init__(self, vb, x, y):
            self._p = vb.mapViewToScene(QtCore.QPointF(x, y))

        def button(self):
            return QtCore.Qt.MouseButton.LeftButton

        def double(self):
            return False

        def scenePos(self):
            return self._p

    w.set_slit_mode(True)
    other = w.linked[0]
    other._click(Click(other.view.vb, 10.2, 12.7))
    print("points after a click on the linked image:", tool.pts, "locked:", w.session.state.locked)
    assert len(tool.pts) == 1 and not w.session.state.locked
    w.set_slit_mode(False)


def test_after_the_window_changes_size_the_images_are_one_width(window):
    """reset_sizes resized the spectra, then shared the images' widths out from widths Qt had not applied yet: the
    main image 223 px against 362 for each linked one (real cubes, the start's size, bellatrix)."""
    w, qapp = window
    for width in (1000, 1700):
        w.resize(width, 700)
        spin(qapp, lambda: False, timeout=0.3)
        w.reset_sizes()
        qapp.processEvents()
        sizes = [w.view.widget.width()] + [c.view.widget.width() for c in w.linked]
        print("window", width, "image widths", sizes)
        assert max(sizes) - min(sizes) <= 2


def test_the_titles_are_thin_and_in_glass_on_the_image_s_colour(window):
    """The image titles thin in every look (the user, 2026-10-06: they took a zoomed image's height), and in glass on
    its title bar's colour (black in the dark theme), their own again out of it."""
    from explorer.look import get_look
    from explorer.ui import glass

    w, qapp = window
    titles = [w.image_title] + [c.title for c in w.linked]
    print("title heights", [t.height() for t in titles], "font px", w.image_title.fontMetrics().height())
    assert len({t.height() for t in titles}) == 1 and titles[0].height() <= 20
    w.set_look(get_look("glass"))
    spin(qapp, lambda: False, timeout=0.5)
    backs = [t.back.name() if t.back is not None else None for t in titles]
    print("in glass", backs)
    assert backs == [glass.TITLE[glass._mode()].name()] * 3
    w.set_look(get_look("classic"))
    spin(qapp, lambda: False, timeout=0.3)
    assert all(t.back is None for t in titles)


def test_in_glass_the_strips_between_the_images_are_the_image_s_colour(window):
    """The panels' separators between the images were the window's grey in glass (the user, 2026-10-06): there the
    image's colour, as its titles; grey again out of it. Read from the window as drawn, every pixel of the strip."""
    from PySide6 import QtGui

    from explorer.look import get_look
    from explorer.ui import glass

    w, qapp = window

    def strip():
        img = w.grab().toImage()
        g = w.centralWidget().geometry()
        x0, x1 = g.right() + 1, w.linked[0].dock.geometry().left()      # between the main image and the next
        ys = range(g.top() + 20, g.bottom() - 20, 37)
        return {QtGui.QColor(img.pixel(x, y)).name() for x in range(x0, x1) for y in ys}, (x0, x1)

    w.set_look(get_look("glass"))
    spin(qapp, lambda: False, timeout=0.6)
    seen, span = strip()
    print("glass: strip", span, "colours", seen)
    assert span[1] > span[0] and seen == {glass.TITLE[glass._mode()].name()}
    w.set_look(get_look("classic"))
    spin(qapp, lambda: False, timeout=0.4)
    seen, span = strip()
    print("classic: strip", span, "colours", seen)
    assert glass.TITLE[glass._mode()].name() not in seen



@pytest.fixture
def restore(qapp):
    """The application's style and palette as they were (a test that switches the theme; test_theme's)."""
    import pyqtgraph as pg
    from PySide6 import QtGui, QtWidgets

    name, pal = qapp.style().name(), QtGui.QPalette(qapp.palette())
    yield qapp
    qapp.setStyle(QtWidgets.QStyleFactory.create(name or "Fusion"))
    qapp.setPalette(pal)
    qapp.setProperty("explorer_light", False)
    pg.setConfigOptions(background="k", foreground="d")


def test_in_glass_the_tabs_are_flat_on_the_panel(window, restore):
    """With linked cubes the panels' tabs stayed the style's grey buttons in glass (the user, 2026-10-06): there they
    are flat on the panel, as the glass bar's buttons are, in either theme; the style's again out of it. Median
    lightness of each tab as drawn (its text is a small part of it), against the panel's."""
    import numpy as np
    from PySide6 import QtGui

    from explorer.look import get_look
    from explorer.ui import glass

    w, qapp = window

    def tabs_lightness():
        """In the panel as drawn (the tabs alone are transparent in glass: grabbed alone, black)."""
        out = []
        for tabs, dock in ((w.spec_tabs, w.spec_dock), (w.lt_tabs, w.lt_dock)):
            bar = tabs.tabBar()
            img = dock.grab().toImage()
            for i in range(bar.count()):
                r = bar.tabRect(i).translated(bar.mapTo(dock, bar.rect().topLeft()))
                px = [QtGui.QColor(img.pixel(x, y)).lightness() for x in range(r.left(), r.right(), 2)
                      for y in range(r.top(), r.bottom(), 2)]
                out.append(int(np.median(px)))
        return out

    w.set_theme("dark")
    w.set_look(get_look("glass"))
    spin(qapp, lambda: False, timeout=0.6)
    dark = tabs_lightness()
    w.set_theme("light")
    spin(qapp, lambda: False, timeout=0.6)
    light = tabs_lightness()
    w.set_look(get_look("classic"))
    spin(qapp, lambda: False, timeout=0.4)
    slab = {m: [c.lightness() for c in glass.SLAB[m]] for m in ("dark", "light")}
    print("tab lightness in glass: dark", dark, "light", light, "slabs", slab)
    assert max(dark) <= 40 and min(light) >= 215          # the style's: 67-74 in the dark theme
    assert w.spec_tabs.styleSheet() == "" and w.lt_tabs.styleSheet() == ""


def test_a_click_on_a_tab_leaves_the_keys_to_the_window(window):
    """The tabs never take the keyboard (their focus ring showed in glass): after a click on one, ← → still move
    lambda. A guard: offscreen, a click did not give the bar the focus before either."""
    from PySide6 import QtCore
    from PySide6.QtTest import QTest

    w, qapp = window
    bar = w.lt_tabs.tabBar()
    QTest.mouseClick(bar, QtCore.Qt.MouseButton.LeftButton, pos=bar.tabRect(1).center())
    qapp.processEvents()
    l0 = w.session.state.l
    QTest.keyClick(w, QtCore.Qt.Key.Key_Right)
    qapp.processEvents()
    print("tab in front", w.lt_tabs.currentIndex(), "focus on the bar", bar.hasFocus(), "lambda", l0, "->",
          w.session.state.l)
    assert w.lt_tabs.currentIndex() == 1 and not bar.hasFocus() and w.session.state.l == l0 + 1


def test_a_smaller_image_keeps_the_same_zoom_factor(window):
    """A linked image made smaller (the user, 2026-10-07: compressed, or floating) showed the same region in fewer
    pixels, at another magnification: the images keep one centre and one magnification (screen px per data pixel),
    as ds9's locked frames; the smaller one shows less. Squeezing it moves nothing else; a zoom on it is everyone's."""
    from PySide6 import QtCore, QtGui, QtWidgets

    w, qapp = window
    other = w.linked[0]
    other.dock.setFloating(True)
    other.dock.resize(220, 300)                         # smaller than the main image
    spin(qapp, lambda: False, timeout=0.4)

    def state(v):
        r = v.vb.viewRect()
        return r.width() / v.vb.width(), r.height() / v.vb.height(), r.center()

    w.view.vb.setRange(QtCore.QRectF(6, 8, 16, 16), padding=0)            # zoom on the main image
    spin(qapp, lambda: False, timeout=0.3)
    (sx0, sy0, c0), (sx1, sy1, c1) = state(w.view), state(other.view)
    print(f"main {1 / sx0:.2f} px/pixel at ({c0.x():.1f}, {c0.y():.1f}); smaller linked {1 / sx1:.2f} px/pixel at "
          f"({c1.x():.1f}, {c1.y():.1f}); boxes {w.view.vb.width():.0f} and {other.view.vb.width():.0f} wide")
    assert abs(sx1 / sx0 - 1) < 0.02 and abs(sy1 / sy0 - 1) < 0.02
    assert abs(c1.x() - c0.x()) < 0.5 and abs(c1.y() - c0.y()) < 0.5
    before = w.view.vb.viewRect()
    other.dock.resize(180, 260)                         # squeezed again: the main image does not move
    spin(qapp, lambda: False, timeout=0.3)
    assert w.view.vb.viewRect() == before
    # the wheel over the linked image: everyone's zoom
    vp = other.view.widget.viewport()
    at = QtCore.QPointF(vp.width() / 2, vp.height() / 2)
    ev = QtGui.QWheelEvent(at, vp.mapToGlobal(at), QtCore.QPoint(0, 0), QtCore.QPoint(0, 120),
                           QtCore.Qt.MouseButton.NoButton, QtCore.Qt.KeyboardModifier.NoModifier,
                           QtCore.Qt.ScrollPhase.NoScrollPhase, False)
    QtWidgets.QApplication.sendEvent(vp, ev)
    spin(qapp, lambda: False, timeout=0.3)
    (sx0, _, c0), (sx1, _, c1) = state(w.view), state(other.view)
    print(f"after the wheel on the linked image: main {1 / sx0:.2f}, linked {1 / sx1:.2f} px/pixel")
    assert w.view.vb.viewRect() != before and abs(sx1 / sx0 - 1) < 0.02
    other.dock.setFloating(False)



def test_one_entry_puts_every_cube_in_a_window_of_its_own_and_back(window):
    """Panels → "Each cube in a window of its own" (the user's mock of a cube apart, 2026-10-07): each linked cube's
    image floats with its spectra and lambda-t beside it, out of the main window's tabs; the window gives up the
    images' room; the zoom stays one. Unticked, back in the window as it was, the tabs as they were."""
    w, qapp = window
    a = w.detach_action
    assert a in w.nav.panels.menu().actions() and a.text() == "Each cube in a window of its own"
    w.resize(min(w.width(), qapp.primaryScreen().geometry().width() - 20), w.height())   # within the screen: given
    spin(qapp, lambda: False, timeout=0.3)                                                # back, its width again
    w.reset_sizes()
    qapp.processEvents()
    main_w, spec_w, win_w = w.view.widget.width(), w.spec_dock.width(), w.width()
    tabs_before = [w.spec_tabs.tabText(i) for i in range(w.spec_tabs.count())]
    other, blos = w.linked
    a.setChecked(True)
    spin(qapp, lambda: False, timeout=0.6)
    views = [w.view] + [c.view for c in w.linked]
    zoom = [round(v.vb.width() / v.vb.viewRect().width(), 3) for v in views]
    tabs = [w.spec_tabs.tabText(i) for i in range(w.spec_tabs.count())]
    print("apart: window", win_w, "->", w.width(), "tabs", tabs_before, "->", tabs, "zoom", zoom,
          "other's window", other.dock.size().toTuple(), "its panels beside its image", other.side.count())
    assert all(c.dock.isFloating() and c.dock.isVisible() for c in w.linked) and a.isChecked()
    assert abs(w.view.widget.width() - main_w) <= 2 and w.width() < win_w and len(set(zoom)) == 1
    assert tabs == tabs_before[:1] and other.windowed and other.side.isVisible() and other.side.count() == 2
    assert other.spectra.widget.isVisibleTo(other.dock) and "spectra:1" in w.session.state.panels
    assert not blos.side.isVisible()                    # a map: an image alone
    a.setChecked(False)
    spin(qapp, lambda: False, timeout=0.6)
    sizes = [v.widget.width() for v in views]
    tabs = [w.spec_tabs.tabText(i) for i in range(w.spec_tabs.count())]
    print("back: window", w.width(), "spectra", spec_w, "->", w.spec_dock.width(), "images", sizes, "tabs", tabs)
    assert not any(c.dock.isFloating() for c in w.linked) and not a.isChecked() and not other.windowed
    assert w.width() == win_w and abs(w.spec_dock.width() - spec_w) <= 2 and max(sizes) - min(sizes) <= 2
    assert tabs == tabs_before


def test_a_cube_s_window_docked_by_hand_takes_its_panels_back(window):
    """Back by any way it is docked (a double click on its title, ↺, glass's leaving): its panels in their tabs."""
    w, qapp = window
    other = w.linked[0]
    w.detach_action.setChecked(True)
    spin(qapp, lambda: False, timeout=0.5)
    other.dock.setFloating(False)                       # what a double click on its title does
    spin(qapp, lambda: False, timeout=0.3)
    print("docked by hand:", other.windowed, w.spec_tabs.count(), "entry ticked", w.detach_action.isChecked())
    assert not other.windowed and w.spec_tabs.count() == 2 and w.lt_tabs.count() == 2
    w.reset_panels()
    spin(qapp, lambda: False, timeout=0.3)
    assert not w.detach_action.isChecked() and not any(c.dock.isFloating() for c in w.linked)

def test_in_glass_cubes_apart_leave_the_window_fitted_and_reset_docks_them(window):
    from explorer.look import get_look

    w, qapp = window
    w.set_look(get_look("glass"))
    spin(qapp, lambda: False, timeout=0.6)
    win_w = w.width()
    w.detach_action.setChecked(True)
    spin(qapp, lambda: False, timeout=0.6)
    print("glass: window", win_w, "->", w.width(), "floating", [c.dock.isFloating() for c in w.linked])
    assert all(c.dock.isFloating() and c.dock.isVisible() for c in w.linked) and w.width() < win_w
    w.reset_panels()                                    # ↺: back in the window, the entry unticked
    spin(qapp, lambda: False, timeout=0.6)
    sizes = [w.view.widget.width()] + [c.view.widget.width() for c in w.linked]
    print("after reset: window", w.width(), "images", sizes)
    assert not any(c.dock.isFloating() for c in w.linked) and not w.detach_action.isChecked()
    assert max(sizes) - min(sizes) <= 2
    w.set_look(get_look("classic"))
    spin(qapp, lambda: False, timeout=0.3)


def test_an_image_title_has_close_then_float_at_the_left_as_every_panel(window):
    """The image titles' marks were at the right, every panel's title (titlebar.DockTitle, glass's) has them at the
    left, close then float (the user, 2026-10-07)."""
    from explorer.ui import titlebar

    w, qapp = window
    t = w.linked[0].title
    t.enterEvent(None)
    qapp.processEvents()
    kinds = [b.kind for b in t.buttons]
    xs = [b.geometry().left() for b in t.buttons]
    ref = titlebar.DockTitle(w.spec_dock)
    ref.resize(300, ref.sizeHint().height())
    ref.layout().activate()
    ref_names = [b.objectName() for b in sorted(ref.buttons, key=lambda b: b.geometry().left())]
    print("image title", kinds, xs, "of", t.width(), "; panel title", ref_names)
    assert kinds == ["close", "float"] and xs[0] < xs[1] < t.width() // 2
    assert ref_names == ["qt_dockwidget_closebutton", "qt_dockwidget_floatbutton"]
    t.leaveEvent(None)


def test_a_cube_s_window_shares_its_width_between_image_and_panels_by_hand(window):
    """In a cube's window the panels' heights could be changed but not the width between them and the image (the
    user, 2026-10-07): a handle between them, as between the spectra and lambda-t."""
    w, qapp = window
    other = w.linked[0]
    w.detach_action.setChecked(True)
    spin(qapp, lambda: False, timeout=0.5)
    split = other.split
    before = split.sizes()
    split.setSizes([before[0] + 40, before[1] - 40])        # what dragging its handle does
    qapp.processEvents()
    print("image | panels:", before, "->", split.sizes(), "handle", split.handle(1).isVisible())
    assert split.count() == 2 and split.handle(1).isVisible() and split.sizes()[0] == before[0] + 40
    w.detach_action.setChecked(False)
    spin(qapp, lambda: False, timeout=0.3)


def test_in_glass_a_cube_s_window_is_on_the_image_s_colour(window, restore):
    """Detached in glass, a cube's spectra and lambda-t (clear over their panel in glass) showed the theme's grey:
    a floating window does not take its parent's colour (the user, 2026-10-07). There, the image's colour (black in
    the dark theme); out of glass, its own again."""
    import collections

    from PySide6 import QtCore, QtGui

    from explorer.look import get_look
    from explorer.ui import glass

    w, qapp = window
    w.set_theme("dark")
    w.set_look(get_look("glass"))
    spin(qapp, lambda: False, timeout=0.6)
    w.detach_action.setChecked(True)
    spin(qapp, lambda: False, timeout=0.6)
    c = w.linked[0]
    img = c.dock.grab().toImage()
    r = QtCore.QRect(c.spectra.w.mapTo(c.dock, QtCore.QPoint(0, 0)), c.spectra.w.size())
    common = collections.Counter(QtGui.QColor(img.pixel(x, y)).lightness() for x in range(r.left(), r.right(), 3)
                                 for y in range(r.top(), r.bottom(), 3)).most_common(1)[0][0]
    print("its spectra's background in glass: lightness", common, "window colour",
          c.dock.palette().window().color().name())
    assert common <= 20 and c.dock.palette().window().color() == glass.TITLE["dark"]
    w.detach_action.setChecked(False)
    w.set_look(get_look("classic"))
    spin(qapp, lambda: False, timeout=0.4)
    assert c.dock.palette().window().color() != glass.TITLE["dark"]

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
    return synth.write_lp(path, np.random.default_rng(n).normal(size=(n, ny, nx)))


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
    # the map has no spectra, and its lambda-t is a curve against t (ui.lambda_t.TimeCurve)
    assert names == {"spectra": ["main_im", "other_im"], "lambda_t": ["main_im", "other_im", "Blos.map"]}
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


def test_c_in_classic_recolours_the_linked_images_of_that_stokes(window):
    """The window starts in classic: C on V puts the linked cube with V on the map, image and lambda-t; the map with
    one plane (I) stays grey; Shift+C takes them back to their plain grey."""
    from explorer.look import colormaps as cm

    w, qapp = window
    other, blos = w.linked
    w.session.set_index("s", 3)
    assert spin(qapp, lambda: w.session.member_state(other.k).s == 3 and other.view._full is not None)
    assert other.view.img.lut is other.view.base_lut
    w.cycle_colours(1)
    qapp.processEvents()
    assert w.look.name == "classic" and w.colours.maps[3] == "CET-D4"
    assert np.array_equal(other.view.img.lut, cm.image_table(cm.table("CET-D4"), False))
    assert other.key.state[3] == "CET-D4"
    assert blos.view.img.lut is blos.view.base_lut
    w.cycle_colours(-1)
    qapp.processEvents()
    assert other.view.img.lut is other.view.base_lut and other.key.lut is other.view.base_lut


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


class _Click:                                           # pyqtgraph's scene click, as the slit tool reads it
    def __init__(self, vb, x, y, double=False):
        from PySide6 import QtCore
        self._p, self._double = vb.mapViewToScene(QtCore.QPointF(x, y)), double

    def button(self):
        from PySide6 import QtCore
        return QtCore.Qt.MouseButton.LeftButton

    def double(self):
        return self._double

    def scenePos(self):
        return self._p


def draw_slit(w, cube, a, b):
    """A slit from a to b, (x, y), drawn with clicks on cube's image (a CubeView), finished with a double click."""
    w.set_slit_mode(True)
    cube._click(_Click(cube.view.vb, *a))
    cube._click(_Click(cube.view.vb, *b))
    cube._click(_Click(cube.view.vb, *b, double=True))


def slices_along(ds, session, k, pix):
    """Cube k's time slice along pix at its own lambda and Stokes, read frame by frame (Dataset.image), and its
    spectral slice at its t."""
    import dataclasses
    st = session.member_state(k)
    r, iy, ix = ds.roles, *pix
    ts = np.stack([ds.image(session.index_of(k, dataclasses.replace(st, t=t))).result()[iy, ix]
                   for t in range(max(1, r.nt))])
    sl = np.stack([ds.image(session.index_of(k, dataclasses.replace(st, l=lam))).result()[iy, ix]
                   for lam in range(max(1, r.nl))])
    return ts, sl


@pytest.mark.parametrize("k", [2, 1, 0])
def test_a_slit_drawn_on_a_cube_s_image_shows_that_cube_s_slices(window, k):
    """A slit drawn on Blos gave the main cube's slices (the user, 2026-10-10): the slit panel shows the slices of the
    cube whose image took the slit, at its own lambda and Stokes. The slit is still on every image; a map without
    times of its own has its t in the main cube's times, and no spectral slice. k: the Blos map, the other line (7
    tunings, its own lambda), the main cube. One slit tab (Shift+S off): the way it was before a tab per cube."""
    w, qapp = window
    w.set_slit_tabs(False)
    cube = w.cubes[k]
    when = w.slit_panel.t_label_fine(1)               # the main cube's times
    w.set_slit_mode(True)
    w.set_slit_mode(False)
    if k:                                               # the slit on the main cube first: the panel moves off it
        draw_slit(w, w.main, (3.5, 4.5), (20.5, 30.5))
    draw_slit(w, cube, (5.2, 6.7), (30.4, 40.1))
    panel = w.slit_panel
    assert spin(qapp, lambda: panel.pix is not None and len(panel.pix[0]) > 30), "no slit"
    ts, sl = slices_along(cube.dataset, w.session, k, panel.pix)

    def same(img, want):
        return img is not None and img.shape == want.shape and np.array_equal(img, want, equal_nan=True)
    spin(qapp, lambda: same(panel.ts_img.image, ts) and same(panel.sl_img.image, sl))
    a, b = panel.ts_img.image, panel.sl_img.image
    diff = np.nanmax(np.abs(a - ts)) if a is not None and a.shape == ts.shape else None
    title = w.slit_dock.windowTitle()
    print(f"cube {k} ({cube.name}): path_cube {getattr(w.session.state, 'path_cube', None)}, panel nt x nl "
          f"{panel.nt} x {panel.nl}, time slice {None if a is None else a.shape} (the cube's {ts.shape}), spectral "
          f"{None if b is None else b.shape} (the cube's {sl.shape}), max |time slice - the cube's| {diff}, "
          f"title {title!r}, t 1 at {panel.t_label_fine(1)!r} (main {when!r})")
    assert same(a, ts) and same(b, sl)
    assert w.session.state.path_cube == k
    assert (panel.nt, panel.nl) == (max(1, cube.dataset.roles.nt), max(1, cube.dataset.roles.nl))
    assert title == f"Slit: {cube.name}"
    assert panel.spectral == (k != 2)                   # the map's one-row spectral slice left out
    assert (panel.sl in panel.w.ci.items) == (k != 2)
    if k != 1:                                          # the map has no times: the main cube's label its t
        assert panel.t_label_fine(1) == when
    assert all(len(m.line.getData()[0]) > 0 for m in w.slit_tool.marks)
    w.clear_slit()


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



def test_a_cube_s_window_larger_than_the_main_image_keeps_the_one_magnification(window):
    """A cube's window larger than the main image at its fit showed another magnification (3.24 px per pixel on the
    main image against 7.95): its guard held it at its own fit. A linked image zooms out as far as the main one, below
    its own fit: one magnification however large the window, after a double click on either image too (the whole
    main image, everyone at its magnification); on the wheel it stops where the main image stops."""
    from PySide6 import QtCore, QtGui, QtWidgets

    w, qapp = window
    other = w.linked[0]

    def mag(v):
        r = v.vb.viewRect()
        return v.vb.width() / r.width(), v.vb.height() / r.height()

    def fit(v):
        return min(v.vb.width() / v.guard.nx, v.vb.height() / v.guard.ny)

    w.detach_action.setChecked(True)
    spin(qapp, lambda: False, timeout=0.6)
    other.dock.resize(1500, 1000)                       # its image panel larger than the main one
    spin(qapp, lambda: False, timeout=0.6)
    w.view.show_all()
    spin(qapp, lambda: False, timeout=0.4)
    (m0, _), (m1, m1y) = mag(w.view), mag(other.view)
    print(f"main {m0:.2f} px/pixel (its fit {fit(w.view):.2f}, box {w.view.vb.width():.0f}x{w.view.vb.height():.0f}); "
          f"cube window {m1:.2f} (its fit {fit(other.view):.2f}, box {other.view.vb.width():.0f}x"
          f"{other.view.vb.height():.0f})")
    assert fit(other.view) > 1.5 * fit(w.view)          # the case: its own fit well above the main one's
    assert abs(m0 / fit(w.view) - 1) < 0.01 and abs(m1 / m0 - 1) < 0.02 and abs(m1y / m0 - 1) < 0.02
    # zoomed in on the main image, then a double click on the cube's image: the whole main image again, one zoom
    w.view.vb.setRange(QtCore.QRectF(6, 8, 12, 12), padding=0)
    spin(qapp, lambda: False, timeout=0.3)
    assert mag(w.view)[0] > 2 * fit(w.view)
    pos = other.view.vb.mapViewToScene(QtCore.QPointF(20.5, 20.5))
    ev = type("Click", (), dict(scenePos=lambda self: pos, double=lambda self: True,
                                button=lambda self: QtCore.Qt.MouseButton.LeftButton))()
    other.view.widget.scene().sigMouseClicked.emit(ev)
    spin(qapp, lambda: False, timeout=0.4)
    (m0, _), (m1, _) = mag(w.view), mag(other.view)
    print(f"after the double click on the cube's image: main {m0:.2f}, cube window {m1:.2f} px/pixel")
    assert abs(m0 / fit(w.view) - 1) < 0.01 and abs(m1 / m0 - 1) < 0.02
    # the wheel out over the cube's image, already at the main fit: nobody goes below it
    vp = other.view.widget.viewport()
    at = QtCore.QPointF(vp.width() / 2, vp.height() / 2)
    for _ in range(3):
        ev = QtGui.QWheelEvent(at, vp.mapToGlobal(at), QtCore.QPoint(0, 0), QtCore.QPoint(0, -120),
                               QtCore.Qt.MouseButton.NoButton, QtCore.Qt.KeyboardModifier.NoModifier,
                               QtCore.Qt.ScrollPhase.NoScrollPhase, False)
        QtWidgets.QApplication.sendEvent(vp, ev)
        spin(qapp, lambda: False, timeout=0.2)
    (m0, _), (m1, _) = mag(w.view), mag(other.view)
    print(f"after the wheel out on the cube's image: main {m0:.2f}, cube window {m1:.2f} px/pixel")
    assert abs(m0 / fit(w.view) - 1) < 0.01 and abs(m1 / m0 - 1) < 0.02
    w.detach_action.setChecked(False)
    spin(qapp, lambda: False, timeout=0.6)


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
    panes = [p for p in other.panes.values() if p.isVisible()]
    print("apart: window", win_w, "->", w.width(), "tabs", tabs_before, "->", tabs, "zoom", zoom,
          "other's window", other.dock.size().toTuple(), "its panels docked beside its image",
          [p.objectName() for p in panes])
    assert all(c.dock.isFloating() and c.dock.isVisible() for c in w.linked) and a.isChecked()
    assert abs(w.view.widget.width() - main_w) <= 2 and w.width() < win_w and len(set(zoom)) == 1
    assert tabs == tabs_before[:1] and other.windowed and [p.objectName() for p in panes] == ["spectra:1", "lambda_t:1"]
    assert all(p.window() is other.dock and not p.isFloating() for p in panes)
    assert other.spectra.widget.isVisibleTo(other.dock) and "spectra:1" in w.session.state.panels
    assert list(blos.panes) == ["lambda_t:2", "slit:2"]  # a map: its image, its curve against t, its slit panel
    assert not other.panes["slit:1"].isVisible()        # no slit drawn: no slit panel
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
    user, 2026-10-07): its spectra and lambda-t are docks beside the image in the window's own frame, and a drag of
    the separator between them shares the width out between the image and the panels, as in the main window."""
    from PySide6 import QtCore
    from PySide6.QtTest import QTest

    w, qapp = window
    other = w.linked[0]
    w.detach_action.setChecked(True)
    spin(qapp, lambda: False, timeout=0.5)
    pane = other.panes["spectra:1"]
    before = (other.view.widget.width(), pane.width())
    f = other.frame
    x = (other.view.widget.mapTo(f, QtCore.QPoint(0, 0)).x() + other.view.widget.width() + pane.x()) // 2
    # on the separator between the image and the panels, through the window as the mouse is (sent to the frame
    # itself, the press never reached the main window layout's separator)
    at = f.mapTo(other.dock, QtCore.QPoint(x, f.height() // 2))
    win = other.dock.windowHandle()
    QTest.mousePress(win, QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier, at)
    QTest.mouseMove(win, at + QtCore.QPoint(20, 0))
    QTest.mouseMove(win, at + QtCore.QPoint(40, 0))
    QTest.mouseRelease(win, QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier,
                       at + QtCore.QPoint(40, 0))
    qapp.processEvents()
    after = (other.view.widget.width(), pane.width())
    print("image | panels:", before, "->", after, "separator at x", x)
    assert after[0] - before[0] == 40 and before[1] - after[1] == 40
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


def test_a_window_of_its_own_is_rounded_with_a_margin_the_corners_do_not_cut(window):
    """A cube's window floats beside the rounded main window: rounded as glass's panels are (RADIUS_PANEL), with a
    margin round its content the rounding does not cut (in glass, docked, it has none, and floating it went on
    without one; the user, 2026-10-07). Docked again, square."""
    from PySide6 import QtCore

    from explorer.look import get_look
    from explorer.platform.xbridge.windows import SHAPE_ATTR
    from explorer.ui import docks

    w, qapp = window
    c = w.linked[0]
    for look in ("glass", "classic"):
        w.set_look(get_look(look))
        spin(qapp, lambda: False, timeout=0.4)
        w.detach_action.setChecked(True)
        spin(qapp, lambda: False, timeout=0.5)
        m = c.dock.widget().layout().contentsMargins()
        region = getattr(c.dock, SHAPE_ATTR)
        print(look, "floating: margins", (m.left(), m.top(), m.right(), m.bottom()), "rounded", not region.isEmpty(),
              "corner in", region.contains(QtCore.QPoint(0, 0)) if not region.isEmpty() else None)
        assert m.left() == m.right() == m.bottom() == docks.PANEL_GUTTER
        assert not region.isEmpty() and not region.contains(QtCore.QPoint(0, 0))      # the corner cut round
        w.detach_action.setChecked(False)
        spin(qapp, lambda: False, timeout=0.4)
        assert getattr(c.dock, SHAPE_ATTR).isEmpty()                                  # docked: square
    w.set_look(get_look("classic"))


def test_a_panel_closed_in_a_cube_s_window_comes_back_from_panels_in_its_place(window):
    """A cube's spectra and lambda-t in its window are docks as the main window's: closed by its close mark, nothing
    is read for it and lambda-t takes its room; Panels lists it while the cube is apart ("name · Spectrum") and shows
    it again where it was, read again."""
    from PySide6 import QtWidgets

    w, qapp = window
    other = w.linked[0]
    w.detach_action.setChecked(True)
    spin(qapp, lambda: False, timeout=0.5)
    pane = other.panes["spectra:1"]
    lt = other.panes["lambda_t:1"]
    before = (pane.geometry().getRect(), lt.geometry().getRect(), other.view.widget.width())
    pane.findChild(QtWidgets.QAbstractButton, "qt_dockwidget_closebutton").click()
    qapp.processEvents()
    closed = (pane.isVisible(), lt.height(), sorted(w.session.state.panels))
    menu = w.nav.panels.menu()
    menu.aboutToShow.emit()
    entry = [a for a in menu.actions() if a.text() == "other_im · Spectrum"]
    print("before", before, "closed: shown, lambda-t's height, read", closed, "entry", [a.text() for a in entry])
    assert not closed[0] and closed[1] > before[1][3] and "spectra:1" not in closed[2] and "lambda_t:1" in closed[2]
    assert len(entry) == 1 and not entry[0].isChecked()
    entry[0].trigger()
    qapp.processEvents()
    after = (pane.geometry().getRect(), lt.geometry().getRect(), other.view.widget.width())
    print("again", after, sorted(w.session.state.panels))
    assert after == before and "spectra:1" in w.session.state.panels
    w.detach_action.setChecked(False)
    spin(qapp, lambda: False, timeout=0.3)
    menu.aboutToShow.emit()
    assert not [a for a in menu.actions() if "·" in a.text()]          # back in the tabs: no entries of its own


def test_a_closed_cube_s_window_comes_back_in_the_window_with_its_panels(window):
    """A cube's window closed, then "each cube in a window of its own" unticked: it was left floating, hidden, its
    spectra and lambda-t inside it, and its own entry brought it back as a window while the entry for all said they
    were back. Every cube comes back, closed or not: docked, its panels in the tabs, shown again by its entry."""
    w, qapp = window
    other = w.linked[0]
    w.detach_action.setChecked(True)
    spin(qapp, lambda: False, timeout=0.5)
    other.title.buttons[0].click()                      # its close mark
    qapp.processEvents()
    w.detach_action.setChecked(False)
    spin(qapp, lambda: False, timeout=0.4)
    tabs = [w.spec_tabs.tabText(i) for i in range(w.spec_tabs.count())]
    print("unticked: floating", other.dock.isFloating(), "shown", other.dock.isVisible(), "windowed", other.windowed,
          "tabs", tabs)
    assert not other.dock.isFloating() and not other.dock.isVisible() and not other.windowed
    assert tabs == ["main_im", "other_im"]
    other.dock.toggleViewAction().trigger()
    spin(qapp, lambda: False, timeout=0.3)
    print("its entry: floating", other.dock.isFloating(), "shown", other.dock.isVisible(), "entry for all",
          w.detach_action.isChecked())
    assert other.dock.isVisible() and not other.dock.isFloating() and not w.detach_action.isChecked()


def test_reset_after_cubes_apart_gives_the_window_its_width_back(window):
    """Cubes apart, the window gives up the images' room; ↺ docked them but left the window narrow (1500 -> 852 px,
    every panel squeezed into it): it takes its width back first, and every panel is where it started (in this
    780-px window too, where the main image had been at its least width: Shell.reset_sizes)."""
    w, qapp = window
    w.resize(min(w.width(), qapp.primaryScreen().geometry().width() - 20), w.height())
    spin(qapp, lambda: False, timeout=0.3)
    w.reset_panels()
    spin(qapp, lambda: False, timeout=0.3)
    start = (w.width(), w.spec_dock.geometry().getRect(), [c.dock.geometry().getRect() for c in w.linked])
    w.detach_action.setChecked(True)
    spin(qapp, lambda: False, timeout=0.5)
    narrow = w.width()
    w.reset_panels()
    spin(qapp, lambda: False, timeout=0.5)
    back = (w.width(), w.spec_dock.geometry().getRect(), [c.dock.geometry().getRect() for c in w.linked])
    print("start", start, "apart", narrow, "reset", back)
    assert narrow < start[0] and back == start


def test_after_a_window_resize_the_images_are_one_width(window):
    """Qt gives a window's change of size to its centre, the main image, and keeps the panels' widths: at 1200 x 700
    the main image was 170 px against 306 for each linked one, and at its whole-image fit the others could not show
    it at its magnification (1.55 against 2.44 px per pixel). The images share the width at every resize."""
    w, qapp = window
    for width in (1000, 1300):
        w.resize(width, 600)
        spin(qapp, lambda: False, timeout=0.3)
        sizes = [w.view.widget.width()] + [c.view.widget.width() for c in w.linked]
        print("window", width, "image widths", sizes)
        assert max(sizes) - min(sizes) <= 2


def test_a_resize_shares_the_widths_once_it_stops_not_at_every_step(window):
    """Shared at every step, a resize laid the window out twice and cost 62 ms against 43 (bellatrix, offscreen):
    while the size keeps changing nothing is shared, and once it has stopped the images share it once."""
    w, qapp = window
    calls = []
    share = w.same_image_widths
    w.same_image_widths = lambda: (calls.append(1), share())     # what resizeEvent and its timer call from here
    try:
        if getattr(w, "_widths_timer", None) is not None:          # made by an earlier resize: bound to the method
            w._widths_timer.timeout.disconnect()
            w._widths_timer.timeout.connect(w.same_image_widths)
        for width in (1000, 1050, 1100, 1150, 1200):               # five steps of one drag, 20 ms apart
            w.resize(width, 600)
            spin(qapp, lambda: False, timeout=0.02)
        during = len(calls)
        spin(qapp, lambda: False, timeout=0.4)
        sizes = [w.view.widget.width()] + [c.view.widget.width() for c in w.linked]
        print("shared during the drag", during, "after it", len(calls), "image widths", sizes)
        assert during == 0
        assert len(calls) == 1
        assert max(sizes) - min(sizes) <= 2
    finally:
        del w.same_image_widths


def test_the_saved_layout_keeps_each_cube_s_window_and_its_panels(window, cubes, tmp_path):
    """The saved layout kept the main window's panels but not those inside a cube's window, nor that the cubes were
    apart (ROADMAP E8.3): at the next start a cube's window came back as its image alone, its spectra and lambda-t
    in the main window's tabs. Saved apart, its panels' width changed by hand and one of them floated out, a new
    window with the same layout (restored before it is shown, as ui.app does) has each cube apart again, in the same
    place and size, its panels in the same place and size inside it or out of it. The layout file is the test's."""
    from PySide6 import QtCore

    from explorer.data.dataset import Dataset
    from explorer.ui.layout import LayoutStore
    from explorer.ui.shell import Shell

    w, qapp = window
    store = LayoutStore("test", str(tmp_path / "layout.ini"), linked=True)
    w.detach_action.setChecked(True)
    spin(qapp, lambda: False, timeout=0.5)
    other = w.linked[0]
    other.panels_width(other.dock.width() // 3)
    sp, lt = other.panes["spectra:1"], other.panes["lambda_t:1"]
    other.frame.resizeDocks([sp, lt], [100, 300], QtCore.Qt.Orientation.Vertical)
    spin(qapp, lambda: False, timeout=0.3)
    lt.setFloating(True)                                # one of its panels floated out of it
    lt.setGeometry(120, 420, 330, 210)
    spin(qapp, lambda: False, timeout=0.3)

    def arrangement(win):
        c = win.linked[0]
        return (win.detach_action.isChecked(), c.windowed, [d.isFloating() for d in (cc.dock for cc in win.linked)],
                c.dock.geometry().getRect(),
                # a hidden panel (the slit's, no slit drawn) has no place to keep
                {k: (p.isVisible(), p.isFloating(), p.geometry().getRect() if p.isVisible() else None)
                 for k, p in sorted(c.panes.items())},
                c.view.widget.width())

    before = arrangement(w)
    store.save(w)
    main, otherc, blos = cubes
    ds = Dataset.open(main)
    linked = [Dataset.open(otherc, executors=ds.executors), Dataset.open(blos, axes="t", executors=ds.executors)]
    b = Shell(ds, linked=linked)
    try:
        store.restore(b, qapp)
        b.show()
        spin(qapp, lambda: False, timeout=0.6)
        after = arrangement(b)
        print("saved", before, "\nrestored", after)
        assert after == before
        tabs = [b.spec_tabs.tabText(i) for i in range(b.spec_tabs.count())]
        assert tabs == ["main_im"]                       # its spectra in its window, not in the main window's tabs
        b.detach_action.setChecked(False)               # and back in the window, its panels in their tabs
        spin(qapp, lambda: False, timeout=0.4)
        assert not b.linked[0].windowed and b.spec_tabs.count() == 2
    finally:
        b.close()
        for d in linked:
            d.close()
        ds.close()
    w.detach_action.setChecked(False)
    spin(qapp, lambda: False, timeout=0.3)


def test_in_glass_a_panel_floated_out_of_a_cube_s_window_wears_the_glass_skin(window, restore):
    """In glass a panel floated from the main window is a rounded slab with glass's title, plots clear over it; one
    floated out of a cube's window came out as the window's plain panel (ROADMAP E8.3). It wears the same skin as one
    floated from the main window; docked in the cube's window again, the skin is gone, and out of glass nothing of it
    is left on its plots."""
    from PySide6 import QtCore, QtGui

    from explorer.look import get_look
    from explorer.platform.xbridge.windows import SHAPE_ATTR

    w, qapp = window
    w.set_theme("dark")
    c = w.linked[0]
    plot_bg = QtGui.QBrush(c.spectra.w.backgroundBrush())
    w.set_look(get_look("glass"))
    spin(qapp, lambda: False, timeout=0.6)
    w.detach_action.setChecked(True)
    spin(qapp, lambda: False, timeout=0.6)
    pane = c.panes["spectra:1"]
    fill = pane.widget().autoFillBackground()
    pane.setFloating(True)
    pane.resize(w.spec_dock.size())
    spin(qapp, lambda: False, timeout=0.4)

    def skin(d):
        region = getattr(d, SHAPE_ATTR, QtGui.QRegion())
        img = d.grab().toImage()
        middle = QtGui.QColor(img.pixel(d.width() // 2, d.height() - 3)).lightness()
        return dict(title=type(d.titleBarWidget()).__name__, rounded=not region.isEmpty(),
                    corner_cut=not region.isEmpty() and not region.contains(QtCore.QPoint(0, 0)),
                    fill=d.widget().autoFillBackground(), gutter=d.widget().layout().contentsMargins().left(),
                    slab=middle <= 40)

    ref, got = skin(w.spec_dock), skin(pane)
    print("floated from the main window", ref, "\nfloated out of a cube's window", got)
    assert w.spec_dock.isFloating() and pane.isFloating()
    assert got == ref and got["title"] == "PanelTitle" and got["rounded"] and got["corner_cut"]
    pane.setFloating(False)                             # docked in its cube's window: the skin gone
    spin(qapp, lambda: False, timeout=0.3)
    assert type(pane.titleBarWidget()).__name__ != "PanelTitle" and getattr(pane, SHAPE_ATTR, QtGui.QRegion()).isEmpty()
    pane.setFloating(True)
    spin(qapp, lambda: False, timeout=0.3)
    w.detach_action.setChecked(False)
    w.set_look(get_look("classic"))
    spin(qapp, lambda: False, timeout=0.4)
    assert c.spectra.w.backgroundBrush() == plot_bg
    assert type(pane.titleBarWidget()).__name__ != "PanelTitle" and pane.widget().autoFillBackground() == fill


def test_a_slit_tab_per_cube_each_with_its_cube_s_slices(window):
    """A tab per cube in the slit panel (the user, 2026-10-11: "each time I draw a slit, as many tabs as cubes"), on
    at start with linked cubes: drawn on any image, each tab shows its own cube's slices along the same slit (its t,
    lambda and Stokes; a map its time slice alone), titled Slit: <name>; the drawn-on cube's tab in front, and a tab
    behind reads nothing until it comes in front. Shift+S (or Panels) off: one tab, the drawn-on cube's slices."""
    w, qapp = window
    tabs = w.slit_tabs
    assert w.session.state.slit_tabs and w.slit_tabs_action.isChecked()
    other, blos = w.linked
    draw_slit(w, blos, (5.2, 6.7), (30.4, 40.1))
    assert spin(qapp, lambda: w.slit_panel.pix is not None and len(w.slit_panel.pix[0]) > 30), "no slit"
    keys = list(tabs.keys)
    front = tabs.keys[tabs.currentIndex()]
    names = [tabs.tabText(i) for i in range(tabs.count())]

    def same(img, want):
        return img is not None and img.shape == want.shape and np.array_equal(img, want, equal_nan=True)

    def check(c):
        p = c.slit_panel
        ts, sl = slices_along(c.dataset, w.session, c.k, p.pix if p.pix is not None else w.slit_panel.pix)
        if p.flat:                                       # never here: the map has 3 t
            return False
        return same(p.ts_img.image, ts) and (not p.spectral or same(p.sl_img.image, sl))

    assert spin(qapp, lambda: check(blos)), "the drawn-on cube's tab without its slices"
    other_reads = list(other.scheduler.slit.reads)
    title = w.slit_dock.windowTitle()
    print("tabs", keys, names, "front", front, "title", repr(title), "reads of the tab behind", other_reads)
    assert keys == ["slit", "slit:1", "slit:2"] and front == "slit:2" and title == f"Slit: {blos.name}"
    assert other_reads == [] and other.slit_panel.ts_img.image is None
    assert not blos.slit_panel.spectral                 # a map: the time slice alone
    shown = {}
    for i, c in enumerate(w.cubes):                     # each tab in front in turn: its own cube's slices
        tabs.setCurrentIndex(i)
        shown[c.k] = spin(qapp, lambda c=c: check(c))
        assert w.slit_dock.windowTitle() == f"Slit: {c.name}"
    print("each tab its own cube's slices along the slit:", shown)
    assert all(shown.values())
    assert np.array_equal(other.slit_panel.pix[0], w.slit_panel.pix[0])        # the same slit
    w.set_slit_tabs(False)                              # one tab: the drawn-on cube's, as before
    spin(qapp, lambda: same(w.slit_panel.ts_img.image, slices_along(blos.dataset, w.session, 2, w.slit_panel.pix)[0]))
    off = (tabs.count(), w.slit_dock.windowTitle(), w.slit_tabs_action.isChecked())
    ts_main = w.slit_panel.ts_img.image
    print("off: tabs, title, ticked", off)
    assert off == (1, f"Slit: {blos.name}", False)
    assert same(ts_main, slices_along(blos.dataset, w.session, 2, w.slit_panel.pix)[0])
    w.set_slit_tabs(True)
    assert spin(qapp, lambda: tabs.count() == 3 and tabs.keys[tabs.currentIndex()] == "slit:2" and check(w.main)
                and check(blos))
    w.clear_slit()


def test_a_cube_in_its_own_window_shows_its_own_slit_panel(window):
    """Each cube in a window of its own: its slit panel goes with it, below its lambda-t, shown while there is a
    slit and with its own cube's slices; back in the window, its tab again."""
    w, qapp = window
    other, blos = w.linked
    w.detach_action.setChecked(True)
    spin(qapp, lambda: False, timeout=0.6)
    hidden = [c.panes[f"slit:{c.k}"].isVisible() for c in w.linked]
    draw_slit(w, w.main, (5.2, 6.7), (30.4, 40.1))
    assert spin(qapp, lambda: w.slit_panel.pix is not None and len(w.slit_panel.pix[0]) > 30), "no slit"
    pane = other.panes["slit:1"]
    ts, sl = slices_along(other.dataset, w.session, 1, w.slit_panel.pix)
    ok = spin(qapp, lambda: pane.isVisible() and other.slit_panel.ts_img.image is not None
              and np.array_equal(other.slit_panel.ts_img.image, ts, equal_nan=True)
              and np.array_equal(other.slit_panel.sl_img.image, sl, equal_nan=True))
    print("apart: slit panels before a slit", hidden, "after", [c.panes[f"slit:{c.k}"].isVisible() for c in w.linked],
          "main tabs", list(w.slit_tabs.keys), "its slices", ok)
    assert hidden == [False, False] and ok and pane.window() is other.dock
    assert list(w.slit_tabs.keys) == ["slit"]
    w.detach_action.setChecked(False)
    spin(qapp, lambda: False, timeout=0.6)
    assert list(w.slit_tabs.keys) == ["slit", "slit:1", "slit:2"] and not pane.isVisible()
    w.clear_slit()


def test_a_cube_s_window_offers_its_slit_panel_only_with_a_slit(window):
    """Each cube in a window of its own: Panels lists its slit panel ("other_im · Slit") but, as the main window's
    Slit, enabled only while there is a slit; without one, a show (as a saved layout's restore asks) leaves it
    hidden: it was an empty panel."""
    w, qapp = window
    other = w.linked[0]
    w.detach_action.setChecked(True)
    spin(qapp, lambda: False, timeout=0.6)
    menu = w.nav.panels.menu()

    def entry():
        menu.aboutToShow.emit()
        return [a for a in menu.actions() if a.text() == f"{other.name} · Slit"]

    pane = other.panes["slit:1"]
    before = entry()
    offered = [a.isEnabled() for a in before]
    main_offered = w.slit_dock.toggleViewAction().isEnabled()
    pane.show()
    qapp.processEvents()
    shown_without = pane.isVisible()
    draw_slit(w, w.main, (5.2, 6.7), (30.4, 40.1))
    assert spin(qapp, lambda: w.slit_panel.pix is not None and pane.isVisible()), "no slit"
    with_slit = [a.isEnabled() for a in entry()]
    w.clear_slit()
    spin(qapp, lambda: False, timeout=0.3)
    cleared = ([a.isEnabled() for a in entry()], pane.isVisible())
    print("no slit: entry enabled", offered, "(main's", main_offered, ") shown by a show", shown_without,
          "| with a slit", with_slit, "| cleared", cleared)
    assert offered == [False] and not main_offered and not shown_without
    assert with_slit == [True] and cleared == ([False], False)
    w.detach_action.setChecked(False)
    spin(qapp, lambda: False, timeout=0.3)


def test_in_glass_a_cube_s_panel_floated_and_docked_leaves_no_skin_behind(window, restore):
    """Each float and re-dock of a cube's panel in glass made a PanelSkin and, docked again, left it a child of the
    panel, inert until the window closed: removed, it is deleted."""
    from PySide6 import QtCore

    from explorer.look import get_look
    from explorer.ui.glass import PanelSkin

    w, qapp = window
    w.set_look(get_look("glass"))
    spin(qapp, lambda: False, timeout=0.6)
    w.detach_action.setChecked(True)
    spin(qapp, lambda: False, timeout=0.6)
    pane = w.linked[0].panes["spectra:1"]
    counts = []
    for _ in range(3):
        pane.setFloating(True)
        spin(qapp, lambda: False, timeout=0.2)
        pane.setFloating(False)
        spin(qapp, lambda: False, timeout=0.2)
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
        counts.append(len(pane.findChildren(PanelSkin)))
    worn = len(w.glass.skins)
    print("skins left on the docked panel after each cycle", counts, "skins glass wears", worn)
    assert counts == [0, 0, 0]
    w.detach_action.setChecked(False)
    w.set_look(get_look("classic"))
    spin(qapp, lambda: False, timeout=0.4)

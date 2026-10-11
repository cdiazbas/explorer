"""The looks (ROADMAP E5.5), offscreen: which parts each has; the colour tables (grey exact, padding at level 0,
one map per Stokes, cycling); classic: the sliders in the cursor's red, the crosshair in its locked colour, rounded
panels, no colour keys; modern: the reticle instead of two lines, the Stokes drop-down in step with the state and
no wider than the classic combo, C recolouring image, lambda-t and key, the zero lines and the cards; the spectra's
corners back on top after its stack swaps page; the key's power of ten on the top row with the unit."""
import sys
import time

import numpy as np
import pytest

from explorer.testing import synth

SHAPE = (6, 4, 21, 48, 40)


def spin(qapp, until, timeout=5.0):
    end = time.perf_counter() + timeout
    while not until() and time.perf_counter() < end:
        qapp.processEvents()
        time.sleep(0.002)
    return until()


def test_the_looks_and_their_parts():
    from explorer.look import PARTS, get_look

    assert get_look().name == "classic" and not get_look().parts
    assert get_look("modern", {}).parts == frozenset(PARTS)
    off = get_look("modern", {"EXPLORER_LOOK_OFF": "reticle, cards"})
    assert not off.has("reticle") and not off.has("cards") and off.has("colour")
    assert not get_look("modern", {"EXPLORER_LOOK_OFF": "colour"}).has("cmap")   # C needs the tables
    with pytest.raises(ValueError):
        get_look("baroque")


def test_the_colour_tables():
    from explorer.look import colormaps as cm

    assert cm.table("gray") is None
    lut = cm.table("CET-L1")
    assert lut.shape == (256, 3) and (lut[:, 0] == lut[:, 1]).all() and (lut[:, 1] == lut[:, 2]).all()
    had = "matplotlib" in sys.modules
    rd = cm.table("RdBu_r")                              # built here, matplotlib not needed
    assert tuple(rd[0]) != tuple(rd[255]) and (had or "matplotlib" not in sys.modules)
    t = cm.image_table(cm.table("CET-D4"), light=False)
    assert tuple(t[0]) == (0, 0, 0) and tuple(t[1]) == tuple(cm.table("CET-D4")[0])
    assert cm.image_table(None, light=False) is None and tuple(cm.image_table(None, light=True)[0]) == (255, 255, 255)
    reg = cm.ColormapRegistry(4)
    assert reg.maps == ["gray", "gray", "gray", "gray"]  # Q U V start in grey, the same scale as I
    assert reg.cycle(3, 1) == "CET-D4" and reg.maps[1] == "gray"       # one map per Stokes
    assert reg.cycle(0, -1) == cm.SEQUENTIAL[-1]
    n = len(reg.names_for(3))
    for _ in range(n - 1):
        reg.cycle(3, 1)
    assert reg.maps[3] == "gray"                         # round the list


def test_another_theme_keeps_each_stokes_map_where_it_can(monkeypatch):
    """Shell.set_theme: a map both themes have stays; one only the dark theme has (CET-D4, second in its list) gives
    way to the light list's second; I's sequential maps are the same in both."""
    from explorer.look import colormaps as cm

    monkeypatch.delenv("EXPLORER_DIVERGING", raising=False)
    reg = cm.ColormapRegistry(4)
    reg.maps = ["CET-L1", "CET-D4", "RdBu_r", "gray"]
    reg.set_light(True)
    assert reg.light and reg.maps == ["CET-L1", cm._divergings(True)[1], "RdBu_r", "gray"]
    assert reg.names_for(1) == cm._divergings(True)


@pytest.fixture(scope="module")
def cube(tmp_path_factory):
    return synth.write_dataset(tmp_path_factory.mktemp("look"), "c", shape=SHAPE, icube=False)["im"]


@pytest.fixture
def themed(qapp):
    """The dark style on the application (the sliders' fill is its attribute), as it was after."""
    import pyqtgraph as pg
    from PySide6 import QtGui, QtWidgets

    from explorer.ui import style

    name, pal = qapp.style().name(), QtGui.QPalette(qapp.palette())
    style.apply_theme(qapp, "dark")
    yield qapp
    qapp.setStyle(QtWidgets.QStyleFactory.create(name or "Fusion"))
    qapp.setPalette(pal)
    qapp.setProperty("explorer_light", False)
    pg.setConfigOptions(background="k", foreground="d")


def make(qapp, cube, name):
    from explorer.data.dataset import Dataset
    from explorer.look import get_look
    from explorer.ui.shell import Shell

    ds = Dataset.open(cube)
    w = Shell(ds, look=get_look(name, {}))
    w.resize(900, 600)
    w.show()
    assert spin(qapp, lambda: w.first_image_s is not None and "lambda_t" in w.last)
    return w, ds


def test_classic(themed, cube):
    from explorer.ui.imageview import CURSOR_PEN, LOCK_PEN

    w, ds = make(themed, cube, "classic")
    try:
        assert themed.style().SLIDER == CURSOR_PEN.color()            # the sliders in the markers' red
        assert w.view.reticle is None and w.view.hl.isVisible()
        w.session.lock(True)
        themed.processEvents()
        assert w.view.hl.pen.color() == LOCK_PEN.color()
        w.session.lock(False)
        themed.processEvents()
        assert w.view.hl.pen.color() == CURSOR_PEN.color()
        assert w.colours is None and w.nav.drop is None
        assert w.colour_key is not None and w.colour_key.isVisible() and w.colour_key.lut is None   # grey, classic
        assert len(w._rounders) == 4                                    # image, spectra, lambda-t, slit
        before = list(w.colours.maps) if w.colours is not None else None
        w.cycle_colours(1)                                              # C: the modern look's only
        assert (list(w.colours.maps) if w.colours is not None else None) == before
    finally:
        w.close()
        ds.close()


def test_modern(themed, cube):
    from PySide6 import QtGui

    from explorer.look import colormaps as cm

    w, ds = make(themed, cube, "modern")
    try:
        assert themed.style().SLIDER is None                           # the accent
        assert w.view.reticle is not None and not w.view.hl.isVisible()
        w.session.lock(True)
        themed.processEvents()
        assert w.view.reticle.locked
        drop = w.nav.drop
        assert drop is not None and drop.isVisible() and not w.nav.stokes.isVisible()  # the combo stays, hidden
        assert not drop.panel.isVisible()
        drop.click()
        assert drop.panel.isVisible() and drop.panel.geometry().top() >= drop.mapToGlobal(drop.rect().bottomLeft()).y()
        drop.segments.group.button(3).click()
        assert not drop.panel.isVisible()                              # a pick closes it
        assert spin(themed, lambda: w.session.state.s == 3 and w.nav.stokes.currentIndex() == 3)
        assert drop.text() == "Stokes V ▾"
        w.session.set_index("s", 1)
        themed.processEvents()
        assert drop.segments.group.checkedId() == 1 and drop.text() == "Stokes Q ▾"
        w.session.set_index("s", 3)
        assert spin(themed, lambda: w.last.get("image", (None,))[0] is not None and w.last["image"][0][1] == 3)
        assert spin(themed, lambda: w.last.get("lambda_t", (0, 0, -1))[2] == 3)
        before = w.view.img.lut
        w.cycle_colours(1)
        assert w.colours.maps[3] == "CET-D4" and w.colour_key.note == "CET-D4"
        assert w.view.img.lut is not None and before is None
        assert np.array_equal(w.lambda_t.img.lut, cm.table("CET-D4"))
        assert w.colour_key.state[0] == "Stokes V" and w.colour_key.state[3] == "CET-D4"
        w.cycle_colours(-1)
        assert w.colours.maps[3] == "gray" and w.view.img.lut is None
        # the cards in the image's black: a grey (20, 20, 22) parted the panels from the image beside them
        image_bg = QtGui.QColor(w.view.widget.backgroundBrush().color()).name()
        cards = {QtGui.QColor(x.backgroundBrush().color()).name() for x in (w.spectra.w, w.lambda_t.w)}
        print("modern: image background", image_bg, "panels", cards)
        assert cards == {image_bg} == {"#000000"}
        assert len([i for i in w.spectra.plots[1].items if type(i).__name__ == "InfiniteLine"]) >= 2   # zero line
    finally:
        w.close()
        ds.close()


def test_parts_can_be_left_out(themed, cube, monkeypatch):
    from explorer.data.dataset import Dataset
    from explorer.look import get_look
    from explorer.ui.shell import Shell

    with Dataset.open(cube) as ds:
        w = Shell(ds, look=get_look("modern", {"EXPLORER_LOOK_OFF": "reticle,stokes,colour"}))
        assert w.view.reticle is None and w.nav.drop is None and w.colours is None
        w.close()


def fire(w, seq):
    from PySide6 import QtGui

    ks = QtGui.QKeySequence(seq)
    hits = [sc for sc in w.findChildren(QtGui.QShortcut) if sc.key() == ks]
    assert len(hits) == 1, seq
    hits[0].activated.emit()


def classic_state(w):
    from PySide6 import QtGui

    return dict(lines=w.view.hl.isVisible(), reticle=w.view.reticle is not None and w.view.reticle.isVisible(),
                drop=w.nav.drop is not None and w.nav.drop.isVisible(), combo=w.nav.stokes.isVisible(),
                slider=QtGui.QGuiApplication.instance().style().SLIDER, lut=w.view.img.lut, lt_lut=w.lambda_t.img.lut,
                mark=w.spectra.lines[0].pen.color().name(), curve=w.spectra.curves[0].opts["pen"],
                zeros=any(z.isVisible() for z in w.spectra._zeros),
                key=w.colour_key is not None and w.colour_key.isVisible(),
                card=QtGui.QColor(w.spectra.w.backgroundBrush().color()).name())


def test_m_goes_round_modern_and_glass_back_to_exactly_classic(themed, cube):
    w, ds = make(themed, cube, "classic")
    try:
        w.session.set_index("s", 3)
        assert spin(themed, lambda: w.last.get("lambda_t", (0, 0, -1))[2] == 3)
        before = classic_state(w)
        fire(w, "M")
        themed.processEvents()
        assert w.look.name == "modern" and w.view.reticle.isVisible() and not w.view.hl.isVisible()
        assert w.nav.drop.isVisible() and not w.nav.stokes.isVisible() and themed.style().SLIDER is None
        assert any(z.isVisible() for z in w.spectra._zeros) and w.colour_key.isVisible()
        fire(w, "C")                                                    # V on its first diverging map
        assert w.colours.maps[3] == "CET-D4" and w.view.img.lut is not None
        fire(w, "M")
        themed.processEvents()
        assert w.look.name == "glass" and w.glass is not None and not w.nav.tb.isVisible()
        fire(w, "M")
        themed.processEvents()
        assert w.look.name == "classic" and w.glass is None and classic_state(w) == before
        fire(w, "M")
        themed.processEvents()
        assert w.colours.maps[3] == "CET-D4" and w.view.img.lut is not None      # the map chosen stays
    finally:
        w.close()
        ds.close()


def test_the_help_button_opens_and_closes_the_sheet(themed, cube):
    w, ds = make(themed, cube, "classic")
    try:
        w.nav.help.click()
        assert w.sheet.isVisible() and "look: classic" in w.sheet.text()
        w.nav.help.click()
        assert not w.sheet.isVisible()
    finally:
        w.close()
        ds.close()


def test_the_layout_keeps_the_look(qapp, tmp_path):
    from PySide6 import QtWidgets

    from explorer.ui.layout import LayoutStore

    store = LayoutStore("test", str(tmp_path / "layout.ini"))
    assert store.look() is None
    w = QtWidgets.QMainWindow()
    store.save(w, look="modern")
    assert LayoutStore("other", store.path).look() == "modern"        # one look for every way of displaying
    w.close()


def test_the_modern_stokes_is_no_wider_than_the_classic(themed, cube):
    """The sliders keep their width in the modern look: its Stokes takes the classic label and combo's room."""
    widths = {}
    for name in ("classic", "modern"):
        w, ds = make(themed, cube, name)
        try:
            w.resize(1100, 600)
            assert spin(themed, lambda: False, timeout=0.3) is False
            nav = w.nav
            stokes = (nav.drop.width() if nav.drop is not None and nav.drop.isVisible()
                      else nav.tb.widgetForAction(nav._stokes_label).width() + nav.stokes.width())
            widths[name] = (stokes, nav.sliders["t"].width())
        finally:
            w.close()
            ds.close()
    assert widths["modern"][0] <= widths["classic"][0], widths
    assert widths["modern"][1] >= widths["classic"][1], widths


def test_the_spectra_corners_come_back_on_top_after_the_stack_swaps_page(themed, cube):
    """While the panel is resized its stack shows a snapshot, then the plots again, with no resize of its own: the
    page shown again came up over the four corners and the reset left the spectra's card square (the prototype's
    F53, app/look.py:511-515)."""
    from PySide6 import QtWidgets

    from explorer.ui.cards import RADIUS

    w, ds = make(themed, cube, "classic")
    try:
        fr = w.spectra.freezer
        stack = fr.stack
        rounder = next((r for r in w._rounders if r.parent() is stack), None)
        assert rounder is not None, dict(rounded=[type(r.parent()).__name__ for r in w._rounders])

        def seen():
            kids = [x for x in stack.children() if isinstance(x, QtWidgets.QWidget)]   # bottom to top
            page = kids.index(stack.currentWidget())
            return {c.which: (c.pos().x(), c.pos().y(), kids.index(c) > page) for c in rounder.corners}
        W, H = stack.width() - RADIUS, stack.height() - RADIUS
        want = {"tl": (0, 0, True), "tr": (W, 0, True), "bl": (0, H, True), "br": (W, H, True)}
        stack.setCurrentWidget(fr.snap)                    # the resize's snapshot, then the plots again
        themed.processEvents()
        fr.timer.timeout.emit()
        assert stack.currentWidget() is fr.panel, dict(current=stack.currentWidget())
        assert spin(themed, lambda: seen() == want, timeout=1.0), dict(seen=seen(), want=want)
    finally:
        w.close()
        ds.close()


@pytest.mark.parametrize("name, lim, unit, want", [
    ("I", (0.0, 4.2e-9), "W m⁻² Hz⁻¹ sr⁻¹", ["I   [10⁻⁹ W m⁻² Hz⁻¹ sr⁻¹]", "0", "4.2"]),
    ("V", (-4.2e-9, 4.2e-9), "W m⁻² Hz⁻¹ sr⁻¹", ["V   [10⁻⁹ W m⁻² Hz⁻¹ sr⁻¹]", "−4.2", "0", "+4.2"]),
    ("V", (-4.2e-9, 4.2e-9), "", ["V   ×10⁻⁹", "−4.2", "0", "+4.2"]),           # no BUNIT
    ("I", (0.0, 42000.0), "DN", ["I   [10⁴ DN]", "0", "4.2"]),
    ("I", (0.0, 4200.0), "DN", ["I   [DN]", "0", "4200"]),                         # up to 10³ written out
])
def test_the_keys_power_of_ten_goes_with_the_unit(themed, monkeypatch, name, lim, unit, want):
    """Written after the last number only ("−4.2  0  +4.2 ×10⁻⁹") it read as that number's; on the top row with the
    unit, as the spectra's axis titles write it, the numbers carry none (the prototype's F60, app/look.py:286-294)."""
    from PySide6 import QtGui, QtWidgets

    from explorer.ui.overlays import ColourKey

    texts = []

    class Writing(QtGui.QPainter):                      # keeps the text the key draws, in order
        def drawText(self, *a):
            texts.append(next(x for x in a if isinstance(x, str)))
            return super().drawText(*a)

    host = QtWidgets.QWidget()
    host.resize(400, 300)
    key = ColourKey(host, unit=unit)
    key.set(name, lim, None)
    with monkeypatch.context() as m:
        m.setattr(QtGui, "QPainter", Writing)
        key.render(QtGui.QPixmap(key.size()))
    host.deleteLater()
    assert texts == want, dict(seen=texts, want=want)

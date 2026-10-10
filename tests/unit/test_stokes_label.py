"""The Stokes shown, "Stokes I" to "Stokes V" (ui.stokeslabel), offscreen: on the image and on lambda-t of every
cube with the four Stokes, the main cube's and a linked one's, following the Stokes of the session at once; none on a
cube with one plane along the Stokes axis nor on a map; on each panel of the 2x2 view; in the theme's ink,
drawn so; not under glass's colour key, whose top row names the Stokes there; the slit's hint below it. Each test
prints what it measured."""
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


def letter(label):
    """What a StokesLabel shows ("Stokes Q"), or None while hidden."""
    return label.toPlainText() if label.isVisible() else None


@pytest.fixture(scope="module")
def cubes(tmp_path_factory):
    d = tmp_path_factory.mktemp("stokes_label")
    main = synth.write_dataset(d, "main", shape=SHAPE, icube=False)["im"]
    other = synth.write_dataset(d, "other", shape=(SHAPE[0], SHAPE[1], 7, SHAPE[3], SHAPE[4]), seed=4, icube=False,
                                sp=False)["im"]
    single = synth.write_dataset(d, "single", shape=(SHAPE[0], 1, SHAPE[2], SHAPE[3], SHAPE[4]), seed=5,
                                 icube=False, sp=False)["im"]
    blos = d / "Blos.map.fcube"
    with open(blos, "wb") as f:
        f.write(f"datatype=4 (float), dims=3, nx={SHAPE[4]}, ny={SHAPE[3]}, nt={SHAPE[0]}, endian=l".encode()
                .ljust(512, b"\0"))
        f.write(np.random.default_rng(1).normal(size=(SHAPE[0], SHAPE[3], SHAPE[4])).astype("<f4").tobytes())
    return {"main": main, "other": other, "single": single, "map": blos}


def open_window(qapp, main, linked=()):
    from explorer.data.dataset import Dataset
    from explorer.ui.shell import Shell

    def kw(p):                                          # a map: its one axis is t
        return {"axes": "t"} if str(p).endswith(".fcube") else {}

    ds = Dataset.open(main, **kw(main))
    others = [Dataset.open(p, executors=ds.executors, **kw(p)) for p in linked]
    w = Shell(ds, linked=others)
    w.resize(1400, 600)
    w.show()
    assert spin(qapp, lambda: w.first_image_s is not None and all(c.scheduler.img is not None for c in w.linked))
    return w, [ds, *others]


@pytest.fixture
def window(qapp, cubes):
    w, files = open_window(qapp, cubes["main"], (cubes["other"], cubes["map"]))
    yield w
    w.close()
    for d in files:
        d.close()


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


def letters(w):
    """name -> (image's letter, lambda-t's letter) for every cube in the window."""
    return {c.name: (letter(c.view.stokes), letter(c.lambda_t.stokes) if c.lambda_t is not None else "no lambda-t")
            for c in w.cubes}


def drawn(view, ink, tol=40):
    """Pixels within tol (per channel) of the ink in the letter's box, with the letter and without it: the letter drawn
    in the ink adds some (an I, 1 px wide, about 9)."""
    box = view.widget.mapFromScene(view.stokes.sceneBoundingRect()).boundingRect()

    def count():
        img = view.widget.grab().toImage()
        n = 0
        for y in range(max(0, box.top()), min(img.height(), box.bottom() + 1)):
            for x in range(max(0, box.left()), min(img.width(), box.right() + 1)):
                c = img.pixelColor(x, y)
                n += abs(c.red() - ink.red()) <= tol and abs(c.green() - ink.green()) <= tol and \
                    abs(c.blue() - ink.blue()) <= tol
        return n

    shown = count()
    view.stokes.hide()
    hidden = count()
    view.stokes.show()
    return shown, hidden, (box.left(), box.top(), box.width(), box.height())


def test_every_cube_with_stokes_names_the_one_shown_on_its_image_and_lambda_t(qapp, window):
    """I -> Q -> U -> V from the session (as keys 1-4, the Stokes control and the glass bar set it): the main cube's
    and the linked cube with the same Stokes follow at once; the map has no letter, nor its curve against t."""
    from explorer.data.axes import STOKES

    w = window
    main, other, blos = w.main, w.linked[0], w.linked[1]
    print("start:", letters(w))
    for s in range(4):
        w.session.set_index("s", s)
        text = f"Stokes {STOKES[s]}"
        assert spin(qapp, lambda t=text: letter(main.view.stokes) == t and letter(other.view.stokes) == t)
        seen = letters(w)
        print(f"s={s}:", seen)
        assert seen[main.name] == (text, text) and seen[other.name] == (text, text)
        assert seen[blos.name] == (None, None)


def test_the_2x2_view_keeps_a_letter_per_panel_and_lambda_t_names_the_session_s(qapp, window):
    w = window
    w.session.store.set(path=((10.5, 10.5), (30.5, 30.5)))          # a slit drawn: its hint at the top left
    w.set_grid(True)
    w.session.set_index("s", 2)
    assert spin(qapp, lambda: letter(w.lambda_t.stokes) == "Stokes U" and w.slit_hint.isVisible())
    panels = [letter(v.stokes) for v in w.grid.views]
    v = w.grid.views[0]
    label = v.widget.mapFromScene(v.stokes.sceneBoundingRect()).boundingRect()
    print("2x2 panels:", panels, "lambda-t:", letter(w.lambda_t.stokes), "top-left panel's letter box",
          label.getRect(), "hint", w.slit_hint.geometry().getRect())
    assert panels == ["Stokes I", "Stokes Q", "Stokes U", "Stokes V"]
    assert w.slit_hint.y() >= label.bottom()        # below the letter (the box's last row: its text's margin)
    w.set_grid(False)


@pytest.mark.parametrize("which", ["single", "map"])
def test_no_label_without_the_four_stokes(qapp, cubes, which):
    """One plane along the Stokes axis (it may be Stokes I, a magnetic field or anything else), or no Stokes axis (a
    map): no label on the image nor on lambda-t, whichever Stokes the session asks for."""
    path = cubes[which]
    w, files = open_window(qapp, path)
    try:
        for s in range(4):
            w.session.set_index("s", s)
            spin(qapp, lambda: False, 0.05)
            seen = letters(w)
            print(f"{which} (ns {w.main.ns}, s {w.session.state.s}):", seen)
            assert seen[w.main.name] == (None, None if w.main.lambda_t is not None else "no lambda-t")
        assert (w.main.lambda_t is None) == (w.dataset.roles.t is None)   # a map with frames: its curve
    finally:
        w.close()
        for d in files:
            d.close()


def test_the_letter_is_in_the_theme_s_ink_and_gives_way_to_glass_s_key(qapp, window, restore):
    from explorer.look import get_look
    from explorer.ui.stokeslabel import INK

    w = window
    main, other = w.main, w.linked[0]
    w.session.store.set(path=((10.5, 10.5), (30.5, 30.5)))          # a slit drawn: its hint at the top left
    assert spin(qapp, lambda: w.slit_hint.isVisible())
    for theme in ("dark", "light"):
        w.set_theme(theme)
        for look in ("classic", "modern", "glass"):
            w.set_look(get_look(look))
            spin(qapp, lambda: False, 0.3)
            ink = INK[theme == "light"]
            colours = {name: lab.color.getRgb()[:3] if lab.isVisible() else None
                       for name, lab in (("main image", main.view.stokes), ("main lambda-t", main.lambda_t.stokes),
                                         ("linked image", other.view.stokes),
                                         ("linked lambda-t", other.lambda_t.stokes))}
            key = w.colour_key
            keyed = look == "glass" and key is not None and key.isVisible()
            px = {name: drawn(c.view, ink) for name, c in (("main", main), ("linked", other))
                  if c.view.stokes.isVisible()}
            print(f"{theme} {look}: ink {ink.getRgb()[:3]}, letters {colours}, glass key over the corner {keyed} "
                  f"(names {key.state[0] if key is not None and key.state else None}), ink px in the letter's box "
                  f"(with, without, box) {px}, hint at {w.slit_hint.pos().toTuple()}")
            want = ink.getRgb()[:3]
            assert colours["linked image"] == colours["main lambda-t"] == colours["linked lambda-t"] == want
            assert colours["main image"] == (None if keyed else want)
            assert all(shown >= hidden + 5 for shown, hidden, _box in px.values())     # drawn, in the ink
            if look == "glass":
                assert keyed and key.state[0] == "Stokes I"                        # the key names the Stokes there
            else:
                label = w.view.widget.mapFromScene(main.view.stokes.sceneBoundingRect()).boundingRect()
                assert w.slit_hint.y() >= label.bottom()    # below the letter (the box's last row: its text's margin)
    w.set_look(get_look("classic"))
    spin(qapp, lambda: False, 0.3)          # glass's own deferred give-backs, before the window closes
    assert letter(main.view.stokes) == "Stokes I"

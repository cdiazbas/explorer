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
    print("image sizes", sizes, "names", [c.name for c in w.linked], "main", w.name_tag.text)
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
    other._spectrum_pick(p.vb.mapViewToScene(QtCore.QPointF(x, 0)))  # its own lambda, on its own spectrum
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
    for look in ("glass", "classic"):
        w.set_look(get_look(look))
        spin(qapp, lambda: False, timeout=0.5)
    views = [w.view] + [c.view for c in w.linked]
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

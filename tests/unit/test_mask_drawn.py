"""The mask's outline on every image (ROADMAP E8.2, ui.mask), offscreen: on the main cube's image, a linked cube's
and the 2x2 view's four, the outline of the mask's frame at the session's t, following t on all of them; in the
look's accent in every look; drawn (pixels of that colour on the image); nothing of it without a mask. Each test
prints what it measured."""
import time

import numpy as np
import pytest

from explorer.testing import synth

SHAPE = (4, 4, 5, 48, 40)                               # t, s, lambda, y, x


def spin(qapp, until, timeout=10.0):
    end = time.perf_counter() + timeout
    while not until() and time.perf_counter() < end:
        qapp.processEvents()
        time.sleep(0.002)
    return until()


@pytest.fixture(scope="module")
def cubes(tmp_path_factory):
    from astropy.io import fits

    d = tmp_path_factory.mktemp("mask_drawn")
    main = synth.write_dataset(d, "main", shape=SHAPE, icube=False)["im"]
    blos = d / "Blos.map.fcube"
    with open(blos, "wb") as f:
        f.write(f"datatype=4 (float), dims=3, nx={SHAPE[4]}, ny={SHAPE[3]}, nt={SHAPE[0]}, endian=l".encode()
                .ljust(512, b"\0"))
        f.write(np.random.default_rng(1).normal(size=(SHAPE[0], SHAPE[3], SHAPE[4])).astype("<f4").tobytes())
    m = np.zeros((SHAPE[0], SHAPE[3], SHAPE[4]), np.uint8)
    for k in range(SHAPE[0]):                           # a box moving right by 3 px per t
        m[k, 10:30, 5 + 3 * k:20 + 3 * k] = 1
    per_t = d / "per_t_mask.fits"
    fits.PrimaryHDU(m).writeto(per_t)
    return {"main": main, "map": blos, "per_t": per_t, "boxes": m}


@pytest.fixture
def window(qapp, cubes):
    from explorer.data.dataset import Dataset
    from explorer.data.mask import Mask
    from explorer.ui.shell import Shell

    ds = Dataset.open(cubes["main"])
    linked = Dataset.open(cubes["map"], axes="t", executors=ds.executors)
    mask = Mask.open(cubes["per_t"], ds)
    w = Shell(ds, linked=[linked], mask=mask)
    w.resize(1400, 600)
    w.show()
    assert spin(qapp, lambda: w.first_image_s is not None and all(c.scheduler.img is not None for c in w.linked))
    yield w
    w.close()
    for c in (mask, linked, ds):
        c.close()


def images(w):
    """Every image view of the window: the main cube's, the linked ones', the 2x2 view's once made."""
    return [w.view, *(c.view for c in w.linked), *(w.grid.views if w.grid is not None else [])]


def drawn(w):
    """The segments each image's outline holds: [(x, y) pairs as (n, 2, 2)] per image, in images()'s order."""
    out = []
    for v in images(w):
        items = [it for it in w.mask_outlines.items if it.getViewBox() is v.vb]
        assert len(items) == 1
        x, y = items[0].getData()
        out.append(np.stack([x, y], -1).reshape(-1, 2, 2))
    return out


def test_on_every_image_following_t(qapp, window, cubes):
    from explorer.data.mask import outline

    w = window
    w.set_grid(True)
    assert spin(qapp, lambda: w.grid is not None and w.grid.isVisible())
    assert len(images(w)) == 6
    for t in (0, 2, 3, 1):
        w.session.set_index("t", t)
        qapp.processEvents()
        want = outline(cubes["boxes"][t] >= 1)
        got = drawn(w)
        print(f"t {t}: {len(want)} segments; leftmost x per image", [float(g[:, :, 0].min()) for g in got])
        for g in got:
            np.testing.assert_array_equal(g, want)
        assert float(got[0][:, :, 0].min()) == 5 + 3 * t


def test_in_the_looks_accent(qapp, window):
    from explorer.look import get_look
    from explorer.ui import glass, style

    w = window
    for name in ("classic", "modern", "glass", "classic"):
        w.set_look(get_look(name))
        qapp.processEvents()
        want = (glass.accent() if name == "glass" else style.accent()).name()
        got = {it.opts["pen"].color().name() for it in w.mask_outlines.items}
        print(name, want, got)
        assert got == {want}


def accent_pixels(w, colour):
    from PySide6 import QtGui

    img = w.view.widget.grab().toImage().convertToFormat(QtGui.QImage.Format.Format_RGB32)
    a = np.frombuffer(img.constBits(), np.uint8).reshape(img.height(), img.bytesPerLine())[:, :img.width() * 4]
    a = a.reshape(img.height(), img.width(), 4).copy()
    bgr = np.array([colour.blue(), colour.green(), colour.red()])
    return int((np.abs(a[:, :, :3].astype(int) - bgr).max(-1) <= 8).sum())


def test_drawn_on_the_image(qapp, window):
    from explorer.ui.mask import mask_colour

    w = window
    n = accent_pixels(w, mask_colour(w.look))
    print("pixels in the outline's colour:", n)
    assert n > 50


def test_nothing_without_a_mask(qapp, cubes):
    from explorer.data.dataset import Dataset
    from explorer.ui.mask import mask_colour
    from explorer.ui.shell import Shell

    ds = Dataset.open(cubes["main"])
    w = Shell(ds)
    w.resize(900, 600)
    w.show()
    try:
        assert spin(qapp, lambda: w.first_image_s is not None)
        w.set_grid(True)
        qapp.processEvents()
        # ui.mask's items are the only curves drawn as pairs of points
        curves = [it for v in images(w) for it in v.vb.allChildren()
                  if type(it).__name__ == "PlotCurveItem" and it.opts.get("connect") == "pairs"]
        n = accent_pixels(w, mask_colour(w.look))
        print("outlines:", w.mask_outlines, "curves:", len(curves), "pixels in the accent:", n)
        assert w.mask_outlines is None and not curves
    finally:
        w.close()
        ds.close()

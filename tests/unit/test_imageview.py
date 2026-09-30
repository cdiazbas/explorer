"""The image panel: what it hands pyqtgraph is the reduction of the visible region (padding at level 0); zoom stays
between the whole image and 3 x 3 pixels; the mouse gives data pixels; the crosshair sits on the cursor."""
import numpy as np
import pytest

from explorer.data.kernels import reduce_u8_serial


@pytest.fixture
def view(qapp):
    from explorer.ui.imageview import ImageView

    got = []
    v = ImageView(on_hover=lambda y, x: got.append((y, x)))
    v.widget.resize(400, 300)
    v.widget.show()
    qapp.processEvents()
    yield v, got, qapp
    v.widget.close()


def image(ny=600, nx=800):
    img = np.random.default_rng(0).normal(10, 2, (ny, nx)).astype(np.float32)
    img[:5, :] = np.nan                                 # padding
    return img


def test_what_is_painted_is_the_reduction_of_the_visible_region(view):
    v, _, qapp = view
    img = image()
    v.set_image(img, (6.0, 14.0))
    qapp.processEvents()
    r = v.last_render
    y0, y1, x0, x1 = r["region"]
    f = r["factor"]
    want = np.empty(r["shape"], np.uint8)
    reduce_u8_serial(img, y0, x0, f, 6.0, 14.0, want)
    assert f > 1 and np.array_equal(v.img.image, want)
    assert (want[0] == 0).all() and want[5 // f + 1:].min() >= 1                # padding at level 0, data on 1..255


def test_zoom_stays_between_the_whole_image_and_three_pixels(view):
    v, _, qapp = view
    img = image()
    v.set_image(img, (6.0, 14.0))
    qapp.processEvents()
    v.vb.scaleBy((8, 8))                                # far out
    qapp.processEvents()
    (x0, x1), (y0, y1) = v.vb.viewRange()
    assert x1 - x0 <= 800 * 1.01 or y1 - y0 <= 600 * 1.01                       # no further out than the fit
    for _ in range(30):                                 # far in
        v.vb.scaleBy((0.5, 0.5))
        qapp.processEvents()
    (x0, x1), (y0, y1) = v.vb.viewRange()
    assert min(x1 - x0, y1 - y0) >= 3 * 0.99                                   # at least 3 x 3 data pixels
    v.render()
    assert v.last_render["factor"] == 1                  # zoomed in: full resolution


def test_the_mouse_gives_data_pixels_and_the_crosshair_follows(view):
    from PySide6 import QtCore

    v, got, qapp = view
    v.set_image(image(), (6.0, 14.0))
    qapp.processEvents()
    v._moved(v.vb.mapViewToScene(QtCore.QPointF(120.5, 40.5)))
    assert got and abs(got[-1][0] - 40.5) < 0.6 and abs(got[-1][1] - 120.5) < 0.6
    v.set_crosshair(40, 120)
    assert (v.hl.value(), v.vl.value()) == (40.5, 120.5)

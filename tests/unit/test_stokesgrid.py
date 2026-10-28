"""The 2x2 view (ROADMAP E5.11), offscreen: key 5 or All shows I Q U V side by side over the image, each its own
Stokes at this t and lambda with its own levels, the region in view kept; zoom and pan linked, each panel rendering
only what it shows at the screen's resolution; a step in t updates all four; a click on a panel locks the cursor
there and makes its Stokes the session's (lambda-t follows); keys 1-4 and the Stokes control bring one Stokes back;
one Stokes, no 2x2 view."""
import time

import numpy as np
import pytest
from astropy.io import fits

from explorer.testing import synth

SHAPE = (3, 4, 5, 400, 360)            # larger than a panel: its render is reduced to the screen


def spin(qapp, until, timeout=10.0):
    end = time.perf_counter() + timeout
    while not until() and time.perf_counter() < end:
        qapp.processEvents()
        time.sleep(0.002)
    return until()


@pytest.fixture(scope="module")
def cube(tmp_path_factory):
    d = synth.write_dataset(tmp_path_factory.mktemp("grid"), "c", shape=SHAPE, icube=False)
    return d["im"], fits.getdata(d["im"]).astype(np.float32)


@pytest.fixture
def shell(qapp, cube):
    from explorer.data.dataset import Dataset
    from explorer.ui.shell import Shell

    ds = Dataset.open(cube[0])
    w = Shell(ds)
    w.resize(1200, 800)
    w.show()
    assert spin(qapp, lambda: w.first_image_s is not None and "lambda_t" in w.last)
    yield w, cube[1]
    w.close()
    ds.close()


def fire(w, seq):
    from PySide6 import QtGui

    ks = QtGui.QKeySequence(seq)
    hits = [sc for sc in w.findChildren(QtGui.QShortcut) if sc.key() == ks]
    assert len(hits) == 1, seq
    hits[0].activated.emit()


def shown(grid, data, st):
    """Every panel holds its own Stokes's frame at this t and lambda."""
    return all(v._full is not None and np.array_equal(v._full, data[st.t, k, st.l], equal_nan=True)
               for k, v in enumerate(grid.views))


def seen(grid):
    """What each panel shows and last rendered: for the message of an assertion that fails."""
    out = []
    for v in grid.views:
        vp, r = v.widget.viewport(), v.last_render or {}
        (x0, x1), (y0, y1) = v.vb.viewRange()
        out.append(dict(viewport=(vp.width(), vp.height()), dpr=vp.devicePixelRatioF(),
                        range=(round(y0, 1), round(y1, 1), round(x0, 1), round(x1, 1)),
                        region=r.get("region"), shape=r.get("shape"), factor=r.get("factor")))
    return out


def click(view, y, x, button=None, double=False):
    """A click at data pixel (y, x) on an ImageView's scene, as pyqtgraph hands it to sigMouseClicked."""
    from PySide6 import QtCore

    pos = view.vb.mapViewToScene(QtCore.QPointF(x + 0.5, y + 0.5))
    ev = type("Click", (), dict(scenePos=lambda self: pos, double=lambda self: double,
                                button=lambda self: button or QtCore.Qt.MouseButton.LeftButton))()
    view.widget.scene().sigMouseClicked.emit(ev)


def test_key_5_shows_the_four_stokes_with_the_region_kept(qapp, shell):
    from PySide6 import QtCore

    w, data = shell
    w.view.vb.setRange(QtCore.QRectF(10, 20, 30, 40), padding=0)
    qapp.processEvents()
    before = w.view.vb.viewRect()
    fire(w, "5")
    g = w.grid
    assert g is not None and g.isVisible() and len(g.views) == 4 and w.scheduler.grid
    assert spin(qapp, lambda: shown(g, data, w.session.state))
    assert g.region().intersects(before) and abs(g.region().center().x() - before.center().x()) < 1
    lev = [w.scheduler.levels.image(w.session.index(), False, data[0, 0, 0])]
    assert lev and w.nav.all and w.nav.stokes.currentText() == "All"
    drawn = w.view.img.image
    w.session.step("t", 1)
    assert spin(qapp, lambda: shown(g, data, w.session.state))
    assert w.view.paused and w.view.img.image is drawn                       # the covered view draws nothing
    fire(w, "5")
    assert not g.isVisible() and not w.scheduler.grid and not w.nav.all and not w.view.paused
    assert abs(w.view.vb.viewRect().center().x() - g.region().center().x()) < 1     # the same region back


def test_zoom_linked_and_each_panel_renders_what_it_shows(qapp, shell):
    from PySide6 import QtCore

    w, data = shell
    w.resize(700, 500)                                  # panels under half the image: its render is reduced
    w.set_grid(True)
    g = w.grid
    assert spin(qapp, lambda: shown(g, data, w.session.state))
    g.show_all()

    def screen_sized():                                 # no more pixels than the panel shows, in either axis
        for v in g.views:
            vp, r = v.widget.viewport(), v.last_render
            dpr = vp.devicePixelRatioF()
            if not r or r["shape"][0] > 2 * vp.height() * dpr or r["shape"][1] > 2 * vp.width() * dpr:
                return False
        return True
    assert spin(qapp, screen_sized), seen(g)
    assert all(v.last_render["factor"] > 1 for v in g.views), seen(g)         # whole: reduced

    def small():
        """The same small region in all four: centres within half a data pixel; the edges within one, as panels whose
        heights differ by a pixel (an odd total) may show a pixel more. pyqtgraph's own link lined the views up by
        where they are on the screen: on Linux the bottom row showed y 56-184 and the top row 136-264."""
        r = [v.last_render.get("region") for v in g.views]
        c = [((y0 + y1) / 2, (x0 + x1) / 2) for (y0, y1), (x0, x1) in
             (reversed(v.vb.viewRange()) for v in g.views)]
        return (all(x is not None for x in r)
                and all(abs(a - b) <= 1 for q in r for a, b in zip(q, r[0], strict=True))
                and all(abs(a - b) <= 0.5 for q in c for a, b in zip(q, c[0], strict=True))
                and r[0][1] - r[0][0] < SHAPE[3] and r[0][3] - r[0][2] < SHAPE[4])
    g.views[2].vb.setRange(QtCore.QRectF(100, 100, 40, 40), padding=0)       # a zoom in one panel
    assert spin(qapp, small), seen(g)                                         # the same small region in all four
    assert all(v.last_render["factor"] == 1 for v in g.views), seen(g)        # at full resolution there


def test_no_panel_zooms_out_past_the_whole_image(qapp, shell):
    """The single view's rule (ViewGuard: no further out than the whole image, 1x) in every panel, whichever one the
    wheel turns: zoomed out in a panel other than I's, the view went past 1x."""
    from PySide6 import QtCore

    w, data = shell
    w.set_grid(True)
    g = w.grid
    assert spin(qapp, lambda: shown(g, data, w.session.state))
    ny, nx = data.shape[-2:]
    for k in (2, 1, 3, 0):                              # the wheel over each panel in turn, far out
        vb = g.views[k].vb
        for _ in range(6):
            vb.scaleBy((1.5, 1.5), center=QtCore.QPointF(nx * 0.3, ny * 0.7))
            qapp.processEvents()
        for v in g.views:
            (x0, x1), (y0, y1) = v.vb.viewRange()
            W, H = v.vb.width(), v.vb.height()
            scale, fit = min(W / (x1 - x0), H / (y1 - y0)), min(W / nx, H / ny)
            assert scale >= fit * 0.999, (k, scale, fit)


def test_a_step_in_t_updates_the_four(qapp, shell):
    w, data = shell
    w.set_grid(True)
    assert spin(qapp, lambda: shown(w.grid, data, w.session.state))
    w.session.step("t", 1)
    assert spin(qapp, lambda: shown(w.grid, data, w.session.state))


def test_a_click_on_a_panel_locks_there_and_lambda_t_shows_its_stokes(qapp, shell):
    from PySide6 import QtCore

    w, data = shell
    w.set_grid(True)
    assert spin(qapp, lambda: shown(w.grid, data, w.session.state))
    click(w.grid.views[2], 190, 170)                    # near the centre: data, not padding
    st = w.session.state
    assert st.s == 2 and st.locked and st.cursor == (190, 170)
    assert spin(qapp, lambda: w.last.get("lambda_t", (None, None, -1))[2] == 2
                and w.last["lambda_t"][1] == (190, 170))
    assert w.grid.isVisible() and w.nav.stokes.currentText() == "All"         # the view stays
    click(w.grid.views[1], 10, 10, button=QtCore.Qt.MouseButton.RightButton)
    assert not w.session.state.locked


def test_one_stokes_back_by_key_or_control(qapp, shell):
    w, data = shell
    w.nav.stokes.setCurrentIndex(4)                                           # All
    assert w.grid.isVisible()
    fire(w, "2")
    assert spin(qapp, lambda: w.nav.stokes.currentText() == "Q")
    assert not w.grid.isVisible() and w.session.state.s == 1
    w.set_grid(True)
    w.nav.stokes.setCurrentIndex(3)
    assert spin(qapp, lambda: w.session.state.s == 3) and not w.grid.isVisible()


def test_one_stokes_no_side_by_side_view(qapp, tmp_path):
    from explorer.data.dataset import Dataset
    from explorer.ui.shell import Shell

    im = synth.write_dataset(tmp_path, "one", shape=(3, 1, 5, 40, 30), icube=False)["im"]
    with Dataset.open(im) as ds:
        w = Shell(ds)
        w.set_grid(True)
        assert w.grid is None and w.nav.stokes is None
        assert not [r for r in w.action_registry.rows if "side by side" in r[1]]
        w.close()

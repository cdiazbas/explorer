"""The mask (ROADMAP E8.2, data.mask), without a screen: a FITS or LP mask on the first cube's grid opens with one
frame (shown at every t) or one per t (its frame t at t), as CRISPEX's MASKCUBE (crispex.pro:10175-10198,
21105-21111); another grid, another number of frames or more than one leading axis is refused saying why; its
outline runs along the edges of the set pixels (value 1 or more), straight runs as one segment. Each test prints
what it decided."""
import numpy as np
import pytest

from explorer.testing import synth

SHAPE = (6, 4, 5, 48, 40)                               # t, s, lambda, y, x


@pytest.fixture(scope="module")
def main(tmp_path_factory):
    from explorer.data.link import describe

    d = tmp_path_factory.mktemp("mask")
    return d, describe(synth.write_dataset(d, "main", shape=SHAPE, sp=False, icube=False)["im"])


def boxes(n, ny=SHAPE[3], nx=SHAPE[4]):
    """n frames, each a box of ones at its own place: frame k covers y 5+k .. 15+k, x 3+2k .. 9+2k."""
    m = np.zeros((n, ny, nx), np.uint8)
    for k in range(n):
        m[k, 5 + k:15 + k, 3 + 2 * k:9 + 2 * k] = 1
    return m


def fits_mask(path, a, header=None):
    from astropy.io import fits

    fits.PrimaryHDU(a, header=header).writeto(path, overwrite=True)
    return path


def lp_mask(path, a):
    """An LP cube as IDL's lpwrite writes a byte mask: dims=3, [nx, ny, n]."""
    a = np.asarray(a, np.uint8).reshape((-1,) + a.shape[-2:])
    head = f"datatype=1 (byte), dims=3, nx={a.shape[2]}, ny={a.shape[1]}, nt={a.shape[0]}, endian=l"
    with open(path, "wb") as f:
        f.write(head.encode().ljust(512, b"\0"))
        f.write(a.tobytes())
    return path


def refused(path, main):
    from explorer.data.mask import Mask, MaskRefused

    with pytest.raises(MaskRefused) as e:
        Mask.open(path, main)
    print("refused:", e.value)
    return str(e.value)


def test_one_frame_is_shown_at_every_t(main):
    from explorer.data.mask import Mask

    d, info = main
    with Mask.open(fits_mask(d / "one.fits", boxes(1)[0]), info) as m:
        print(m.describe(), m.t)
        assert m.n == 1 and list(m.t) == [0] * SHAPE[0]
        assert all(m.inside(m.frame_at(t)).sum() == 60 for t in range(SHAPE[0]))
        assert "every t" in m.how


def test_one_frame_along_a_leading_axis_of_one_is_one_frame(main):
    from explorer.data.mask import Mask

    d, info = main
    with Mask.open(fits_mask(d / "one3.fits", boxes(1)), info) as m:        # (1, ny, nx)
        assert m.n == 1 and list(m.t) == [0] * SHAPE[0]


@pytest.mark.parametrize("kind", ["fits", "lp"])
def test_a_frame_per_t_follows_t(main, kind):
    from explorer.data.mask import Mask

    d, info = main
    a = boxes(SHAPE[0])
    path = fits_mask(d / "per_t.fits", a) if kind == "fits" else lp_mask(d / "per_t.icube", a)
    with Mask.open(path, info) as m:
        print(m.describe(), m.t)
        assert m.n == SHAPE[0] and list(m.t) == list(range(SHAPE[0]))
        for t in range(SHAPE[0]):
            np.testing.assert_array_equal(m.inside(m.frame_at(t)), a[t] >= 1)


def test_another_grid_is_refused(main):
    d, info = main
    why = refused(fits_mask(d / "wide.fits", boxes(1, nx=SHAPE[4] + 1)[0]), info)
    assert why.startswith("wide.fits:") and f"{SHAPE[4] + 1}x{SHAPE[3]} pixels against {SHAPE[4]}x{SHAPE[3]}" in why


def test_another_number_of_frames_is_refused(main):
    d, info = main
    why = refused(lp_mask(d / "four.icube", boxes(4)), info)
    assert "4 frames against 6 times" in why and "one per time" in why


def test_more_than_one_leading_axis_is_refused(main):
    d, info = main
    why = refused(fits_mask(d / "cube.fits", np.zeros((SHAPE[0], 2, SHAPE[3], SHAPE[4]), np.uint8)), info)
    assert "a mask is one frame (y, x) or one per time (t, y, x)" in why


def test_a_file_that_is_no_cube_is_refused(main):
    d, info = main
    p = d / "notes.txt"
    p.write_text("not a cube")
    assert "cannot be read as a mask" in refused(p, info)


def test_set_is_one_or_more_as_crispex_contour_level(main):
    """Level 1 (crispex.pro:7176): 0.5 is not set, 1 and 255 are, NaN is not."""
    from explorer.data.mask import Mask

    d, info = main
    a = np.zeros(SHAPE[3:], np.float32)
    a[0, :4] = [0.5, 1.0, 255.0, np.nan]
    with Mask.open(fits_mask(d / "levels.fits", a), info) as m:
        assert list(m.inside(0)[0, :4]) == [False, True, True, False]


def test_outline_of_a_box_is_its_four_sides():
    from explorer.data.mask import outline

    m = np.zeros((10, 12), bool)
    m[2:5, 3:9] = True                                  # y 2..5, x 3..9 in edge coordinates
    seg = outline(m)
    got = sorted(tuple(map(tuple, s)) for s in seg.tolist())
    print(got)
    assert got == sorted([((3, 2), (9, 2)), ((3, 5), (9, 5)), ((3, 2), (3, 5)), ((9, 2), (9, 5))])


def test_outline_at_the_border_and_of_nothing():
    from explorer.data.mask import outline

    assert outline(np.zeros((4, 5), bool)).shape == (0, 2, 2)
    full = outline(np.ones((4, 5), bool))               # the image's border
    assert sorted(tuple(map(tuple, s)) for s in full.tolist()) == sorted(
        [((0, 0), (5, 0)), ((0, 4), (5, 4)), ((0, 0), (0, 4)), ((5, 0), (5, 4))])


def test_outline_separates_every_set_pixel_from_every_unset_one():
    """On a random mask: each unit edge between two pixels that differ is covered by exactly one segment, and no
    segment covers an edge between two pixels that agree."""
    from explorer.data.mask import outline

    m = np.random.default_rng(0).random((30, 25)) > 0.6
    seg = outline(m)
    p = np.zeros((32, 27), bool)
    p[1:-1, 1:-1] = m
    want_h = p[1:, 1:-1] != p[:-1, 1:-1]
    want_v = p[1:-1, 1:] != p[1:-1, :-1]
    h, v = np.zeros_like(want_h, int), np.zeros_like(want_v, int)
    for (x0, y0), (x1, y1) in seg.astype(int).tolist():
        if y0 == y1:
            h[y0, x0:x1] += 1
        else:
            v[y0:y1, x0] += 1
    print(len(seg), "segments for", int(want_h.sum() + want_v.sum()), "unit edges")
    assert (h == want_h).all() and (v == want_v).all()
    assert len(seg) < want_h.sum() + want_v.sum()       # runs joined


def test_outline_follows_t_and_is_kept(main):
    from explorer.data.mask import Mask

    d, info = main
    with Mask.open(lp_mask(d / "kept.icube", boxes(SHAPE[0])), info) as m:
        x0 = [m.outline(t)[:, :, 0].min() for t in range(SHAPE[0])]
        print("leftmost edge per t:", x0)
        assert x0 == [3 + 2 * t for t in range(SHAPE[0])]
        assert m.outline(2) is m.outline(2)             # the second time from what was kept


def test_link_still_refuses_another_grid_with_its_words(main):
    """The grid check moved to link.other_grid: plan's message as before."""
    from explorer.data.link import plan

    d, info = main
    p = lp_mask(d / "wide.fcube", boxes(1, nx=SHAPE[4] + 1))
    link = plan(info, p)
    print(link.why)
    assert not link.ok and link.why == (f"wide.fcube: {SHAPE[4] + 1}x{SHAPE[3]} pixels against "
                                        f"{SHAPE[4]}x{SHAPE[3]} of main_im.fits; other grids are not linked yet")


def test_the_command_hands_the_mask_to_the_window(main, monkeypatch):
    from explorer import cli
    from explorer.ui import app

    d, info = main
    path = str(fits_mask(d / "given.fits", boxes(1)[0]))
    seen: dict = {}
    monkeypatch.setattr(app, "run", lambda p, **kw: seen.update(kw, path=p) or 0)    # the window, not opened here
    assert cli.main([info.path, "--mask", path]) == 0
    assert seen["mask"] == path and seen["path"] == info.path
    assert cli.main([info.path]) == 0 and seen["mask"] is None


def test_a_mask_that_does_not_exist(main, capsys):
    from explorer import cli

    d, info = main
    assert cli.main([info.path, "--mask", str(d / "none.fits")]) == 2
    assert "no such file" in capsys.readouterr().err


def test_a_refused_mask_is_said_and_nothing_opens(main, capsys, monkeypatch):
    """A mask that cannot be drawn on the first cube (here 5 frames against 6 times) stops the start, as IDL does:
    a window opened without it would leave the reason in a terminal nobody looks at."""
    from explorer.ui import app as app_mod
    from explorer.ui.app import open_mask

    d, info = main
    bad = lp_mask(d / "five.icube", boxes(5))
    assert open_mask(bad, info) is None
    err = capsys.readouterr().err
    print(err)
    assert "not opened: the mask five.icube: 5 frames against 6 times" in err
    assert "Without --mask the cube opens without it" in err
    shells = []
    monkeypatch.setattr("explorer.ui.shell.Shell.__init__", lambda self, *a, **k: shells.append(1) or None)
    assert app_mod.start(info.path, mask=bad, saved_layout=False) is None
    assert shells == []                                         # no window was made
    m = open_mask(lp_mask(d / "six.icube", boxes(6)), info)
    try:
        assert m is not None and "its 6 frames are the 6 times of main_im.fits" in capsys.readouterr().err
    finally:
        m.close()

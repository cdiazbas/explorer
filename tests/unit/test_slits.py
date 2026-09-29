"""Slits: the path through the points clicked, runs of neighbouring pixels, and the values along it against the
FITS data; and FrameReader.points, which the profile sample reads with."""
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest
from astropy.io import fits

from explorer.data import axes, formats
from explorer.data.io import FrameReader
from explorer.data.pixel import open_pixel
from explorer.data.slits import (
    frame_index,
    pixel_runs,
    read_slit_bands,
    read_slit_blocks,
    read_slit_slab,
    slit_path,
    slit_pixels,
)
from explorer.testing import synth

SHAPE = (3, 4, 5, 48, 40)


@pytest.fixture(scope="module")
def dataset(tmp_path_factory):
    return synth.write_dataset(tmp_path_factory.mktemp("slits"), "c", shape=SHAPE)


def test_path_passes_through_every_point_about_step_apart():
    pts = [(5.5, 10.5), (20.5, 30.5), (32.5, 12.5)]
    p = slit_path(pts)
    assert np.allclose(p[0], pts[0]) and np.allclose(p[-1], pts[-1])
    assert min(np.hypot(*(p - pts[1]).T)) < 0.5                        # through the middle point
    steps = np.hypot(*np.diff(p, axis=0).T)
    assert np.all(steps[:-1] < 1.001) and np.all(steps[:-1] > 0.9)
    straight = slit_path([(0.5, 0.5), (10.5, 0.5)])
    assert np.allclose(straight[:, 1], 0.5) and len(straight) == 11
    assert len(slit_path([(3.0, 4.0)])) == 1 and len(slit_path([(3.0, 4.0), (3.0, 4.0)])) == 1


def test_pixels_are_clipped_to_the_image():
    iy, ix = slit_pixels(np.array([[-2.0, 3.7], [45.2, 60.0]]), 48, 40)
    assert iy.tolist() == [3, 47] and ix.tolist() == [0, 39]


def test_runs_of_neighbouring_pixels():
    assert pixel_runs([(1, 2), (1, 3), (1, 5), (0, 9), (1, 4), (1, 3)]) == [(0, 9, 1), (1, 2, 4)]
    assert pixel_runs([]) == []


def test_slab_and_bands_equal_the_fits_data(dataset):
    data = fits.getdata(dataset["im"]).astype(np.float32)             # (t, s, l, y, x)
    lay = formats.open_layout(dataset["im"])
    roles = axes.roles(lay.axes, lay.shape)
    iy, ix = slit_pixels(slit_path([(5.5, 10.5), (20.5, 30.5), (32.5, 12.5)]), SHAPE[3], SHAPE[4])
    with FrameReader(lay) as fr, open_pixel(dataset["im"], fr) as sp:
        slab, runs = read_slit_slab(sp, iy, ix)
        assert runs == len(pixel_runs(zip(iy.tolist(), ix.tolist(), strict=True)))
        assert np.array_equal(slab, np.moveaxis(data[:, :, :, iy, ix], -1, 0).transpose(0, 2, 1, 3), equal_nan=True)
        with ThreadPoolExecutor(4) as pool:
            assert np.array_equal(read_slit_slab(sp, iy, ix, pool=pool)[0], slab, equal_nan=True)
        blocks, n = read_slit_blocks(sp, [(int(iy[0]), int(ix[0]))])
        assert n == 1 and np.array_equal(blocks[(int(iy[0]), int(ix[0]))], slab[0], equal_nan=True)
        idxs = [frame_index(3, roles, t=t, s=2, l=1) for t in range(SHAPE[0])]
        bands = read_slit_bands(fr, idxs, iy, ix)
        assert np.array_equal(bands, data[:, 2, 1][:, iy, ix], equal_nan=True)


def test_points_read_pixels_at_their_own_frames(dataset):
    data = fits.getdata(dataset["im"]).astype(np.float32)
    with FrameReader(formats.open_layout(dataset["im"])) as fr:
        ys, xs = np.array([20, 24, 2]), np.array([15, 20, 2])
        fn = np.array([[0, 7], [21, 59], [30, 5]])                     # frame numbers, (t, s, l) in file order
        got = fr.points(ys, xs, fn)
        t, s, lam = np.unravel_index(fn, SHAPE[:3])
        assert np.array_equal(got, data[t, s, lam, ys[:, None], xs[:, None]], equal_nan=True)
        with pytest.raises(IndexError):
            fr.points([48], [0], [[0]])
        with pytest.raises(IndexError):
            fr.points([0], [0], [[60]])


def test_frame_index_skips_absent_axes():
    r = axes.roles(("WAVE", "UTC", "HPLT", "HPLN"), (7, 3, 8, 8))
    assert frame_index(2, r, t=2, s=3, l=5) == (5, 2)

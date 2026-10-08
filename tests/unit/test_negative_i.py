"""The negative-I rule (data/masking.py): in a cube of 4 Stokes, where I is negative every Stokes is NaN, at every
path a value leaves the data layer, with and without a per-pixel file, FITS and LP; a cube of one Stokes keeps its
negative values. The cubes have a ring inside the field of view as an aligned cube's border: I negative near the
padding value, Q = U = V = I there; in the LP cube the ring holds the padding value itself (its idlsave's
nan_rplcmnt) and copies of it perturbed by the alignment's interpolation, which the exact blank test misses."""
import threading
import time

import numpy as np
import pytest
from astropy.io import fits

from explorer.core.levels import image_levels, panel_levels
from explorer.data import axes, formats
from explorer.data.dataset import Dataset
from explorer.data.io import FrameReader
from explorer.data.rowbands import RowBands
from explorer.data.slits import frame_index, slit_path
from explorer.data.stats import quv_amplitude_ranges, sample_profiles
from explorer.testing import synth

SHAPE = (3, 4, 5, 40, 36)                   # (t, s, lambda, y, x)
BLANK = np.float32(-1.7691475e-08)          # an aligned 8542 cube's nan_rplcmnt
RING = (20, 1)                              # a pixel of the ring (y, x), perturbed in the LP cube; GOOD inside
GOOD = (20, 18)


def ring(ny, nx):
    """A border 3-4 pixels wide along the left and right edges, where the levels' [::8, ::8] subsample sees it."""
    r = np.zeros((ny, nx), bool)
    r[10:30, :3] = r[10:30, nx - 4:] = True
    return r


def with_ring(data, perturbed=True):
    """data (t, s, lambda, y, x) with the ring set to the padding value at every Stokes (Q = U = V = I), every other
    ring pixel perturbed as interpolation leaves it (-1.76914732e-08, -1.76914714e-08, ...)."""
    out = data.copy()
    r = ring(*data.shape[-2:])
    vals = np.full(r.sum(), BLANK, np.float32)
    if perturbed:
        vals[1::2] = BLANK * np.float32(1 - 1e-7 * (1 + np.arange(vals[1::2].size) % 5))
    out[..., r] = vals
    return out


def expected(data):
    """What every read must give: NaN at every Stokes where I is negative."""
    out = data.astype(np.float32).copy()
    neg = out[:, :1] < 0
    out[np.broadcast_to(neg, out.shape)] = np.nan
    return out


def _lp_header(nx, ny, nt, ns):
    stokes = "[I,Q,U,V]" if ns == 4 else "[I]"
    return f"stokes={stokes}, ns={ns} :  datatype=4 (float), dims=3, nx={nx}, ny={ny}, nt={nt}, endian=l".encode()


def write_lp(directory, data, sp: bool, blank=True):
    """An LP float cube c=0-<nt-1>_im.fcube from data (t, s, lambda, y, x), its _sp.fcube when sp, and its idlsave
    (fac 1, nan_rplcmnt the padding value) when blank."""
    nt, ns, nl, ny, nx = data.shape
    stem = f"c=0-{nt - 1}"
    im = directory / f"{stem}_im.fcube"
    im.write_bytes(_lp_header(nx, ny, nt * ns * nl, ns).ljust(512, b"\0") + data.astype("<f4").tobytes())
    if sp:
        pp = data.transpose(3, 4, 1, 0, 2)                                     # (y, x, s, t, lambda)
        (directory / f"{stem}_sp.fcube").write_bytes(_lp_header(nl, nt, ny * nx * ns, ns).ljust(512, b"\0")
                                                     + pp.astype("<f4").tobytes())
    if blank:
        synth.write_idlsave(directory / f"{stem}_im_times+wvl.idlsave",
                            {"fac": np.float32(1.0), "nan_rplcmnt": BLANK})
    return im


@pytest.fixture(scope="module")
def cubes(tmp_path_factory):
    """{(kind, sp): (path, the values every read must give)} for kind fits and lp, with and without a per-pixel file."""
    d = tmp_path_factory.mktemp("negi")
    im = synth.write_stokes_cube(d / "f_im.fits", shape=SHAPE)
    with fits.open(im, mode="update") as h:
        h[0].data[...] = with_ring(np.asarray(h[0].data, np.float32), perturbed=False).astype(">f4")
    synth.write_sp_fits(im, d / "f_sp.fits")
    nosp = d / "nosp"
    nosp.mkdir()
    lp_sp, lp_nosp = d / "lpsp", d / "lpnosp"
    lp_sp.mkdir()
    lp_nosp.mkdir()
    data = fits.getdata(im).astype(np.float32)
    lp_data = with_ring(data)
    return {("fits", True): (im, expected(data)), ("fits", False): (im, expected(data)),
            ("lp", True): (write_lp(lp_sp, lp_data, sp=True), expected(lp_data)),
            ("lp", False): (write_lp(lp_nosp, lp_data, sp=False), expected(lp_data))}


CASES = [("fits", True), ("fits", False), ("lp", True), ("lp", False)]


def open_ds(cubes, case):
    path, want = cubes[case]
    ds = Dataset.open(path, no_sp=not case[1])
    assert (ds.pixel is not None) == case[1]
    return ds, want


def nans(a):
    return int(np.isnan(a).sum())


@pytest.mark.parametrize("case", CASES)
def test_frames_of_every_stokes_are_nan_where_i_is_negative(cubes, case):
    ds, want = open_ds(cubes, case)
    with ds:
        y, x = RING
        if case[0] == "lp":                                                    # missed by the blank test
            raw = ds.frames.read_raw((1, 0, 2))[y, x]
            print(case, "as stored", repr(raw), "nan_rplcmnt", repr(BLANK))
            assert raw < 0 and raw != BLANK
        for s in range(4):
            got = ds.image((1, s, 2)).result(5)
            print(case, "Stokes", "IQUV"[s], f"ring ({y}, {x}): {got[y, x]!r}", "NaN", nans(got),
                  "want", nans(want[1, s, 2]))
            np.testing.assert_array_equal(got, want[1, s, 2])
            assert np.isnan(got[ring(*got.shape)]).all()


@pytest.mark.parametrize("case", CASES)
def test_frames_of_q_u_v_without_i_read_before(cubes, case):
    """Q first, before any frame of I: one read of I's frame, kept; then U and V find it."""
    ds, want = open_ds(cubes, case)
    with ds:
        q = ds.frames.read((2, 1, 4))
        assert len(ds.frames.neg_i._lru) == 1
        np.testing.assert_array_equal(q, want[2, 1, 4])
        np.testing.assert_array_equal(ds.frames.read((2, 3, 4)), want[2, 3, 4])
        assert len(ds.frames.neg_i._lru) == 1 and ds.nbytes() >= ds.frames.neg_i.nbytes() > 0


@pytest.mark.parametrize("case", CASES)
def test_spectra_and_lambda_t_at_a_ring_pixel_are_nan(cubes, case):
    ds, want = open_ds(cubes, case)
    with ds:
        for y, x in (RING, GOOD):
            if ds.pixel is not None:
                blk = ds.pixel_block(y, x).result(5)                         # (s, t, lambda)
                print(case, (y, x), "block NaN", nans(blk), "of", blk.size)
                np.testing.assert_array_equal(blk, want[:, :, :, y, x].transpose(1, 0, 2))
            spec = ds.read_series(y, x, (1, 0, 0), [1, 2])                   # (s, lambda) at t = 1
            np.testing.assert_array_equal(spec, want[1, :, :, y, x])
            for s in range(4):
                lt = ds.series(y, x, (0, s, 0), [0, 2]).result(5)            # (t, lambda) of one Stokes
                print(case, (y, x), "lambda-t", "IQUV"[s], "NaN", nans(lt), "of", lt.size)
                np.testing.assert_array_equal(lt, want[:, s, :, y, x])
            prof = ds.read_series(y, x, (1, 2, 0), [2])                     # one Stokes' profile
            np.testing.assert_array_equal(prof, want[1, 2, :, y, x])


@pytest.mark.parametrize("case", CASES)
def test_slit_slices_are_nan_where_i_is_negative(cubes, case):
    ds, want = open_ds(cubes, case)
    with ds:
        iy, ix = ds.slit(slit_path([(1.5, 15.5), (18.5, 25.5), (34.5, 15.5)]))  # across both sides of the ring
        assert ring(ds.ny, ds.nx)[iy, ix].any()
        if ds.pixel is not None:
            slab = ds.slab(iy, ix).result(5)                                   # (npath, s, t, lambda)
            print(case, "slab NaN", nans(slab))
            np.testing.assert_array_equal(slab, want[:, :, :, iy, ix].transpose(3, 1, 0, 2))
        for s in range(4):
            idxs = [frame_index(3, ds.roles, t=t, s=s, l=3) for t in range(SHAPE[0])]
            band = ds.bands(idxs, iy, ix).result(5)
            print(case, "slit", "IQUV"[s], "NaN", nans(band))
            np.testing.assert_array_equal(band, want[:, s, 3][:, iy, ix])
            np.testing.assert_array_equal(ds.frames.read_rows((1, s, 3), 5, 25), want[1, s, 3, 5:25])


@pytest.mark.parametrize("case", [("fits", False), ("lp", False)])
def test_levels_leave_out_negative_intensity(cubes, case):
    """Levels come from what is read: no negative I in Stokes I's percentiles, no padding in Q's."""
    ds, want = open_ds(cubes, case)
    with ds:
        img = ds.image((0, 0, 0)).result(5)
        lo, hi = image_levels(img, symmetric=False)
        print(case, "I levels", lo, hi)
        assert lo > 0 and (lo, hi) == image_levels(want[0, 0, 0], symmetric=False)
        lt = ds.read_series(*RING, (0, 1, 0), [0, 2])
        assert panel_levels(lt, symmetric=True) == (0.0, 1.0)                 # nothing finite at the ring
        assert image_levels(ds.image((0, 1, 0)).result(5), True) == image_levels(want[0, 1, 0], True)


@pytest.mark.parametrize("case", [("fits", False), ("lp", False)])
def test_row_blocks_keep_i_beside_q(cubes, case):
    """Series a row at a time (network storage): Q's lambda-t takes I's block of the same rows, kept beside it."""
    path, want = cubes[case]
    with Dataset.open(path, no_sp=True) as ds:
        rb = RowBands(ds.frames)
        y, x = RING
        got = rb.series(y, x, (0, 1, 0), [0, 2])
        print(case, "row block lambda-t of Q at the ring: NaN", nans(got), "of", got.size)
        np.testing.assert_array_equal(got, want[:, 1, :, y, x])
        assert len(rb._lru) == 2                                               # Q's block and I's
        np.testing.assert_array_equal(rb.peek(*GOOD, (0, 1, 0), [0, 2]), want[:, 1, :, GOOD[0], GOOD[1]])
        np.testing.assert_array_equal(rb.series(y, x, (0, 0, 0), [1, 2]), want[0, :, :, y, x])


@pytest.mark.parametrize("case", [("fits", False), ("lp", False), ("lp", True)])
def test_points_and_the_profile_sample(cubes, case):
    path, want = cubes[case]
    with Dataset.open(path, no_sp=not case[1]) as ds:
        ys, xs, ts = np.array([RING[0], GOOD[0]]), np.array([RING[1], GOOD[1]]), np.array([1, 2])
        prof = ds.executors.numba.submit(sample_profiles, ys, xs, ts, ds.frames, ds.roles, ds.pixel).result(5)
        np.testing.assert_array_equal(prof, np.stack([want[1, :, :, RING[0], RING[1]],
                                                      want[2, :, :, GOOD[0], GOOD[1]]]))
        q_only = ds.executors.numba.submit(ds.frames.points, ys, xs, np.array([[1 * 20 + 5 + 2], [1 * 20 + 5 + 2]]))
        got = q_only.result(5)                                                 # Q at t 1, lambda 2: I gathered
        print(case, "points of Q", got.ravel())
        assert np.isnan(got[0, 0]) and got[1, 0] == want[1, 1, 2, GOOD[0], GOOD[1]]


def test_quv_ranges_ignore_the_ring(cubes, tmp_path):
    """The Q U V ranges from whole frames, with no continuum tuning to divide by: the ring's |Q| = |I| would set
    them; with the rule they equal those of the cube with NaN there."""
    path, want = cubes[("lp", False)]
    nan_cube = write_lp(tmp_path, want, sp=False, blank=False)
    got = []
    for p in (path, nan_cube):
        with Dataset.open(p, no_sp=True) as ds:
            got.append(quv_amplitude_ranges(ds.frames, ds.roles, None, 1, min_px=10)[:2])
    print("with the ring", got[0][0], "with NaN", got[1][0])
    assert repr(got[0]) == repr(got[1])


def test_one_stokes_cubes_and_maps_keep_negative_values(tmp_path):
    """A Doppler map or a difference is negative by nature: nothing masked without exactly 4 Stokes (a guard: it
    passes before the rule too)."""
    im = synth.write_stokes_cube(tmp_path / "one_im.fits", shape=(2, 1, 3, 24, 20))
    with fits.open(im, mode="update") as h:
        h[0].data[..., 5:15, 5:15] *= -1
    data = fits.getdata(im).astype(np.float32)
    with Dataset.open(im, no_sp=True) as ds:
        img = ds.image((1, 0, 2)).result(5)
        print("one Stokes: negative pixels kept", int((img < 0).sum()))
        np.testing.assert_array_equal(img, data[1, 0, 2])
        np.testing.assert_array_equal(ds.read_series(8, 8, (0, 0, 0), [0, 2]), data[:, 0, :, 8, 8])
    frames = np.linspace(-1, 1, 3 * 6 * 5, dtype=np.float32).reshape(3, 6, 5)  # a velocity map, one frame per scan
    vmap = tmp_path / "Vlos_x=0-2.fcube"
    vmap.write_bytes(b" :  datatype=4 (float), dims=3, nx=5, ny=6, nt=3, endian=l".ljust(512, b"\0")
                     + frames.astype("<f4").tobytes())
    with Dataset.open(vmap, no_sp=True) as ds:
        np.testing.assert_array_equal(ds.image((1,)).result(5), frames[1])


def test_where_i_is_negative_is_read_once_for_q_u_v_at_once(cubes):
    """The 2x2 view asks for Q, U and V together: I's frame is read once, beside the first of them, and the others
    wait for it; a read ahead (one part, a pool thread) never waits, and reads it again instead."""
    path, want = cubes[("fits", False)]
    lay = formats.open_layout(path)
    with FrameReader(lay) as fr:
        fr.stokes = axes.roles(lay.axes, lay.shape).s
        reads, raws = [], fr._read_raws

        def slow(idxs, chunks=None):
            i = [tuple(j) for j in idxs if tuple(j)[1] == 0]
            reads.extend(i)
            if i:
                time.sleep(0.05)
            return raws(idxs, chunks)

        fr._read_raws = slow
        out = {}
        th = [threading.Thread(target=lambda s=s: out.__setitem__(s, fr.read((1, s, 2)))) for s in (1, 2, 3)]
        for t in th:
            t.start()
        for t in th:
            t.join()
        assert reads == [(1, 0, 2)]
        for s in (1, 2, 3):
            np.testing.assert_array_equal(out[s], want[1, s, 2])
        reads.clear()
        th = [threading.Thread(target=lambda s=s: out.__setitem__(s, fr.read((2, s, 2), chunks=1))) for s in (1, 2)]
        for t in th:
            t.start()
        for t in th:
            t.join()
        assert reads == [(2, 0, 2), (2, 0, 2)]
        np.testing.assert_array_equal(out[2], want[2, 2, 2])

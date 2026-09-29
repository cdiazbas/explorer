"""Series a block of rows at a time: the same values as FrameReader.series, neighbours of the block from memory,
the budget respected; Dataset uses it on network storage only, without a per-pixel file."""
import types

import numpy as np
import pytest
from astropy.io import fits

from explorer.data import formats
from explorer.data.dataset import Dataset
from explorer.data.io import FrameReader
from explorer.data.rowbands import RowBands
from explorer.testing import synth

SHAPE = (3, 4, 5, 20, 12)                  # 20 rows: blocks of 8 are [0, 8), [8, 16) and the partial [16, 20)
R8 = 8                                     # blocks of 8 rows here, to test blocks and their edges


@pytest.fixture(scope="module")
def dataset(tmp_path_factory):
    d = synth.write_dataset(tmp_path_factory.mktemp("rb"), "c", shape=SHAPE)
    return d, fits.getdata(d["im"]).astype(np.float32)


def test_row_band_is_the_rows_of_every_frame(dataset):
    d, data = dataset
    with FrameReader(formats.open_layout(d["im"])) as fr:
        band = fr.row_band((0, 2, 0), [0, 2], 8, 16)                  # lambda-t frames of Stokes 2
        assert band.shape == (3, 5, 8, 12)
        np.testing.assert_array_equal(band.astype(np.float32), data[:, 2, :, 8:16, :])


@pytest.mark.parametrize("idx, free", [((0, 1, 0), [0, 2]), ((2, 0, 0), [1, 2]), ((0, 0, 0), [0, 1, 2])])
def test_values_equal_the_series_and_neighbours_come_from_memory(dataset, idx, free):
    d, _ = dataset
    with FrameReader(formats.open_layout(d["im"])) as fr:
        rb = RowBands(fr, rows=R8)
        for y, x in [(9, 3), (19, 11), (0, 0)]:                         # middle, last partial block, corner
            assert rb.peek(y, x, idx, free) is None
            np.testing.assert_array_equal(rb.series(y, x, idx, free), fr.series(y, x, idx, free))
            ny = y + 1 if (y + 1) % 8 and y + 1 < SHAPE[3] else y - 1   # a neighbour in the same block
            got = rb.peek(ny, (x + 5) % SHAPE[4], idx, free)
            assert got is not None
            np.testing.assert_array_equal(got, fr.series(ny, (x + 5) % SHAPE[4], idx, free))
        assert rb.peek(7, 3, idx, free) is not None and rb.peek(8, 3, idx, free) is not None


def test_another_fixed_index_is_another_series(dataset):
    d, _ = dataset
    with FrameReader(formats.open_layout(d["im"])) as fr:
        rb = RowBands(fr, rows=R8)
        rb.series(9, 3, (0, 1, 0), [0, 2])                              # lambda-t of Stokes 1
        assert rb.peek(9, 3, (0, 3, 0), [0, 2]) is None                  # Stokes 3: not held
        assert rb.peek(9, 3, (2, 1, 4), [0, 2]) is not None              # t and lambda are free: same series


def test_budget_evicts_old_blocks_and_small_budgets_read_the_pixel_alone(dataset):
    d, _ = dataset
    with FrameReader(formats.open_layout(d["im"])) as fr:
        block = 3 * 5 * 8 * 12 * 4                                      # lambda-t block of 8 rows, bytes
        rb = RowBands(fr, rows=R8, max_bytes=block)
        rb.series(1, 1, (0, 0, 0), [0, 2])
        rb.series(9, 1, (0, 0, 0), [0, 2])                              # evicts the first block
        assert rb.nbytes() == block and rb.peek(1, 1, (0, 0, 0), [0, 2]) is None
        tiny = RowBands(fr, rows=R8, max_bytes=block - 1)
        np.testing.assert_array_equal(tiny.series(1, 1, (0, 0, 0), [0, 2]), fr.series(1, 1, (0, 0, 0), [0, 2]))
        assert tiny.nbytes() == 0


def _probe(network):
    return types.SimpleNamespace(strip=8, read_ahead=2, readers=2, gather_threads=4, network=network,
                                 describe=lambda: "stand-in probe")


def test_dataset_uses_row_blocks_on_network_storage_without_a_per_pixel_file(dataset):
    d, data = dataset
    with Dataset.open(d["im"], no_sp=True, probe=_probe(True)) as ds:
        assert ds.rowbands is not None and ds.rowbands.rows == 1 and "a block of 1 row" in ds.describe()
        first = ds.series(9, 3, (0, 1, 0), [0, 2]).result(5)
        np.testing.assert_array_equal(first, data[:, 1, :, 9, 3])
        along = ds.series(9, 11, (0, 1, 0), [0, 2])                       # the same row: from memory
        assert along.done() and np.array_equal(along.result(), data[:, 1, :, 9, 11], equal_nan=True)
        assert ds.rowbands.peek(10, 3, (0, 1, 0), [0, 2]) is None         # the next row: not read yet
        assert ds.nbytes() >= ds.rowbands.nbytes() > 0
        ds.update_memory()
        assert ds.rowbands.max_bytes == ds.budgets.pixel
    with Dataset.open(d["im"], no_sp=True, probe=_probe(False)) as ds:
        assert ds.rowbands is None
    with Dataset.open(d["im"], probe=_probe(True)) as ds:
        assert ds.pixel is not None and ds.rowbands is None                # the per-pixel file serves pixels

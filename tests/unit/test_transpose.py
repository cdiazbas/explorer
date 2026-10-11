"""`explorer transpose`: the image cube of a per-pixel FITS file alone, written once in blocks of rows (data.transpose).
Its images equal the image cube's the per-pixel file was made from, byte for byte; its header pairs it with the
per-pixel file and gives the same times and wavelengths; never written under the observatory's read-only tree."""
import os
import shutil

import numpy as np
import pytest
from astropy.io import fits

from explorer import cli
from explorer.data import axes as _axes
from explorer.data import formats
from explorer.data.formats.companions import pairs
from explorer.data.transpose import read_only_trees, refused_output, transpose
from explorer.testing import synth

SHAPE = (3, 4, 5, 16, 12)          # (t, s, lambda, y, x)


@pytest.fixture(scope="module")
def alone(tmp_path_factory):
    """c_im.fits (the reference) and c_sp.fits made from it, the per-pixel file alone in another directory."""
    d = tmp_path_factory.mktemp("transpose")
    im = synth.write_stokes_cube(d / "c_im.fits", shape=SHAPE)
    a = d / "alone"
    a.mkdir()
    sp = synth.write_sp_fits(im, a / "c_sp.fits", wcs=True)
    return str(im), str(sp)


@pytest.mark.parametrize("block", [1, 3 * 12 * 4 * 3 * 5 * 4, 64 << 20])     # a row, 3 rows, the whole file
def test_the_copy_equals_the_image_cube(alone, tmp_path, block):
    im, sp = alone
    out = tmp_path / "c_im.fits"
    r = transpose(sp, out, block=block)
    print(r)
    with fits.open(im) as a, fits.open(out) as b:
        assert b[0].data.dtype == a[0].data.dtype and np.array_equal(a[0].data, b[0].data, equal_nan=True)
        assert [h.name for h in b] == [h.name for h in a]
    assert formats.fits_layout(out).axes == formats.fits_layout(im).axes
    assert pairs(out, sp) and formats.per_pixel(out) is None
    ra, rb = _axes.read(im, formats.fits_layout(im)), _axes.read(out, formats.fits_layout(out))
    assert ra[0] == rb[0]
    assert np.array_equal(ra[1].t_sec, rb[1].t_sec) and np.array_equal(ra[1].lam_nm, rb[1].lam_nm)
    assert not os.path.exists(str(out) + ".part")


def test_refused_beside_the_data_and_over_an_existing_file(alone, tmp_path, monkeypatch):
    """Never beside the per-pixel file itself; for one reached through a link (data/ links to the observatory's
    reduced data), never anywhere in the tree its target is in, beside the link allowed; never under
    EXPLORER_READ_ONLY; never over an existing file."""
    _, sp = alone
    tree = tmp_path / "observatory" / "reduc" / "2024" / "cubes"
    tree.mkdir(parents=True)
    (tmp_path / "observatory" / "other").mkdir()
    real = shutil.copy(sp, tree / "c_sp.fits")
    mine = tmp_path / "project" / "data"
    mine.mkdir(parents=True)
    given = mine / "c_sp.fits"
    os.symlink(real, given)
    print("read only:", read_only_trees(given))
    for p in (tree / "c_im.fits", tmp_path / "observatory" / "other" / "c_im.fits"):
        with pytest.raises(ValueError, match="never written there") as e:
            transpose(given, p)
        print(e.value)
    assert not os.path.exists(tree / "c_im.fits.part")
    assert refused_output(mine / "c_im.fits", given) is None                  # beside the link: allowed
    assert refused_output(tmp_path / "project" / "c_im.fits", given) is None
    os.symlink(tmp_path / "observatory", tmp_path / "project" / "obs")        # a link into the tree: followed
    assert refused_output(tmp_path / "project" / "obs" / "other" / "c_im.fits", given) is not None
    assert refused_output(os.path.join(os.path.dirname(sp), "c_im.fits"), sp) is not None     # beside it
    monkeypatch.setenv("EXPLORER_READ_ONLY", str(tmp_path / "project"))
    assert refused_output(mine / "c_im.fits", given) is not None
    monkeypatch.delenv("EXPLORER_READ_ONLY")
    (tmp_path / "x_im.fits").write_bytes(b"")
    with pytest.raises(ValueError, match="exists"):
        transpose(sp, tmp_path / "x_im.fits")


def test_the_command_writes_it_beside_a_link_and_explorer_pairs_them(alone, tmp_path, capsys):
    """explorer transpose c_sp.fits <dir>: <dir>/c_im.fits, and a link <dir>/c_sp.fits to the per-pixel file, so
    `explorer <dir>/c_im.fits` opens both."""
    im, sp = alone
    assert cli.main(["transpose", sp, str(tmp_path), "--block-mb", "1"]) == 0
    err = capsys.readouterr().err
    print(err)
    out = tmp_path / "c_im.fits"
    assert out.exists() and os.path.islink(tmp_path / "c_sp.fits")
    assert os.path.realpath(tmp_path / "c_sp.fits") == os.path.realpath(sp)
    assert formats.opening(str(tmp_path / "c_sp.fits")).path == str(out)
    assert "100 %" in err and f"explorer {out}" in err
    assert cli.main(["transpose", sp, os.path.dirname(sp)]) == 1                 # beside the per-pixel file
    assert "never written there" in capsys.readouterr().err

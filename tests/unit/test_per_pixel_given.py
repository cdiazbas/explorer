"""A per-pixel file opened as a cube is refused by its header, and a header whose times or wavelengths do not match
the data is refused at opening: `explorer nb_6563_..._sp.fits` read the header's 35 times for 2028 steps along the
image's rows, and the toolbar indexed time 2027."""
import shutil

import pytest
from astropy.io import fits

from explorer.data import axes as _axes
from explorer.data.dataset import Dataset
from explorer.testing import synth

SHAPE = (3, 1, 5, 16, 12)          # (t, s, lambda, y, x): rows (16) and times (3) differ, as in the real file


@pytest.fixture(scope="module")
def pair(tmp_path_factory):
    """c_im.fits, c_sp.fits with the WCS-TAB as SSTRED writes it, c_sp.icube; and the same per-pixel files alone in
    another directory, without their image cube."""
    d = tmp_path_factory.mktemp("pair")
    paths = synth.write_dataset(d, "c", shape=SHAPE, sp=False)
    paths["sp"] = synth.write_sp_fits(paths["im"], d / "c_sp.fits", wcs=True)
    alone = d / "alone"
    alone.mkdir()
    paths["sp_alone"] = shutil.copy(paths["sp"], alone / "c_sp.fits")
    paths["icube_alone"] = shutil.copy(paths["icube"], alone / "c_sp.icube")
    paths["renamed"] = shutil.copy(paths["sp"], alone / "renamed.fits")      # nothing in its name says it
    return {k: str(v) for k, v in paths.items()}


def test_a_per_pixel_file_is_refused_as_a_cube_and_its_times_never_indexed(pair):
    """Before: it opened, (t, s, lambda) = (rows, cols, Stokes), its 3 times for 16 steps in t; Axes.utc_str(15)
    raised the IndexError the toolbar raised on the real file."""
    with pytest.raises(ValueError, match="per-pixel file") as e:
        Dataset.open(pair["renamed"], no_sp=True)
    print("refused:", e.value)


def test_times_that_do_not_match_the_frames_are_refused_at_opening(tmp_path):
    """An image cube whose WCS-TAB holds 2 times for 3 frames in t: refused at opening with both counts; before, it
    opened and the last time step raised IndexError while drawing."""
    im = synth.write_stokes_cube(tmp_path / "x_im.fits", shape=SHAPE)
    other = synth.write_stokes_cube(tmp_path / "y_im.fits", shape=(2,) + SHAPE[1:])
    with fits.open(im) as a, fits.open(other) as b:
        fits.HDUList([fits.PrimaryHDU(a[0].data, a[0].header), b["WCS-TAB"].copy()]).writeto(tmp_path / "z_im.fits")
    ax = _axes.from_fits(tmp_path / "z_im.fits")
    print("times in the header:", len(ax.t_sec), "frames in t:", SHAPE[0])
    with pytest.raises(ValueError, match="2 times for 3 steps along its t") as e:
        Dataset.open(tmp_path / "z_im.fits", no_sp=True)
    print("refused:", e.value)
    r = _axes.roles(("UTC", "STOKES", "WAVE", "HPLT", "HPLN"), SHAPE)
    _axes.check(_axes.from_fits(im), r)                 # the cube as written passes


def test_roles_never_put_two_on_one_axis():
    r = _axes.roles(("A", "B", "STOKES", "Y", "X"), (2, 3, 4, 5, 6))
    print("named STOKES third, the others by SOLARNET order on the free axes:", r)
    assert (r.t, r.s, r.l) == (0, 2, 1) and (r.nt, r.ns, r.nl) == (2, 4, 3)

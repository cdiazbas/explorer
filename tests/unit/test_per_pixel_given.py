"""A per-pixel file given where an image cube is wanted (`explorer c_sp.fits`): recognised by its header or by the
image cube next to it, and the image cube opened with it; refused, with what is needed, when there is none. A header
whose times or wavelengths do not match the data is refused at opening: `explorer nb_6563_..._sp.fits` read the
header's 35 times for 2028 steps along the image's rows, and the toolbar indexed time 2027."""
import os
import shutil

import numpy as np
import pytest
from astropy.io import fits

from explorer.data import axes as _axes
from explorer.data import formats
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


def _lp_pair(directory, stem="c", tag="", ext="icube"):
    """An LP image cube <stem>_im<tag>.<ext> and its per-pixel file <stem>_sp<tag>.<ext> (t, s, lambda, y, x)."""
    nt, ns, nl, ny, nx = SHAPE
    counts = np.arange(np.prod(SHAPE), dtype="<i2").reshape(SHAPE)
    dt = "datatype=2 (integer)" if ext == "icube" else "datatype=4 (float)"
    head = f"stokes=[I], ns={ns} :  {dt}, dims=3, nx={{}}, ny={{}}, nt={{}}, endian=l"
    data = counts if ext == "icube" else counts.astype("<f4")
    im, sp = directory / f"{stem}_im{tag}.{ext}", directory / f"{stem}_sp{tag}.{ext}"
    im.write_bytes(head.format(nx, ny, nt * ns * nl).encode().ljust(512, b"\0") + data.tobytes())
    sp.write_bytes(head.format(nl, nt, ny * nx * ns).encode().ljust(512, b"\0")
                   + data.transpose(3, 4, 1, 0, 2).tobytes())
    return str(im), str(sp)


def test_the_header_of_the_per_pixel_file_says_what_it_is(pair):
    lay = formats.fits_layout(pair["sp"])
    print("per-pixel FITS axes, numpy order:", lay.axes, lay.shape)
    for p in ("sp", "sp_alone", "renamed"):
        why = formats.per_pixel(pair[p])
        print(f"{os.path.basename(pair[p])}: {why}")
        assert why == "its header puts HPLT, HPLN first"
    assert formats.per_pixel(pair["im"]) is None


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


def test_a_per_pixel_file_opens_its_image_cube_with_it(pair, tmp_path):
    o = formats.opening(pair["sp"])
    print("given c_sp.fits:", o.note)
    assert o.path == pair["im"] and o.sp == pair["sp"] and "per-pixel file of c_im.fits" in o.note
    o = formats.opening(pair["icube"])                  # an LP per-pixel file next to a FITS image cube
    print("given c_sp.icube:", o.note)
    assert o.path == pair["im"] and o.sp == pair["icube"]
    im, sp = _lp_pair(tmp_path)
    o = formats.opening(sp)
    print("given an LP c_sp.icube:", o.note)
    assert o.path == im and o.sp == sp and o.note.startswith("c_sp.icube is the per-pixel file of c_im.icube (by its")
    with Dataset.open(o.path, sp=o.sp) as ds:
        assert ds.pixel is not None and ds.pixel.layout.path == sp


@pytest.mark.parametrize("tag, ext", [(".aligned6173", "icube"), (".aligned6173", "fcube")])
def test_a_tagged_lp_per_pixel_file_finds_its_image_cube(tmp_path, tag, ext):
    """SSTRED's nb_8542_..._stokesI_corrected_sp.aligned6173.icube beside ..._im.aligned6173.icube."""
    im, sp = _lp_pair(tmp_path, "nb_8542_stokesI_corrected", tag, ext)
    o = formats.opening(sp)
    print(o.note)
    assert o.path == im and o.sp == sp


def test_a_per_pixel_file_without_its_image_cube_says_what_is_needed(pair, tmp_path):
    for p, want in (("sp_alone", "c_im.fits"), ("icube_alone", "c_im.icube"), ("renamed", "--sp renamed.fits")):
        with pytest.raises(ValueError, match="is a per-pixel file") as e:
            formats.opening(pair[p])
        print(e.value)
        assert want in str(e.value)
    _, sp = _lp_pair(tmp_path)
    os.remove(tmp_path / "c_im.icube")
    with pytest.raises(ValueError, match=r"named _sp, 192 frames of 5 x 3 pixels"):
        formats.opening(sp)


def test_a_file_that_is_not_a_cube_is_passed_on_for_the_opening_to_say_why(tmp_path):
    p = tmp_path / "notes_sp.fits"
    p.write_text("not a cube")
    assert formats.opening(p) == (str(p), None, "")


def test_sp_given_the_other_way_round(pair):
    o = formats.opening(pair["sp"], sp=pair["im"])        # explorer c_sp.fits --sp c_im.fits
    print(o.note)
    assert o.path == pair["im"] and o.sp == pair["sp"]
    with pytest.raises(ValueError, match="is an image cube") as e:
        formats.opening(pair["im"], sp=pair["im"])        # explorer c_im.fits --sp c_im.fits
    print(e.value)
    assert formats.opening(pair["im"], sp=pair["sp"]) == (pair["im"], pair["sp"], "")


def test_among_linked_cubes(pair, tmp_path, capsys):
    from explorer.ui.app import given_cubes

    _, lp_sp = _lp_pair(tmp_path, "d")
    path, sp, linked, sps = given_cubes(pair["im"], None, False, [pair["sp"], lp_sp, pair["sp_alone"]])
    err = capsys.readouterr().err
    print(err)
    assert (path, sp) == (pair["im"], pair["sp"])       # its own per-pixel file: taken as such, not linked
    assert linked == [str(tmp_path / "d_im.icube")] and sps == {linked[0]: lp_sp}
    assert "not linked: c_sp.fits is a per-pixel file" in err


def test_the_command_opens_nothing_and_says_why(pair, capsys, monkeypatch):
    """`explorer c_sp.fits` without its image cube: exit status 1, one line, no traceback, before any window."""
    from explorer import cli

    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    assert cli.main([pair["sp_alone"]]) == 1
    err = capsys.readouterr().err
    print(err)
    assert "c_sp.fits is a per-pixel file" in err and "c_im.fits" in err and "Traceback" not in err


def test_start_opens_the_image_cube_with_the_per_pixel_file_given(qapp, pair, tmp_path, monkeypatch, capsys):
    from explorer.ui.app import start

    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    s = start(pair["sp"], saved_layout=False)
    assert s is not None
    try:
        print(capsys.readouterr().err)
        assert s.ds.path == pair["im"] and s.ds.pixel is not None and s.ds.pixel.layout.path == pair["sp"]
        assert s.ds.axes.utc_str(s.ds.roles.nt - 1) is not None
    finally:
        s.shell.close()
        s.close()

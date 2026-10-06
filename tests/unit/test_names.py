"""Short names for cubes (data.names): SST file names run long; the window shows the line and, for a map, what it is,
cut to MAX_CHARS when nothing better is known. The names of the cubes in the project's data, as they read."""
import types

import pytest

from explorer.data.names import MAX_CHARS, cube_names, short_name

CASES = [
    ("stokes_6173_im.icube", "Fe I 617.3"),
    ("Blos.6173_map.fcube", "Blos · Fe I 617.3"),
    ("Vlos.6173_map.icube", "Vlos · Fe I 617.3"),
    ("Bstr.6173_map.fcube", "Bstr · Fe I 617.3"),
    ("Blos_6173_map=0-3.fcube", "Blos · Fe I 617.3"),
    ("aligned_stokes_8542=0-54_=0-28_im.aligned6173.fcube", "Ca II 854.2"),
    ("aligned_6563=0-59_im.aligned6173.icube", "Hα"),
    ("halpha_6563_im.fits", "Hα"),
    ("doppl_6563=0-105_im.fcube", "Doppler · Hα"),
    ("cmapcorr_5576_cmapcorr_im.icube", "Fe I 557.6"),
    ("nb_8542_clipped=0-85.icube", "Ca II 854.2"),
    ("nb_6173_YYYY-MM-DDT08:16:57_08:16:57=0-185_stokes_corrected_im.fits", "Fe I 617.3"),   # a date, times
    ("wb_3950_im.fits", "3950 Å"),                       # a wavelength no known line matches
]


@pytest.mark.parametrize("name,want", CASES)
def test_the_names_of_the_projects_cubes(name, want):
    got = short_name(name)
    print(f"{name} -> {got}")
    assert got == want and len(got) <= MAX_CHARS


def test_the_header_s_line_comes_first_and_without_one_the_file_is_cut_in_the_middle():
    assert short_name("cube_im.fits", types.SimpleNamespace(line="Ca II K")) == "Ca II K"
    long = "a_very_long_reduction_name_without_any_wavelength_im.fits"
    got = short_name(long)
    print(long, "->", got)
    assert len(got) == MAX_CHARS and "…" in got and got.startswith("a_very") and got.endswith("ngth_im")


def test_cubes_that_would_share_a_name_are_told_apart():
    def cube(path):
        return types.SimpleNamespace(path=path, axes=None)

    got = cube_names([cube("stokes_6173_im.icube"), cube("stokes_6173_im.fits"), cube("Blos.6173_map.fcube")])
    print(got)
    assert got == ["Fe I 617.3 (LP)", "Fe I 617.3 (FITS)", "Blos · Fe I 617.3"]
    got = cube_names([cube("stokes_6173_im.fits"), cube("stokesI_6173_im.fits")])
    print(got)
    assert got == ["stokes_6173_im", "stokesI_6173_im"]

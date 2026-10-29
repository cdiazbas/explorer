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


def _roles(t=0, l=None, nl=1, how="header"):  # noqa: E741
    from explorer.data.axes import Roles
    return Roles(t, None, l, 17, 1, nl, how)


def _axes(dl=None, btype=None):
    return types.SimpleNamespace(dlam_A=lambda: dl, btype=btype, line=None)


def test_the_axis_other_than_t_is_lambda_only_when_known():
    """lambda-t and "λ index" only for an axis known to be lambda (tunings in Å, or named by the header, --axes or
    SOLARNET's order); a map, or an unnamed axis taken for lambda by default, by what the cube shows: its BTYPE,
    else the map's word in its file name, else its file name."""
    from explorer.data.names import slice_names
    cases = [
        (_roles(l=1, nl=5, how="default (t, lambda)"), _axes(dl=list(range(5))), "x_im.icube",
         ("λ–t", "λ index", True)),
        (_roles(l=1, nl=5), _axes(), "x_im.fits", ("λ–t", "λ index", True)),
        (_roles(l=1, nl=5, how="--axes"), _axes(), "x.icube", ("λ–t", "λ index", True)),
        (_roles(), _axes(), "Blos.6173_map.fcube", ("Blos–t", "Blos index", False)),
        (_roles(), _axes(btype="Magnetic field"), "Blos.6173_map.fcube",
         ("Magnetic field–t", "Magnetic field index", False)),
        (_roles(l=1, nl=6, how="default (t, lambda)"), _axes(), "meinv_6173_im.icube",
         ("Fe I 617.3 inversion (parameter–t)", "parameter index", False)),
    ]
    for r, ax, path, want in cases:
        got = slice_names(r, ax, path)
        print(path, r.how, "->", got)
        assert got[:3] == want and got.mapped == (r.l is None)


# ---------------------------------------------------------------- names from the header (ROADMAP E8.8)
# Each header below is built like a real one a survey of real headers read: the same
# cards, values and types (WAVELNTH a number, BIFROST's BUNIT = T a logical), on images of 8 x 10.

NY8, NX10 = 8, 10
T_OBS = "2025-07-05T00:{:02d}:00.00Z"


def _write(path, data, cards):
    from astropy.io import fits

    h = fits.Header()
    for k, v in cards.items():
        h[k] = v
    fits.PrimaryHDU(data, h).writeto(path)
    return str(path)


def _series(d, name, cards, n=3):
    """n files of an imager, one image each, read as explorer reads --series: their layout, the first's header.
    name: the files' names, file k's where {k} is (else name_k)."""
    import numpy as np

    from explorer.data import axes as _axes
    from explorer.data.formats import series_layout

    names = [name.format(k=k) if "{k}" in name else f"{name}_{k}" for k in range(n)]
    paths = [_write(d / f"{f}.fits", np.full((NY8, NX10), k, np.int16), {**cards, "T_OBS": T_OBS.format(k)})
             for k, f in enumerate(names)]
    lay = series_layout(paths)
    r, ax = _axes.read(lay.path, lay)
    return r, ax, lay.path


def _cube(path, shape, cards):
    """One FITS cube as explorer opens it: its layout, then its roles and axes from its header."""
    import numpy as np

    from explorer.data import axes as _axes
    from explorer.data.formats import open_layout

    _write(path, np.zeros(shape, np.float32), cards)
    lay = open_layout(path)
    r, ax = _axes.read(str(path), lay)
    return r, ax, str(path)


AIA = {"TELESCOP": "SDO/AIA", "INSTRUME": "AIA_3", "WAVELNTH": 171, "WAVEUNIT": "angstrom", "WAVE_STR": "171_THIN",
       "PIXLUNIT": "DN", "CTYPE1": "HPLN-TAN", "CTYPE2": "HPLT-TAN", "IMG_TYPE": "LIGHT"}
EUI = {"TELESCOP": "SOLO/EUI/FSI", "DETECTOR": "FSI", "WAVELNTH": 174, "WAVEUNIT": "Angstrom", "BTYPE": "Intensity",
       "BUNIT": "DN", "LEVEL": "L1", "CTYPE1": "HPLN-TAN", "CTYPE2": "HPLT-TAN"}
EUVI = {"TELESCOP": "STEREO", "INSTRUME": "SECCHI", "DETECTOR": "EUVI", "WAVELNTH": 171, "BUNIT": "DN",
        "CTYPE1": "HPLN-TAN", "CTYPE2": "HPLT-TAN"}
GONG = {"TELESCOP": "NSO-GONG", "WAVELNTH": 6562.808, "IMTYPE": "H-ALPHA", "CTYPE1": "HPLN-TAN", "CTYPE2": "HPLT-TAN"}


@pytest.mark.parametrize("cards,name,panel,value", [
    (AIA, "aia.lev1_euv_12s.2025-07-05T005959Z.171.image", "AIA 171 Å–t", "AIA 171 Å [DN]"),
    (EUI, "solo_L1_eui-fsi174-image_20250705T000000", "EUI/FSI 174 Å–t", "EUI/FSI 174 Å [DN]"),
    (EUVI, "stereo_a_euvi_171_2025_07_05", "EUVI 171 Å–t", "EUVI 171 Å [DN]"),
    (GONG, "20250705010042Lh", "GONG Hα–t", "GONG Hα"),
])
def test_an_imager_is_named_by_its_instrument_and_band(tmp_path, cards, name, panel, value):
    """Rule 5, and rule 1 passing over a generic BTYPE ("Intensity"): a series of an imager without WAVEBAND, by its
    instrument (TELESCOP after its "/", else DETECTOR, else TELESCOP's last word) and WAVELNTH in Å, a known line
    within 6 Å by its name; its unit BUNIT, else PIXLUNIT. Before: the file's name, or "Intensity"."""
    from explorer.data.names import slice_names

    r, ax, path = _series(tmp_path, name, cards)
    got = slice_names(r, ax, path)
    print(name, "->", got)
    assert got.mapped and (got.panel, got.value) == (panel, value)


def test_an_sst_map_keeps_its_name(tmp_path):
    """Rule 4 after rule 1: an SST map by the word of its file name ("Blos–t", as an LP map without a header always
    was), whatever its generic BTYPE and its WAVELNTH (the prefilter: with WAVEBAND, rule 5 does not apply). Before:
    "Intensity–t"."""
    from explorer.data.names import slice_names

    cards = {"CTYPE1": "HPLN-TAB", "CTYPE2": "HPLT-TAB", "CTYPE3": "UTC--TAB", "WAVEBAND": "Fe I 6173",
             "WAVELNTH": 617.38, "WAVEUNIT": -9, "BTYPE": "Intensity", "INSTRUME": "CRISP",
             "TELESCOP": "Swedish 1-meter Solar Telescope (SST)", "DETECTOR": "camXXXII,camXXXIII"}
    r, ax, path = _cube(tmp_path / "Blos_6173_map=0-3.fits", (4, NY8, NX10), cards)
    got = slice_names(r, ax, path)
    print(got)
    assert (got.panel, got.label) == ("Blos–t", "Blos index")


def test_an_axis_named_by_the_header_is_called_so(tmp_path):
    """The axis rule: BIFROST's [z, y, x], CTYPE3 = 'z': its axis other than t is z, and BTYPE names what it shows
    (a log10 as "log₁₀(tg)"); BUNIT = T (a logical) without INSTRUME 'Bifrost' is no unit. Before: "lg(tg)–t",
    "lg(tg) index"."""
    from explorer.data.names import slice_names

    base = {"CTYPE1": "x", "CTYPE2": "y", "CTYPE3": "z", "OBJECT": "en024048_hion", "ORIGIN": "ITA/Oslo"}
    r, ax, path = _cube(tmp_path / "BIFROST_en024048_hion_lgtg_385.fits", (6, NY8, NX10),
                        {**base, "BTYPE": "lg(tg)", "BUNIT": "K"})
    got = slice_names(r, ax, path)
    print(r.how, got)
    assert (got.panel, got.label, got.value, got.mapped) == ("log₁₀(tg) (z–t)", "z index", "log₁₀(tg) [K]", False)
    r, ax, path = _cube(tmp_path / "BIFROST_en024048_hion_bz_385.fits", (6, NY8, NX10),
                        {**base, "BTYPE": "bz", "BUNIT": True})
    got = slice_names(r, ax, path)
    print(r.how, got)
    assert (got.label, got.value) == ("z index", "bz")


def test_an_inversion_s_planes_are_never_lambda(tmp_path):
    """Rule 3: an inversion's file (meinv, inversion, inv: a word of its name) by its line, its planes by
    "parameter", whatever the LP pair layout (the meinv LP: [106, 1, 3], "header") or SOLARNET's order (the
    headerless WFA_inversion_8542.fits: [83, 2, 3, y, x]) calls them. Before: "λ–t", "λ index"."""
    from explorer.data.axes import Axes, Roles
    from explorer.data.names import slice_names

    got = slice_names(Roles(0, 1, 2, 106, 1, 3, "header"), Axes(), "data/lp/inversion_6173_im.icube")
    print("meinv", got)
    assert (got.panel, got.label, got.spectral) == ("Fe I 617.3 inversion (parameter–t)", "parameter index", False)
    r, ax, path = _cube(tmp_path / "WFA_inversion_8542.fits", (5, 2, 3, NY8, NX10), {})
    got = slice_names(r, ax, path)
    print("wfa", r.how, got)
    assert (r.how, r.planes, r.ns, r.nl) == ("inversion", "parameter", 2, 3)        # SOLARNET order: t, s, lambda
    assert (got.panel, got.label, got.spectral) == ("Ca II 854.2 inversion (parameter–t)", "parameter index", False)


def test_content_and_a_jsoc_segment_name_a_map(tmp_path):
    """Rules 2 and 4: an HMI magnetogram by its CONTENT, a SHARP map by the segment its JSOC name ends in (its
    CONTENT, "HMI observable", is generic). Before: the file's name."""
    from explorer.data.names import slice_names

    r, ax, path = _series(tmp_path, "hmi_m_nrt", {"TELESCOP": "SDO/HMI", "INSTRUME": "HMI_FRONT2",
                                                  "CONTENT": "MAGNETOGRAM", "BUNIT": "Gauss", "WAVELNTH": 6173.0})
    got = slice_names(r, ax, path)
    print(got)
    assert (got.panel, got.value) == ("magnetogram–t", "magnetogram [Gauss]")
    d = tmp_path / "sharp"
    d.mkdir()
    r, ax, path = _series(d, "hmi.sharp_cea_720s.377.2014020{k}_030000_TAI.Br",
                          {"TELESCOP": "SDO/HMI", "CONTENT": "HMI observable", "BUNIT": "Mx/cm^2"})
    print(path)
    got = slice_names(r, ax, path)
    print(got)
    assert got.panel == "Br–t"


def test_without_a_name_in_the_header_the_line_of_the_file_then_quantity(tmp_path):
    """Rules 7 and 8: a headerless cube [n, y, x] (one unnamed axis: "unknown") by the line in its file name, else
    "Quantity", never by its file's name; its values the same. Before: the file's name, and "value"."""
    from explorer.data.names import slice_names

    r, ax, path = _cube(tmp_path / "delacruz_8542_denoise.fits", (5, NY8, NX10), {})
    got = slice_names(r, ax, path)
    print(r.how, got)
    assert (got.panel, got.label) == ("Ca II 854.2–t", "Ca II 854.2 index")
    r, ax, path = _cube(tmp_path / "flare_spt_denoised.fits", (5, NY8, NX10), {})
    got = slice_names(r, ax, path)
    print(r.how, got)
    assert (got.panel, got.label, got.value) == ("Quantity–t", "Quantity index", "Quantity")


def test_an_imager_s_unit_from_pixlunit_in_the_status_line_and_its_key(tmp_path):
    """AIA has no BUNIT, its unit is PIXLUNIT = 'DN': the status line says it (and the image's colour key, from the
    same data.names.unit), as the curve's axis does ("AIA 171 Å [DN]"). Before: the curve alone."""
    from explorer.ui.status import pixel_text

    r, ax, path = _series(tmp_path, "aia.lev1_euv_12s.2025-07-05T005959Z.171.image", AIA)
    got = pixel_text(ax, 1, 2, 3, 0, 0, 0, 363.0, None, None, False, ("t",), "AIA 171 Å")
    print(repr(got))
    assert got.endswith("AIA 171 Å 363.0\u00a0DN")
    from explorer.data.names import unit
    assert unit(ax) == "DN"


@pytest.mark.parametrize("kind", ["stokes", "blos", "aia", "euvi", "nothing"])
def test_a_cube_s_short_name_is_the_header_s_where_its_file_name_says_nothing(tmp_path, kind):
    """short_name (the cube's tab, its image's title, its window's): the map's word and the line, or the line, as
    before (an SST Stokes cube, a Blos map); where those leave only the file's name cut, the header's own name for
    what it shows (data.names.header_name: an AIA series "AIA 171 Å", an EUVI file "EUVI 195 Å"); a file whose header
    says nothing keeps its name. Before: "aia.lev1_euv_12…", "stereo_a_euvi_…"."""
    from explorer.data.names import cube_names, short_name

    if kind == "stokes":
        path, ax = "nb_6173_YYYY-MM-DDT08:16:57_08:16:57=0-185_stokes_corrected_im.fits", None
        want = "Fe I 617.3"
    elif kind == "blos":
        path, ax, want = "Blos_6173_map=0-3.fcube", None, "Blos · Fe I 617.3"
    elif kind == "aia":
        r, ax, path = _series(tmp_path, "aia.lev1_euv_12s.2025-07-05T005959Z.171.image", AIA)
        want = "AIA 171 Å"
    elif kind == "euvi":
        r, ax, path = _cube(tmp_path / "stereo_a_euvi_195_2025_07_05_00_05_30.fits", (NY8, NX10),
                            {**EUVI, "WAVELNTH": 195})
        want = "EUVI 195 Å"
    else:
        r, ax, path = _cube(tmp_path / "flare_spt_denoised.fits", (3, NY8, NX10), {})
        want = "flare_spt_denoised"
    got = short_name(path, ax)
    print(kind, path.rsplit("/", 1)[-1], "->", got)
    assert got == want
    assert cube_names([types.SimpleNamespace(path=path, axes=ax)]) == [want]

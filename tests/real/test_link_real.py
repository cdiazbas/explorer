"""Linking the shared real cubes to the Stokes 6173 LP cube (ROADMAP E8.1, data.link): field and velocity maps of
its 17 scans follow its times; a map of another number of frames, another grid, another cadence are refused; the
same observation as FITS links with the same times. Only where the data/lp/ links resolve (bellatrix)."""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
LP = ROOT.parent / "data" / "lp"
MAIN = LP / "stokes_6173_im.icube"
CASES = [  # file, linked, what its reason or account must say
    ("Blos.6173_map.fcube", True, "17 times"),
    ("Vlos.6173_map.icube", True, "17 times"),
    ("Bstr.6173_map.fcube", False, "pixels"),            # 2031x2025: three rows short
    ("Blos_6173_map=0-3.fcube", False, "pixels"),
    ("aligned_stokes_8542=0-54_=0-28_im.aligned6173.fcube", False, "84 times"),
    ("stokes_6173_im.fits", True, "same times"),
    ("halpha_6563_im.fits", False, "pixels"),
]


@pytest.mark.real_cubes
@pytest.mark.parametrize("name, linked, says", CASES, ids=[c[0] for c in CASES])
def test_the_real_cubes_link_or_say_why(name, linked, says):
    if not (MAIN.exists() and (LP / name).exists()):
        pytest.skip(f"no link here: {MAIN.name} or {name}")
    from explorer.data.link import describe, plan

    link = plan(describe(MAIN), LP / name)
    print(f"{name}: ok={link.ok} axes={link.axes!r} how={link.how!r} why={link.why!r}")
    assert link.ok is linked and says in (link.how if linked else link.why)

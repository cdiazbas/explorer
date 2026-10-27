"""The status bar's texts (ROADMAP E4.6), without Qt: the cursor's pixel in physical units, and the diagnostics
shown with F12.

From the prototype's app/viewer.py: _pixel_text (1217), _status and set_diagnostics (1826, 1198).
"""
import math

import numpy as np

from ..data.axes import SUP, fmt_sig, fmt_signed, unit_text
from ..data.names import plane, unit

SEP = "   ·   "
NB = "\u00a0"                                           # between a number and its unit: never apart at a line end
# (U+202F, the narrow one, is nearly nothing in SF: "08:17:40UT")


def padding(v0: float, s: int) -> bool:
    """No data here: NaN, or exactly 0 in Stokes I (aligned cubes' padding), as the core skips it."""
    return not math.isfinite(v0) or (v0 == 0 and s == 0)


def pixel_text(ax, ns: int, y: int, x: int, t: int, l: int, s: int, v0: float, ic: float | None,  # noqa: E741
               iscale: float | None, locked: bool, present=("t", "l"), value: str = "I",
               planes: str = "stokes") -> str:
    """The cursor's pixel, fields separated by thin dots: helioprojective x, y when the header gives the field's
    corners (else the pixel), t in UT (else its index), lambda in Å, delta-lambda and the Doppler velocity (else the
    tuning index), the value: Q U V in % of this pixel's I_c when it is known, I (and Q U V without I_c) in its
    power of ten of BUNIT; "no data (padding)" on padding; "locked" when the cursor is. The value is named by its
    Stokes when the cube has them (an inversion's parameter: "Quantity 2", planes), else by value ("I", or what a
    cube without lambda shows: "Blos")."""
    f = []
    xy = ax.arcsec(y, x, t) if ax is not None and ax.corners is not None else None
    f.append(f"x {fmt_signed(xy[0], 1)}″  y {fmt_signed(xy[1], 1)}″" if xy else f"x {x}  y {y}")
    if "t" in present:
        u = ax.utc_str(t) if ax is not None and ax.t_sec is not None else None
        f.append(f"{u}{NB}UT" if u else f"t {t}")
    if "l" in present:
        dl = ax.dlam_A() if ax is not None else None
        if dl is not None:
            f.append(f"λ {ax.lam_A(l):.3f}{NB}Å")
            f.append(f"Δλ {fmt_signed(float(dl[l]), 3)}{NB}Å")
            f.append(f"v {fmt_signed(ax.vel_kms(l), 2)}{NB}km s⁻¹")
        else:
            f.append(f"λ {l}")
    name = plane(s, planes) if ns > 1 else value
    bunit = unit_text(unit(ax))                         # BUNIT, else PIXLUNIT (data.names.unit)
    if padding(v0, s):
        f.append(f"{name}  no data (padding)")
    elif s > 0 and ic and planes == "stokes":
        f.append(f"{name}/Ic {fmt_signed(100 * v0 / ic, 2)}{NB}%")
    elif iscale:
        e = str(int(np.log10(iscale))).translate(SUP)
        f.append(f"{name} {v0 / iscale:.3f} × 10{e}{NB}{bunit}".rstrip().replace("-", "−"))
    else:
        f.append(f"{name} {fmt_sig(v0)}{NB}{bunit}".rstrip())
    if locked:
        f.append("locked")
    return SEP.join(f)


def diagnostics_text(dataset) -> str:
    """F12: what explorer runs on: the cube, its per-pixel file, the storage probe and memory, and whether a whole
    t loop fits in the image cache."""
    b = getattr(dataset, "budgets", None)
    cache = f"image cache {b.images / 2**30:.1f} GB" + (" (whole loop)" if b.whole_loop else "") if b else ""
    return "  |  ".join(x for x in (dataset.describe(), cache) if x)

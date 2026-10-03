"""Physical axes of a cube from its FITS header (SOLARNET, as SSTRED writes it), the roles of its leading axes, and
the units the spectra are shown in. From the prototype's app/physics.py, viewer.axis_positions and
Viewer._set_spectra.

Everything is read, not guessed; what the header does not say stays None and the app shows indices. Reading
follows the reference reader sunalign/sst.py:
- lambda per tuning, time and field corners live in the WCS-TAB binary table; the ORDER of the components is in
  the column name ("HPLN+HPLT+WAVE+TIME"), shape (nt, nl, 2, 2, ncomp);
- each tuning is its own exposure: the time of a scan is the mean over its tunings;
- the field is given by 4 corners per time step, at the pixel indices of HPLN-INDEX / HPLT-INDEX;
- WAVELNTH / WAVEMIN / WAVEMAX describe the PREFILTER, not the line: the line comes from WAVEBAND, its laboratory
  wavelength from LINES below;
- the continuum tuning is the one SSTRED used for the Stokes cross-talk correction (PRPARA of the
  STOKES-CROSSTALK-CORRECTION step, "TUNING_SELECTION").

An LP cube has no header: its lambda and times come from the IDL save file SSTRED writes beside it (from_lp).

Not applied: the per-pixel wavelength distortion in WCSDVARR (CWDIS3 = 'Lookup'), up to 0.12 Å in the Fe I 6173
cube (~6 km/s); velocities are those of the tabulated lambda. Axes.distortion says when a header has one.
"""
import json
import re
from typing import NamedTuple

import numpy as np

from ..obs import get_logger

log = get_logger("data")

C_KMS = 299792.458
STOKES = "IQUV"
SUP = str.maketrans("-0123456789", "⁻⁰¹²³⁴⁵⁶⁷⁸⁹")

# Laboratory wavelengths in AIR, nm (to ~1 pm; NIST / standard solar line lists). Keys are normalised WAVEBAND
# strings: lower case, letters and digits only.
LINES = {
    "fei6173": ("Fe I 617.3", 617.3341), "fei6302": ("Fe I 630.25", 630.2494), "fei6301": ("Fe I 630.15", 630.1501),
    "fei5250": ("Fe I 525.02", 525.0208), "fei5576": ("Fe I 557.6", 557.6099),
    "halpha": ("Hα", 656.2808), "hi6563": ("Hα", 656.2808), "hbeta": ("Hβ", 486.1333),
    "caii8542": ("Ca II 854.2", 854.2091), "caii8498": ("Ca II 849.8", 849.8018), "caii8662": ("Ca II 866.2", 866.2141),
    "caiik": ("Ca II K", 393.3663), "caiih": ("Ca II H", 396.8469),
    "naid1": ("Na I D1", 589.5924), "naid2": ("Na I D2", 588.9950),
    "mgib2": ("Mg I b2", 517.2684), "hei10830": ("He I 1083.0", 1083.0300), "ci5380": ("C I 538.0", 538.0337),
}


def _norm(s) -> str:
    return "".join(ch for ch in str(s).lower() if ch.isalnum())


# ---------------------------------------------------------------- roles of the leading axes

class Roles(NamedTuple):
    """Positions of t, Stokes and lambda among the leading axes (None if absent), their sizes (1 if absent), and how
    they were decided: "header" (CTYPE), "SOLARNET order" (three unnamed axes: t, s, lambda), "default (t, lambda)"
    (two unnamed axes), "unknown" (one unnamed axis: whatever it is, it is stepped and plotted as a profile in
    indices, and must not be labelled lambda or t), "--axes" (given by the user)."""
    t: int | None
    s: int | None
    l: int | None  # noqa: E741
    nt: int
    ns: int
    nl: int
    how: str = "header"


def parse_axes(spec: str, n_lead: int) -> tuple:
    """--axes: one letter per leading axis, slowest first as numpy stores them (t, s or l for lambda), e.g. "t,l" for
    (t, lambda, y, x) or "s,l" for (s, lambda, y, x). Returns (t, s, l) positions."""
    letters = [a.strip().lower() for a in str(spec).replace(" ", "").split(",") if a.strip()]
    if len(letters) != n_lead:
        raise ValueError(f"--axes {spec!r}: {len(letters)} axes given, the cube has {n_lead} before (y, x)")
    if set(letters) - {"t", "s", "l"} or len(set(letters)) != len(letters):
        raise ValueError(f"--axes {spec!r}: each of t, s, l at most once (l is lambda)")
    return tuple(letters.index(k) if k in letters else None for k in ("t", "s", "l"))


def roles(names, shape, axes: str | None = None) -> Roles:
    """By --axes when given; else by axis name (CTYPE); else by the number of unnamed leading axes: three are
    SOLARNET's (t, s, lambda), two are (t, lambda), one is unknown (a profile axis: it may be t or lambda, and only
    the user can tell, with --axes). names and shape are those of the whole cube, numpy order; the last two axes are
    the image."""
    lead = [str(a).upper() for a in names[:-2]]
    how = "header"
    if axes:
        t, s, l = parse_axes(axes, len(lead))  # noqa: E741
        how = "--axes"
    else:
        def find(*keys):
            return next((i for i, a in enumerate(lead) if any(a.startswith(k) for k in keys)), None)

        t, s, l = find("UTC", "TIME", "TAI"), find("STOKES"), find("WAVE", "AWAV", "FREQ")  # noqa: E741
        named = (t, s, l) != (None, None, None)
        if len(lead) == 3:
            if None in (t, s, l):                       # what the names do not say comes from SOLARNET's order
                how = "SOLARNET order"
            t, s, l = (0 if t is None else t), (1 if s is None else s), (2 if l is None else l)  # noqa: E741
        elif not named and len(lead) == 2:
            t, l, how = 0, 1, "default (t, lambda)"  # noqa: E741
        elif not named and len(lead) == 1:
            l, how = 0, "unknown"  # noqa: E741

    def size(a):
        return int(shape[a]) if a is not None else 1

    return Roles(t, s, l, size(t), size(s), size(l), how)


# ---------------------------------------------------------------- physical axes

class Axes:
    """Physical values for indices of the cube. Attributes are None when the header does not say."""

    def __init__(self):
        self.lam_nm = None          # (nl,) tabulated wavelength per tuning, nm
        self.line = None            # e.g. "Fe I 617.3"
        self.lam0_nm = None         # laboratory line centre, nm (air)
        self.cont = None            # continuum tuning index
        self.t_sec = None           # (nt,) seconds since DATEREF, scan means
        self.dateref = None         # numpy datetime64 of DATEREF
        self.time_of_day = False    # t_sec counts from midnight UT of a day the file does not give (LP cubes)
        self.corners = None         # (nt, 2, 2, 2) [t, j, i, (x", y")] field corners
        self.corner_px: tuple | None = None  # ((x0, x1), (y0, y1)) 0-based pixel indices of the corners
        self.bunit = None
        self.distortion = None      # the header's wavelength distortion (e.g. "WCSDVARR Lookup"), not applied
        self.source: list[str] = []  # what was read, for the status and about texts

    # ---- conversions (all take indices; None when unknown)
    def dlam_A(self, l=None):  # noqa: E741
        """Offset from the laboratory line centre, in Ångström."""
        if self.lam_nm is None or self.lam0_nm is None:
            return None
        d = (self.lam_nm - self.lam0_nm) * 10.0
        return d if l is None else float(d[l])

    def lam_A(self, l):  # noqa: E741
        return None if self.lam_nm is None else float(self.lam_nm[l]) * 10.0

    def vel_kms(self, l=None):  # noqa: E741
        if self.lam_nm is None or self.lam0_nm is None:
            return None
        v = (self.lam_nm - self.lam0_nm) / self.lam0_nm * C_KMS
        return v if l is None else float(v[l])

    def utc(self, t):
        if self.t_sec is None or self.dateref is None:
            return None
        return self.dateref + np.timedelta64(int(round(self.t_sec[t] * 1e3)), "ms")

    def utc_str(self, t, seconds=True):
        if self.time_of_day and self.t_sec is not None:     # the time of day alone: formatted on any day
            u = np.datetime64(0, "ms") + np.timedelta64(int(round(self.t_sec[t] * 1e3)), "ms")
        else:
            u = self.utc(t)
        return None if u is None else str(u)[11:19 if seconds else 16]

    def arcsec(self, y, x, t):
        """Helioprojective (x", y") of pixel (y, x) at time step t: bilinear between the 4 corners."""
        if self.corners is None or self.corner_px is None:      # set together
            return None
        (x0, x1), (y0, y1) = self.corner_px
        fx = (x - x0) / (x1 - x0) if x1 != x0 else 0.0
        fy = (y - y0) / (y1 - y0) if y1 != y0 else 0.0
        c = self.corners[min(t, self.corners.shape[0] - 1)]        # [j, i, (x, y)]
        top = c[0, 0] * (1 - fx) + c[0, 1] * fx
        bot = c[1, 0] * (1 - fx) + c[1, 1] * fx
        v = top * (1 - fy) + bot * fy
        return float(v[0]), float(v[1])


def from_fits(path) -> Axes:
    """The axes of a FITS cube. Never raises: a header that cannot be read leaves the axes unknown (indices), and
    says why in Axes.source and the log."""
    from astropy.io import fits

    try:
        with fits.open(path, memmap=True, lazy_load_hdus=True) as h:
            return from_hdul(h)
    except Exception as e:
        ax = Axes()
        ax.source.append(f"header not read: {type(e).__name__}: {e}")
        log.warning("axes of %s: %s", path, ax.source[-1])
        return ax


def from_hdul(h) -> Axes:
    ax = Axes()
    try:
        _read(h, ax)
    except Exception as e:                                          # never block opening a cube
        ax.source.append(f"header not read: {type(e).__name__}: {e}")
        log.warning("axes: %s", ax.source[-1])
    return ax


def _read(h, ax: Axes) -> None:
    hd = h[0].header
    ax.bunit = hd.get("BUNIT")
    # line: WAVEBAND -> laboratory wavelength
    wb = hd.get("WAVEBAND")
    if wb is not None and _norm(wb) in LINES:
        ax.line, ax.lam0_nm = LINES[_norm(wb)]
        ax.source.append(f"line {wb} (WAVEBAND) -> {ax.lam0_nm} nm lab, air")
    # continuum: the tuning SSTRED used for the cross-talk correction
    steps = {str(hd[k]).strip(): k[6:] for k in hd if k.startswith("PRSTEP")}
    n = steps.get("STOKES-CROSSTALK-CORRECTION")
    if n is not None and f"PRPARA{n}" in hd:
        try:
            sel = json.loads(hd[f"PRPARA{n}"]).get("TUNING_SELECTION")
            if sel:
                ax.cont = int(sel[0])
                ax.source.append(f"continuum tuning {ax.cont} (PRPARA{n} TUNING_SELECTION)")
        except (ValueError, TypeError):
            pass
    if "DATEREF" in hd:
        ax.dateref = np.datetime64(str(hd["DATEREF"])[:23])
    dis = [f"{k} = {str(hd[k]).strip()}" for k in hd if re.fullmatch(r"CWDIS\d", k)]
    if dis:
        ax.distortion = "WCSDVARR " + ", ".join(dis)
    # tabulated WCS
    name = str(hd.get("PS3_0", hd.get("PS1_0", "WCS-TAB"))).strip()
    if name in h:
        tab = h[name].data
        col = str(hd.get("PS1_1", hd.get("PS3_1", ""))).strip()
        if col in tab.names:
            a = np.asarray(tab[col][0])
            parts = [p.strip().upper() for p in col.split("+")]
            if a.ndim == 5 and a.shape[-1] == len(parts):          # (nt, nl, 2, 2, ncomp)
                if "WAVE" in parts:
                    ax.lam_nm = a[0, :, 0, 0, parts.index("WAVE")].astype(float)
                    ax.source.append("lambda per tuning (WCS-TAB WAVE)")
                if "TIME" in parts:
                    ax.t_sec = a[..., parts.index("TIME")].reshape(a.shape[0], -1).mean(axis=1)
                    ax.source.append("time per scan (WCS-TAB TIME, mean over tunings)")
                if "HPLN" in parts and "HPLT" in parts:
                    m = a.mean(axis=1)                               # the field is the same at every tuning
                    ax.corners = np.stack([m[..., parts.index("HPLN")], m[..., parts.index("HPLT")]], -1)

                    def idx(nm, default):
                        try:
                            v = np.asarray(tab[nm][0]).ravel()
                            return float(v[0]) - 1, float(v[-1]) - 1     # FITS 1-based -> 0-based
                        except Exception:
                            return default

                    nx, ny = hd.get("NAXIS1", 2), hd.get("NAXIS2", 2)
                    ax.corner_px = (idx("HPLN-INDEX", (0, nx - 1)), idx("HPLT-INDEX", (0, ny - 1)))
                    ax.source.append("field corners (WCS-TAB HPLN/HPLT)")
    _isolated_continuum(ax)


def _isolated_continuum(ax: Axes) -> None:
    """No continuum from the reduction: an isolated end tuning is the continuum (as in 6173)."""
    if ax.cont is None and ax.lam_nm is not None and ax.lam_nm.size > 3:
        d = np.diff(ax.lam_nm)
        med = float(np.median(np.abs(d)))
        if med > 0 and abs(d[-1]) > 4 * med:
            ax.cont = ax.lam_nm.size - 1
            ax.source.append("continuum: isolated red tuning")
        elif med > 0 and abs(d[0]) > 4 * med:
            ax.cont = 0
            ax.source.append("continuum: isolated blue tuning")


def from_lp(path, r: Roles) -> Axes:
    """The axes of an LP cube from the IDL save file beside it (formats.lp_sidecar): lambda per tuning (nm), and
    each scan's time as the mean over its tunings, as from_fits takes it. The times are seconds since midnight UT
    of a day the file does not give, so they are shown as times of day (Axes.time_of_day). Measured on real cubes
    against their FITS siblings: lambda identical, times within 1e-10 s. The line is the one laboratory line of
    LINES inside the tuned range. Never raises: without the file, or with values that do not match the cube's axes,
    what it cannot give stays unknown, and Axes.source says why."""
    from .formats import idlsave, lp_sidecar

    ax = Axes()
    side = lp_sidecar(path)
    if side is None:
        ax.source.append("no IDL save file beside the cube")
        return ax
    try:
        v = idlsave.read(side, names={"lambda", "time", "times"})
    except (OSError, ValueError) as e:
        ax.source.append(f"IDL save file not read: {e}")
        log.warning("axes of %s: %s", path, ax.source[-1])
        return ax

    def mismatch(what):
        ax.source.append(f"IDL save {what} does not match the cube (nt={r.nt}, nl={r.nl}): not used")
        log.warning("axes of %s: %s", path, ax.source[-1])

    lam = v.get("lambda")
    if isinstance(lam, np.ndarray) and lam.dtype.kind == "f" and r.l is not None and lam.shape == (r.nl,):
        ax.lam_nm = lam.astype(float)
        ax.source.append("lambda per tuning (IDL save lambda)")
    elif lam is not None:
        mismatch(f"lambda {getattr(lam, 'shape', '')}")
    # the (scan, tuning) seconds are "time" in some files and "times" in others, the other holding 'HH:MM:SS' text
    t = next((a for a in (v.get("time"), v.get("times")) if isinstance(a, np.ndarray) and a.dtype.kind == "f"), None)
    if t is not None and r.t is not None and t.shape[0] == r.nt:
        ax.t_sec, ax.time_of_day = t.reshape(r.nt, -1).mean(axis=1).astype(float), True
        ax.source.append("time per scan (IDL save, seconds of the day UT, mean over tunings)")
    elif t is not None:
        mismatch(f"time {t.shape}")
    if ax.lam_nm is not None:
        inside = {line for line in LINES.values() if ax.lam_nm.min() <= line[1] <= ax.lam_nm.max()}
        if len(inside) == 1:
            ax.line, ax.lam0_nm = inside.pop()
            ax.source.append(f"line {ax.line}: the one laboratory line inside the tuned range")
    _isolated_continuum(ax)
    return ax


# ---------------------------------------------------------------- units of the spectra

def power_of_ten(intensity):
    """The power of ten Stokes I is shown in: of the median of its finite, non-zero magnitudes; None if there is
    none. The first profile read, or the profiles of the y-range sample, whichever comes first."""
    v = np.asarray(intensity, dtype=np.float64)
    f = v[np.isfinite(v) & (v != 0)]
    return float(10.0 ** np.floor(np.log10(np.median(np.abs(f))))) if f.size else None


def plot_units(spec, cont, iscale):
    """(ns, nl) spectrum as plotted: Q U V in % of this pixel's I_c when the continuum tuning is known; I (and Q U V
    without a continuum tuning) over iscale. A continuum sample that is not finite or zero (padding) leaves Q U V as
    read, as the prototype did."""
    spec = np.asarray(spec, dtype=np.float64)
    ns = spec.shape[0]
    ic = spec[0, cont] if cont is not None and ns > 1 else None
    out = spec.copy()
    for k in range(ns):
        if k > 0 and ic is not None and np.isfinite(ic) and ic != 0:
            out[k] = 100.0 * spec[k] / ic
        elif (k == 0 or cont is None) and iscale:
            out[k] = spec[k] / iscale
    return out


def unit_text(u) -> str:
    """'W m^-2 Hz^-1 sr^-1' -> 'W m⁻² Hz⁻¹ sr⁻¹'."""
    return re.sub(r"\^(-?\d+)", lambda m: m.group(1).translate(SUP), str(u or ""))


def fmt_signed(v, nd=1) -> str:
    """+1.3 / −1.3 with a typographic minus; 0 stays 0."""
    s = f"{v:+.{nd}f}"
    if float(s) == 0:
        return f"{0:.{nd}f}"
    return s.replace("-", "−")

"""A slit's time slice to a FITS file of its own, simple to read from Python (astropy) and IDL (readfits, mrdfits):
the slice as the slit panel has it (its t steps, data.tsample; one Stokes and one lambda), the pixels along the slit
and the points that drew it, and the t of each row.

    HDU 0  PRIMARY   float32 (n_t, n_points) in numpy order: NAXIS1 runs along the slit, NAXIS2 over the rows of
                     TIME; IDL's readfits gives it as [n_points, n_t]
    HDU 1  SLIT      a row per point along the slit: X, Y (the pixel read), XPOS, YPOS (where the point lies), DIST
    HDU 2  TIME      a row per row of the slice: TINDEX, TSEC, UTC
    HDU 3  VERTICES  a row per point clicked: XPOS, YPOS

Indices count from 0 (IDXBASE = 0): t, Stokes and lambda are the cube's array indices, X and Y the main image's
(column, row), as numpy and IDL index them; FITS's own pixel numbers start at 1, so X = 0 is FITS pixel 1. XPOS and
YPOS put pixel centres at integers. The vertices are a table rather than header cards: the same mrdfits call as the
other tables, any number of them, no indexed keywords to gather. The tables' columns are the same for every cube,
values not known left NaN or blank, so one script reads every file.

Keywords where SOLARNET (Haugan & Fredvik, SOLARNET metadata recommendations) has one: DATE (written), FILENAME,
PARENT (the cube's file), CREATOR, VERS_SW, BUNIT, BTYPE, WAVELNTH with WAVEUNIT, WAVEBAND, DATEREF, TIMESYS. The
rest are this file's: STOKES, STOKESIX, LAMIDX, LAMBDA0, DLAMBDA, NTCUBE, TSTEPS, IDXBASE.

    path = write_time_slice(folder, values, t=steps, pix=(iy, ix), pts=points, source=cube_path, axes=axes, s=s, l=l)
"""
import datetime as dt
import os
import re

import numpy as np

from .. import __version__
from .._name import APP_NAME
from .axes import STOKES
from .names import stem
from .slits import slit_samples
from .tsample import label

_UNSAFE = re.compile(r"[^A-Za-z0-9._=+-]")             # a file name's characters that shells and IDL take as they are
UTC_CHARS = 23                                          # 'YYYY-MM-DDThh:mm:ss.sss'
LONG = 68                                               # characters of a string card's value without CONTINUE
COMMENTS = ("The slit's time slice: NAXIS1 along the slit, NAXIS2 over t.",       # each within a COMMENT card's 72
            "numpy reads it as [t, point], IDL's readfits as [point, t].",
            "NaN: no value (the cube's padding, or a pixel not read yet).",
            "HDU 1 SLIT: a row per point along the slit (X, Y, XPOS, YPOS, DIST).",
            "HDU 2 TIME: a row per t of the slice (TINDEX, TSEC, UTC).",
            "HDU 3 VERTICES: the points the slit was drawn through (XPOS, YPOS).",
            "X, Y, XPOS, YPOS: main image pixels from 0, centres at integers.")


def stokes_name(s: int | None, ns: int) -> str | None:
    """'I', 'Q', 'U', 'V' with the four Stokes; 's<k>' with another number of them; None without a Stokes axis."""
    if s is None:
        return None
    return STOKES[s] if ns == len(STOKES) else f"s{int(s)}"


def file_name(source, stokes: str | None, l: int | None, when: dt.datetime) -> str:  # noqa: E741
    """<cube's file name without its suffix>_slit[_<Stokes>][_l<lambda index>]_<YYYYmmddTHHMMSS, UTC>.fits; the
    cube's name with only the characters a shell takes as they are (an SST name's ':' becomes '-')."""
    parts = [_UNSAFE.sub("-", stem(os.path.basename(str(source).rstrip("/")))) or "cube", "slit"]
    if stokes is not None:
        parts.append(stokes)
    if l is not None:
        parts.append(f"l{int(l):02d}")
    parts.append(when.strftime("%Y%m%dT%H%M%S"))
    return "_".join(parts) + ".fits"


def _utc(times, t: np.ndarray) -> tuple[np.ndarray, list[str], str]:
    """Seconds and text of each t, and what the seconds count from: 'DATEREF', 'midnight UT' (a time of day with no
    day: LP cubes, data.axes.from_lp) or '' (no times: NaN and blank)."""
    t_sec = getattr(times, "t_sec", None)
    if t_sec is None:
        return np.full(len(t), np.nan), [""] * len(t), ""
    sec = np.asarray(t_sec, float)[t]
    dateref = getattr(times, "dateref", None)
    of_day = bool(getattr(times, "time_of_day", False)) or dateref is None
    base = np.datetime64(0, "ms") if of_day else np.datetime64(dateref, "ms")
    text = [str(base + np.timedelta64(int(round(v * 1e3)), "ms"))[11 if of_day else 0:UTC_CHARS] for v in sec]
    return sec, text, "midnight UT" if of_day else "DATEREF"


def hdus(values, *, t, pix, pts, source, axes=None, times=None, s: int | None = None, ns: int = 1,
         l: int | None = None, nt: int | None = None, name: str = "", when: dt.datetime | None = None):  # noqa: E741
    """The file's HDUs (an astropy HDUList), from:
    values  (len(t), n_points): the time slice, as the panel has it;
    t       the cube's t index of each row;
    pix     (iy, ix): the pixel read at each point along the slit (data.slits.slit_pixels);
    pts     the points clicked, (x, y) in the view's coordinates, pixel centres at .5 (ViewState.path);
    source  the cube's file (its base name alone is written);
    axes    its data.axes.Axes (BUNIT, BTYPE, lambda), times: the Axes whose times label its t (default axes);
    s, ns   its Stokes index and number of Stokes (s None: no Stokes axis); l: its lambda index (None: no lambda);
    nt      its number of t steps (TSTEPS says 'all' when every one is in the file);
    name    this file's name (FILENAME); when: the time it is written (DATE), UTC."""
    from astropy.io import fits

    values = np.asarray(values, np.float32)
    t = np.asarray(t, np.int64).reshape(-1)
    iy, ix = (np.asarray(a, np.int64).reshape(-1) for a in pix)
    path, dist = slit_samples(np.asarray(pts, np.float64))
    if values.ndim != 2 or values.shape != (len(t), len(ix)) or len(iy) != len(ix) or len(path) != len(ix):
        raise ValueError(f"a time slice {values.shape} for {len(t)} t and {len(ix)} points along the slit "
                         f"({len(path)} from its vertices)")
    times = times if times is not None else axes
    when = when or dt.datetime.now(dt.UTC)
    nt = len(t) if nt is None else int(nt)

    h = fits.Header()
    h["DATE"] = (when.strftime("%Y-%m-%dT%H:%M:%S"), "when this file was written, UTC")
    if name:
        h["FILENAME"] = name
    h["PARENT"] = (os.path.basename(str(source).rstrip("/")), "the cube this is a slice of")
    if max(len(name), len(h["PARENT"])) > LONG:          # the long-string convention (CONTINUE) said
        h["LONGSTRN"] = ("OGIP 1.0", "CONTINUE cards carry long strings")
    h["CREATOR"] = (APP_NAME, "the software that wrote this file")
    h["VERS_SW"] = (str(__version__), f"{APP_NAME}'s version")
    for key in ("BUNIT", "BTYPE"):
        v = getattr(axes, key.lower(), None)
        if v:
            h[key] = (str(v), "as the cube's header")
    stokes = stokes_name(s, ns)
    if stokes is not None and s is not None:
        h["STOKES"] = (stokes, "the Stokes parameter of the slice")
        h["STOKESIX"] = (int(s), "its index in the cube, from 0")
    if l is not None:
        h["LAMIDX"] = (int(l), "lambda index in the cube, from 0")
        lam = getattr(axes, "lam_nm", None)
        if lam is not None and int(l) < len(lam):
            h["WAVELNTH"] = (float(lam[l]), "[nm] its wavelength, air, as tabulated")
            h["WAVEUNIT"] = (-9, "WAVELNTH in 10^WAVEUNIT m: nm")
        if getattr(axes, "line", None):
            h["WAVEBAND"] = (str(axes.line), "the line")
        lam0 = getattr(axes, "lam0_nm", None)
        if lam0 is not None:
            h["LAMBDA0"] = (float(lam0), "[nm] the line's laboratory centre, air")
            d = axes.dlam_A(l) if lam is not None and int(l) < len(lam) else None
            if d is not None:
                h["DLAMBDA"] = (float(d), "[Angstrom] WAVELNTH - LAMBDA0")
    sec, text, since = _utc(times, t)
    if since == "DATEREF":
        h["DATEREF"] = (str(np.datetime64(times.dateref, "ms")), "TSEC counts from it")
        h["TIMESYS"] = ("UTC", "")
    h["NTCUBE"] = (nt, "t steps in the cube")
    h["TSTEPS"] = (label(None if len(t) >= nt else len(t)), "t steps here: all, or NAXIS2 of NTCUBE")
    h["IDXBASE"] = (0, "indices count from 0: t, Stokes, lambda, X, Y")
    for c in COMMENTS:
        h.add_comment(c)
    primary = fits.PrimaryHDU(values, header=h)

    xy = path - 0.5                                     # pixel centres at integers, as the array indices
    slit = fits.BinTableHDU.from_columns([
        fits.Column("X", "J", unit="pixel", array=ix.astype(np.int32)),
        fits.Column("Y", "J", unit="pixel", array=iy.astype(np.int32)),
        fits.Column("XPOS", "D", unit="pixel", array=xy[:, 0]),
        fits.Column("YPOS", "D", unit="pixel", array=xy[:, 1]),
        fits.Column("DIST", "D", unit="pixel", array=np.asarray(dist, np.float64))], name="SLIT")
    for c in ("A row per point along the slit, a column of the primary array each.",
              "X, Y: the pixel read (column, row of the main image, from 0).",
              "XPOS, YPOS: where the point lies; X = floor(XPOS + 0.5).",
              "DIST: distance along the slit from its first point, pixels."):
        slit.header.add_comment(c)

    tab = fits.BinTableHDU.from_columns([
        fits.Column("TINDEX", "J", array=t.astype(np.int32)),
        fits.Column("TSEC", "D", unit="s", array=sec),
        fits.Column("UTC", f"{UTC_CHARS}A", array=np.array(text, dtype=f"U{UTC_CHARS}"))], name="TIME")
    if since == "DATEREF":
        tab.header["DATEREF"] = (h["DATEREF"], "TSEC counts from it")
    for c in ("A row per row of the primary array; TINDEX: the cube's t, from 0.",
              *{"DATEREF": ("TSEC: seconds since DATEREF, as the viewer's t axis.", "UTC: the same time, ISO 8601."),
                "midnight UT": ("TSEC: seconds since midnight UT of a day the cube does not give.",
                                "UTC: the same time of day, hh:mm:ss.sss."),
                "": ("TSEC, UTC: the cube gives no times (NaN, blank).",)}[since]):
        tab.header.add_comment(c)

    vx = np.asarray(pts, np.float64).reshape(-1, 2) - 0.5
    vert = fits.BinTableHDU.from_columns([
        fits.Column("XPOS", "D", unit="pixel", array=vx[:, 0]),
        fits.Column("YPOS", "D", unit="pixel", array=vx[:, 1])], name="VERTICES")
    for c in ("The points the slit was drawn through, in order: main image pixels",
              "from 0, centres at integers, as SLIT's XPOS, YPOS."):
        vert.header.add_comment(c)
    return fits.HDUList([primary, slit, tab, vert])


def write_time_slice(folder, values, *, t, pix, pts, source, axes=None, times=None, s: int | None = None, ns: int = 1,
                     l: int | None = None, nt: int | None = None, when: dt.datetime | None = None) -> str:  # noqa: E741
    """The time slice to a new file in folder (hdus has the arguments), named file_name's way; an existing file is
    never written over: _2, _3, ... after the name. Returns its path."""
    when = when or dt.datetime.now(dt.UTC)
    base = file_name(source, stokes_name(s, ns), l, when)
    for n in range(1, 1000):
        name = base if n == 1 else f"{base[:-len('.fits')]}_{n}.fits"
        path = os.path.join(os.fspath(folder), name)
        try:                                            # the name taken at once: a file there is never replaced
            os.close(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666))
        except FileExistsError:
            continue
        try:
            hdus(values, t=t, pix=pix, pts=pts, source=source, axes=axes, times=times, s=s, ns=ns, l=l, nt=nt,
                 name=name, when=when).writeto(path, overwrite=True)
        except BaseException:
            os.remove(path)                             # no half-written file left behind
            raise
        return path
    raise FileExistsError(f"{base} and 998 more of its name in {folder}")

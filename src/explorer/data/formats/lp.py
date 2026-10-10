"""LP (La Palma) cubes as SSTRED writes them for CRISPEX: a 512-byte ASCII header, then raw samples.

    _im.icube / _im.fcube   frames [nx, ny, nframes] (IDL order), frame index = (t * ns + s) * nl + l
    _sp.icube / _sp.fcube   the same values per pixel [nl, nt, npix * ns], pixel-major, Stokes fastest

An image cube's header does not say how its frames split into (t, s, lambda): that comes from its per-pixel
file (nl = its nx, nt = its ny), so the two are read as a pair. Without one (field and velocity maps, products,
clipped cubes), the scans in the file name say it (lp_single_layout).

Values are counts in the integer cubes. What they mean is in the IDL save file SSTRED writes beside the cube,
<stem>_im_times+wvl.idlsave (lp_sidecar; _times_wvl beside its 2019 cubes): the scale (fac) and the value that
stands for no data (nan_rplcmnt), read by lp_values; its wavelengths and times by axes.from_lp. A cube derived
from another of the same observation (<stem>_stokesI_..., Stokes I alone) has none of its own: the full-Stokes
cube's (lp_sibling_sidecar) gives its times and wavelengths only, never its values' meaning.
"""
import os
import re
from dataclasses import dataclass, replace

import numpy as np

from ...obs import get_logger
from .layout import Layout

log = get_logger("data")

HEADER_BYTES = 512
_SCANS = re.compile(r"=(\d+)-(\d+)(?=[._]|$)")      # "=0-85": the scans in a cube, as SSTRED names it
_DATATYPE = {"1": "u1", "2": "i2", "3": "i4", "4": "f4"}
_IMAGE_CUBE = re.compile(r"(.*)_im(?:\.[^.]+)*?\.[if]cube$")       # <stem>_im[.tag].icube: tag as in "aligned6173"
_DERIVED = re.compile(r"_stokes[IQUV]+(?=_)")      # "_stokesI_": some of the Stokes of the "_stokes_" cube
SIDECAR = "_im_times+wvl.idlsave"
SIDECARS = (SIDECAR, "_im_times_wvl.idlsave")      # SSTRED's name, and its 2019 cubes' (an underscore for the plus)
_said: set[str] = set()     # cubes whose IDL save file was named: the layout and the axes look it up, linking twice


@dataclass(frozen=True)
class LPHeader:
    text: str
    dtype: np.dtype
    nx: int
    ny: int
    nt: int
    ns: int


def lp_header(path) -> LPHeader:
    """Parse the header, e.g. "stokes=[I], ns=1 :  datatype=2 (integer), dims=3, nx=21, ny=66, nt=4068240,
    endian=l"."""
    with open(path, "rb") as f:
        raw = f.read(HEADER_BYTES)
    text = raw.rstrip(b"\0").decode("ascii", "replace")
    kv = dict(re.findall(r"(\w+)=([^,:]+)", text))
    try:
        dt = _DATATYPE[kv["datatype"].split()[0]]
        order = "<" if kv.get("endian", "l").strip() == "l" else ">"
        return LPHeader(text=text.strip(), dtype=np.dtype(order + dt), nx=int(kv["nx"]), ny=int(kv["ny"]),
                        nt=int(kv["nt"]), ns=int(kv.get("ns", 1)))
    except (KeyError, ValueError) as e:
        raise ValueError(f"{path}: not an LP cube header ({e}): {text[:80]!r}") from None


def lp_pair_layouts(im_path, sp_path) -> tuple[Layout, Layout]:
    """Layouts of an LP image cube and its per-pixel file.

    Image (nt, ns, nl, ny, nx); per-pixel (ny, nx, ns, nt, nl), Stokes before t inside a pixel as the prototype's
    SpLP reads it (not checked yet against a real multi-Stokes _sp.icube)."""
    im, sp = lp_header(im_path), lp_header(sp_path)
    nx, ny, nframes = im.nx, im.ny, im.nt
    nl, nt, ns = sp.nx, sp.ny, sp.ns
    if nl * nt * ns != nframes or sp.nt != nx * ny * ns:
        raise ValueError(f"{im_path} and {sp_path} do not describe the same cube: image {nx}x{ny}x{nframes}, "
                         f"per-pixel nl={nl} nt={nt} ns={ns} npix*ns={sp.nt}")
    image = Layout(path=str(im_path), kind="lp", offset=HEADER_BYTES, shape=(nt, ns, nl, ny, nx), dtype=im.dtype,
                   axes=("UTC", "STOKES", "WAVE", "HPLT", "HPLN"))
    per_pixel = Layout(path=str(sp_path), kind="lp", offset=HEADER_BYTES, shape=(ny, nx, ns, nt, nl), dtype=sp.dtype,
                       axes=("HPLT", "HPLN", "STOKES", "UTC", "WAVE"))
    return image, per_pixel


def scans_in_name(path) -> int | None:
    """How many scans the file name says the cube holds: the sum of its "=a-b" ranges (a cube joined from two
    series has two), or None without any."""
    ranges = _SCANS.findall(os.path.basename(str(path)))
    return sum(int(b) - int(a) + 1 for a, b in ranges) if ranges else None


def lp_single_layout(path) -> Layout:
    """An LP cube without a per-pixel file: frames [nx, ny, n] in CRISPEX's order, frame = (t * ns + s) * nl + l.
    With n equal to the scans in the name: one frame per scan, (t, y, x) (maps of B or v, Doppler products). With
    a multiple of scans x ns: (t, s, lambda, y, x), ns from the header (a clipped image cube: its frames equal
    the first scans of the whole cube's, checked on real data). Without scans in the name, or with a number they
    do not divide, one leading axis that nothing names: roles() calls it unknown, and --axes says what it is."""
    h = lp_header(path)
    n, scans, ns = h.nt, scans_in_name(path), max(1, h.ns)
    shape: tuple[int, ...]
    axes: tuple[str, ...]
    if scans and n == scans:
        shape, axes = (n, h.ny, h.nx), ("UTC", "HPLT", "HPLN")
    elif scans and n % (scans * ns) == 0:
        shape, axes = (scans, ns, n // (scans * ns), h.ny, h.nx), ("UTC", "STOKES", "WAVE", "HPLT", "HPLN")
    else:
        shape, axes = (n, h.ny, h.nx), ("FRAME", "HPLT", "HPLN")
    return Layout(path=str(path), kind="lp", offset=HEADER_BYTES, shape=shape, dtype=h.dtype, axes=axes)


def lp_sidecar(path) -> str | None:
    """The IDL save file beside an LP image cube: <stem>_im_times+wvl.idlsave, or _times_wvl, for <stem>_im[.tag].icube
    or .fcube (an aligned cube's tag is not in its name; its counts are on the scale of the unaligned cube's, the
    same fac), next to the path given, else next to the file it links to (a cube linked alone, under another name,
    into another directory, as companions() does); None when there is none. With both names there, the one whose
    fac fits the cube's values (_fits_values): SSTRED wrote one for the integer cubes and one for the float cube of
    the same observation, with the same times and lambda; when not exactly one fits, neither. A file under another
    name than the cube's own is said once on the console, and so is a choice that could not be made."""
    for p in dict.fromkeys((os.path.abspath(str(path)), os.path.realpath(str(path)))):
        m = _IMAGE_CUBE.match(os.path.basename(p))
        found = _beside(p, m.group(1)) if m else []
        chosen = len(found) > 1
        if chosen:
            fit = [s for s in found if _fits_values(p, s)]
            if len(fit) != 1:
                _say(path, f"{len(found)} IDL save files of the same observation ("
                           f"{', '.join(os.path.basename(s) for s in found)}), and {'each' if fit else 'none'} of "
                           f"them can scale its values: none taken")
                return None
            found = fit
        if found:
            if found[0] != os.path.splitext(os.path.abspath(str(path)))[0] + "_times+wvl.idlsave":
                _say(path, f"scale, padding, times and wavelengths from {found[0]}"
                           + (" (of the two there, the one whose fac fits its values)" if chosen else ""))
            return found[0]
    return None


def _beside(p, stem: str) -> list[str]:
    """The IDL save files <stem>_im_times+wvl.idlsave and <stem>_im_times_wvl.idlsave next to p, those that exist."""
    return [s for s in (os.path.join(os.path.dirname(p), stem + suffix) for suffix in SIDECARS) if os.path.isfile(s)]


def _fits_values(cube, side) -> bool:
    """Whether an IDL save file's fac can be the scale of an LP cube's values: other than 1 for integer counts, 1
    or none for floats. On the one observation with both files (SSTRED's 8542 Stokes cubes of 2019), the integer
    cubes' counts are the float cube's values times the 1e9 of one file, and the other file says 1."""
    from .idlsave import read

    try:
        fac = read(side, names={"fac"}).get("fac")
        integer = lp_header(cube).dtype.kind in "iu"
    except (OSError, ValueError):
        return False
    return (isinstance(fac, np.number) and bool(np.isfinite(fac)) and float(fac) not in (0.0, 1.0)) == integer


def _say(path, what: str) -> None:
    if str(path) not in _said:
        _said.add(str(path))
        log.warning("%s: %s", os.path.basename(str(path)), what)


def lp_sibling_sidecar(path) -> str | None:
    """For an LP image cube without an IDL save file of its own (lp_sidecar), the one of the cube it was derived
    from in the same observation: <stem>_stokes_<rest>_im_times+wvl.idlsave (or _times_wvl, the first there) for
    <stem>_stokesI_<rest>_im[.tag].icube, next to the path given, else next to the file it links to; None when the
    name says no such cube or there is no file. The same scans and tunings, so its times and wavelengths can be the
    derived cube's (axes.from_lp checks their sizes); its fac and nan_rplcmnt describe the other cube's values
    (float, unscaled), never these."""
    for p in dict.fromkeys((os.path.abspath(str(path)), os.path.realpath(str(path)))):
        m = _IMAGE_CUBE.match(os.path.basename(p))
        if m is None or not _DERIVED.search(m.group(1)):
            continue
        found = _beside(p, _DERIVED.sub("_stokes", m.group(1), count=1))
        if found:
            return found[0]
    return None


def lp_values(layout: Layout, sidecar) -> Layout:
    """The layout with what the values mean, from the IDL save file beside the cube: physical = raw / fac (1e11 or
    1e9 in SSTRED's integer cubes, 1 in its float ones), and raw == nan_rplcmnt is no data, as FITS BLANK. Measured
    on real cubes with FITS siblings: the same values, and nan_rplcmnt at exactly the pixels the FITS cube has NaN
    (the padding); no value below it. A variable that is not there leaves its part unchanged. ValueError or
    OSError when the file cannot be read."""
    from .idlsave import read

    v = read(sidecar, names={"fac", "nan_rplcmnt"})
    fac, blank = v.get("fac"), v.get("nan_rplcmnt")
    kw: dict = {}
    if isinstance(fac, np.number) and np.isfinite(fac) and fac != 0:
        kw["scale"] = 1.0 / float(fac)
    if isinstance(blank, np.number) and (layout.dtype.kind == "f" or float(blank).is_integer()):
        kw["blank"] = blank.item()
    return replace(layout, **kw)

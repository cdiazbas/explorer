"""Short names for cubes, as the window shows them over each image and on the panels' tabs (ROADMAP E8.1). SST file
names run long (nb_6173_YYYY-MM-DDThh:mm:ss_hh:mm:ss=0-185_stokes_corrected_im, aligned_stokes_8542=0-54_=0-28_im.
aligned6173): the name is what the cube shows, the line and, for a derived map, the quantity:

    Fe I 617.3              an intensity cube: its line (WAVEBAND, else the wavelength in its file name)
    Blos · Fe I 617.3       a map: what it is (the first word of its file name), then its line
    8542 Å                  a wavelength in the name that no known line matches

The line comes from the header first (axes.line), else from a four-digit wavelength in Ångström in the file name
(6173, 8542, 6563), matched to the known lines (axes.LINES) within MATCH_A. Cubes that would share a name are told
apart by their format (FITS, LP), else by their files. Nothing left to go on: the file's own name, cut in the middle
to MAX_CHARS.

The panels of an axis not known to be lambda name it by what the cube shows (quantity, ROADMAP E8.8): its header's
BTYPE or CONTENT, an inversion's line, the map's word, an imager's instrument and band ("AIA 171 Å"), else
"Quantity"; and the axis by its own name in the header when it has one (axis_word: BIFROST's z).
"""
import math
import os
import re
from typing import NamedTuple

from .axes import LINES, STOKES, Planes, is_inversion, logs

MAX_CHARS = 32              # a name longer than this is cut in the middle (…), its file in the tooltip
MATCH_A = 6.0               # Å: a wavelength in a file name is a known line within this (the name rounds it: 6563)
# what a map is, by the first word of its file name (lower case): the quantity shown before the line
QUANTITIES = {"blos": "Blos", "bstr": "Bstr", "btr": "Btr", "binc": "Binc", "bazi": "Bazi", "bhor": "Bhor",
              "vlos": "Vlos", "vdop": "Vdop", "doppl": "Doppler", "dopp": "Doppler", "temp": "T",
              "inversion": "Inversion"}
SUFFIXES = (".fits", ".icube", ".fcube")
_WAVE = re.compile(r"(?<![0-9])([3-9][0-9]{3}|1[0-9]{4})(?![0-9])")      # 3000-19999 Å, alone
# what a header says of every cube, so names nothing: such a BTYPE or CONTENT gives way to the rules after it
GENERIC = {"intensity", "data", "image", "value", "values", "counts", "main", "primary", "blank", "unknown",
           "hmi observable"}
FALLBACK = "Quantity"                           # what a cube shows when nothing names it
PLANE = "plane"                                 # an axis not known to be lambda that nothing names, as counted
# an axis's own name (CNAMEn, CTYPEn) that says nothing explorer's own names do not: by its first word
GENERIC_AXIS = {"", "wave", "awav", "freq", "wavelength", "stokes", "utc", "time", "tai", "hpln", "hplt", "spatial",
                "frame", "index", "pixel", "axis"}


def stem(path) -> str:
    """The file's name without its cube suffix: Blos.6173_map for Blos.6173_map.fcube."""
    name = os.path.basename(str(path))
    for suf in SUFFIXES:
        if name.endswith(suf):
            return name[:-len(suf)]
    return name


def cut(text: str, n: int = MAX_CHARS) -> str:
    """text, cut in the middle to n characters (both ends say the most: the kind and the scans)."""
    if len(text) <= n:
        return text
    head = (n - 1) // 2
    return text[:head] + "…" + text[len(text) - (n - 1 - head):]


def line_of(path, axes=None) -> str | None:
    """The cube's line: the header's, else the first wavelength in its file name that matches a known line, else
    that wavelength in Å; None without either."""
    line = getattr(axes, "line", None)
    if line:
        return line
    waves = [int(m) for m in _WAVE.findall(stem(path))]
    for w in waves:
        best = min(LINES.values(), key=lambda v: abs(v[1] * 10 - w))
        if abs(best[1] * 10 - w) <= MATCH_A:
            return best[0]
    return f"{waves[0]} Å" if waves else None


def short_name(path, axes=None) -> str:
    """The name the window shows for the cube at path (axes: its data.axes.Axes, for the header's line and name):
    the map's word and the line, the line, else the header's own name for what it shows (header_name: "AIA 171 Å",
    "lg(tg)"), else its file's name, cut."""
    s = stem(path)
    word = re.split(r"[^A-Za-z]+", s)[0].lower() if s else ""
    quantity = QUANTITIES.get(word)
    line = line_of(path, axes)
    if line and quantity:
        return f"{quantity} · {line}"
    if line:
        return line
    return cut(header_name(axes) or s)


def card(axes, key: str) -> str:
    """A naming card of the cube's header (data.axes.naming_cards), "" without it."""
    return str((getattr(axes, "cards", None) or {}).get(key, "")).strip()


def map_word(path) -> str | None:
    """What a map is, by the first word of its file name (QUANTITIES: "Blos"), or by the segment a JSOC file name
    ends in (hmi.sharp_cea_720s.377.20140205_030000_TAI.Br: "Br"); None without either."""
    s = stem(path)
    word = re.split(r"[^A-Za-z]+", s)[0].lower() if s else ""
    if word in QUANTITIES:
        return QUANTITIES[word]
    if word in ("hmi", "aia") and "." in s:
        seg = s.rsplit(".", 1)[-1]
        if seg.isalpha() and seg.lower() not in GENERIC:
            return seg
    return None


def passband(axes) -> str | None:
    """An imager's instrument and passband from its header: "AIA 171 Å", "EUI/FSI 174 Å", "EUVI 171 Å", "GONG Hα".
    The instrument: TELESCOP after its first "/", else DETECTOR when it is one word, else TELESCOP's last word, else
    INSTRUME. The band: WAVELNTH in its WAVEUNIT (Å without one), the known line within MATCH_A when there is one,
    else in Å. None without a WAVELNTH in a unit it reads."""
    try:
        w = float(card(axes, "WAVELNTH"))
    except ValueError:
        return None
    unit = card(axes, "WAVEUNIT").lower()
    if unit in ("-9", "nm", "nanometer", "nanometers"):
        w *= 10.0
    elif unit not in ("", "-10", "angstrom", "angstroms", "a", "å"):
        return None
    if not (math.isfinite(w) and w > 0):
        return None
    tel, det = card(axes, "TELESCOP"), card(axes, "DETECTOR")
    if "/" in tel:
        inst = tel.split("/", 1)[1]
    elif det.isalpha():
        inst = det
    elif tel:
        inst = re.split(r"[-\s]", tel)[-1].strip("()")
    else:
        inst = card(axes, "INSTRUME")
    best = min(LINES.values(), key=lambda v: abs(v[1] * 10 - w))
    band = best[0] if abs(best[1] * 10 - w) <= MATCH_A else f"{w:g} Å"
    return f"{inst} {band}".strip()


def header_name(axes) -> str | None:
    """What the header alone says a cube shows, by quantity's rules that read it: BTYPE or CONTENT, unless generic;
    without WAVEBAND, the imager's instrument and band (passband). None when it says nothing of its own."""
    btype = str(getattr(axes, "btype", None) or "").strip()
    if btype and btype.lower() not in GENERIC:
        return logs(btype)
    content = card(axes, "CONTENT")
    if content and content.lower() not in GENERIC:
        return content.lower()
    return passband(axes) if not card(axes, "WAVEBAND") else None


def quantity(path, axes=None) -> str:
    """What the cube shows, for the panels of an axis not known to be lambda; the first rule that gives a name:
    1. BTYPE, unless generic (GENERIC: "Intensity"), a log10 written as one (logs: "log₁₀(tg)");
    2. CONTENT, unless generic;
    3. an inversion (is_inversion): "<line> inversion", "Inversion" without a line;
    4. the map's word in its file name (map_word: "Blos");
    5. without WAVEBAND (an SST cube's WAVELNTH is its prefilter): the imager's instrument and band (passband);
    6. the generic BTYPE;
    7. the line, from the header's WAVEBAND or a wavelength in the file name (line_of);
    8. FALLBACK, "Quantity": the file's name is the cube's tab and tooltip already."""
    btype = str(getattr(axes, "btype", None) or "").strip()
    if btype and btype.lower() not in GENERIC:
        return logs(btype)
    content = card(axes, "CONTENT")
    if content and content.lower() not in GENERIC:
        return content.lower()
    if is_inversion(path):
        line = line_of(path, axes)
        return f"{line} inversion" if line else "Inversion"
    word = map_word(path)
    if word:
        return word
    band = passband(axes) if not card(axes, "WAVEBAND") else None
    return band or btype or line_of(path, axes) or FALLBACK


def axis_word(roles, axes) -> str | None:
    """The name the header gives the cube's axis other than t (CNAMEn, else CTYPEn before its "-"), unless it says
    nothing explorer's own names do not (GENERIC_AXIS); None without one."""
    if roles.l is None:
        return None
    try:
        n = int(card(axes, "NAXIS")) - roles.l      # FITS numbers the axes the other way round
    except ValueError:
        return None
    for key in (f"CNAME{n}", f"CTYPE{n}"):
        v = card(axes, key)
        v = v.split("-")[0].strip() if key.startswith("CTYPE") else v
        first = re.split(r"[^a-z]+", v.lower())[0] if v else ""
        if v and first not in GENERIC_AXIS:
            return v
    return None


class SliceNames(NamedTuple):
    """How a cube's panels name its axis other than t: panel, the title of that axis against t ("λ–t"); label, that
    axis's label in index units ("λ index"; in Ångström the panels say "Δλ [Å]" themselves); spectral: the axis is
    known to be lambda; mapped: the cube has no axis but t, or one plane along the other (a map, a single tuning), so
    a slice along that axis is one row and says nothing: lambda-t is a curve against t, the slit's spectral slice is
    left out; value: what a curve's values are, with their unit when the header gives it ("Blos [G]"); axis: that
    axis's own name where a slider or the status line counts along it: "λ" when known to be lambda, else the
    header's name for it (axis_word: "z"), an inversion's "parameter", else "plane"."""
    panel: str
    label: str
    spectral: bool
    mapped: bool
    value: str = "value"
    axis: str = "λ"


KNOWN_LAMBDA = ("header", "--axes", "SOLARNET order")   # Roles.how that name lambda; else it is a guess


def value_name(path, axes=None) -> str:
    """What a cube's values are, without their unit: what it shows (quantity)."""
    return quantity(path, axes)


def unit(axes) -> str:
    """The unit of a cube's values: BUNIT, else PIXLUNIT (an AIA file's DN); "" without either."""
    return str(getattr(axes, "bunit", None) or "").strip() or card(axes, "PIXLUNIT")


def value_label(path, axes=None) -> str:
    """What a cube's values are, for the axis of a curve: value_name, with its unit in brackets when the header gives
    one (unit)."""
    q, u = value_name(path, axes), unit(axes)
    return f"{q} [{u}]" if u else q


def slice_names(roles, axes, path) -> SliceNames:
    """The names of a cube's axis other than t, in one place. Known to be lambda (its tunings in Å, or so named by
    the header, by --axes or by SOLARNET's order of three axes; never in an inversion's file), with more than one
    tuning: "λ–t" and "λ index", as always. Otherwise by what the cube shows (quantity): "Blos–t", "Blos index"; a
    single tuning known to be lambda by its line ("Fe I 617.3–t"); an axis of several planes by its own name too,
    the header's (axis_word: "lg(tg) (z–t)", "z index") or an inversion's "parameter"."""
    dl = axes.dlam_A() if axes is not None and roles.l is not None else None
    spectral = (roles.l is not None and not is_inversion(path)
                and ((dl is not None and len(dl) == roles.nl) or roles.how in KNOWN_LAMBDA))
    mapped = roles.l is None or roles.nl <= 1
    if spectral and not mapped:
        return SliceNames("λ–t", "λ index", True, False)
    q = (line_of(path, axes) if spectral else None) or quantity(path, axes)
    word = axis_word(roles, axes) or ("parameter" if is_inversion(path) else None)
    x = None if mapped else word
    panel, label = (f"{q} ({x}–t)", f"{x} index") if x else (f"{q}–t", f"{q} index")
    return SliceNames(panel, label, spectral, mapped, value_label(path, axes),
                      "λ" if spectral else word or PLANE)


def plane(s: int, planes: Planes = "stokes") -> str:
    """Plane s along a cube's s axis as its selector names it (planes: data.axes.Roles.planes): I, Q, U, V for
    Stokes; "Quantity 1", "Quantity 2", … for an inversion's parameters (data.axes.by_parameter), which no file on
    disk names; a snapshot's variables by their own names (a tuple)."""
    if isinstance(planes, tuple):
        return planes[s]
    if planes == "parameter":
        return f"{FALLBACK} {s + 1}"
    return STOKES[s] if s < len(STOKES) else f"s{s}"


def plane_text(s: int, ns: int, planes: Planes = "stokes") -> str:
    """Plane s of ns as the image, its key and its scale say it: "Stokes Q" with the four Stokes, "Quantity 2" for a
    parameter; "" otherwise (one Stokes, or not the four)."""
    if planes != "stokes":
        return plane(s, planes)
    return f"Stokes {STOKES[s]}" if ns == len(STOKES) else ""


def cube_names(datasets) -> list[str]:
    """A short name for each cube (short_name); cubes that would share one are told apart by their format, else by
    their files (each cut to fit)."""
    names = [short_name(d.path, getattr(d, "axes", None)) for d in datasets]
    for n in set(names):
        same = [i for i, m in enumerate(names) if m == n]
        if len(same) < 2:
            continue
        kinds = ["FITS" if str(datasets[i].path).endswith(".fits") else "LP" for i in same]
        if len(set(kinds)) == len(kinds):
            for i, k in zip(same, kinds, strict=True):
                names[i] = f"{n} ({k})"
        else:
            for i in same:
                names[i] = cut(stem(datasets[i].path))
    return names

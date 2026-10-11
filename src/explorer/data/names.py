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
"""
import os
import re
from typing import NamedTuple

from .axes import LINES

MAX_CHARS = 32              # a name longer than this is cut in the middle (…), its file in the tooltip
MATCH_A = 6.0               # Å: a wavelength in a file name is a known line within this (the name rounds it: 6563)
# what a map is, by the first word of its file name (lower case): the quantity shown before the line
QUANTITIES = {"blos": "Blos", "bstr": "Bstr", "btr": "Btr", "binc": "Binc", "bazi": "Bazi", "bhor": "Bhor",
              "vlos": "Vlos", "vdop": "Vdop", "doppl": "Doppler", "dopp": "Doppler", "temp": "T",
              "inversion": "Inversion"}
SUFFIXES = (".fits", ".icube", ".fcube")
_WAVE = re.compile(r"(?<![0-9])([3-9][0-9]{3}|1[0-9]{4})(?![0-9])")      # 3000-19999 Å, alone


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
    """The name the window shows for the cube at path (axes: its data.axes.Axes, for the header's line)."""
    s = stem(path)
    word = re.split(r"[^A-Za-z]+", s)[0].lower() if s else ""
    quantity = QUANTITIES.get(word)
    line = line_of(path, axes)
    if line and quantity:
        return f"{quantity} · {line}"
    if line:
        return line
    return cut(s)


def quantity(path, axes=None) -> str:
    """What the cube shows, for the panels of an axis not known to be lambda: the header's BTYPE, else the word that
    names a map at the start of its file name (QUANTITIES), else its file's name, cut."""
    btype = getattr(axes, "btype", None)
    if btype and str(btype).strip():
        return str(btype).strip()
    s = stem(path)
    word = re.split(r"[^A-Za-z]+", s)[0].lower() if s else ""
    return QUANTITIES.get(word) or cut(s)


class SliceNames(NamedTuple):
    """How a cube's panels name its axis other than t: panel, the title of that axis against t ("λ–t"); label, that
    axis's label in index units ("λ index"; in Ångström the panels say "Δλ [Å]" themselves); spectral: the axis is
    known to be lambda; mapped: the cube has no axis but t, or one plane along the other (a map, a single tuning), so
    a slice along that axis is one row and says nothing: lambda-t is a curve against t, the slit's spectral slice is
    left out; value: what a curve's values are, with their unit when the header gives it ("Blos [G]")."""
    panel: str
    label: str
    spectral: bool
    mapped: bool
    value: str = "value"


KNOWN_LAMBDA = ("header", "--axes", "SOLARNET order")   # Roles.how that name lambda; else it is a guess


def value_name(path, axes=None) -> str:
    """What a cube's values are, without their unit: its BTYPE, else the word naming a map in its file name, else
    "value"."""
    btype = str(getattr(axes, "btype", None) or "").strip()
    s = stem(path)
    word = re.split(r"[^A-Za-z]+", s)[0].lower() if s else ""
    return btype or QUANTITIES.get(word) or "value"


def value_label(path, axes=None) -> str:
    """What a cube's values are, for the axis of a curve: value_name, with BUNIT in brackets when the header gives
    it."""
    q = value_name(path, axes)
    unit = str(getattr(axes, "bunit", None) or "").strip()
    return f"{q} [{unit}]" if unit else q


def slice_names(roles, axes, path) -> SliceNames:
    """The names of a cube's axis other than t, in one place. Known to be lambda (its tunings in Å, or so named by
    the header, by --axes or by SOLARNET's order of three axes), with more than one tuning: "λ–t" and "λ index", as
    always. Otherwise (a map, a single tuning, or an unnamed axis taken for lambda by default) by what the cube shows:
    its quantity (quantity), "Blos–t", "Blos index"; a single tuning known to be lambda by its line ("Fe I 617.3–t")."""
    dl = axes.dlam_A() if axes is not None and roles.l is not None else None
    spectral = roles.l is not None and ((dl is not None and len(dl) == roles.nl) or roles.how in KNOWN_LAMBDA)
    mapped = roles.l is None or roles.nl <= 1
    if spectral and not mapped:
        return SliceNames("λ–t", "λ index", True, False)
    q = (line_of(path, axes) if spectral else None) or quantity(path, axes)
    return SliceNames(f"{q}–t", f"{q} index", spectral, mapped, value_label(path, axes))


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

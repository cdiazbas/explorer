"""The colour tables of the modern look's colour part (ROADMAP E5.5), from the prototype's app/look.py (_lut, _table,
_image_table, SEQUENTIAL, DIVERGINGS, 137-200).

- I steps through SEQUENTIAL (lightness monotonic); Q U V through DIVERGINGS (lightness monotonic on each half):
  dark-centre maps first on a dark window, light-centre first on a light one, grey last. Every map in the lists
  keeps +max and -max apart under simulated protanopia, deuteranopia and tritanopia (CIEDE2000 >= 20 between the two
  signs at every |v| >= 1/8). hsv is left out: its two ends are one red.
- Q U V start in grey (EXPLORER_DIVERGING names another start).
- A grey map is made exactly grey: one entry 1/255 off R = G = B sends the bridge's whole tile at 4 B/px instead of 1.
- The image's table has the padding at level 0 (the reduction puts NaN padding there) and the map on 1..255.
"""
import os

import numpy as np

SEQUENTIAL = ("gray", "CET-L1", "viridis", "inferno", "magma", "cividis")


def _divergings(light: bool) -> tuple:
    first = os.environ.get("EXPLORER_DIVERGING", "gray")
    rest = ("CET-D1A", "RdBu_r", "coolwarm", "CET-CBD1", "gray") if light else \
        ("CET-D4", "CET-D6", "CET-D1A", "RdBu_r", "CET-CBD1", "gray")
    return tuple(dict.fromkeys((first,) + rest))


# ColorBrewer's 11-class RdBu, the points matplotlib's RdBu interpolates: built here, importing matplotlib for it cost
# 320 ms on the first C; this gives its table to 1/255 in 3 of 768 channels
_OWN = {"RdBu": [(103, 0, 31), (178, 24, 43), (214, 96, 77), (244, 165, 130), (253, 219, 199), (247, 247, 247),
                 (209, 229, 240), (146, 197, 222), (67, 147, 195), (33, 102, 172), (5, 48, 97)]}
GREY = np.repeat(np.arange(256, dtype=np.uint8)[:, None], 3, 1)
_TABLES: dict = {"gray": None}                         # None: pyqtgraph's own grey, no table at all


def _lut(name: str) -> np.ndarray:
    """256 x 3 uint8 from pyqtgraph's maps, else matplotlib's; an unknown name falls back to CET-D4."""
    import pyqtgraph as pg

    for src in (None, "matplotlib"):
        try:
            return pg.colormap.get(name, source=src).getLookupTable(nPts=256, alpha=False)
        except Exception:
            pass
    from ..obs import get_logger

    get_logger("look").warning("no colour map %r in pyqtgraph or matplotlib: CET-D4 instead", name)
    return pg.colormap.get("CET-D4").getLookupTable(nPts=256, alpha=False)


def table(name: str) -> np.ndarray | None:
    """The map's 256-entry table, read once; None for grey."""
    if name not in _TABLES:
        import pyqtgraph as pg

        own = _OWN.get(name[:-2] if name.endswith("_r") else name)
        if own is not None:
            lut = pg.ColorMap(np.linspace(0, 1, len(own)), own[::-1] if name.endswith("_r") else own
                              ).getLookupTable(nPts=256, alpha=False)
        else:
            lut = _lut(name)
        if np.ptp(lut.astype(np.int16), axis=1).max() <= 1:
            lut = np.ascontiguousarray(lut[:, [1, 1, 1]])
        _TABLES[name] = lut
    return _TABLES[name]


def image_table(lut: np.ndarray | None, light: bool) -> np.ndarray | None:
    """The table for the image's uint8 levels: entry 0 the padding (black, white on a light window), the map on the
    other 255. None: pyqtgraph's own grey, whose 0 is already black."""
    pad = (255, 255, 255) if light else (0, 0, 0)
    if lut is None:
        if not light:
            return None
        lut = GREY
    t = np.empty((256, 3), np.uint8)
    t[0] = pad
    t[1:] = lut[np.round(np.linspace(0, 255, 255)).astype(int)]
    return t


class ColormapRegistry:
    """The map each Stokes wears: I the first sequential, Q U V the first diverging; C steps the shown one's."""

    def __init__(self, ns: int, light: bool = False):
        self.light = light
        self.maps = [SEQUENTIAL[0]] + [_divergings(light)[0]] * (max(1, ns) - 1)
        for m in set(self.maps):
            table(m)                                    # read now, not on the first frame of V

    def set_light(self, light: bool) -> None:
        """The other theme's diverging maps: Q U V keep theirs if that theme has it, else the one in its place."""
        if light == self.light:
            return
        old, new = _divergings(self.light), _divergings(light)
        self.maps = [m if s == 0 or m in new else new[min(old.index(m), len(new) - 1)] if m in old else new[0]
                     for s, m in enumerate(self.maps)]
        self.light = light
        for m in set(self.maps):
            table(m)

    def names_for(self, s: int) -> tuple:
        return SEQUENTIAL if s == 0 else _divergings(self.light)

    def lut(self, s: int) -> np.ndarray | None:
        return table(self.maps[s])

    def image_lut(self, s: int) -> np.ndarray | None:
        return image_table(self.lut(s), self.light)

    def cycle(self, s: int, step: int) -> str:
        names = self.names_for(s)
        i = names.index(self.maps[s]) if self.maps[s] in names else -1
        self.maps[s] = names[(i + step) % len(names)]
        return self.maps[s]

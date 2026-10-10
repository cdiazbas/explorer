"""A mask over the first cube (ROADMAP E8.2, `--mask file`): where it is set, outlined on every image. CRISPEX's
MASKCUBE (crispex.pro:58-61): a cube on the main cube's pixels, [nx, ny, masknt] with masknt equal to its nt or 1,
refused otherwise with the dimensions of both (CRISPEX_IO_FAILSAFES_MASK, crispex.pro:10175-10198). At each t the
frame shown is the mask's frame t when it has more than one, else its only frame (crispex.pro:21105-21111, frame
t_main or 0), contoured at level 1 (CRISPEX_DRAW_MASK_OVERLAYS, crispex.pro:7174-7177).

    mask = Mask.open(path, main)        # main: the first cube (a Dataset or link.describe(path)); MaskRefused: why
    mask.frame_at(t)                    # the mask's frame shown at the first cube's t
    mask.outline(t)                     # the edges round its set pixels at t: (n, 2, 2) segments, (x, y) per end

The file is read as a cube is (FITS or an LP .icube / .fcube, by content: formats.detect), its values as stored
(FITS BSCALE, BZERO and BLANK applied; never an IDL save file's scale, which belongs to the cube beside it). Its
frames are (y, x), alone or along one leading axis; leading axes of one plane are dropped. Set: a value of 1 or more,
as CRISPEX's contour at level 1 (0 / 1 masks, 0 / 255 byte masks); NaN is not set. The checks are data.link's: the
first cube's grid (other_grid) and its times (frames: one frame at every t, else as many as its times).

The outline runs along the pixels' edges, in the view's coordinates (pixel (y, x) covers x..x+1, y..y+1): every
edge between a set pixel and an unset one (or the image's border), straight runs joined into one segment. CRISPEX's
IDL contour of a 0 / 1 mask at level 1 runs through the centres of the edge pixels instead, half a pixel inside.
"""
import os
import threading
from collections import OrderedDict

import numpy as np

from .formats import detect, fits_layout, lp_single_layout
from .io import FrameReader
from .link import frames, other_grid

LEVEL = 1.0                 # set where the value is at least this: CRISPEX's contour level (crispex.pro:7176)
KEPT = 16                   # outlines kept, by mask frame: a step back and forth in t draws without reading


class MaskRefused(ValueError):
    """The mask cannot be drawn on the first cube: why, in one line (the file's name first)."""


def runs(a: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The runs of True along each row of a 2-D boolean array: (row, start, end) per run, end exclusive. One flat
    search for the changes along the rows, the outside False at both ends, so starts and ends alternate in each row
    (np.nonzero on the 2-D array, once for the starts and once for the ends, took 25 ms for a 2k mask against 2)."""
    rows, n = a.shape
    pad = np.zeros((rows, n + 1), bool)
    pad[:, :-1] = a
    d = np.empty((rows, n + 1), bool)                   # a change between x - 1 and x; at x = 0, against the outside
    d[:, 0] = pad[:, 0]
    np.not_equal(pad[:, 1:], pad[:, :-1], out=d[:, 1:])
    r, c = np.divmod(np.flatnonzero(d), n + 1)
    return r[0::2], c[0::2], c[1::2]


def outline(inside: np.ndarray) -> np.ndarray:
    """The edges round the True pixels of a (ny, nx) array, as (n, 2, 2) segments [[x0, y0], [x1, y1]] in pixel-edge
    coordinates: an edge wherever a pixel and its neighbour (or the outside) differ, straight runs as one segment."""
    m = np.asarray(inside, bool)
    ny, nx = m.shape
    p = np.zeros((ny + 2, nx + 2), bool)
    p[1:-1, 1:-1] = m
    horiz = p[1:, 1:-1] != p[:-1, 1:-1]                 # (ny + 1, nx): the edge at y = i over x .. x + 1
    vert = p[1:-1, 1:] != p[1:-1, :-1]                  # (ny, nx + 1): the edge at x = j over y .. y + 1
    hy, hx0, hx1 = runs(horiz)
    vx, vy0, vy1 = runs(vert.T)
    seg = np.empty((len(hy) + len(vx), 2, 2), np.float64)
    n = len(hy)
    seg[:n, 0, 0], seg[:n, 0, 1], seg[:n, 1, 0], seg[:n, 1, 1] = hx0, hy, hx1, hy
    seg[n:, 0, 0], seg[n:, 0, 1], seg[n:, 1, 0], seg[n:, 1, 1] = vx, vy0, vx, vy1
    return seg


class Mask:
    def __init__(self, path, reader: FrameReader, axis: int | None, t: np.ndarray, how: str):
        """Mask.open makes it. axis: the leading axis its frames run along (None: one frame); t: its frame at each
        of the first cube's t; how: how its frames were matched, for the start-up's line."""
        self.path, self.reader, self.axis, self.how = str(path), reader, axis, how
        self.t = t
        self.n = int(reader.shape[axis]) if axis is not None else 1
        self._kept: OrderedDict[int, np.ndarray] = OrderedDict()
        self._lock = threading.Lock()

    @classmethod
    def open(cls, path, main) -> "Mask":
        """The mask at path over main (a Dataset or a link.CubeInfo); MaskRefused when it cannot be read as one, is
        on another grid, or has neither one frame nor one per time of main."""
        name, lead = os.path.basename(str(path)), os.path.basename(str(main.path))
        try:
            kind = detect(path)
            layout = fits_layout(path) if kind == "fits" else lp_single_layout(path)
        except (OSError, ValueError) as e:
            raise MaskRefused(f"{name}: cannot be read as a mask ({e})") from None
        ny, nx = (int(n) for n in layout.shape[-2:])
        grid = other_grid(ny, nx, main)
        if grid:
            raise MaskRefused(f"{name}: {grid}; a mask is drawn on the first cube's pixels only")
        lead_axes = [i for i, n in enumerate(layout.shape[:-2]) if n > 1]
        if len(lead_axes) > 1:
            raise MaskRefused(f"{name}: {'x'.join(str(n) for n in layout.shape)} values; a mask is one frame (y, x) "
                              f"or one per time (t, y, x)")
        axis = lead_axes[0] if lead_axes else None
        n = int(layout.shape[axis]) if axis is not None else 1
        nt = main.roles.nt if main.roles.t is not None else 1
        fr = frames(getattr(main, "axes", None), None, nt, n, lead)     # the mask's own times are not read
        if fr.t is None:
            raise MaskRefused(f"{name}: {n} frames against {nt} times of {lead}; a mask has one frame, shown at every "
                              f"t, or one per time")
        how = "one frame: shown at every t" if n == 1 else f"its {n} frames are the {nt} times of {lead}"
        return cls(path, FrameReader(layout, chunks=1), axis, np.asarray(fr.t, int), how)

    def frame_at(self, t: int) -> int:
        """The mask's frame shown at the first cube's t: its frame t, or its only one (crispex.pro:21106-21110)."""
        return int(self.t[int(t)])

    def inside(self, k: int) -> np.ndarray:
        """Where frame k of the mask is set, (ny, nx) bool."""
        idx = [0] * (len(self.reader.shape) - 2)
        if self.axis is not None:
            idx[self.axis] = int(k)
        with np.errstate(invalid="ignore"):
            return self.reader.read(tuple(idx)) >= LEVEL

    def outline(self, t: int) -> np.ndarray:
        """The outline of the mask's frame at the first cube's t (outline()), kept for the last KEPT frames."""
        k = self.frame_at(t)
        with self._lock:
            seg = self._kept.get(k)
            if seg is not None:
                self._kept.move_to_end(k)
                return seg
        seg = outline(self.inside(k))
        with self._lock:
            self._kept[k] = seg
            while len(self._kept) > KEPT:
                self._kept.popitem(last=False)
        return seg

    def describe(self) -> str:
        return f"mask {os.path.basename(self.path)}: {self.how}"

    def close(self) -> None:
        self.reader.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

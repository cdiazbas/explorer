"""Per-pixel files: everything at one pixel (all Stokes, all t, all lambda) in one contiguous read.

Two layouts, both written by SSTRED next to the image cube:
  _sp.fits           FITS, numpy (y, x, s, t, lambda), same dtype and units as the image cube
  _sp.icube/.fcube   LP cube [nl, nt, npix * ns], pixel-major, Stokes fastest; integer counts are converted to
                     physical units with a scale and zero fitted against the image cube (calibrate)
A read takes the aligned strip of `strip` pixels around the one asked for, and keeps them in a small LRU: on
StorNext a strip of up to 64 pixels costs about the same as one pixel (docs/measured.md), so the pixels around
the cursor come with it.
"""
import os
import threading
from collections import OrderedDict

import numpy as np

from ..obs import span
from .formats import Layout, fits_layout
from .io import FrameReader, ShortRead


class PixelReader:
    """Base: block(y, x) -> (s, t, l) float32 through a strip-filled LRU; subclasses implement strip_read."""

    kind = "per-pixel"

    def __init__(self, layout: Layout, strip: int = 16, max_bytes: int = 64 << 20):
        self.layout = layout
        self.ny, self.nx, self.ns, self.nt, self.nl = layout.shape
        self.pix = self.ns * self.nt * self.nl * layout.dtype.itemsize
        self.strip, self.max_bytes = max(1, int(strip)), int(max_bytes)
        self._lru: OrderedDict = OrderedDict()
        self._bytes = 0
        self._lock = threading.Lock()
        self.fd = os.open(layout.path, os.O_RDONLY)
        self.scale, self.zero = np.float32(1.0), np.float32(0.0)

    # ---- reads
    def _read(self, y: int, x0: int, k: int) -> np.ndarray:
        """Raw values of k neighbouring pixels of row y, (k, ns, nt, nl), as stored."""
        if not (0 <= y < self.ny and 0 <= x0 and k >= 1 and x0 + k <= self.nx):
            raise IndexError(f"strip ({y}, {x0}..{x0 + k}) outside {self.ny}x{self.nx}")
        n = k * self.pix
        raw = os.pread(self.fd, n, self.layout.offset + (y * self.nx + x0) * self.pix)
        if len(raw) != n:
            raise ShortRead(f"read {len(raw)} of {n} bytes for strip ({y}, {x0}) in {self.layout.path}")
        return np.frombuffer(raw, self.layout.dtype).reshape(k, self.ns, self.nt, self.nl)

    def strip_read(self, y: int, x0: int, k: int) -> np.ndarray:
        """(k, ns, nt, nl) float32 in physical units, k neighbouring pixels of row y."""
        raise NotImplementedError

    def block(self, y: int, x: int) -> np.ndarray:
        """(s, t, l) float32 at pixel (y, x); on a miss the aligned strip around it is read and cached."""
        key = (int(y), int(x))
        with self._lock:
            b = self._lru.get(key)
            if b is not None:
                self._lru.move_to_end(key)
                return b
        x0 = key[1] // self.strip * self.strip
        k = min(self.strip, self.nx - x0)
        with span("data.pixel.strip"):
            blocks = self.strip_read(key[0], x0, k)
        with self._lock:
            for i in range(k):
                if (key[0], x0 + i) not in self._lru:
                    self._lru[(key[0], x0 + i)] = blocks[i]
                    self._bytes += blocks[i].nbytes
            self._trim()
            return self._lru.get(key, blocks[key[1] - x0])

    # ---- memory (the budget comes from the memory guard)
    def nbytes(self) -> int:
        return self._bytes

    def set_budget(self, max_bytes: int) -> None:
        with self._lock:
            self.max_bytes = int(max_bytes)
            self._trim()

    def _trim(self) -> None:
        while self._bytes > self.max_bytes and self._lru:
            self._bytes -= self._lru.popitem(last=False)[1].nbytes

    def close(self) -> None:
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1
        with self._lock:
            self._lru.clear()
            self._bytes = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class SpFits(PixelReader):
    kind = "sp.fits"

    def __init__(self, path, shape_stl=None, **kw):
        lay = fits_layout(path)
        if len(lay.shape) != 5:
            raise ValueError(f"{path}: a per-pixel FITS file has 5 axes (y, x, s, t, lambda), not {lay.shape}")
        super().__init__(lay, **kw)
        if shape_stl is not None and (self.ns, self.nt, self.nl) != tuple(shape_stl):
            raise ValueError(f"{path}: (s, t, l) = {(self.ns, self.nt, self.nl)} does not match the image cube "
                             f"{tuple(shape_stl)}")

    def strip_read(self, y, x0, k):
        raw = self._read(y, x0, k)
        out = raw.astype(np.float32)
        lay = self.layout
        if lay.scaled:
            out = out * np.float32(lay.scale) + np.float32(lay.zero)
        if lay.blank is not None:
            out[raw == lay.blank] = np.nan
        return out


class SpLP(PixelReader):
    """_sp.icube / _sp.fcube. Integer counts become physical values after calibrate(); until then scale 1, zero 0."""

    kind = "sp.icube"

    def __init__(self, layout: Layout, shape_stl=None, **kw):
        super().__init__(layout, **kw)
        if shape_stl is not None and (self.ns, self.nt, self.nl) != tuple(shape_stl):
            raise ValueError(f"{layout.path}: (s, t, l) = {(self.ns, self.nt, self.nl)} does not match the image "
                             f"cube {tuple(shape_stl)}")
        if layout.dtype.kind == "f":
            self.kind = "sp.fcube"

    def calibrate(self, frames: FrameReader, pixels=None) -> dict:
        """Fit physical = scale * counts + zero on the lambda-t of one pixel (Stokes I) against the image cube, as
        the prototype does at the image centre (app/sources.py SpLP.calibrate); zero counts are ignored. When the
        centre holds no data (padding), further pixels are tried, so a padded centre cannot leave the scale at 1.
        Raises if no pixel has at least 4 valid samples."""
        if len(frames.shape) != 5:
            raise ValueError("calibration needs an image cube with (t, s, lambda) leading axes")
        ny, nx = frames.ny, frames.nx
        tries = pixels or [(ny // 2, nx // 2)] + [(int(ny * fy), int(nx * fx)) for fy in (0.25, 0.5, 0.75)
                                                 for fx in (0.25, 0.5, 0.75) if (fy, fx) != (0.5, 0.5)]
        for y, x in tries:
            counts = self._read(y, x, 1)[0, 0].ravel().astype(np.float64)
            phys = frames.series(y, x, (0, 0, 0), [0, 2]).ravel().astype(np.float64)
            ok = np.isfinite(phys) & (counts != 0)
            if ok.sum() > 3:
                scale, zero = np.polyfit(counts[ok], phys[ok], 1)
                resid = phys[ok] - (scale * counts[ok] + zero)
                self.scale, self.zero = np.float32(scale), np.float32(zero)
                with self._lock:
                    self._lru.clear()
                    self._bytes = 0
                return dict(scale=float(scale), zero=float(zero), max_resid=float(np.abs(resid).max()),
                            pixel=(y, x))
        raise ValueError(f"{self.layout.path}: no pixel with data to calibrate against the image cube")

    def strip_read(self, y, x0, k):
        return self._read(y, x0, k).astype(np.float32) * self.scale + self.zero


def lp_pixel_layout(sp_path, ny: int, nx: int) -> Layout:
    """Layout of an LP per-pixel file for an image cube of ny x nx pixels (its header alone does not say)."""
    from .formats import lp_header
    from .formats.lp import HEADER_BYTES

    h = lp_header(sp_path)
    if h.nt != ny * nx * h.ns:
        raise ValueError(f"{sp_path}: {h.nt} pixel-Stokes do not match an image of {ny}x{nx} with {h.ns} Stokes")
    return Layout(path=str(sp_path), kind="lp", offset=HEADER_BYTES, shape=(ny, nx, h.ns, h.ny, h.nx),
                  dtype=h.dtype, axes=("HPLT", "HPLN", "STOKES", "UTC", "WAVE"))


def open_pixel(im_path, frames: FrameReader, strip: int = 16, max_bytes: int = 64 << 20,
               sp_path=None) -> PixelReader | None:
    """The per-pixel reader for an image cube: the file given, or the best companion next to it (_sp.fits, then
    _sp.icube, then _sp.fcube), checked against the cube's (s, t, lambda); None if there is none. Integer LP files
    are calibrated against the cube (frames) before they are returned."""
    from .formats import companions, detect

    lead = frames.shape[:-2]
    stl = (lead[1], lead[0], lead[2]) if len(lead) == 3 else None
    for p in [sp_path] if sp_path else companions(im_path):
        if detect(p) == "fits":
            return SpFits(p, stl, strip=strip, max_bytes=max_bytes)
        r = SpLP(lp_pixel_layout(p, frames.ny, frames.nx), stl, strip=strip, max_bytes=max_bytes)
        if r.layout.dtype.kind in "iu":
            r.calibrate(frames)
        return r
    return None

"""Per-pixel files: everything at one pixel (all Stokes, all t, all lambda) in one contiguous read.

Two layouts, both written by SSTRED next to the image cube:
  _sp.fits           FITS, numpy (y, x, s, t, lambda), same dtype and units as the image cube
  _sp.icube/.fcube   LP cube [nl, nt, npix * ns], pixel-major, Stokes fastest; integer counts are converted to
                     physical units with a scale and zero fitted against the image cube (calibrate)
A read takes the aligned strip of `strip` pixels around the one asked for, and keeps them in a small LRU: on
StorNext a strip of up to 64 pixels costs about the same as one pixel, so the pixels around
the cursor come with it.
A block of 4 Stokes leaves with the negative-I rule applied (masking.py): every Stokes NaN where I is negative.
"""
import os
import threading
from collections import OrderedDict
from dataclasses import replace

import numpy as np

from ..obs import span
from . import masking
from .formats import Layout, fits_layout
from .io import Closing, FrameReader, ShortRead


class PixelReader(Closing):
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
        self.calibration: dict | None = None            # SpLP.calibrate's result, once calibrated

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
        """(k, ns, nt, nl) float32 in physical units, k neighbouring pixels of row y; with 4 Stokes, NaN at every
        Stokes where I is negative."""
        raise NotImplementedError

    def _masked(self, out: np.ndarray) -> np.ndarray:
        return masking.mask_along(out, 1) if self.ns == masking.STOKES else out

    def peek(self, y: int, x: int):
        """The block at (y, x) if it is cached (marked as just used), else None; never reads."""
        key = (int(y), int(x))
        with self._lock:
            b = self._lru.get(key)
            if b is not None:
                self._lru.move_to_end(key)
            return b

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
        lay = self.layout
        self._conv = (np.float32(lay.scale), np.float32(lay.zero)) if lay.scaled else None
        self._blank, self._dtype, self._offset = lay.blank, lay.dtype, lay.offset

    def strip_read(self, y, x0, k):
        # _read inlined and the conversion decided once: a slit issues one call per run of pixels, hundreds from
        # 64 threads under the GIL, and the extra call and lookups cost 0.5 us each (slab 41.07 -> 40.67 ms warm)
        if not (0 <= y < self.ny and 0 <= x0 and k >= 1 and x0 + k <= self.nx):
            raise IndexError(f"strip ({y}, {x0}..{x0 + k}) outside {self.ny}x{self.nx}")
        n = k * self.pix
        raw = os.pread(self.fd, n, self._offset + (y * self.nx + x0) * self.pix)
        if len(raw) != n:
            raise ShortRead(f"read {len(raw)} of {n} bytes for strip ({y}, {x0}) in {self.layout.path}")
        a = np.frombuffer(raw, self._dtype)
        out = a.astype(np.float32)
        if self._conv is not None:
            out = out * self._conv[0] + self._conv[1]
        if self._blank is not None:
            out[a == self._blank] = np.nan
        return self._masked(out.reshape(k, self.ns, self.nt, self.nl))


class SpLP(PixelReader):
    """_sp.icube / _sp.fcube. Integer counts become physical values after calibrate(); until then the layout's scale
    (that of the IDL save file beside the cube, else 1). Its blank value is NaN."""

    kind = "sp.icube"

    def __init__(self, layout: Layout, shape_stl=None, **kw):
        super().__init__(layout, **kw)
        self.scale = np.float32(layout.scale)
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
                self.calibration = dict(scale=float(scale), zero=float(zero),
                                        max_resid=float(np.abs(resid).max()), pixel=(y, x))
                return self.calibration
        raise ValueError(f"{self.layout.path}: no pixel with data to calibrate against the image cube")

    def strip_read(self, y, x0, k):
        raw = self._read(y, x0, k)
        out = raw.astype(np.float32) * self.scale + self.zero
        if self.layout.blank is not None:
            out[raw == raw.dtype.type(self.layout.blank)] = np.nan
        return self._masked(out)


def calibrate_frames(frames: FrameReader, sp: PixelReader, pixels=None) -> dict:
    """physical = scale * counts + zero for integer LP frames read beside a per-pixel file in physical units (a FITS
    one given by hand, with no IDL save file to say it), fitted on Stokes I's lambda-t at one pixel as
    SpLP.calibrate fits the other way round; and blank, the one count found where the per-pixel file has NaN
    (SSTRED's padding, its nan_rplcmnt), looked for at that pixel and at the image's corners; None when there is
    none or those counts differ. Raises if no pixel has at least 4 samples with data."""
    if len(frames.shape) != 5:
        raise ValueError("calibration needs an image cube with (t, s, lambda) leading axes")
    ny, nx = frames.ny, frames.nx
    tries = pixels or [(ny // 2, nx // 2)] + [(int(ny * fy), int(nx * fx)) for fy in (0.25, 0.5, 0.75)
                                             for fx in (0.25, 0.5, 0.75) if (fy, fx) != (0.5, 0.5)]
    padded: set[float] = set()

    def look(y, x):
        counts = np.asarray(frames.series(y, x, (0, 0, 0), [0, 2]), np.float64).ravel()
        phys = np.asarray(sp.block(y, x)[0], np.float64).ravel()
        padded.update(np.unique(counts[np.isnan(phys)]).tolist())
        return counts, phys

    fit = None
    for y, x in tries:
        counts, phys = look(y, x)
        ok = np.isfinite(phys)
        if ok.sum() > 3:
            scale, zero = np.polyfit(counts[ok], phys[ok], 1)
            resid = phys[ok] - (scale * counts[ok] + zero)
            fit = dict(scale=float(scale), zero=float(zero), max_resid=float(np.abs(resid).max()), pixel=(y, x))
            break
    if fit is None:
        raise ValueError(f"{frames.layout.path}: no pixel with data to calibrate against {sp.layout.path}")
    for y, x in ((0, 0), (ny - 1, nx - 1)):
        look(y, x)
    fit["blank"] = int(padded.pop()) if len(padded) == 1 else None
    return fit


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
    """The per-pixel reader for an image cube: the file given, or the best companion next to it (formats.companions:
    the image cube's own format first), checked against the cube's (s, t, lambda); None if there is none. Integer LP
    files are calibrated against the cube (frames) before they are returned."""
    from .formats import companions, detect

    lead = frames.shape[:-2]
    stl = (lead[1], lead[0], lead[2]) if len(lead) == 3 else None
    for p in [sp_path] if sp_path else companions(im_path):
        if detect(p) == "fits":
            return SpFits(p, stl, strip=strip, max_bytes=max_bytes)
        lay = lp_pixel_layout(p, frames.ny, frames.nx)
        if frames.layout.kind == "lp":                  # one IDL save file says what both files' values mean
            lay = replace(lay, scale=frames.layout.scale, blank=frames.layout.blank)
        r = SpLP(lay, stl, strip=strip, max_bytes=max_bytes)
        if r.layout.dtype.kind in "iu":
            r.calibrate(frames)
        return r
    return None

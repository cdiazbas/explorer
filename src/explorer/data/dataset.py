"""One cube, as the rest of the app sees it: its axes, and its images, pixel blocks and slices along slits as
futures. Assembled as the prototype's startup.open_cube and Viewer assemble their pieces: the storage probe
decides strips, read-ahead and thread counts; the memory guard the caches' budget; a broken per-pixel file is
ignored with a warning and never stops a cube from opening.

Which thread does what (explorer.data.executors):
- images: missing frames on a small pool of their own (the probe's readers), each read in chunks on the I/O pool,
  so a thread waiting for its chunks never waits on the pool it is part of; frames in the cache come back as
  completed futures, with no thread hop;
- series without a per-pixel file: the numba thread (one parallel numba region at a time), a whole row at a time on
  network storage (rowbands.py), so the pixels along the cursor's row come from memory;
- per-pixel blocks: the I/O pool; slabs along a slit: a pool of the probe's gather threads, kept open (starting
  64 threads per slit cost 10-16 % of a warm slab, docs/measured.md).
Latest-wins (Executors.submit_latest) is for the caller to use: the Dataset serves every request it gets.
"""
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import replace

import numpy as np

from ..obs import get_logger, span
from . import axes as _axes
from . import formats
from .cache import FrameCache
from .executors import Executors
from .io import FrameReader
from .pixel import PixelReader, SpFits, calibrate_frames, open_pixel
from .policy import Budgets, MemoryGuard, StorageProbe, plan_budgets
from .rowbands import RowBands
from .slits import read_slit_bands, read_slit_blocks, read_slit_slab, slit_pixels

log = get_logger("data")

IO_THREADS = 16             # the prototype's Cube pool: frame chunks and frames read ahead
SLAB_THREADS = 64           # slabs along a slit: measured with 64 Python threads (E1.9), not beyond


def _done(value) -> Future:
    f: Future = Future()
    f.set_result(value)
    return f


class Dataset:
    def __init__(self, path, *, sp=None, no_sp=False, probe=None, guard=None, axes=None):
        """Open the cube at path; sp: a per-pixel file to use instead of the companions next to it; no_sp: none;
        axes: what the leading axes are when the header does not say it right (--axes, axes.roles), e.g. "s,l".
        probe and guard: given instead of measured (tests, or a second cube on the same storage)."""
        self.path = str(path)
        self.layout = formats.open_layout(path)
        self.executors: Executors | None = None
        self._io = ThreadPoolExecutor(IO_THREADS, thread_name_prefix="io")
        self.frames = FrameReader(self.layout, pool=self._io)
        try:
            self.shape = self.layout.shape
            self.ny, self.nx = self.frames.ny, self.frames.nx
            self.roles = _axes.roles(self.layout.axes, self.shape, axes)
            self.axes = _axes.from_fits(path) if self.layout.kind == "fits" else _axes.from_lp(path, self.roles)
            with span("data.open.probe"):
                self.probe = probe if probe is not None else StorageProbe(self.frames)
            self.guard = guard if guard is not None else MemoryGuard()
            self.frames.gather_threads = self.probe.gather_threads
            self.executors = Executors(gather_threads=self.probe.gather_threads, io_threads=1)
            self._images = ThreadPoolExecutor(max(1, self.probe.readers), thread_name_prefix="images")
            self._slab_pool: ThreadPoolExecutor | None = None
            self.budgets: Budgets = self._plan()
            self.cache = FrameCache(self.frames, self.budgets.images)
            self.pixel: PixelReader | None = None
            self.calibration = None
            self.frame_calibration: dict | None = None  # integer LP frames fitted to a FITS per-pixel file
            if not no_sp:
                self._open_pixel(sp)
            # without a per-pixel file, series come a row at a time on network storage (rowbands.py)
            self.rowbands: RowBands | None = (RowBands(self.frames, max_bytes=self.budgets.pixel)
                                           if self.pixel is None and getattr(self.probe, "network", False) else None)
        except BaseException:
            self.close()
            raise

    @classmethod
    def open(cls, path, sp=None, **kw) -> "Dataset":
        return cls(path, sp=sp, **kw)

    def _open_pixel(self, sp) -> None:
        try:
            self.pixel = open_pixel(self.path, self.frames, strip=self.probe.strip, max_bytes=self.budgets.pixel,
                                    sp_path=sp)
        except Exception as e:                          # a per-pixel file that cannot be used: the cube alone
            log.warning("per-pixel file ignored for %s: %s: %s", self.path, type(e).__name__, e)
            self.pixel = None
            return
        if self.pixel is not None:
            self.calibration = getattr(self.pixel, "calibration", None)
            log.info("per-pixel file %s (%s)", self.pixel.layout.path, self.pixel.kind)
        lay = self.layout
        if isinstance(self.pixel, SpFits) and lay.kind == "lp" and lay.dtype.kind in "iu" and not lay.scaled:
            self._calibrate_frames()

    def _calibrate_frames(self) -> None:
        """Integer LP frames in counts beside a FITS per-pixel file in physical units (no IDL save file says what
        the counts are): the frames take the file's units, so the image and the spectra agree. Before any frame
        is read into the cache: every read converts through the frames' layout."""
        assert self.pixel is not None
        try:
            cal = calibrate_frames(self.frames, self.pixel)
        except (ValueError, OSError) as e:
            log.warning("%s: frames in counts, %s in physical units: not calibrated: %s", self.path,
                        self.pixel.layout.path, e)
            return
        self.layout = replace(self.layout, scale=cal["scale"], zero=cal["zero"], blank=cal["blank"])
        self.frames.layout = self.layout
        self.frame_calibration = cal
        log.info("frames calibrated against %s: %s", self.pixel.layout.path, cal)

    # ---------------------------------------------------------------- memory
    def _plan(self) -> Budgets:
        return plan_budgets(self.guard.budget, self.guard.room(), self.frames.ny * self.frames.nx * 4,
                            self.roles.nt, self.probe.read_ahead)

    def update_memory(self) -> Budgets:
        """Re-read the machine's memory and re-split the budget between images and per-pixel blocks; about once a
        second (the prototype's Viewer._memory)."""
        self.guard.update()
        self.budgets = self._plan()
        self.cache.set_budget(self.budgets.images)
        if self.pixel is not None:
            self.pixel.set_budget(self.budgets.pixel)
        if self.rowbands is not None:
            self.rowbands.set_budget(self.budgets.pixel)
        return self.budgets

    def nbytes(self) -> int:
        return (self.cache.nbytes() + (self.pixel.nbytes() if self.pixel is not None else 0)
                + (self.rowbands.nbytes() if self.rowbands is not None else 0))

    # ---------------------------------------------------------------- reads
    def image(self, idx) -> Future:
        """The frame at idx (native float32, physical units, (ny, nx)); completed at once when it is cached."""
        idx = tuple(int(i) for i in idx)
        hit = self.cache.peek(idx)
        if hit is not None:
            return _done(hit)
        return self._images.submit(self.cache.get, idx)

    def prefetch(self, idx) -> Future | None:
        """Read the frame at idx ahead, in the background: the read's future, the one in flight if any (None when
        cached or outside the cube)."""
        return self.cache.prefetch(idx)

    def pixel_block(self, y: int, x: int) -> Future:
        """(s, t, lambda) float32 at pixel (y, x) from the per-pixel file (one read of the strip around it, or its
        cache, then completed at once). Only with a per-pixel file: without one use series()."""
        if self.pixel is None:
            raise LookupError(f"{self.path}: no per-pixel file; use series()")
        hit = self.pixel.peek(y, x)
        if hit is not None:
            return _done(hit)
        return self._io.submit(self.pixel.block, int(y), int(x))

    def series(self, y: int, x: int, idx, free_axes) -> Future:
        """Values at (y, x) along the leading axes in free_axes, the others fixed at idx (FrameReader.series), on
        the numba thread; from the row blocks in memory, completed at once, when they hold it."""
        assert self.executors is not None
        if self.rowbands is not None:
            hit = self.rowbands.peek(y, x, idx, free_axes)
            if hit is not None:
                return _done(hit)
            return self.executors.numba.submit(self.rowbands.series, int(y), int(x), tuple(idx), list(free_axes))
        return self.executors.numba.submit(self.frames.series, int(y), int(x), tuple(idx), list(free_axes))

    def peek_series(self, y: int, x: int, idx, free_axes):
        """The series from memory (the row blocks), or None: never reads, never waits. With a per-pixel file use
        peek_block."""
        return self.rowbands.peek(y, x, idx, free_axes) if self.rowbands is not None else None

    def read_series(self, y: int, x: int, idx, free_axes):
        """The series, read now on the calling thread, which must be the one that runs parallel numba (as
        Executors.submit_latest does); from the row blocks when they hold it."""
        if self.rowbands is not None:
            return self.rowbands.series(int(y), int(x), tuple(idx), list(free_axes))
        return self.frames.series(int(y), int(x), tuple(idx), list(free_axes))

    def peek_block(self, y: int, x: int):
        """The (s, t, lambda) block at (y, x) from the per-pixel file's cache, or None; never reads."""
        return self.pixel.peek(y, x) if self.pixel is not None else None

    def slit(self, path_xy):
        """(iy, ix): the pixels under a slit path (view coordinates, pixel centres at .5)."""
        return slit_pixels(np.asarray(path_xy, np.float64), self.ny, self.nx)

    def _slab_threads(self) -> ThreadPoolExecutor:
        if self._slab_pool is None:
            self._slab_pool = ThreadPoolExecutor(min(SLAB_THREADS, self.probe.gather_threads),
                                                 thread_name_prefix="slab")
        return self._slab_pool

    def slab(self, iy, ix) -> Future:
        """[npath, s, t, lambda] float32 along a slit from the per-pixel file."""
        if self.pixel is None:
            raise LookupError(f"{self.path}: no per-pixel file; use bands()")
        pool, sp = self._slab_threads(), self.pixel
        return self._io.submit(lambda: read_slit_slab(sp, iy, ix, pool=pool)[0])

    def slit_blocks(self, pixels) -> Future:
        """({(y, x): (s, t, lambda) float32}, number of reads) for the given pixels from the per-pixel file: one read
        per run of neighbouring pixels in a row, all on the slab pool. Not through the per-pixel cache of the cursor's
        blocks: a slit's pixels would push the cursor's strips out of it."""
        if self.pixel is None:
            raise LookupError(f"{self.path}: no per-pixel file; use bands()")
        pool, sp, pix = self._slab_threads(), self.pixel, [(int(y), int(x)) for y, x in pixels]
        return self._io.submit(lambda: read_slit_blocks(sp, pix, pool=pool))

    def bands(self, idxs, iy, ix, threads: int | None = None) -> Future:
        """(len(idxs), npath) float32 along a slit from whole frames, one read of its rows per frame."""
        assert self.executors is not None
        return self.executors.background.submit(self.read_bands, idxs, iy, ix, threads)

    def read_bands(self, idxs, iy, ix, threads: int | None = None):
        """bands(), read now on the calling thread (a worker of the caller's: never the UI's)."""
        n = min(16, self.probe.gather_threads) if threads is None else threads
        return read_slit_bands(self.frames, idxs, iy, ix, n)

    # ---------------------------------------------------------------- description and closing
    def describe(self) -> str:
        sp = (f", per-pixel {self.pixel.kind}" if self.pixel is not None else ", no per-pixel file"
              + (f" (series a block of {self.rowbands.rows} row(s) at a time)" if self.rowbands is not None else ""))
        return (f"{self.layout.kind} {tuple(self.shape)} {self.layout.dtype}{sp}; {self.probe.describe()}; "
                f"{self.guard.describe()}")

    def close(self) -> None:
        """Stop the pools (reads in flight finish, queued ones are dropped), then close the files."""
        for name in ("_images", "_slab_pool", "_io"):
            p = getattr(self, name, None)
            if p is not None:
                p.shutdown(wait=True, cancel_futures=True)
                setattr(self, name, None)
        if self.executors is not None:
            self.executors.close()
            self.executors = None
        sp = getattr(self, "pixel", None)
        if sp is not None:
            sp.close()
            self.pixel = None
        if getattr(self, "frames", None) is not None:
            self.frames.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

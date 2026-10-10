"""What the slit panel reads, and what of it reaches the screen (ROADMAP E7.3).

From the prototype's app/viewer.py, its variant D (its audit's F73, F74): _slitd_preview (1664), _slitc_kick and
_slitc_job (1692-1707), _slitc_slices (1709), _slit_changed (1745), _slit_refresh (1788), _slit_band_job (1842),
_slit_ready (1852), _slit_paint (1877).

The slit shown is the one being drawn once it has two points (the points clicked and the pointer's pixel,
ViewState.draft), else the finished one (ViewState.path); its pixels are the path sampled every pixel, each sample's
nearest pixel (data.slits). Two slices along it share the position axis: the time slice (t x position, at this Stokes
and lambda) and the spectral slice (lambda x position, at this Stokes and t). They are the slices of the cube the slit
was drawn on (ViewState.path_cube, draft_cube): with linked cubes (ROADMAP E8.1) on the main cube's grid, the same
pixels of that member, at its own t, lambda and Stokes (Session.member_state); a map without lambda gives a spectral
slice of one row. Another cube is another slit: its results for the one before are dropped.

With a per-pixel file:
- the (s, t, lambda) block of each pixel along the slit, read in runs of neighbouring pixels in a row on the slab
  pool (Dataset.slit_blocks), and kept (Dataset.slit_cache, counted in the Dataset's memory and bounded by its
  budget): a slit moved, redrawn or still being drawn reads only its new pixels, and a change of t, lambda or Stokes
  reads nothing. One read at a time; the latest slit's missing pixels are read next.
  The prototype measured 5-21 ms per read and 112-120 updates in 1.5-1.7 s of pointer motion this way (F73, 6173 on
  bellatrix);
- the slices come from the blocks kept, NaN where a pixel's block has not come yet: they follow the pointer while
  the rest is read.
Without one:
- the rows the slit spans, one read per frame (Dataset.read_bands): the time slice for each (Stokes, lambda), the
  spectral slice for each (Stokes, t), kept per slit (BANDS of them); the spectral slice is not read while playing
  (CRISPEX does the same) and comes when playback stops. While the slit is drawn the reads wait for the pointer to
  rest REST_S: a read of the rows took 0.15-0.8 s (F71).

Threads: the blocks are read on the slab pool; the slices and their levels are made on the slit thread
(Executors.slit), where the reads without a per-pixel file run too. Latest wins: a job is skipped if a newer request
came before it started, and a result is shown unless a newer one already is. A result made for another slit is
dropped, except one for an earlier stage of the slit being drawn while it is still drawn: the pointer gives a new
slit every pixel, and each result came after the next one (6173 on bellatrix, 60 moves 16 ms apart: 31 of 50 shown,
the prototype's synchronous paint 75), the panels frozen as the cursor's were before ShownGate. While it is drawn,
one request per notice of the Store, that is per pass of the event loop: the moves that come within one pass give
the latest pixel's, as no paint comes between them (6173 on bellatrix, offscreen, 60 moves 16 ms apart: passes of
35-41 ms, 24 notices; the prototype handles each move inside it and gave the time slice 72-81 images, of which
24-28 were painted, explorer 37-46, bench/slit_read.py). The UI thread
computes the path's pixels (a few hundred points) and draws. Nothing is read while the panel's tab is behind
("slit" not in ViewState.panels), except the blocks of a slit just finished: its tab comes in front with it (the
shell's _slit_shown, as the prototype's _slit_changed, 1745), a notice later, and the read no longer waits for it.
"""
import time
from collections import OrderedDict

import numpy as np

from ..data.executors import Generations, ShownGate
from ..data.slits import SLIT_BLOCKS, SlitCache, frame_index, slit_path, slit_pixels
from ..obs import counter, get_logger
from .levels import panel_levels
from .state import ViewState

log = get_logger("core")

REST_S = 0.25               # without a per-pixel file, a slit being drawn is read once the pointer rests this long
BANDS = 64                  # slices kept per slit without a per-pixel file (the prototype kept every one)
DRAFTS = 64                 # stages of the slit being drawn whose late results may still be shown


class SlitReads:
    """Owned by the Scheduler, which passes on every notice of the Store (on_change) and tracks its futures."""

    def __init__(self, session, sink, track, when_read):
        """track(fut) -> fut and when_read(fut, fn): the Scheduler's, so its in_flight() covers the slit's work."""
        self.session, self.sink = session, sink
        self.cube = 0                                   # the member read: the one the slit shown was drawn on
        self.ds = session.main
        self.loop = session.store.loop
        self._track, self._when_read = track, when_read
        self.gens, self.shown = Generations(), ShownGate()
        self.pts = None                                 # the points of the slit shown, (x, y)
        self.pix: tuple[np.ndarray, np.ndarray] | None = None   # its pixels (iy, ix), one per sample
        self.path_id = 0                                # changes with the pixels: a result for another slit is dropped
        self._drafts: set[int] = set()                  # the path_ids that were stages of a slit being drawn
        # (y, x) -> (s, t, lambda) float32 with a per-pixel file: the Dataset's, counted in its memory
        self.blocks: SlitCache = self._blocks_of(self.ds)
        self._want: tuple | None = None                 # pixels whose missing blocks are read next
        self._busy = False                              # a block read in flight
        self._bands: OrderedDict = OrderedDict()        # (path_id, kind, s, u) -> (slice, levels); slit thread only
        self._made: dict = {}                           # kind -> (key, slice, levels): the last made; slit thread only
        self._rest = 0
        self._front = False
        self._closed = False
        self.reads: list[dict] = []                     # the block reads: pixels, runs, ms (benches, diagnostics)

    @staticmethod
    def _blocks_of(ds) -> SlitCache:
        cache = getattr(ds, "slit_cache", None)
        return cache if cache is not None else SlitCache(max_blocks=SLIT_BLOCKS)

    @property
    def per_pixel(self) -> bool:
        return getattr(self.ds, "pixel", None) is not None

    def close(self) -> None:
        self._closed = True
        self.gens.new("slit")                           # what is queued is skipped

    # ---------------------------------------------------------------- changes of state
    def on_change(self, st: ViewState, changed: frozenset) -> None:
        if self._closed:
            return
        front = "slit" in st.panels
        came, self._front = front and not self._front, front
        if changed & {"path", "draft", "path_cube", "draft_cube"} and self._set_path(st):
            self._rest += 1                             # a rest timer for an older slit does nothing
            if self.pix is None:
                return
            if not front:
                if self.per_pixel and not self._drawing(st):
                    self._want = self.pix               # its tab comes in front with it: the read starts a pass early
                    self._kick()
                return
            if not self.per_pixel and self._drawing(st):
                token = self._rest
                self.loop.call_later(REST_S, lambda: self._rested(token))
            else:
                self._refresh(st)
            return
        if not front:
            return
        if came or ("playing" in changed and not st.playing) or changed & ({"t", "s", "l", "own"} if self.cube
                                                                           else {"t", "s", "l"}):
            self._refresh(st)

    def _drawing(self, st: ViewState) -> bool:
        return st.draft is not None and len(st.draft) >= 2

    def _rested(self, token: int) -> None:
        if token == self._rest and not self._closed:
            self._refresh(self.session.state)

    def _set_path(self, st: ViewState) -> bool:
        """The slit shown, from the state; True when its pixels changed (the sink then has them)."""
        pts = st.draft if self._drawing(st) else st.path
        cube = (st.draft_cube if self._drawing(st) else st.path_cube) if pts is not None else self.cube
        if not self._drawing(st):
            self._drafts = set()                        # drawn or given up: no late result of its stages any more
        if pts == self.pts and cube == self.cube:
            return False
        self.pts = pts
        other = cube != self.cube
        if other:                                       # the same pixels on another cube: another slit
            self.cube, self.ds = cube, self.session.members[cube].dataset
            self.blocks, self._want = self._blocks_of(self.ds), None
            self._drafts = set()
        pix = None
        if pts is not None:
            pix = slit_pixels(slit_path(np.asarray(pts, np.float64)), self.ds.ny, self.ds.nx)
        old = self.pix
        if not other and ((pix is None and old is None) or (
                pix is not None and old is not None and len(pix[0]) == len(old[0])
                and np.array_equal(pix[0], old[0]) and np.array_equal(pix[1], old[1]))):
            return False
        self.pix = pix
        self.path_id += 1
        if pix is not None and self._drawing(st):
            self._drafts = {p for p in self._drafts if p > self.path_id - DRAFTS} | {self.path_id}
        self.gens.new("slit")                           # a job for the slit before is skipped
        self.blocks.keep(zip(pix[0].tolist(), pix[1].tolist(), strict=True) if pix is not None else ())
        self.sink.slit_path(pix)
        return True

    # ---------------------------------------------------------------- requests
    def _refresh(self, st: ViewState) -> None:
        if self.pix is None or self._closed:
            return
        if self.per_pixel:
            self._want = self.pix
            self._kick()
        self._slices(st)

    def _slices(self, st: ViewState) -> None:
        g = self.gens.new("slit")
        mine = self.session.member_state(self.cube, st)  # its t, lambda and Stokes
        args = (g, self.path_id, self.pix, mine.t, mine.s, mine.l, st.playing, self.ds, self.blocks)
        job = self._from_blocks if self.per_pixel else self._from_bands
        counter("core.slit.requests")

        def run():
            if self.gens.stale("slit", g):
                counter("core.slit.skipped_stale")
                return
            job(*args)

        def failed(f) -> None:
            if not f.cancelled() and f.exception() is not None:
                log.warning("slit slices not made: %r", f.exception())

        self._track(self.ds.executors.slit.submit(run)).add_done_callback(failed)

    # ---------------------------------------------------------------- the per-pixel file: blocks
    def _kick(self) -> None:
        """The missing blocks of the latest slit asked for, unless a read is in flight (it asks again when done)."""
        if self._busy or self._want is None or self._closed:
            return
        iy, ix = self._want
        self._want = None
        miss = self.blocks.missing(zip(iy.tolist(), ix.tolist(), strict=True))
        if not miss:
            return
        self._busy = True
        q = time.perf_counter()
        fut = self.ds.slit_blocks(miss)
        blocks = self.blocks                            # this cube's: the slit may move to another before they come

        def done(f) -> None:                            # on the thread that read them
            if not f.cancelled() and f.exception() is None:
                got, runs = f.result()
                ms = (time.perf_counter() - q) * 1e3
                blocks.add(got)                         # over its bounds, the shown slit's only (_slit_ready, 1857)
                self.reads = self.reads[-999:] + [dict(pixels=len(miss), runs=runs, ms=round(ms, 2))]
                counter("core.slit.block_reads")
            elif not f.cancelled():
                log.warning("slit: blocks along it not read: %r", f.exception())
            self.loop.post(self._blocks_in)

        self._when_read(fut, done)

    def _blocks_in(self) -> None:
        self._busy = False
        if self._closed:
            return
        st = self.session.state
        if self.pix is not None and "slit" in st.panels:
            self._slices(st)
        self._kick()

    def _from_blocks(self, g, pid, pix, t, s, l, playing, ds, blocks) -> None:  # noqa: E741
        """Both slices from the blocks kept (the prototype's _slitc_slices, 1709), on the slit thread; one made from
        the same blocks kept (SlitCache.version) for the same slit, Stokes and lambda (or t) is reused."""
        ver, got = blocks.along(zip(pix[0].tolist(), pix[1].tolist(), strict=True))
        r, n = ds.roles, len(pix[0])
        out = {}
        for kind, rows, u in (("ts", max(1, r.nt), l), ("sl", max(1, r.nl), t)):
            key = (pid, ver, s, u)
            made = self._made.get(kind)
            if made is not None and made[0] == key:
                out[kind] = made[1:]
                continue
            a = np.full((rows, n), np.nan, np.float32)
            for i, b in enumerate(got):
                if b is not None:
                    a[:, i] = b[s, :, l] if kind == "ts" else b[s, t, :]
            out[kind] = (a, panel_levels(a, symmetric=s > 0))
            self._made[kind] = (key, *out[kind])
        self.loop.post(lambda: self._show(g, pid, s, out["ts"], out["sl"]))

    # ---------------------------------------------------------------- no per-pixel file: rows per frame
    def _from_bands(self, g, pid, pix, t, s, l, playing, ds, blocks) -> None:  # noqa: E741
        """Each slice from those kept or read now (the prototype's _slit_band_job, 1842), the time slice first; the
        spectral slice not read while playing. Each is shown as it comes."""
        r = ds.roles
        nlead = len(ds.shape) - 2
        for kind, u in (("ts", l), ("sl", t)):
            key = (pid, kind, s, u)
            hit = self._bands.get(key)
            if hit is not None:
                self._bands.move_to_end(key)
            elif kind == "sl" and playing:
                continue
            else:
                if self.gens.stale("slit", g):
                    counter("core.slit.skipped_stale")
                    return
                idxs = ([frame_index(nlead, r, t=k, s=s, l=l) for k in range(max(1, r.nt))] if kind == "ts"
                        else [frame_index(nlead, r, t=t, s=s, l=k) for k in range(max(1, r.nl))])
                q = time.perf_counter()
                a = ds.read_bands(idxs, *pix)
                self.reads = self.reads[-999:] + [dict(kind=kind, frames=len(idxs),
                                                       ms=round((time.perf_counter() - q) * 1e3, 2))]
                counter("core.slit.band_reads")
                hit = (a, panel_levels(a, symmetric=s > 0))
                self._bands[key] = hit
                while len(self._bands) > BANDS:
                    self._bands.popitem(last=False)
            if kind == "ts":
                self.loop.post(lambda h=hit: self._show(g, pid, s, ts=h))
            else:
                self.loop.post(lambda h=hit: self._show(g, pid, s, sl=h))

    # ---------------------------------------------------------------- results, on the main thread
    def _show(self, g: int, pid: int, s: int, ts=None, sl=None) -> None:
        if self._closed:
            return
        if pid != self.path_id and not (pid in self._drafts and self.path_id in self._drafts):
            counter("core.slit.dropped_other_slit")
            return
        ts = ts if ts is not None and self.shown.accept("slit_ts", g) else None
        sl = sl if sl is not None and self.shown.accept("slit_sl", g) else None
        if ts is None and sl is None:
            counter("core.slit.dropped_older")
            return
        self.sink.slit(None if ts is None else ts[0], None if sl is None else sl[0], s,
                       None if ts is None else ts[1], None if sl is None else sl[1])

"""What the viewer reads after each change of state, and what of it reaches the screen.

From the prototype's Viewer.set_index, show_frame, _update_cursor, _series_job and _lt_ready. After a notice of
the Store:
- t, Stokes or lambda changed: the image at the new index, and frames ahead along the axis that moved (the
  probe's read-ahead). The cursor's panels are evaluated when that image arrives, since it tells whether the
  cursor is on padding.
- the cursor moved (or a panel was shown): the cursor's panels, at once.
What each change asks of the panels: the cursor -> spectra and lambda-t; t -> spectra (the lambda-t already holds
every t); Stokes -> lambda-t; lambda -> nothing (the markers are the UI's). Nothing is read for a hidden panel,
nor on padding (the image NaN at the cursor, or exactly 0 in Stokes I): the panels are cleared once, and after
padding the next valid pixel fills both panels whatever changed. The prototype refilled both only with a
per-pixel file; without one, a t or Stokes step back from padding left the other panel empty.

Reads without a per-pixel file: served from memory at once when the row blocks hold them (Dataset.peek_series),
else on the numba thread, the spectrum first and the lambda-t after, skipped when a newer cursor position came
before they start (the spectrum is 56 reads, the lambda-t ~2600: sent together, the spectrum waited for the
lambda-t, Mac 18-23 -> 3-5 ms, StorNext ~165 -> ~40 ms). A result is shown unless a newer one already is
(executors.ShownGate): showing only the latest request's froze the panels while the mouse moved.
Results come back from other threads through Loop.post, and the Sink is called on the main thread only.
"""
import dataclasses
import threading
from concurrent.futures import Future
from typing import Protocol

import numpy as np

from ..data.executors import Generations, ShownGate
from ..data.stats import quv_amplitude_ranges, quv_threads, sample_pixels, sample_profiles
from ..obs import counter, get_logger
from .levels import Levels, panel_levels
from .session import Session
from .state import ViewState
from .yrange import YRange

log = get_logger("core")

SAMPLE_AFTER_S = 0.3        # the y-range sample starts after the first image (it takes 0.04-0.9 s on bellatrix)


class Sink(Protocol):
    """Where results go (the UI; a recorder in tests). Called on the main thread."""

    def image(self, idx: tuple, img: np.ndarray, levels: tuple[float, float]) -> None: ...

    def spectra(self, spec: np.ndarray, pixel: tuple[int, int], t: int) -> None: ...     # (ns, nl)

    def lambda_t(self, lt: np.ndarray, pixel: tuple[int, int], s: int, levels: tuple[float, float]) -> None: ...

    def cleared(self, pixel: tuple[int, int]) -> None: ...                             # padding under the cursor

    def y_range(self, k: int, r: tuple[float, float]) -> None: ...                     # spectrum plot k's y range

    def units(self, iscale: float | None) -> None: ...                                 # I's power of ten, for titles

    def grid_image(self, s: int, idx: tuple, img: np.ndarray, levels: tuple[float, float]) -> None: ...  # 2x2 view


class Scheduler:
    def __init__(self, session: Session, sink: Sink):
        self.session, self.sink = session, sink
        self.ds = session.main
        self.loop = session.store.loop
        self.gens, self.shown = Generations(), ShownGate()
        self.img: np.ndarray | None = None              # the image on screen
        self.img_idx: tuple | None = None
        self.levels = Levels()
        r = self.ds.roles
        self.yrange = YRange(self.loop, r.ns, self._cont(), sink.y_range, sink.units,
                             self._start_quv, quv_ok=r.s is not None)
        self._sampled = False
        self.grid = False                               # the 2x2 view: every Stokes's frame at this t and lambda
        self._grid_gen = 0
        self._closed = False
        self._pending: set[str] = set()                 # cursor work waiting for the latest image
        self._cleared = False
        self._futures: set[Future] = set()
        self._flock = threading.Lock()
        self._off = session.store.subscribe(self._on_change)
        self._first_units(session.state)
        self._pending.add("cursor")                     # the first image brings the first cursor
        self._request_image(session.state)

    def _first_units(self, st: ViewState) -> None:
        """With a per-pixel file, the cursor's block read now, as the window is built (the prototype's first
        spectrum, app/viewer.py _set_spectra 1927): I's title has its power of ten from the first frame, and the axis
        does not widen once the spectrum comes. One small read (0.1 ms on a synthetic cube), then in the cache: the
        first cursor read finds it there. Without that file the first spectrum brings it, as in the prototype."""
        if getattr(self.ds, "pixel", None) is None or self.ds.roles.l is None:
            return
        try:
            blk = self.ds.pixel.block(*st.cursor)
        except Exception as e:                          # the first cursor read then reports and retries it
            log.warning("first block (%d, %d) not read: %r", *st.cursor, e)
            return
        self.yrange.first(blk[0, st.t, :])

    def close(self) -> None:
        """No more work: what is due later (the y-range sample) or still on its way is dropped."""
        self._closed = True
        self._off()

    # ---------------------------------------------------------------- bookkeeping for tests and idle checks
    def _track(self, fut: Future) -> Future:
        with self._flock:
            self._futures.add(fut)
        fut.add_done_callback(self._untrack)
        return fut

    def _untrack(self, fut: Future) -> None:
        with self._flock:
            self._futures.discard(fut)

    def in_flight(self) -> list[Future]:
        """Reads not finished yet (their results then come through the loop)."""
        with self._flock:
            return list(self._futures)

    # ---------------------------------------------------------------- changes of state
    def _on_change(self, st: ViewState, changed: frozenset) -> None:
        moved = changed & {"t", "s", "l"}
        if moved:
            self._pending |= moved | (changed & {"cursor"})
            self._request_image(st)
            if self.grid and moved & {"t", "l"}:        # a change of Stokes alone: the same frames
                self._request_grid(st)
            # on the loop's next pass, after this frame is painted: started here, the reads ahead slowed the paint
            # (step in t, real cube, bellatrix: median 17.9-19.3 ms -> 13.8-15.0, the prototype 15.8)
            self.loop.call_soon(lambda: self._prefetch(st, moved))
        elif changed & {"cursor", "panels"}:
            kinds = set(changed & {"cursor"})
            if "panels" in changed:
                kinds |= {f"show:{p}" for p in st.panels}
            self._evaluate(st, kinds)

    def _request_image(self, st: ViewState) -> None:
        g = self.gens.new("image")
        idx = self.session.index(state=st)
        fut = self.ds.image(idx)
        if fut.done():
            self._image_ready(g, idx, fut)
        else:
            self._track(fut).add_done_callback(lambda f: self.loop.post(lambda: self._image_ready(g, idx, f)))

    def _prefetch(self, st: ViewState, moved) -> None:
        if self._closed:
            return
        n_ahead = getattr(getattr(self.ds, "probe", None), "read_ahead", 0)
        for axis in moved:
            n = self.session.sizes[axis]
            # the 2x2 view shows every Stokes: their next frames along t or lambda too
            stokes = range(self.session.sizes["s"]) if self.grid and axis != "s" else (st.s,)
            for d in range(1, n_ahead + 1):
                for s in stokes:
                    ahead = dataclasses.replace(st, **{axis: (getattr(st, axis) + d) % n})
                    if axis != "s":
                        ahead = dataclasses.replace(ahead, s=s)
                    self.ds.prefetch(self.session.index(state=ahead))

    # ---------------------------------------------------------------- the 2x2 view
    def set_grid(self, on: bool) -> None:
        """The 2x2 view (I Q U V side by side, ROADMAP E5.11) on or off: on, every Stokes's frame at this t and
        lambda goes to sink.grid_image as it comes, now and at every change of t or lambda, with its own levels (Q U
        V symmetric about 0), and the next frames of all of them are read ahead. From the prototype's
        app/look_glass.py StokesGrid.refresh (278-313)."""
        self.grid = bool(on)
        self._grid_gen += 1
        if self.grid:
            self._request_grid(self.session.state)

    def _request_grid(self, st: ViewState) -> None:
        self._grid_gen += 1
        g = self._grid_gen
        for s in range(self.session.sizes["s"]):
            idx = self.session.index(state=dataclasses.replace(st, s=s))
            fut = self.ds.image(idx)
            if fut.done():
                self._grid_ready(g, s, idx, fut)
            else:
                def done(f: Future, s: int = s, idx: tuple = idx) -> None:
                    self.loop.post(lambda: self._grid_ready(g, s, idx, f))
                self._track(fut).add_done_callback(done)

    def _grid_ready(self, g: int, s: int, idx: tuple, fut: Future) -> None:
        if self._closed or fut.cancelled() or not self.grid or g != self._grid_gen:   # off, or a newer t or lambda
            return
        if fut.exception() is not None:
            log.warning("image %s not read: %r", idx, fut.exception())
            return
        img = fut.result()
        self.sink.grid_image(s, idx, img, self.levels.image(idx, s > 0, img))

    def _image_ready(self, g: int, idx: tuple, fut: Future) -> None:
        if self._closed or fut.cancelled():            # closing: nothing more to show nor to read ahead
            return
        if fut.exception() is not None:
            log.warning("image %s not read: %r", idx, fut.exception())
            counter("core.image.failed")
            return
        if self.shown.accept("image", g):
            self.img, self.img_idx = fut.result(), idx
            self._show_image()
            if not self._sampled:                        # the y-range sample, after the first image and cursor
                self._sampled = True
                self.loop.call_later(SAMPLE_AFTER_S, self._start_sample)
        if not self.gens.stale("image", g) and self._pending:
            kinds, self._pending = self._pending, set()
            self._evaluate(self.session.state, kinds)

    # ---------------------------------------------------------------- the cursor's panels
    def _evaluate(self, st: ViewState, kinds: set) -> None:
        if self.img is None:
            return
        y, x = st.cursor
        counter("core.cursor.updates")
        v0 = self.img[y, x]
        if not np.isfinite(v0) or (v0 == 0 and st.s == 0):
            counter("core.cursor.skipped_padding")
            g = self.gens.new("cursor")                 # results still in flight are now stale
            self.shown.accept("spectra", g)
            self.shown.accept("lambda_t", g)
            if not self._cleared:
                self.sink.cleared((y, x))
                self._cleared = True
            return
        refill = self._cleared
        r = self.ds.roles                               # a spectrum needs lambda; a lambda-t needs t and lambda
        want_spec = (r.l is not None and "spectra" in st.panels
                     and bool(kinds & {"cursor", "t", "show:spectra"} or refill))
        want_lt = (r.l is not None and r.t is not None and "lambda_t" in st.panels
                   and bool(kinds & {"cursor", "s", "show:lambda_t"} or refill))
        if not (want_spec or want_lt):
            if "cursor" in kinds:
                counter("core.cursor.skipped_hidden")
            return
        self._cleared = False
        g = self.gens.new("cursor")
        counter("core.cursor.reads")
        if getattr(self.ds, "pixel", None) is not None:
            self._read_block(g, st, want_spec, want_lt)
        else:
            self._read_series(g, st, want_spec, want_lt)

    def _show(self, kind: str, g: int, arr, pixel, at: int) -> None:
        if self._closed:
            return
        if self.shown.accept(kind, g):
            if kind == "lambda_t":                      # Q U V symmetric about 0
                self.sink.lambda_t(arr, pixel, at, panel_levels(arr, symmetric=at > 0))
            else:
                self.sink.spectra(self.yrange.spectrum(arr), pixel, at)

    # ---------------------------------------------------------------- the image's levels
    def _show_image(self) -> None:
        if self._closed or self.img is None or self.img_idx is None:
            return
        lim = self.levels.image(self.img_idx, self.session.state.s > 0, self.img)
        self.sink.image(self.img_idx, self.img, lim)

    def fix_levels(self, on: bool, refit: bool = False) -> None:
        """The image padlock: on fixes the levels to the image shown (refit: to it again, when already fixed); off
        lets each image have its own. The image is shown again with them."""
        if self.img is None:
            return
        sym = self.session.state.s > 0
        if not on:
            self.levels.unfix()
        elif refit or not self.levels.fixed(sym):
            self.levels.fix(self.img, sym)
        self._show_image()

    def _read_block(self, g: int, st: ViewState, want_spec: bool, want_lt: bool) -> None:
        y, x = st.cursor

        def deliver(blk):
            if want_spec:
                self._show("spectra", g, blk[:, st.t, :], (y, x), st.t)
            if want_lt:
                self._show("lambda_t", g, blk[st.s], (y, x), st.s)

        blk = self.ds.peek_block(y, x)
        if blk is not None:
            deliver(blk)
            return
        def arrived(f: Future) -> None:                  # on the main thread
            if f.cancelled():
                return
            if f.exception() is None:
                deliver(f.result())
            else:
                log.warning("block (%d, %d) not read: %r", y, x, f.exception())

        fut = self._track(self.ds.pixel_block(y, x))
        fut.add_done_callback(lambda f: self.loop.post(lambda: arrived(f)))

    def _as(self, arr, axes, want) -> np.ndarray:
        """arr, read along `axes` in the cube's order, as an array over the axes in `want` (the panels' order):
        a cube keeping lambda before t or Stokes (--axes l,t) gave lambda-t transposed and the spectra scrambled."""
        r = self.ds.roles
        size = {r.t: r.nt, r.s: r.ns, r.l: r.nl}
        a = np.asarray(arr).reshape([size[ax] for ax in axes])
        want = [ax for ax in want if ax is not None]
        return a if list(axes) == want else a.transpose([list(axes).index(ax) for ax in want])

    def _spec(self, arr, spec_axes) -> np.ndarray:
        """The spectra as (Stokes, lambda), a single Stokes as one row."""
        r = self.ds.roles
        return self._as(arr, spec_axes, (r.s, r.l)).reshape(r.ns, r.nl)

    def _read_series(self, g: int, st: ViewState, want_spec: bool, want_lt: bool) -> None:
        r, (y, x) = self.ds.roles, st.cursor
        idx = self.session.index(state=st)
        spec_axes = sorted(a for a in (r.s, r.l) if a is not None)
        lt_axes = sorted((r.t, r.l)) if r.t is not None and r.l is not None else None
        want_lt = want_lt and lt_axes is not None
        spec = self.ds.peek_series(y, x, idx, spec_axes) if want_spec else None
        lt = self.ds.peek_series(y, x, idx, lt_axes) if want_lt else None
        if spec is not None:
            self._show("spectra", g, self._spec(spec, spec_axes), (y, x), st.t)
        if lt is not None:
            self._show("lambda_t", g, self._as(lt, lt_axes, (r.t, r.l)), (y, x), st.s)
        need_spec, need_lt = want_spec and spec is None, want_lt and lt is None
        if not (need_spec or need_lt):
            return

        def job():
            if self.gens.stale("cursor", g):
                counter("core.cursor.skipped_stale")
                return
            if need_spec:
                sp = self._spec(self.ds.read_series(y, x, idx, spec_axes), spec_axes)
                self.loop.post(lambda: self._show("spectra", g, sp, (y, x), st.t))
            if need_lt and not self.gens.stale("cursor", g):
                lt_ = self._as(self.ds.read_series(y, x, idx, lt_axes), lt_axes, (r.t, r.l))
                self.loop.post(lambda: self._show("lambda_t", g, lt_, (y, x), st.s))

        def failed(f: Future) -> None:
            if not f.cancelled() and f.exception() is not None:
                log.warning("series (%d, %d) not read: %r", y, x, f.exception())

        self._track(self.ds.executors.numba.submit(job)).add_done_callback(failed)

    # ---------------------------------------------------------------- the spectra's y ranges: reads
    def _start_sample(self) -> None:
        """SAMPLE_N profiles at random valid pixels of the image shown, each at its own t (stats.sample_*), on the
        numba thread: the fixed y ranges of the padlock."""
        r = self.ds.roles
        if self._closed or self.img is None or r.l is None:
            return
        pix = sample_pixels(self.img, getattr(self.ds, "path", ""), r.nt)
        if pix is None:
            return
        ys, xs, ts = pix
        threads = getattr(getattr(self.ds, "probe", None), "gather_threads", 16)
        pixel = getattr(self.ds, "pixel", None)

        def job():
            prof = sample_profiles(ys, xs, ts, self.ds.frames, r, pixel, threads)
            self.loop.post(lambda: self.yrange.sample_ready(prof))

        self._track(self.ds.executors.numba.submit(job)).add_done_callback(self._log_failure("y-range sample"))

    def _start_quv(self) -> None:
        """Q U V's ranges from the whole frames at the t shown, on the background thread (never delaying the cursor's
        reads); asked for once, when the spectra padlock first closes."""
        r, t = self.ds.roles, self.session.state.t
        limit = getattr(getattr(self.ds, "probe", None), "gather_threads", 16)
        threads = quv_threads(self.ds.frames.frame_bytes, limit)

        def job():
            try:
                half = quv_amplitude_ranges(self.ds.frames, r, self._cont(), t, threads=threads,
                                            strips=self.ds.executors.strips)[0]
            except Exception as e:                      # the sample's ranges stay: a range, not a failure
                log.warning("Q U V ranges from whole frames failed: %r", e)
                half = None
            self.loop.post(lambda: self.yrange.quv_ready(half))

        self._track(self.ds.executors.background.submit(job))

    def _cont(self):
        """The continuum tuning, when the cube's header gives one."""
        return getattr(getattr(self.ds, "axes", None), "cont", None)

    @staticmethod
    def _log_failure(what: str):
        def done(f: Future) -> None:
            if not f.cancelled() and f.exception() is not None:
                log.warning("%s failed: %r", what, f.exception())
        return done

    # ---------------------------------------------------------------- the spectra's y ranges: the user's actions
    def set_y_fixed(self, on: bool) -> None:
        self.yrange.set_fixed(on)

    def fit_y(self) -> None:
        self.yrange.fit(force=True)

    def y_to_sample(self) -> None:
        self.yrange.to_sample()

    def reset_y(self) -> None:
        self.yrange.reset()

    def set_y_manual(self, k: int, r: tuple) -> None:
        self.yrange.manual(k, r)

    def y_auto(self, k: int) -> None:
        self.yrange.auto(k)

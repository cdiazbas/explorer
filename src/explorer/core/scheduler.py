"""What the viewer reads after each change of state, and what of it reaches the screen.

From the prototype's Viewer.set_index, show_frame, _update_cursor, _series_job and _lt_ready. After a notice of
the Store:
- t, Stokes or lambda changed: the image at the new index, and frames ahead along the axis that moved (the
  probe's read-ahead). The cursor's panels are evaluated when that image arrives, since it tells whether the
  cursor is on padding.
- the cursor moved (or a panel was shown): the cursor's panels, at once; for a panel shown, only that one: a tab
  brought in front (the slit's, beside lambda-t) or a panel closed leaves the others as they are.
What each change asks of the panels: the cursor -> spectra and lambda-t; t -> spectra (the lambda-t already holds
every t); Stokes -> lambda-t; lambda -> nothing (the markers are the UI's); the cap of t steps (ViewState.t_cap) ->
lambda-t, which reads only the steps it shows (data.tsample). Nothing is read for a hidden panel,
nor on padding (the image NaN at the cursor, or exactly 0 in Stokes I): the panels are cleared once, and after
padding the next valid pixel fills both panels whatever changed. The prototype refilled both only with a
per-pixel file; without one, a t or Stokes step back from padding left the other panel empty.

Reads without a per-pixel file: served from memory at once when the row blocks hold them (Dataset.peek_series),
else on the numba thread, the spectrum first and the lambda-t after, skipped when a newer cursor position came
before they start (the spectrum is 56 reads, the lambda-t ~2600: sent together, the spectrum waited for the
lambda-t, Mac 18-23 -> 3-5 ms, StorNext ~165 -> ~40 ms). A result is shown unless a newer one already is
(executors.ShownGate): showing only the latest request's froze the panels while the mouse moved.
Results come back from other threads through Loop.post, and the Sink is called on the main thread only.
The slit panel's reads and slices are SlitReads' (core.slitreads), which sees every notice first.
A linked cube (ROADMAP E8.1) has a scheduler of its own (member=k): it reads the state as its cube does
(Session.member_state: its lambda and Stokes, its panels), and a change reaches it only when its frame or its
cursor changes (a single frame does not move with t). No 2x2 view: that is the main cube's scheduler's. The slit
reads (SlitReads) of each cube see every notice of the whole state: the main cube's follow the cube the slit was drawn
on (ViewState.path_cube), and with a slit tab per cube (ViewState.slit_tabs) each cube's reads its own. Its
image is a panel that can be closed: then no image is read nor read ahead, and the cursor's panels go on from the
last image (for the padding under the cursor); shown again, the image of now.
The spectra's reads that are not the cursor's (the first block for the units, the y-range sample) wait for the
spectra to be shown: a linked cube's tab behind read 100 profiles at start, on the numba thread the main cube's
cursor reads share.
The image's levels are computed on the thread that read the frame, before its result is posted, and on the threads
that read frames ahead (Levels.ahead): the UI thread finds them cached. Never for a read already stale, nor on the
main thread: a future that completed before its callback was added runs it there, and the levels are then computed
when the image is shown, as before.
"""
import dataclasses
import functools
import threading
from concurrent.futures import Future
from typing import Any, Protocol

import numpy as np

from ..data.executors import Generations, ShownGate
from ..data.stats import quv_amplitude_ranges, quv_threads, sample_pixels, sample_profiles
from ..data.tsample import time_samples
from ..obs import counter, get_logger
from .levels import Levels, panel_levels, rule_levels
from .session import Session
from .slitreads import SlitReads
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

    def slit_path(self, pix: tuple[np.ndarray, np.ndarray] | None) -> None: ...        # the slit's pixels (iy, ix)

    def slit(self, ts: np.ndarray | None, sl: np.ndarray | None, s: int,                # its slices; None: unchanged
             ts_levels: tuple[float, float] | None, sl_levels: tuple[float, float] | None) -> None: ...


class Scheduler:
    def __init__(self, session: Session, sink: Sink, member: int = 0):
        self.session, self.sink, self.member = session, sink, member
        self.ds: Any = session.members[member].dataset   # a Dataset: the session types only what it needs of one
        self.loop = session.store.loop
        self.gens, self.shown = Generations(), ShownGate()
        self.img: np.ndarray | None = None              # the image on screen
        self.img_idx: tuple | None = None
        self.levels = Levels()
        r = self.ds.roles
        self.sizes = {"t": r.nt, "s": r.ns, "l": r.nl}
        # a linked cube's image is a panel that can be closed; the main cube's is always there
        self._image_shown = (lambda st: True) if member == 0 else (lambda st: "image" in st.panels)
        self.yrange = YRange(self.loop, r.ns, self._cont(), sink.y_range, sink.units,
                             self._start_quv, quv_ok=r.s is not None)
        self._sampled = False
        self.grid = False                               # the 2x2 view: every Stokes's frame at this t and lambda
        self._grid_gen = 0
        self._closed = False
        self._pending: set[str] = set()                 # cursor work waiting for the latest image
        self._cleared = False
        self._futures: set[Future] = set()
        st = self.state
        self._panels = st.panels                        # the panels shown at the last notice
        self._seen = st                                 # a linked cube's state at the last notice
        self._flock = threading.Lock()
        self._scale_seen = self._my_scale(st)
        self.slit = SlitReads(session, sink, self._track, self._when_read, cube=member)
        self._off = session.store.subscribe(self._on_change)
        self._units_read = False
        if "spectra" in st.panels:
            self._first_units(st)
        self._pending.add("cursor")                     # the first image brings the first cursor
        if self._image_shown(st):
            self._request_image(st)

    @property
    def state(self) -> ViewState:
        """The session's state as this scheduler's cube reads it (Session.member_state)."""
        return self.session.member_state(self.member)

    def _start_sample_once(self) -> None:
        """The y-range sample, SAMPLE_AFTER_S from now: once, with an image to sample and the spectra shown."""
        if self._sampled or self.img is None or "spectra" not in self.state.panels:
            return
        self._sampled = True
        self.loop.call_later(SAMPLE_AFTER_S, self._start_sample)

    def _first_units(self, st: ViewState) -> None:
        """With a per-pixel file, the cursor's block read now, as the window is built (the prototype's first
        spectrum, app/viewer.py _set_spectra 1927): I's title has its power of ten from the first frame, and the axis
        does not widen once the spectrum comes. One small read (0.1 ms on a synthetic cube), then in the cache: the
        first cursor read finds it there. Without that file the first spectrum brings it, as in the prototype."""
        self._units_read = True
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
        self.slit.close()
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

    def _when_read(self, fut: Future, fn) -> None:
        """fn(fut) on the thread that completes fut (the levels, then the post); in flight until fn returns, so
        that a wait on in_flight() covers the levels computed after the read."""
        posted: Future = Future()
        self._track(posted)

        def run(f: Future) -> None:
            try:
                fn(f)
            finally:
                posted.set_result(None)
        fut.add_done_callback(run)

    def in_flight(self) -> list[Future]:
        """Reads not finished yet (their results then come through the loop)."""
        with self._flock:
            return list(self._futures)

    # ---------------------------------------------------------------- changes of state
    def _on_change(self, st: ViewState, changed: frozenset) -> None:
        self.slit.on_change(st, changed)               # the whole state: the slit is not in a member's (member_state)
        if "scale" in changed:                          # its levels' rule or fixed levels: drawn again from memory
            mine = self._my_scale(st)
            if mine != self._scale_seen:
                self._scale_seen = mine
                self._show_image()
                if self.grid:
                    self._request_grid(self.state)
        if self.member:
            st, changed = self._as_member(st)
            if not changed:
                return
        came, self._panels = st.panels - self._panels, st.panels
        if "spectra" in came:                           # shown for the first time: what waited for it
            if not self._units_read:
                self._first_units(st)
            self._start_sample_once()
        moved = changed & {"t", "s", "l"}
        here = changed & {"cursor", "t_cap"}            # what the cursor's panels read changed, not the image
        if not self._image_shown(st):                   # its image closed: the panels only, from the last image
            if moved or here or came:
                self._evaluate(st, set(moved | here) | {f"show:{p}" for p in came})
            return
        if "image" in came and not moved:               # shown again: the image of now, then the panels
            self._pending |= {"cursor"} | {f"show:{p}" for p in came}
            self._request_image(st)
            return
        if moved:
            self._pending |= moved | here | {f"show:{p}" for p in came}
            self._request_image(st)
            if self.grid and moved & {"t", "l"}:        # a change of Stokes alone: the same frames
                self._request_grid(st)
            # on the loop's next pass, after this frame is painted: started here, the reads ahead slowed the paint
            # (step in t, real cube, bellatrix: median 17.9-19.3 ms -> 13.8-15.0, the prototype 15.8)
            self.loop.call_soon(lambda: self._prefetch(st, moved))
        elif here or came:
            # only the panels that came: the spectra shown again when the slit's tab came in front cost 3.5-17 ms of
            # the UI thread between a finished slit and its slices (6173, bellatrix)
            self._evaluate(st, set(here) | {f"show:{p}" for p in came})

    def _as_member(self, st: ViewState) -> tuple[ViewState, frozenset]:
        """The notice as the linked cube reads it: its state, and what changed of it since its last notice (a t of
        the main cube that shows the same of its frames is no change: a single frame, or its nearest time again)."""
        mine, seen = self.session.member_state(self.member, st), self._seen
        self._seen = mine
        fields = ("t", "s", "l", "cursor", "panels", "locked", "playing", "t_cap")
        return mine, frozenset(f for f in fields if getattr(mine, f) != getattr(seen, f))

    def _request_image(self, st: ViewState) -> None:
        g = self.gens.new("image")
        idx = self.session.index_of(self.member, st)
        fut = self.ds.image(idx)
        if fut.done():
            self._image_ready(g, idx, fut)
        else:
            def done(f: Future, s: int = st.s) -> None:     # on the thread that read the frame
                self._levels_ahead(idx, s, f, lambda: self.gens.stale("image", g))
                self.loop.post(lambda: self._image_ready(g, idx, f))
            self._when_read(fut, done)

    def _prefetch(self, st: ViewState, moved) -> None:
        if self._closed:
            return
        n_ahead = getattr(getattr(self.ds, "probe", None), "read_ahead", 0)
        for axis in moved:
            n = self.sizes[axis]
            # the 2x2 view shows every Stokes: their next frames along t or lambda too
            stokes = range(self.sizes["s"]) if self.grid and axis != "s" else (st.s,)
            for d in range(1, n_ahead + 1):
                for s in stokes:
                    ahead = dataclasses.replace(st, **{axis: (getattr(st, axis) + d) % n})
                    if axis != "s":
                        ahead = dataclasses.replace(ahead, s=s)
                    idx = self.session.index_of(self.member, ahead)
                    fut = self.ds.prefetch(idx)
                    if isinstance(fut, Future):         # None: cached, or outside the cube
                        fut.add_done_callback(functools.partial(self._levels_ahead, idx, ahead.s))

    def _levels_ahead(self, idx: tuple, s: int, fut: Future, stale=None) -> None:
        """The levels of the frame fut read at Stokes s, by its rule now, into the cache, on the thread that read it
        (Levels.ahead); nothing on the main thread, for a read that failed or was cancelled, or a request already
        stale, nor while its levels are fixed. The rule is read off the state's latest snapshot (immutable: a
        reference read); a rule changed meanwhile computes its own when shown."""
        if (self._closed or threading.current_thread() is threading.main_thread() or fut.cancelled()
                or fut.exception() is not None or (stale is not None and stale())):
            return
        rule = self.session.scale(self.member, s)[0]
        if rule == "fixed":
            return
        try:
            self.levels.ahead(idx, s > 0, fut.result(), rule)
        except Exception as e:                          # computed again when shown, where it reports
            log.warning("levels of %s not computed ahead: %r", idx, e)

    # ---------------------------------------------------------------- the 2x2 view
    def set_grid(self, on: bool) -> None:
        """The 2x2 view (I Q U V side by side, ROADMAP E5.11) on or off: on, every Stokes's frame at this t and
        lambda goes to sink.grid_image as it comes, now and at every change of t or lambda, with its own levels (Q U
        V symmetric about 0), and the next frames of all of them are read ahead. From the prototype's
        app/look_glass.py StokesGrid.refresh (278-313)."""
        self.grid = bool(on)
        self._grid_gen += 1
        if self.grid:
            self._request_grid(self.state)

    def _request_grid(self, st: ViewState) -> None:
        self._grid_gen += 1
        g = self._grid_gen
        for s in range(self.sizes["s"]):
            idx = self.session.index_of(self.member, dataclasses.replace(st, s=s))
            fut = self.ds.image(idx)
            if fut.done():
                self._grid_ready(g, s, idx, fut)
            else:
                def done(f: Future, s: int = s, idx: tuple = idx) -> None:     # on the thread that read the frame
                    self._levels_ahead(idx, s, f, lambda: not self.grid or g != self._grid_gen)
                    self.loop.post(lambda: self._grid_ready(g, s, idx, f))
                self._when_read(fut, done)

    def _grid_ready(self, g: int, s: int, idx: tuple, fut: Future) -> None:
        if self._closed or fut.cancelled() or not self.grid or g != self._grid_gen:   # off, or a newer t or lambda
            return
        if fut.exception() is not None:
            log.warning("image %s not read: %r", idx, fut.exception())
            return
        img = fut.result()
        self.sink.grid_image(s, idx, img, self.image_levels(s, idx, img))

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
            self._start_sample_once()                   # the y-range sample, after the first image and cursor
        if not self.gens.stale("image", g) and self._pending:
            kinds, self._pending = self._pending, set()
            self._evaluate(self.state, kinds)

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
        r = self.ds.roles                               # a spectrum needs lambda; a lambda-t needs t (without
        want_spec = (r.l is not None and "spectra" in st.panels     # lambda, one column: the value against t)
                     and bool(kinds & {"cursor", "t", "show:spectra"} or refill))
        want_lt = (r.t is not None and "lambda_t" in st.panels
                   and bool(kinds & {"cursor", "s", "t_cap", "show:lambda_t"} or refill))
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
        self.sink.image(self.img_idx, self.img, self.image_levels(self.state.s, self.img_idx, self.img))

    def _my_scale(self, st: ViewState) -> tuple:
        return tuple(e for e in st.scale if e[0] == self.member)

    def image_levels(self, s: int, idx: tuple, img) -> tuple[float, float]:
        """The levels of img (the frame at idx, Stokes s) by its cube's rule at s (Session.scale): fixed, or its
        own by a per-frame rule (cached: Levels)."""
        rule, lo, hi = self.session.scale(self.member, s)
        if rule == "fixed":
            return (lo, hi)
        return self.levels.image(idx, s > 0, img, rule)

    def levels_now(self) -> tuple[float, float] | None:
        """The levels of the image on screen; None before the first."""
        if self.img is None or self.img_idx is None:
            return None
        return self.image_levels(self.state.s, self.img_idx, self.img)

    def fix_levels(self, on: bool, refit: bool = False) -> None:
        """The image padlock, for its cube's Stokes now (Session.scale): on fixes the levels to the image shown, by
        its rule (refit: to its 1-99 percentiles again, when already fixed); off gives each image its own again (the
        default rule). The image is shown again with them."""
        if self.img is None:
            return
        s = self.state.s
        rule = self.session.scale(self.member, s)[0]
        if not on:
            self.session.set_scale(self.member, s, "p1")
        elif refit or rule != "fixed":
            lim = rule_levels(self.img, s > 0, "p1" if rule == "fixed" else rule)
            self.session.set_scale(self.member, s, "fixed", *lim)
        self._scale_seen = self._my_scale(self.session.store.state)     # drawn now, not again at the notice
        self._show_image()
        if self.grid:
            self._request_grid(self.state)

    def _steps(self, st: ViewState) -> np.ndarray | None:
        """The t steps lambda-t reads and shows (data.tsample), or None: every t."""
        nt = self.ds.roles.nt
        ts = time_samples(nt, st.t_cap)
        return ts if len(ts) < nt else None

    def _read_block(self, g: int, st: ViewState, want_spec: bool, want_lt: bool) -> None:
        y, x = st.cursor
        ts = self._steps(st)

        def deliver(blk):
            if want_spec:
                self._show("spectra", g, blk[:, st.t, :], (y, x), st.t)
            if want_lt:
                self._show("lambda_t", g, blk[st.s] if ts is None else blk[st.s][ts], (y, x), st.s)

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

    def _as(self, arr, axes, want, nt: int | None = None) -> np.ndarray:
        """arr, read along `axes` in the cube's order, as an array over the axes in `want` (the panels' order):
        a cube keeping lambda before t or Stokes (--axes l,t) gave lambda-t transposed and the spectra scrambled.
        nt: the steps of t read, when not all."""
        r = self.ds.roles
        size = {r.t: r.nt if nt is None else nt, r.s: r.ns, r.l: r.nl}
        a = np.asarray(arr).reshape([size[ax] for ax in axes])
        want = [ax for ax in want if ax is not None]
        return a if list(axes) == want else a.transpose([list(axes).index(ax) for ax in want])

    def _spec(self, arr, spec_axes) -> np.ndarray:
        """The spectra as (Stokes, lambda), a single Stokes as one row."""
        r = self.ds.roles
        return self._as(arr, spec_axes, (r.s, r.l)).reshape(r.ns, r.nl)

    def _lt(self, arr, lt_axes, nt: int | None = None) -> np.ndarray:
        """lambda-t as (t, lambda), nt steps of t (all when None); a cube without lambda as one column."""
        r = self.ds.roles
        nt = r.nt if nt is None else nt
        return self._as(arr, lt_axes, (r.t, r.l), nt).reshape(nt, r.nl)

    def _read_series(self, g: int, st: ViewState, want_spec: bool, want_lt: bool) -> None:
        r, (y, x) = self.ds.roles, st.cursor
        idx = self.session.index_of(self.member, st)
        spec_axes = sorted(a for a in (r.s, r.l) if a is not None)
        lt_axes = sorted(a for a in (r.t, r.l) if a is not None) if r.t is not None else None
        want_lt = want_lt and lt_axes is not None
        ts = self._steps(st) if want_lt else None
        # only the t steps shown are read (data.tsample); every t as before when they are all
        lt_kw, n_lt = ({} if ts is None else {"at": {r.t: ts}}), (None if ts is None else len(ts))
        spec = self.ds.peek_series(y, x, idx, spec_axes) if want_spec else None
        lt = self.ds.peek_series(y, x, idx, lt_axes, **lt_kw) if want_lt else None
        if spec is not None:
            self._show("spectra", g, self._spec(spec, spec_axes), (y, x), st.t)
        if lt is not None:
            self._show("lambda_t", g, self._lt(lt, lt_axes, n_lt), (y, x), st.s)
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
                lt_ = self._lt(self.ds.read_series(y, x, idx, lt_axes, **lt_kw), lt_axes, n_lt)
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
        r, t = self.ds.roles, self.state.t
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

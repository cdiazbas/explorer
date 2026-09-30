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
from ..obs import counter, get_logger
from .levels import Levels, panel_levels
from .session import Session
from .state import ViewState

log = get_logger("core")


class Sink(Protocol):
    """Where results go (the UI; a recorder in tests). Called on the main thread."""

    def image(self, idx: tuple, img: np.ndarray, levels: tuple[float, float]) -> None: ...

    def spectra(self, spec: np.ndarray, pixel: tuple[int, int], t: int) -> None: ...     # (ns, nl)

    def lambda_t(self, lt: np.ndarray, pixel: tuple[int, int], s: int, levels: tuple[float, float]) -> None: ...

    def cleared(self, pixel: tuple[int, int]) -> None: ...                             # padding under the cursor


class Scheduler:
    def __init__(self, session: Session, sink: Sink):
        self.session, self.sink = session, sink
        self.ds = session.main
        self.loop = session.store.loop
        self.gens, self.shown = Generations(), ShownGate()
        self.img: np.ndarray | None = None              # the image on screen
        self.img_idx: tuple | None = None
        self.levels = Levels()
        self._pending: set[str] = set()                 # cursor work waiting for the latest image
        self._cleared = False
        self._futures: set[Future] = set()
        self._flock = threading.Lock()
        self._off = session.store.subscribe(self._on_change)
        self._pending.add("cursor")                     # the first image brings the first cursor
        self._request_image(session.state)

    def close(self) -> None:
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
            self._prefetch(st, moved)
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
        n_ahead = getattr(getattr(self.ds, "probe", None), "read_ahead", 0)
        for axis in moved:
            n = self.session.sizes[axis]
            for d in range(1, n_ahead + 1):
                ahead = dataclasses.replace(st, **{axis: (getattr(st, axis) + d) % n})
                self.ds.prefetch(self.session.index(state=ahead))

    def _image_ready(self, g: int, idx: tuple, fut: Future) -> None:
        if fut.exception() is not None:
            log.warning("image %s not read: %r", idx, fut.exception())
            counter("core.image.failed")
            return
        if self.shown.accept("image", g):
            self.img, self.img_idx = fut.result(), idx
            self._show_image()
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
        if self.shown.accept(kind, g):
            if kind == "lambda_t":                      # Q U V symmetric about 0
                self.sink.lambda_t(arr, pixel, at, panel_levels(arr, symmetric=at > 0))
            else:
                self.sink.spectra(arr, pixel, at)

    # ---------------------------------------------------------------- the image's levels
    def _show_image(self) -> None:
        if self.img is None or self.img_idx is None:
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
            if f.exception() is None:
                deliver(f.result())
            else:
                log.warning("block (%d, %d) not read: %r", y, x, f.exception())

        fut = self._track(self.ds.pixel_block(y, x))
        fut.add_done_callback(lambda f: self.loop.post(lambda: arrived(f)))

    def _read_series(self, g: int, st: ViewState, want_spec: bool, want_lt: bool) -> None:
        r, (y, x) = self.ds.roles, st.cursor
        idx = self.session.index(state=st)
        spec_axes = sorted(a for a in (r.s, r.l) if a is not None)
        lt_axes = sorted((r.t, r.l)) if r.t is not None and r.l is not None else None
        want_lt = want_lt and lt_axes is not None
        spec = self.ds.peek_series(y, x, idx, spec_axes) if want_spec else None
        lt = self.ds.peek_series(y, x, idx, lt_axes) if want_lt else None
        if spec is not None:
            self._show("spectra", g, spec.reshape(r.ns, r.nl), (y, x), st.t)
        if lt is not None:
            self._show("lambda_t", g, lt, (y, x), st.s)
        need_spec, need_lt = want_spec and spec is None, want_lt and lt is None
        if not (need_spec or need_lt):
            return

        def job():
            if self.gens.stale("cursor", g):
                counter("core.cursor.skipped_stale")
                return
            if need_spec:
                sp = self.ds.read_series(y, x, idx, spec_axes).reshape(r.ns, r.nl)
                self.loop.post(lambda: self._show("spectra", g, sp, (y, x), st.t))
            if need_lt and not self.gens.stale("cursor", g):
                lt_ = self.ds.read_series(y, x, idx, lt_axes)
                self.loop.post(lambda: self._show("lambda_t", g, lt_, (y, x), st.s))

        def failed(f: Future) -> None:
            if f.exception() is not None:
                log.warning("series (%d, %d) not read: %r", y, x, f.exception())

        self._track(self.ds.executors.numba.submit(job)).add_done_callback(failed)

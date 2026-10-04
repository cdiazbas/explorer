"""Contrast levels of what is drawn: the image, the lambda-t and the slices along a slit, in one place.

From the prototype: limits and Viewer._limits (the image), _set_lt and _paint_slice (lambda-t and slices), the
symmetric Q U V of look.py, and the fixed levels of _toggle_fix and _image_refit. Two rules, as there:
- the image: from its [::8, ::8] subsample, finite non-zero values; Stokes I at the 1-99 percentiles, Q U V
  symmetric at the 99th percentile of |value| (stats.limits: 55 -> 1 ms on a 2k frame against the whole frame).
  Cached per (index, Q U V or not), 4096 at most, as the prototype's _lim_cache: stepping back and forth through
  frames recomputes nothing.
- lambda-t and slices: every finite value (small images, no subsample), 1-99 percentiles (min-max with 10 values
  or fewer), (0, 1) when nothing is finite; Q U V symmetric at the 99th percentile of |value| when it is above 0.
Fixed levels hold the image's levels while the index changes. They are kept for Stokes I and for Q U V apart: the
prototype held one pair, so levels fixed on I went on drawing Q with I's range.
The image's levels are computed on the thread that read the frame (Levels.ahead), the frames read ahead too, so
the UI thread finds them cached: with the 2x2 view a step in t computed four on it, ~11 ms of a ~47 ms step on
bellatrix. A computation in progress on another thread is waited for, never repeated.
"""
import threading
from collections import OrderedDict
from concurrent.futures import Future

import numpy as np

from ..data.stats import limits
from ..obs import counter

CACHE = 4096


def image_levels(img, symmetric: bool) -> tuple[float, float]:
    return limits(img, symmetric=symmetric)


def panel_levels(a, symmetric: bool) -> tuple[float, float]:
    """Levels of a lambda-t or a slice along a slit."""
    f = np.asarray(a)[np.isfinite(a)]
    if not f.size:
        return (0.0, 1.0)
    if symmetric:
        m = float(np.percentile(np.abs(f), 99))
        if m > 0:
            return (-m, m)
    lo, hi = np.percentile(f, (1, 99)) if f.size > 10 else (f.min(), f.max())
    return (float(lo), float(hi) if hi > lo else float(lo) + 1)


class Levels:
    """The image's levels for each index, cached, and the fixed levels when fixed. Thread-safe: ahead() fills the
    cache from the threads that read the frames, image() serves the UI thread."""

    def __init__(self, capacity: int = CACHE):
        self.capacity = capacity
        self._cache: OrderedDict = OrderedDict()
        self._fixed: dict[bool, tuple[float, float]] = {}
        self._busy: dict[tuple, Future] = {}           # levels being computed, by key
        self._lock = threading.Lock()

    def image(self, idx, symmetric: bool, img) -> tuple[float, float]:
        """The levels to draw img (the frame at idx) with: the fixed ones when fixed, else its own."""
        with self._lock:
            if bool(symmetric) in self._fixed:
                return self._fixed[bool(symmetric)]
        return self._levels(_key(idx, symmetric), img, ui=True)

    def ahead(self, idx, symmetric: bool, img) -> None:
        """Compute and cache img's levels before they are drawn (off the UI thread); nothing while fixed, as
        image() would not use them."""
        with self._lock:
            if bool(symmetric) in self._fixed:
                return
        self._levels(_key(idx, symmetric), img, ui=False)

    def _levels(self, key: tuple, img, ui: bool) -> tuple[float, float]:
        """Counters: computed (every computation), ahead (those off the UI thread); cached and waited count the UI's
        calls only."""
        with self._lock:
            lim = self._cache.get(key)
            if lim is not None:
                self._cache.move_to_end(key)
                if ui:
                    counter("core.levels.cached")
                return lim
            busy = self._busy.get(key)
            if busy is None:
                mine: Future = Future()
                self._busy[key] = mine
        if busy is not None:                            # on another thread now: its result, not a second computation
            if ui:
                counter("core.levels.waited")
            return busy.result()
        return self._compute(key, img, ui, mine)

    def _compute(self, key: tuple, img, ui: bool, mine: Future) -> tuple[float, float]:
        try:
            lim = image_levels(img, key[1])
        except BaseException as e:
            with self._lock:
                self._busy.pop(key, None)
            mine.set_exception(e)
            raise
        counter("core.levels.computed")
        if not ui:
            counter("core.levels.ahead")
        with self._lock:
            self._busy.pop(key, None)
            self._cache[key] = lim
            if len(self._cache) > self.capacity:
                self._cache.popitem(last=False)
        mine.set_result(lim)
        return lim

    def fix(self, img, symmetric: bool) -> tuple[float, float]:
        """Fix the levels to this image's (the padlock closed, or refitted to the image shown)."""
        lim = image_levels(img, symmetric)
        with self._lock:
            self._fixed[bool(symmetric)] = lim
        return lim

    def unfix(self) -> None:
        with self._lock:
            self._fixed.clear()

    def fixed(self, symmetric: bool) -> bool:
        with self._lock:
            return bool(symmetric) in self._fixed


def _key(idx, symmetric: bool) -> tuple:
    return (tuple(int(i) for i in idx), bool(symmetric))

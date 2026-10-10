"""Contrast levels of what is drawn: the image, the lambda-t and the slices along a slit, in one place.

From the prototype: limits and Viewer._limits (the image), _set_lt and _paint_slice (lambda-t and slices), the
symmetric Q U V of look.py, and the fixed levels of _toggle_fix and _image_refit. Two rules, as there:
- the image: from its [::8, ::8] subsample, finite non-zero values; Stokes I at the 1-99 percentiles, Q U V
  symmetric at the 99th percentile of |value| (stats.limits: 55 -> 1 ms on a 2k frame against the whole frame).
  Cached per (index, Q U V or not), 4096 at most, as the prototype's _lim_cache: stepping back and forth through
  frames recomputes nothing.
- lambda-t and slices: every finite value (small images, no subsample), 1-99 percentiles (min-max with 10 values
  or fewer), (0, 1) when nothing is finite; Q U V symmetric at the 99th percentile of |value| when it is above 0.
Gamma (per cube and Stokes: Session.gamma) bends the line between the levels: limits from 0 up go x^gamma after x is
put on 0..1 between them; symmetric ones (Q U V, -m..m) go sign(x)|x/m|^gamma, 0 staying in the middle (CRISPEX's
sign-kept gamma, crispex.pro:8027-8036). The image reads it off a table in the reduce kernel (kernels.gamma_table),
lambda-t and the slit's slices here (gamma_panel). Gamma 1 is the straight line, by the same code as without it.
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


GAMMA_MIN, GAMMA_MAX = 0.1, 10.0           # CRISPEX's gamma slider: 10^(v/500 - 1), v 0..1000 (crispex.pro:24436-24441)
GAMMA_STEP = 0.1                            # decades per step: 1, 0.79, 0.63, 0.50, 0.40 ... and back to 1 exactly


def gamma_step(gamma: float, d: int) -> float:
    """gamma moved d steps of GAMMA_STEP decades, on that grid (no drift: up and down again is 1.0 exactly), within
    GAMMA_MIN..GAMMA_MAX."""
    n = round(np.log10(gamma) / GAMMA_STEP) + int(d)
    lim = round(np.log10(GAMMA_MAX) / GAMMA_STEP)
    n = max(-lim, min(lim, n))
    return 1.0 if n == 0 else float(10.0 ** (n * GAMMA_STEP))


def symmetric_levels(levels) -> bool:
    """Levels centred on 0 (-m, m), as Q U V's are: gamma keeps the sign about 0 there."""
    lo, hi = float(levels[0]), float(levels[1])
    return lo < 0 < hi and lo == -hi


def gamma_panel(a, levels, gamma: float):
    """(values, levels) to draw a lambda-t or a slit's slice with gamma: as given at 1; else the values bent between
    the levels, on (0, 1), or (-1, 1) for symmetric levels. NaN stays NaN (no data)."""
    if gamma == 1:
        return a, levels
    lo, hi = float(levels[0]), float(levels[1])
    a = np.asarray(a, np.float32)
    with np.errstate(invalid="ignore"):
        if symmetric_levels(levels):
            u = np.clip(a / hi, -1.0, 1.0)
            return (np.sign(u) * np.abs(u) ** gamma).astype(np.float32), (-1.0, 1.0)
        u = np.clip((a - lo) / (hi - lo), 0.0, 1.0)
        return (u ** gamma).astype(np.float32), (0.0, 1.0)


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

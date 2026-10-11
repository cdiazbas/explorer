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
How the image's levels are found is a rule per cube and Stokes (Session.scale, next to gamma): the percentiles of
each frame (1-99, the default, or 0.5-99.5), each frame's min-max, or fixed levels that hold while the index changes
(the padlock closed, or limits dragged or typed). Q U V stay symmetric about 0 under every rule.
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


# how the image's levels are found (Session.scale): each frame's percentiles (lo, hi), or fixed levels
RULES = {"p1": (1.0, 99.0), "p05": (0.5, 99.5), "minmax": (0.0, 100.0), "fixed": None}
RULE_DEFAULT = "p1"


def image_levels(img, symmetric: bool) -> tuple[float, float]:
    return limits(img, symmetric=symmetric)


def rule_levels(img, symmetric: bool, rule: str = RULE_DEFAULT) -> tuple[float, float]:
    """The levels of img by a per-frame rule (RULES): the [::8, ::8] subsample's percentiles, Q U V symmetric at the
    upper one of |value|; the default rule is image_levels itself."""
    if rule == RULE_DEFAULT:
        return image_levels(img, symmetric)
    pct = RULES[rule]
    lo, hi = pct if pct is not None else (1.0, 99.0)
    return limits(img, symmetric=symmetric, lo=lo, hi=hi)


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
    """The image's levels for each index and per-frame rule, cached (fixed levels are the session's: Session.scale).
    Thread-safe: ahead() fills the cache from the threads that read the frames, image() serves the UI thread."""

    def __init__(self, capacity: int = CACHE):
        self.capacity = capacity
        self._cache: OrderedDict = OrderedDict()
        self._busy: dict[tuple, Future] = {}           # levels being computed, by key
        self._lock = threading.Lock()

    def image(self, idx, symmetric: bool, img, rule: str = RULE_DEFAULT) -> tuple[float, float]:
        """The levels to draw img (the frame at idx) with by a per-frame rule (RULES)."""
        return self._levels(_key(idx, symmetric, rule), img, ui=True)

    def ahead(self, idx, symmetric: bool, img, rule: str = RULE_DEFAULT) -> None:
        """Compute and cache img's levels before they are drawn (off the UI thread)."""
        self._levels(_key(idx, symmetric, rule), img, ui=False)

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
            lim = rule_levels(img, key[1], key[2])
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



def _key(idx, symmetric: bool, rule: str = RULE_DEFAULT) -> tuple:
    if RULES.get(rule) is None:
        raise ValueError(f"no per-frame rule {rule!r}: one of {[r for r, v in RULES.items() if v]}")
    return (tuple(int(i) for i in idx), bool(symmetric), rule)

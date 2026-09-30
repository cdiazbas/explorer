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
"""
from collections import OrderedDict

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
    """The image's levels for each index, cached, and the fixed levels when fixed."""

    def __init__(self, capacity: int = CACHE):
        self.capacity = capacity
        self._cache: OrderedDict = OrderedDict()
        self._fixed: dict[bool, tuple[float, float]] = {}

    def image(self, idx, symmetric: bool, img) -> tuple[float, float]:
        if symmetric in self._fixed:
            return self._fixed[symmetric]
        key = (tuple(int(i) for i in idx), bool(symmetric))
        lim = self._cache.get(key)
        if lim is not None:
            self._cache.move_to_end(key)
            counter("core.levels.cached")
            return lim
        lim = image_levels(img, symmetric)
        counter("core.levels.computed")
        self._cache[key] = lim
        if len(self._cache) > self.capacity:
            self._cache.popitem(last=False)
        return lim

    def fix(self, img, symmetric: bool) -> tuple[float, float]:
        """Fix the levels to this image's (the padlock closed, or refitted to the image shown)."""
        self._fixed[bool(symmetric)] = image_levels(img, symmetric)
        return self._fixed[bool(symmetric)]

    def unfix(self) -> None:
        self._fixed.clear()

    def fixed(self, symmetric: bool) -> bool:
        return bool(symmetric) in self._fixed

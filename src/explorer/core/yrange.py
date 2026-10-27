"""The y ranges of the spectra, one per Stokes, and the units they are drawn in.

From the prototype's Viewer._set_spectra, _yfit, _set_yfixed, _lock_spectra, _ysample_fixed, _sample_ready and
_quv_ready. Only the logic: what each plot's range is and when it changes; the reads (the sample, Q U V from whole
frames) are the scheduler's, and drawing is the UI's.
- Units: Stokes I in a power of ten of BUNIT, from the first spectrum with data or from the sample, whichever comes
  first; Q U V in % of the pixel's I_c when the continuum tuning is known, else as I (axes.plot_units).
- Padlock open (the start): while the cursor moves a range only grows, to 1-2-5 values (a new range re-renders
  the axes: ~40 ms of the ~57 ms a cursor move cost; 5.9 ms per plot whose range changes with the axes cached);
  at rest (0.4 s without a new spectrum) each becomes its profile's own range.
- Padlock closed: the ranges of the random sample, fixed (CRISPEX fixed them per Stokes, crispex.pro L12519,
  L12588); Q U V from whole frames once they come, asked for when the padlock first closes (not at start: while it
  ran the cursor went 14.8 -> 18.5-19.3 ms).
- fit(): each plot to the profile shown, and fixed there (key F, the padlock's right click); reset(): the sample's
  ranges when fixed, else the profile's.
- manual(k, range): one plot's range set by the user (dragging its y axis, ROADMAP E4.1), kept until fit, reset,
  the sample's ranges or auto(k) (a double click on the axis) give it back; the rules above leave it alone.
"""
from collections.abc import Callable

import numpy as np

from ..data.axes import plot_units, power_of_ten
from ..data.stats import nice_range, quv_plot_ranges, sample_ranges
from .loop import Loop

REST_S = 0.4


class YRange:
    def __init__(self, loop: Loop, ns: int, cont, apply: Callable[[int, tuple], None],
                 units: Callable[[float | None], None] = lambda s: None, want_quv: Callable[[], None] = lambda: None,
                 quv_ok: bool = True, intensity: bool = True):
        """apply(k, (lo, hi)): set plot k's range; units(iscale): I's power of ten is known (for the titles);
        want_quv(): start reading Q U V's ranges from whole frames (once). intensity: the planes are Stokes (or one
        plane): I's power of ten, I from 0, Q U V symmetric; else (an inversion's parameters, a snapshot's
        variables) each plane in its own units and range."""
        self.loop, self.ns, self.cont = loop, int(ns), cont
        self._apply, self._units, self._want_quv = apply, units, want_quv
        self.iscale: float | None = None
        self.intensity = intensity
        self.fixed = False                              # both padlocks open at start, as the prototype
        self.r: list[tuple | None] = [None] * self.ns   # the range each plot has
        self.last: list[tuple | None] = [None] * self.ns
        self.sample: list | None = None                 # per Stokes, from the random sample (Q U V from frames)
        self.quv: dict | None = None
        self.quv_ok = quv_ok and self.ns > 1
        self.quv_started = self.quv_pending = False
        self._rest_token = 0
        self.manual_k: set[int] = set()                 # plots whose range the user set

    # ---------------------------------------------------------------- helpers
    def _set(self, k: int, r: tuple) -> None:
        self.r[k] = r
        self._apply(k, r)

    def _rest_later(self) -> None:
        self._rest_token += 1
        token = self._rest_token
        self.loop.call_later(REST_S, lambda: self._rest(token))

    def _rest(self, token: int) -> None:
        if token == self._rest_token:                   # no spectrum came since: the cursor is at rest
            self.fit(force=False)

    # ---------------------------------------------------------------- a spectrum on screen
    def first(self, i_profile) -> None:
        """I's power of ten from the first profile of I that has one; later ones change nothing."""
        if self.iscale is None and self.intensity:
            self.iscale = power_of_ten(np.asarray(i_profile, dtype=np.float64))
            if self.iscale is not None:
                self._units(self.iscale)

    def spectrum(self, spec) -> np.ndarray:
        """spec: (ns, nl) as read; returns it in the plots' units, and updates the ranges."""
        spec = np.asarray(spec, dtype=np.float64)
        self.first(spec[0])
        out = plot_units(spec, self.cont, self.iscale)
        refit = False
        for k in range(min(self.ns, out.shape[0])):
            f = out[k][np.isfinite(out[k])]
            if not f.size:                              # the cursor on padding for this Stokes: nothing to fit
                continue
            lo, hi = float(f.min()), float(f.max())
            self.last[k] = (lo, hi)
            if k in self.manual_k:
                continue
            r = self.r[k]
            if self.fixed and (r is not None or self.sample is not None):
                if r is None and self.sample is not None and self.sample[k] is not None:
                    self._set(k, self.sample[k])
                continue
            if r is None or lo < r[0] or hi > r[1]:
                r = nice_range(min(lo, r[0]) if r else lo, max(hi, r[1]) if r else hi)
                self._set(k, r)
            if r != nice_range(lo, hi):
                refit = True
        if refit:
            self._rest_later()                          # not this profile's own range yet: refit at rest
        return out

    # ---------------------------------------------------------------- the user's actions
    def fit(self, force: bool = True, lock: bool | None = None) -> None:
        """Each plot to the profile shown (key F: force, then fixed there; lock=False: leave the padlock)."""
        if self.fixed and not force:
            return
        if force:
            self.manual_k.clear()
        for k, d in enumerate(self.last):
            if k in self.manual_k:
                continue
            if d is None:
                continue
            nr = nice_range(*d)
            if nr != self.r[k]:
                self._set(k, nr)
        if force if lock is None else lock:
            self.fixed = True

    def set_fixed(self, on: bool) -> None:
        """The padlock: closed -> the sample's ranges, fixed; open -> automatic again, refit at rest."""
        self.fixed = bool(on)
        if on:
            self.to_sample()
        else:
            self._rest_later()

    def to_sample(self, lock: bool = True) -> None:
        """Back to the sample's ranges (Shift+F; closing the padlock), fixed; asks for Q U V from whole frames."""
        if lock:
            self.fixed = True
        self.manual_k.clear()
        self.start_quv()
        if self.sample is None:
            return
        for k, r in enumerate(self.sample):
            if k > 0 and self.quv_pending:              # Q U V keep theirs until the whole frames are in
                continue
            if r is not None and self.r[k] != r:
                self._set(k, r)

    def reset(self) -> None:
        if self.fixed and self.sample is not None:
            self.to_sample(lock=False)
        else:
            self.fit(force=True, lock=False)

    def manual(self, k: int, r: tuple) -> None:
        """Plot k's range as the user set it; the automatic rules leave it alone until given back."""
        lo, hi = float(r[0]), float(r[1])
        if not hi > lo:
            raise ValueError(f"a range needs hi > lo, not {r}")
        self.manual_k.add(int(k))
        self._set(int(k), (lo, hi))

    def auto(self, k: int) -> None:
        """Give plot k back to the automatic rules: the sample's range when fixed, else its profile's."""
        self.manual_k.discard(int(k))
        if self.fixed and self.sample is not None and self.sample[k] is not None:
            self._set(int(k), self.sample[k])
        else:
            last = self.last[k]
            if last is not None:
                self._set(int(k), nice_range(*last))

    def set_cont(self, cont) -> None:
        """The continuum tuning known from now on (chosen from the sample, core.scheduler): Q U V go to % of I_c, so
        their ranges, the user's included, and the whole frames' half-widths, read in I's units, are forgotten; the
        next spectrum and the sample (sample_ready, after this) give them again, and Q U V from whole frames are
        asked for again when the padlock is closed."""
        self.cont = cont
        for k in range(1, self.ns):
            self.manual_k.discard(k)
            self.r[k] = self.last[k] = None
        self.sample = self.quv = None
        self.quv_started = self.quv_pending = False

    def start_quv(self) -> None:
        if self.quv_started or not self.quv_ok:
            return
        self.quv_started = self.quv_pending = True
        self._want_quv()

    # ---------------------------------------------------------------- results of the reads
    def sample_ready(self, prof) -> None:
        """The random sample's profiles (n, ns, nl), as read."""
        had = self.iscale
        ranges, self.iscale, _ = sample_ranges(prof, self.cont, self.iscale, intensity_rules=self.intensity)
        if had is None and self.iscale is not None:
            self._units(self.iscale)
        if ranges is None:
            return
        for k, r in (self.quv or {}).items():           # Q U V from whole frames, if they came first
            ranges[k] = r
        self.sample = ranges
        if self.fixed:                                  # the padlock closed before the sample came
            self.to_sample()

    def quv_ready(self, half) -> None:
        """Q U V's half-widths from whole frames (stats.quv_amplitude_ranges), or None if that read failed."""
        self.quv_pending = False
        if half is None:
            if self.fixed:
                self.to_sample()
            return
        self.quv = quv_plot_ranges(half, self.cont, self.iscale)
        if self.sample is not None:
            for k, r in self.quv.items():
                self.sample[k] = r
        if self.fixed:
            self.to_sample()

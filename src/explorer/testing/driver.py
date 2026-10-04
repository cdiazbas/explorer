"""Driver: explorer's core driven from tests without a display, through a public API (docs/plan.md §2, rule 11:
tests never reach into attributes).

    with Driver.open("cube_im.fits", no_sp=True) as d:
        d.hover(120, 300)
        d.wait_idle()
        assert d.shown.lambda_t is not None

It holds a Dataset, a Session on a ManualLoop and a Scheduler whose Sink records what would be drawn (Shown). Nothing
runs until pump() or wait_idle(); timers (the spectra's refit at rest, the y-range sample) wait for advance(), so a
test decides what happens when.
"""
import concurrent.futures as cf
from dataclasses import dataclass, field

import numpy as np

from ..core.loop import ManualLoop
from ..core.scheduler import Scheduler
from ..core.session import Session
from ..core.state import ViewState
from ..data.dataset import Dataset


@dataclass
class Shown:
    """What the sink received last, and how many times each kind came."""
    image: np.ndarray | None = None
    image_idx: tuple | None = None
    image_levels: tuple | None = None
    spectra: np.ndarray | None = None                   # in the plots' units
    spectra_at: tuple | None = None                     # (pixel, t)
    lambda_t: np.ndarray | None = None
    lambda_t_at: tuple | None = None                    # (pixel, s)
    lambda_t_levels: tuple | None = None
    y_ranges: dict = field(default_factory=dict)        # plot k -> (lo, hi)
    iscale: float | None = None
    cleared_at: tuple | None = None
    slit_pix: tuple | None = None                       # (iy, ix) of the slit shown
    slit_ts: np.ndarray | None = None                   # its time slice (t x position), spectral slice (lambda x ...)
    slit_sl: np.ndarray | None = None
    slit_s: int | None = None
    counts: dict = field(default_factory=dict)


class Driver:
    def __init__(self, dataset, own: bool = False):
        self.dataset, self._own = dataset, own
        self.loop = ManualLoop()
        self.session = Session(self.loop, dataset)
        self.shown = Shown()
        self.scheduler = Scheduler(self.session, _Recorder(self.shown))
        self.wait_idle()

    @classmethod
    def open(cls, path, **dataset_kw) -> "Driver":
        """A Driver over a cube opened here (and closed with it); dataset_kw as Dataset's (sp, no_sp, axes...)."""
        return cls(Dataset.open(path, **dataset_kw), own=True)

    # ---------------------------------------------------------------- state
    def state(self) -> ViewState:
        return self.session.state

    def index(self) -> tuple:
        return self.session.index()

    def y_sample(self) -> list | None:
        """The spectra's y ranges from the random sample, per Stokes, once it came (None before)."""
        return self.scheduler.yrange.sample

    # ---------------------------------------------------------------- actions (they take effect at the next pump)
    def hover(self, y: int, x: int) -> None:
        self.session.hover(y, x)

    def step(self, axis: str, d: int = 1, wrap: bool = False) -> None:
        self.session.step(axis, d, wrap)

    def set_index(self, axis: str, v: int) -> None:
        self.session.set_index(axis, v)

    def set_stokes(self, s: int) -> None:
        self.session.set_index("s", s)

    def lock(self, on: bool = True) -> None:
        self.session.lock(on)

    def show(self, panel: str, on: bool = True) -> None:
        self.session.show(panel, on)

    def set_slit(self, points) -> None:
        """The finished slit, (x, y) points in view coordinates; None removes it."""
        self.session.set_path(points)

    def draw_slit(self, points) -> None:
        """The slit being drawn (the points so far and the pointer's pixel); None: drawing ended."""
        self.session.set_draft(points)

    def play(self, on: bool = True) -> None:
        self.session.set_playing(on)

    def fix_levels(self, on: bool = True, refit: bool = False) -> None:
        self.scheduler.fix_levels(on, refit)

    def set_y_fixed(self, on: bool = True) -> None:
        self.scheduler.set_y_fixed(on)

    def fit_y(self) -> None:
        self.scheduler.fit_y()

    def reset_y(self) -> None:
        self.scheduler.reset_y()

    # ---------------------------------------------------------------- time
    def pump(self) -> int:
        """Run what is pending (notices, results that came back); returns how many callbacks ran."""
        return self.loop.pump()

    def advance(self, seconds: float) -> None:
        """Move the virtual clock: timers now due are pending (then pump() or wait_idle())."""
        self.loop.advance(seconds)

    def wait_idle(self, timeout: float = 30.0, rounds: int = 1000) -> None:
        """Pump until nothing is pending and no read is in flight (timers not yet due do not count)."""
        for _ in range(rounds):
            pending = self.scheduler.in_flight()
            if pending:
                done, not_done = cf.wait(pending, timeout=timeout)
                if not_done:
                    raise TimeoutError(f"{len(not_done)} reads still running after {timeout} s")
            if self.loop.pump() == 0 and not self.scheduler.in_flight():
                return
        raise RuntimeError(f"not idle after {rounds} rounds")

    # ---------------------------------------------------------------- closing
    def close(self) -> None:
        self.scheduler.close()
        if self._own:
            self.dataset.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class _Recorder:
    """The Scheduler's Sink: writes what would be drawn into a Shown."""

    def __init__(self, shown: Shown):
        self.s = shown

    def _count(self, kind):
        self.s.counts[kind] = self.s.counts.get(kind, 0) + 1

    def image(self, idx, img, levels):
        self.s.image, self.s.image_idx, self.s.image_levels = img, tuple(idx), levels
        self._count("image")

    def grid_image(self, s, idx, img, levels):
        self._count("grid_image")                      # the 2x2 view: only counted here

    def spectra(self, spec, pixel, t):
        self.s.spectra, self.s.spectra_at = spec, (tuple(pixel), t)
        self._count("spectra")

    def lambda_t(self, lt, pixel, s, levels):
        self.s.lambda_t, self.s.lambda_t_at, self.s.lambda_t_levels = lt, (tuple(pixel), s), levels
        self._count("lambda_t")

    def cleared(self, pixel):
        self.s.spectra = self.s.lambda_t = None
        self.s.cleared_at = tuple(pixel)
        self._count("cleared")

    def slit_path(self, pix):
        self.s.slit_pix = pix
        if pix is None:
            self.s.slit_ts = self.s.slit_sl = None
        self._count("slit_path")

    def slit(self, ts, sl, s, ts_levels, sl_levels):
        if ts is not None:
            self.s.slit_ts = ts
        if sl is not None:
            self.s.slit_sl = sl
        self.s.slit_s = s
        self._count("slit")

    def y_range(self, k, r):
        self.s.y_ranges[k] = r
        self._count("y_range")

    def units(self, iscale):
        self.s.iscale = iscale

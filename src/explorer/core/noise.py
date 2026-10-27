"""The noise levels of Q U V at the t shown, for their +-sigma on the spectra (ui.spectra: lines or a band, by look).

CRISPEX reads the ns frames at the continuum tuning at every change of t and takes, per Stokes, the standard
deviation of S/I_c over the whole frame (crispex.pro L21033-21043), drawn at +-1 sigma on each profile (L8554-8562).
Here the same sigma (data.stats.stokes_noise), in % of I_c as Q U V are plotted:
- the four frames at (t, continuum) on the background thread, from the frame cache when there, else read and not
  kept (Dataset.read_frame);
- once per t: kept for the session (three floats per t), so a t seen again reads nothing;
- latest wins: a job for a t already left stops before its next read;
- not while playing: the t it stops on, at the pause. Until a t's sigma comes, the last one stays on screen;
- only in a cube of 4 Stokes with a continuum tuning (the header's, or from the moment one is chosen from the sample:
  core.scheduler), with its spectra shown, and not with the images of a per-pixel file alone (each frame a pass over
  the file).
"""
from collections.abc import Callable
from concurrent.futures import Future

from ..data.axes import stokes
from ..data.executors import Generations
from ..data.masking import STOKES
from ..data.stats import stokes_noise
from ..obs import counter, get_logger
from .state import ViewState

log = get_logger("core")


class NoiseReads:
    def __init__(self, ds, loop, show: Callable[[dict, int], None], track: Callable[[Future], Future],
                 index: Callable[[ViewState, int, int], tuple], state: Callable[[], ViewState]):
        """ds: the cube (a Dataset); show(sigma, t): sigma {1: Q, 2: U, 3: V} of the t shown, on the main thread;
        track: the scheduler's bookkeeping of reads in flight; index(st, s, l): the frame's index at Stokes s and
        lambda l of state st; state(): the cube's state now."""
        self.ds, self.loop, self._show, self._track, self._index, self._state = ds, loop, show, track, index, state
        r = ds.roles
        self._can = (stokes(r) and r.ns == STOKES and r.l is not None
                     and not getattr(ds, "images_from_sp", False))
        self.known: dict[int, dict[int, float]] = {}   # t -> sigma
        self.gens = Generations()
        self._closed = False

    @property
    def cont(self) -> int | None:
        """The cube's continuum tuning now: the header's, or the one chosen from the sample later (core.scheduler)."""
        return getattr(getattr(self.ds, "axes", None), "cont", None)

    @property
    def applies(self) -> bool:
        return self._can and self.cont is not None

    def close(self) -> None:
        self._closed = True

    def want(self, st: ViewState) -> None:
        """The sigma of st's t: shown at once when known, else read (not while playing)."""
        cont = self.cont
        if self._closed or not self._can or cont is None or "spectra" not in st.panels:
            return
        t = st.t
        hit = self.known.get(t)
        if hit is not None:
            counter("core.noise.known")
            self._show(hit, t)
            return
        if st.playing:
            return
        g = self.gens.new("noise")

        def job():
            frames = {}
            for s in range(STOKES):                     # I first: its negative pixels then mask Q U V from memory
                if self.gens.stale("noise", g) or self._closed:
                    counter("core.noise.skipped_stale")
                    return
                frames[s], read = self.ds.read_frame(self._index(st, s, cont))
                counter("core.noise.frames_read", int(read))
            sig = stokes_noise(frames[0], {s: frames[s] for s in range(1, STOKES)})
            self.loop.post(lambda: self._ready(t, sig))

        def failed(f: Future) -> None:
            if not f.cancelled() and f.exception() is not None:
                log.warning("noise levels at t=%d not read: %r", t, f.exception())

        counter("core.noise.jobs")
        self._track(self.ds.executors.background.submit(job)).add_done_callback(failed)

    def _ready(self, t: int, sig: dict) -> None:
        if self._closed:
            return
        self.known[t] = sig
        if self._state().t == t:                       # else a newer t is shown or on its way
            self._show(sig, t)

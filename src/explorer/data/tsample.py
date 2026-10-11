"""The time steps a temporal panel reads and shows (lambda-t, the value against t, the slit's time slice): at most a
cap of them, evenly spread over t. A compressed series costs ~0.12 s per frame read (AIA 1986x1986, Rice), so a pixel
along all 300 t took 3.2 s and a slit's time slice 40.6 s; a cap of 100 reads a third of that, whatever nt is.

The steps are the centres of `cap` equal bins of [0, nt): bin j is [j nt/cap, (j+1) nt/cap) and its step
floor((j + 1/2) nt/cap). Drawn as cap rows over the whole t range, each row then covers the t it was read at, and the
axes stay in the cube's own t. The same steps at every t (they do not follow the current t): a step in t reads nothing
again, as without a cap. With nt <= cap, or no cap, every t: the panels as without one.
"""
import numpy as np

CAP = 100                   # the default: what the panels show at most along t
CHOICES = (25, 50, 100, None)        # what the panels' number offers: past the cap only "all" (None, every t)


def time_samples(nt: int, cap: int | None) -> np.ndarray:
    """The t indices read and shown, increasing: every t when cap is None or nt <= cap."""
    nt = max(1, int(nt))
    if cap is None or nt <= int(cap):
        return np.arange(nt)
    cap = max(1, int(cap))
    return ((np.arange(cap) + 0.5) * nt / cap).astype(np.int64)


def nearest_sample(samples: np.ndarray, y: float) -> int:
    """The step drawn at y on a panel whose t axis runs over [0, nt): the sample nearest to y (cell centres at
    t + 0.5) when fewer than nt are shown; the cell under y otherwise."""
    s = np.asarray(samples)
    return int(s[int(np.argmin(np.abs(s + 0.5 - float(y))))])


def label(cap: int | None) -> str:
    """The number as the panels show it: "all" for every t."""
    return "all" if cap is None else str(int(cap))

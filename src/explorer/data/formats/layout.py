"""Layout: where the samples of a cube are in its file and how raw values become physical ones."""
from dataclasses import dataclass

import numpy as np

# axis names (CTYPE up to its first dash) that are positions on the Sun or the sky: helioprojective, heliographic,
# Carrington, solar, celestial
SPATIAL = ("HPLN", "HPLT", "HGLN", "HGLT", "CRLN", "CRLT", "SOLX", "SOLY", "RA", "DEC")


def spatial_lead(axes) -> tuple[str, ...]:
    """The spatial axes among the leading ones (numpy order) when the last two are not both spatial: the order of a
    per-pixel file (SSTRED's _sp.fits: HPLT, HPLN, STOKES, UTC, WAVE), whose frames would be lambda-t planes. Empty
    for an image cube, and for axes no header names."""
    names = [str(a).upper() for a in axes]
    if len(names) < 3 or all(a in SPATIAL for a in names[-2:]):
        return ()
    return tuple(a for a in names[:-2] if a in SPATIAL)


@dataclass(frozen=True)
class Layout:
    path: str
    kind: str                       # "fits" or "lp"
    offset: int                     # bytes from the start of the file to the first sample
    shape: tuple[int, ...]          # numpy order, fastest axis last
    dtype: np.dtype                 # as stored, byte order included
    axes: tuple[str, ...]           # a name per axis, numpy order (e.g. UTC, STOKES, WAVE, HPLT, HPLN)
    scale: float = 1.0              # physical = raw * scale + zero (FITS BSCALE, BZERO)
    zero: float = 0.0
    blank: int | float | None = None    # raw value that means "no data" (FITS BLANK, LP nan_rplcmnt)

    @property
    def nbytes(self) -> int:
        return int(np.prod(self.shape)) * self.dtype.itemsize

    @property
    def scaled(self) -> bool:
        return self.scale != 1.0 or self.zero != 0.0

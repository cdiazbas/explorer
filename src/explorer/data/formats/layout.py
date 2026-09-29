"""Layout: where the samples of a cube are in its file and how raw values become physical ones."""
from dataclasses import dataclass

import numpy as np


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
    blank: int | None = None        # integer raw value that means "no data" (FITS BLANK)

    @property
    def nbytes(self) -> int:
        return int(np.prod(self.shape)) * self.dtype.itemsize

    @property
    def scaled(self) -> bool:
        return self.scale != 1.0 or self.zero != 0.0

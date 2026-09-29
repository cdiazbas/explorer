"""numba for the data layer: its compiled-kernel cache goes to the user's cache directory.

numba chooses where a function's cache lives when the function is decorated, so every module with cached
kernels imports numba through here. In a shared install (StorNext) the package directory may not be writable;
numba would then compile every kernel at every start (0.35-0.8 s each on the Mac, docs/journal.md).
NUMBA_CACHE_DIR, when set, is respected.
"""
import os

import numba

from .._paths import cache_dir

if not os.environ.get("NUMBA_CACHE_DIR"):
    numba.config.CACHE_DIR = str(cache_dir() / "numba")  # type: ignore[attr-defined]

__all__ = ["numba"]

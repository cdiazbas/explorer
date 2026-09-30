"""numba for the data layer: its compiled-kernel cache goes to the user's cache directory.

numba chooses where a function's cache lives when the function is decorated, so every module with cached
kernels imports numba through here. In a shared install (StorNext) the package directory may not be writable;
numba would then compile every kernel at every start (0.35-0.8 s each on the Mac, docs/journal.md).
NUMBA_CACHE_DIR, when set, is respected.

numba's thread pool is sized when numba is imported (NUMBA_NUM_THREADS, by default the number of cores: 32 on
bellatrix). Here it holds at least GATHER_MAX threads, unless NUMBA_NUM_THREADS is set; each scattered read then
uses one thread per request up to the storage probe's limit (gather.gather_limited), so a pool larger than the
cores costs idle threads only. A cold lambda-t (2604 requests, one row each), bellatrix, not pinned: 32 threads
1.00 (A/A 0.81), 64 0.56, 128 0.42 (261 ms, p90 380 against 900 ms), docs/measured.md.
"""
import os
import sys

GATHER_MAX = 128

if "numba" not in sys.modules and not os.environ.get("NUMBA_NUM_THREADS"):
    os.environ["NUMBA_NUM_THREADS"] = str(max(GATHER_MAX, os.cpu_count() or 1))

import numba  # noqa: E402

from .._paths import cache_dir  # noqa: E402

if not os.environ.get("NUMBA_CACHE_DIR"):
    numba.config.CACHE_DIR = str(cache_dir() / "numba")  # type: ignore[attr-defined]

__all__ = ["numba"]

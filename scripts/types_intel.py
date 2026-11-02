"""mypy with the Intel Mac's types, for the errors only that machine's mypy finds: numpy as pyproject pins it there
and numba without type information (0.62.1 ships none), where everywhere else numpy and numba are newer and typed.
The CI's macos-15-intel job found two that no other check saw: an np.datetime64 overload numpy 2.3.5 lacks, and an
ignore numba 0.67 needs and an untyped numba leaves unused.

numpy's wheel for that machine comes from uv.lock (its URL and sha256), once, into the cache; only its Python and
stub files are kept. mypy reads them and an untyped numba stand-in from MYPYPATH, as source: their own errors are
not explorer's, and only what mypy says about src/ counts.

    python scripts/types_intel.py          # scripts/check.sh runs it after mypy with this machine's types
Exit code: 0 clean, or skipped ("skipped: ...": numpy's wheel could not be fetched, offline); 1 errors in src/.
Standard library only (and the environment's mypy).
"""
import hashlib
import os
import re
import subprocess
import sys
import tempfile
import tomllib
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INTEL = "sys_platform == 'darwin' and platform_machine == 'x86_64'"
UNTYPED = "from typing import Any\n\n\ndef __getattr__(name: str) -> Any: ...\n"


def intel_pin(pyproject: str, name: str) -> str:
    """The version pyproject pins name to on the Intel Mac: "numpy==2.3.5; <INTEL>"."""
    m = re.search(rf'"{re.escape(name)}==([^;"]+); {re.escape(INTEL)}"', pyproject)
    if m is None:
        raise SystemExit(f"types_intel: no {name} pin for the Intel Mac in pyproject.toml")
    return m.group(1).strip()


def intel_wheel(lock: dict, name: str, version: str) -> dict:
    """uv.lock's wheel of name==version for CPython 3.12 on macOS x86_64: {url, hash, ...}."""
    for p in lock["package"]:
        if p["name"] == name and p["version"] == version:
            for w in p.get("wheels", []):
                f = w["url"].rsplit("/", 1)[-1]
                if "-cp312-" in f and "macosx" in f and f.endswith("_x86_64.whl"):
                    return w
    raise SystemExit(f"types_intel: no {name} {version} wheel for macOS x86_64 in uv.lock")


def kept(member: str) -> bool:
    """What mypy reads of a package: its Python and stub files, and py.typed."""
    return member.endswith((".py", ".pyi")) or member.endswith("/py.typed")


def numpy_types(cache: Path, wheel: dict, version: str) -> Path:
    """A folder holding numpy/ as the wheel has it (Python and stubs only), fetched and checked once."""
    dest = cache / f"numpy-{version}"
    if (dest / "numpy" / "__init__.pyi").exists():
        return dest
    algo, _, want = wheel["hash"].partition(":")
    with tempfile.TemporaryDirectory(dir=cache) as tmp:
        whl = Path(tmp) / "numpy.whl"
        with urllib.request.urlopen(wheel["url"], timeout=60) as r, open(whl, "wb") as f:
            f.write(r.read())
        got = hashlib.new(algo, whl.read_bytes()).hexdigest()
        if got != want:
            raise SystemExit(f"types_intel: {wheel['url']}: {algo} {got}, uv.lock says {want}")
        part = Path(tmp) / "unpacked"
        with zipfile.ZipFile(whl) as z:
            z.extractall(part, [m for m in z.namelist() if m.startswith("numpy/") and kept(m)])
        part.rename(dest)                               # whole or not at all
    return dest


def main() -> int:
    pyproject = (ROOT / "pyproject.toml").read_text()
    version = intel_pin(pyproject, "numpy")
    wheel = intel_wheel(tomllib.loads((ROOT / "uv.lock").read_text()), "numpy", version)
    cache = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "explorer" / "types-intel"
    cache.mkdir(parents=True, exist_ok=True)
    try:
        numpy_dir = numpy_types(cache, wheel, version)
    except OSError as e:                                # urllib's errors are OSErrors: no network
        print(f"skipped: numpy {version} for the Intel Mac could not be fetched ({e})")
        return 0
    numba_dir = cache / "numba-untyped"
    (numba_dir / "numba").mkdir(parents=True, exist_ok=True)
    (numba_dir / "numba" / "__init__.pyi").write_text(UNTYPED)
    env = dict(os.environ, MYPYPATH=os.pathsep.join([str(numpy_dir), str(numba_dir)]))
    r = subprocess.run([sys.executable, "-m", "mypy", "--cache-dir", str(cache / "mypy")], cwd=ROOT, env=env,
                       capture_output=True, text=True)
    ours = [ln for ln in r.stdout.splitlines() if ln.startswith("src" + os.sep)]
    errors = [ln for ln in ours if ": error:" in ln]
    print("\n".join(ours) if ours else f"no errors in src/ with numpy {version} and an untyped numba")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())

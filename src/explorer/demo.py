"""`explorer demo`: run the most complete thing explorer can do so far, on a cube, to try it at any moment.

    explorer demo [cube_im.fits] [--no-window]

Without a cube it uses a small synthetic one (explorer.testing.synth), written once to ~/.cache/explorer/demo/:
the right default on a machine without the shared test cubes (a Mac on its local disk, where big cubes are not
welcome). scripts/demo.sh picks the real test cube when the project's data/ link resolves.

What it runs grows with the ROADMAP; today: doctor on the cube, with a 2 s window that shows whether the display
works (over ssh -Y too). From E3 on it opens the viewer.
"""
import argparse
import os
import sys

from . import __version__
from ._name import APP_NAME
from ._paths import cache_dir


def synthetic_cube() -> str:
    """The cached synthetic demo cube, written if missing (atomically: a half-written file is never used)."""
    from .testing import synth

    d = cache_dir() / "demo"
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"synth_stokes_v{synth.SYNTH_VERSION}_im.fits"
    if not path.exists():
        print(f"writing the synthetic demo cube (once): {path}", flush=True)
        tmp = path.with_suffix(f".tmp{os.getpid()}.fits")
        try:
            synth.write_stokes_cube(tmp)
            os.replace(tmp, path)
        finally:
            if tmp.exists():
                tmp.unlink()
    return str(path)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog=f"{APP_NAME} demo", description="try what explorer can do so far, on a cube")
    ap.add_argument("cube", nargs="?", help="default: a small synthetic cube")
    ap.add_argument("--no-window", action="store_true", help="do not open any window (headless runs, tests)")
    a = ap.parse_args(argv)
    cube = a.cube or synthetic_cube()
    kind = "synthetic" if a.cube is None else "given"
    print(f"{APP_NAME} {__version__} demo on the {kind} cube {cube}", flush=True)
    print("  implemented so far: doctor (environment, numba, Qt, the cube's header); the viewer comes with ROADMAP E3",
          flush=True)
    from . import doctor

    return doctor.main([cube] + ([] if a.no_window else ["--show"]))


if __name__ == "__main__":
    sys.exit(main())

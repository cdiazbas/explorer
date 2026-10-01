"""The `explorer` command: `explorer cube.fits` opens a cube, `explorer <subcommand> ...` runs a tool.

Imports stay light here: a subcommand's module (and Qt, numba, astropy) is imported only when that
subcommand runs, so `explorer --version` and `explorer doctor --help` answer at once.
"""
import argparse
import os
import sys

from . import __version__
from ._name import APP_NAME, ENV_PREFIX

# name -> (module, one-line help). Each module has main(argv) -> exit code.
SUBCOMMANDS = {
    "doctor": ("doctor", "check that this user can run explorer here (environment, numba, Qt, a cube)"),
    "demo": ("demo", "try what explorer can do so far, on a cube (default: a small synthetic one)"),
}


def _parser() -> argparse.ArgumentParser:
    lines = "\n".join(f"  {n:10s} {h}" for n, (_, h) in SUBCOMMANDS.items())
    ap = argparse.ArgumentParser(
        prog=APP_NAME, formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Viewer for solar spectropolarimetric cubes [t, Stokes, lambda, y, x].",
        epilog=f"subcommands (explorer <subcommand> --help):\n{lines}")
    ap.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    ap.add_argument("cube", nargs="?", help="a cube to open (_im.fits); its per-pixel file is found next to it")
    ap.add_argument("--sp", help="this per-pixel file instead of the one found next to the cube")
    ap.add_argument("--nosp", action="store_true", help="read without the per-pixel file")
    ap.add_argument("--axes", help="what the leading axes are, slowest first, e.g. t,l or s,l (l is lambda), for "
                                   "cubes whose header does not say it")
    ap.add_argument("--x11", choices=("auto", "native", "bridge"), default="auto",
                    help="over ssh -Y: Qt's own X11 (native) or the bridge; auto decides")
    ap.add_argument("--theme", choices=("auto", "dark", "light", "native"), default="auto",
                    help="dark or light everywhere; native: the system's (macOS); auto: native on a Mac, else dark")
    ap.add_argument("--look", choices=("classic", "modern"), default=None,
                    help="classic: red cursor and markers; modern: reticle, accent marks, cards, Stokes segments, "
                         "colour maps on C (EXPLORER_LOOK_OFF=part,...: leave parts out). M switches while it runs; "
                         "without --look, the one worn at the last close")
    ap.add_argument("--reset-layout", action="store_true",
                    help="start with the first window's size and panels (the saved layout of this display is dropped)")
    ap.add_argument("--quit-after", type=float, metavar="S", help="quit S seconds after the first image (measurements)")
    return ap


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    from . import obs  # standard library only: cheap

    obs.setup_from_env()                                # EXPLORER_LOG
    if os.environ.get(ENV_PREFIX + "TRACE"):            # EXPLORER_TRACE=t.json: Perfetto trace of the spans
        obs.trace.start(os.environ[ENV_PREFIX + "TRACE"])
    if argv and argv[0] in SUBCOMMANDS:
        import importlib

        mod = importlib.import_module(f".{SUBCOMMANDS[argv[0]][0]}", __package__)
        return mod.main(argv[1:])
    a = _parser().parse_args(argv)
    if a.cube is None:
        _parser().print_help()
        return 0
    if not os.path.exists(a.cube):
        print(f"{APP_NAME}: no such file: {a.cube}", file=sys.stderr)
        return 2
    from .ui.app import run

    return run(a.cube, sp=a.sp, no_sp=a.nosp, axes=a.axes, x11=a.x11, theme=a.theme,
               look=a.look, reset_layout=a.reset_layout, quit_after=a.quit_after)

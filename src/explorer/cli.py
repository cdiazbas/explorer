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
        description="Viewer for solar spectropolarimetric cubes [t, Stokes, lambda, y, x]: SOLARNET FITS (_im.fits) "
                    "and La Palma cubes (.icube, .fcube).",
        epilog=f"""examples:
  explorer stokes_6173_im.fits                  one cube; its per-pixel file (_sp) is found next to it
  explorer stokes_6173_im.icube                 a La Palma cube: its axes from its _sp file or the scans in its name
  explorer Blos.6173_map.fcube --axes t         a map whose frames are times (nothing in the file says so)
  explorer stokes_6173_im.icube Blos.6173_map.fcube Vlos.6173_map.icube
                                                linked cubes: the first leads; the others, on its pixels, show beside
                                                it and follow its cursor and t (their times nearest to its), each at
                                                its own λ (other pixels: not linked yet, and said why)
  explorer --series aia*.fits                   one image per file (e.g. SDO/AIA), the files as one cube's t, in
                                                the order of their header times (T_OBS, DATE-AVG or DATE-OBS)
  explorer stokes_6173_sp.fits                  a per-pixel file: its _im beside it is opened with it; without one,
                                                its images are read from it (slow: each one a pass over the file)
  explorer stokes_6173_im.fits --mask spots.fits
                                                the outline of a 0/1 mask on the first cube's pixels over every
                                                image: one frame at every t, or one per t
subcommands (explorer <subcommand> --help):
{lines}

explorer --demo is explorer demo""")
    ap.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    ap.add_argument("cubes", nargs="*", metavar="cube",
                    help="a cube to open: _im.fits, or a La Palma .icube / .fcube; its per-pixel file is found next "
                         "to it. More cubes: linked to the first (the same pixels; at each of its times, their "
                         "nearest; without times, as many as its; a map of one frame is shown at every t); a cube that "
                         "cannot be linked yet is left out, with the reason")
    ap.add_argument("--series", action="store_true",
                    help="the files given are one cube, one image (y, x) per file, its t in their header times' "
                         "order (T_OBS, else DATE-AVG, else DATE-OBS; without times, their names'); a quoted "
                         "pattern (\"aia*.fits\") is expanded here, in name order")
    ap.add_argument("--sp", help="this per-pixel file instead of the one found next to the (first) cube; the cube "
                                 "itself, when it is a per-pixel FITS file: opened alone, its images read from it "
                                 "(as without its _im beside it: slow, each image a pass over the file)")
    ap.add_argument("--nosp", action="store_true", help="read without the per-pixel files")
    ap.add_argument("--axes", help="what the (first) cube's leading axes are, slowest first: t,s,l, s,l, t,l, or t "
                                   "for a map whose frames are times (l is lambda), for cubes whose header or name "
                                   "does not say it")
    ap.add_argument("--mask", metavar="FILE",
                    help="a mask on the first cube's pixels, outlined on every image where it is 1 or more: FITS or "
                         "a La Palma .icube / .fcube, one frame (y, x) shown at every t, or one per t (t, y, x); "
                         "another grid or number of frames is left out, with the reason")
    ap.add_argument("--x11", choices=("auto", "native", "bridge"), default="auto",
                    help="over ssh -Y: Qt's own X11 (native) or the bridge; auto decides")
    from .ui.app import window_options

    window_options(ap)
    ap.add_argument("--quit-after", type=float, metavar="S", help="quit S seconds after the first image (measurements)")
    return ap


REEXEC_ENV = ENV_PREFIX + "REEXEC"
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # src/explorer/cli.py: the tree


def clean_library_path(environ, platform: str, root: str = ROOT) -> dict | None:
    """The environment to start again in, before Qt loads, or None to go on. On Linux another environment's
    LD_LIBRARY_PATH (conda's, from .bashrc) loads its own Qt and PySide6 fails (Qt_6_PRIVATE_API, bellatrix
    2026-09-28): without it, or with the tree's .qtlibs/only alone (libxcb-cursor, what scripts/run.sh sets). Once
    only (EXPLORER_REEXEC). From the prototype's test.py:19-28."""
    if not platform.startswith("linux") or environ.get(REEXEC_ENV):
        return None
    qt = os.path.join(root, ".qtlibs", "only")
    want = qt if os.path.isdir(qt) else ""
    if environ.get("LD_LIBRARY_PATH", "") == want:
        return None
    env = dict(environ)
    env[REEXEC_ENV] = "1"
    env.pop("LD_LIBRARY_PATH", None)
    if want:
        env["LD_LIBRARY_PATH"] = want
    return env


def main(argv: list[str] | None = None) -> int:
    if argv is None:                                    # the command itself, not a call from a test
        env = clean_library_path(os.environ, sys.platform)
        if env is not None:
            # the command line as given: under `python -m explorer` sys.argv[0] is __main__.py, a script there
            os.execve(sys.executable, [sys.executable] + sys.orig_argv[1:], env)
    argv = sys.argv[1:] if argv is None else list(argv)
    from . import obs  # standard library only: cheap

    obs.setup_from_env()                                # EXPLORER_LOG
    if os.environ.get(ENV_PREFIX + "TRACE"):            # EXPLORER_TRACE=t.json: Perfetto trace of the spans
        obs.trace.start(os.environ[ENV_PREFIX + "TRACE"])
    if argv and argv[0] == "--demo":                    # the subcommand as one would guess it, an option
        argv = ["demo"] + argv[1:]
    if argv and argv[0] in SUBCOMMANDS:
        import importlib

        mod = importlib.import_module(f".{SUBCOMMANDS[argv[0]][0]}", __package__)
        return mod.main(argv[1:])
    a = _parser().parse_args(argv)
    if not a.cubes:
        _parser().print_help()
        return 0
    if a.series:                                        # a pattern the shell left alone (quoted, or no match)
        import glob

        a.cubes = [f for c in a.cubes for f in (sorted(glob.glob(c)) if glob.has_magic(c) else [c])] or a.cubes
    for c in a.cubes + ([a.mask] if a.mask else []):
        if not os.path.exists(c):
            print(f"{APP_NAME}: no such file: {c}", file=sys.stderr)
            return 2
    from .ui.app import run

    return run(a.cubes[0], sp=a.sp, no_sp=a.nosp, axes=a.axes, x11=a.x11, theme=a.theme, look=a.look,
               reset_layout=a.reset_layout, traces=a.log, quit_after=a.quit_after,
               linked=[] if a.series else a.cubes[1:], mask=a.mask, series=a.cubes if a.series else None)

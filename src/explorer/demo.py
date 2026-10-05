"""`explorer demo`: run the most complete thing explorer can do so far, on a cube, to try it at any moment.

    explorer demo [cube_im.fits] [--no-window] [--x11 auto|native|bridge]

Without a cube it uses a small synthetic one (explorer.testing.synth), written once to ~/.cache/explorer/demo/:
the right default on a machine without the shared test cubes (a Mac on its local disk, where big cubes are not
welcome). scripts/demo.sh picks the real test cube when the project's data/ link resolves.

What it runs grows with the ROADMAP; today: the viewer on the cube (the image, and keys for t, lambda and Stokes:
ROADMAP E3.6), and doctor's checks only when the window cannot open or with --doctor. With --no-window, doctor
and then, instead of the viewer, a cursor walk through the data layer:
the cursor visits pixels across the field and each move prints how long the spectrum and the lambda-t took, with
the per-pixel file (default, when there is one) or without it (--nosp), so both can be compared on the same cube:
first jumps across the field, then a drag in 1-pixel steps.

    explorer demo [cube] [--nosp | --sp FILE] [--moves N] [--no-window]
"""
import argparse
import os
import sys

from . import __version__
from ._name import APP_NAME
from ._paths import cache_dir


def synthetic_cube() -> str:
    """The cached synthetic demo cube and its per-pixel file (_sp.fits), written once, atomically (a half-written
    set is never used); cubes of older synthetic versions are removed."""
    import shutil

    from .testing import synth

    d = cache_dir() / "demo"
    d.mkdir(parents=True, exist_ok=True)
    name = f"synth_stokes_v{synth.SYNTH_VERSION}"
    path = d / f"{name}_im.fits"
    for old in d.glob("synth_stokes_v*"):
        if not old.name.startswith(name + "_"):
            old.unlink()
    if not path.exists():
        print(f"writing the synthetic demo cube (once): {path}", flush=True)
        tmp = d / f".tmp{os.getpid()}"
        try:
            paths = synth.write_dataset(tmp, name, icube=False)
            os.replace(paths["sp"], d / os.path.basename(paths["sp"]))
            os.replace(paths["im"], path)                  # last: its presence means the set is complete
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return str(path)


def cursor_walk(cube, sp=None, no_sp=False, moves=12, drag=False, axes=None) -> dict:
    """Move a cursor over `moves` pixels on a diagonal across the middle of the field (shifted at random on each
    run), each on a row not visited before, and time what the viewer would read at each: the spectrum (all Stokes
    and lambda at t = 0), then the lambda-t of Stokes I (all t and lambda). With a per-pixel file both come from
    one block; without it, the spectrum is read first and the lambda-t after, as the viewer shows them.
    drag: 1-pixel steps instead (right, and one row down every 4 moves), as a mouse dragged across the image.
    Returns the medians in ms."""
    import statistics
    import time

    import numpy as np

    from .data.dataset import Dataset

    with Dataset.open(cube, sp=sp, no_sp=no_sp, axes=axes) as ds:
        r = ds.roles
        print(f"cursor walk: {ds.describe()}; axes t/s/l at {tuple(r[:3])} ({r.how})", flush=True)
        if r.t is None or r.l is None:
            print("  no t or no lambda axis: nothing to walk", flush=True)
            return {}
        idx = [0] * len(ds.shape[:-2])
        idx[r.l] = r.nl // 2
        spec_axes = sorted(a for a in (r.s, r.l) if a is not None)
        lt_axes = sorted((r.t, r.l))
        # shifted at random on each run, so a second run does not find the first one's pixels in the OS cache
        dy, dx = (int(v) for v in np.random.default_rng().integers(-(ds.ny // 10), ds.ny // 10 + 1, 2))
        if drag:
            step = np.arange(moves)
            ys = np.clip(ds.ny // 2 + dy + step // 4, 0, ds.ny - 1)
            xs = np.clip(ds.nx // 2 + dx + step, 0, ds.nx - 1)
        else:
            ys = np.clip(np.linspace(ds.ny * 0.3, ds.ny * 0.7, moves).astype(int) + dy, 0, ds.ny - 1)
            xs = np.clip(np.linspace(ds.nx * 0.3, ds.nx * 0.7, moves).astype(int) + dx, 0, ds.nx - 1)
        print(f"  {'drag, 1-pixel steps' if drag else 'jumps across the field'}:", flush=True)
        spec_ms, lt_ms = [], []
        for k, (y, x) in enumerate(zip(ys.tolist(), xs.tolist(), strict=True)):
            q = time.perf_counter()
            if ds.pixel is not None:
                ds.pixel_block(y, x).result()                  # (s, t, lambda): both from one read
                spec_ms.append((time.perf_counter() - q) * 1e3)
                lt_ms.append(spec_ms[-1])
            else:
                ds.series(y, x, idx, spec_axes).result()
                spec_ms.append((time.perf_counter() - q) * 1e3)
                ds.series(y, x, idx, lt_axes).result()
                lt_ms.append((time.perf_counter() - q) * 1e3)
            print(f"  move {k + 1:2d}  pixel ({y:4d}, {x:4d})  spectrum {spec_ms[-1]:7.1f} ms   "
                  f"lambda-t {lt_ms[-1]:7.1f} ms", flush=True)
        med = dict(spectrum=statistics.median(spec_ms), lambda_t=statistics.median(lt_ms))
        src = f"per-pixel file ({ds.pixel.kind})" if ds.pixel is not None else "no per-pixel file"
        print(f"  median over {moves} {'steps' if drag else 'moves'}, {src}: spectrum {med['spectrum']:.1f} ms, "
              f"lambda-t {med['lambda_t']:.1f} ms (from the move to its lambda-t on screen)", flush=True)
        return med


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog=f"{APP_NAME} demo", description="try what explorer can do so far, on a cube")
    ap.add_argument("cube", nargs="?", help="default: a small synthetic cube")
    ap.add_argument("--no-window", action="store_true", help="do not open any window (headless runs, tests)")
    ap.add_argument("--doctor", action="store_true", help="run doctor's checks after the viewer closes")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--nosp", action="store_true", help="read without the per-pixel file, from the image cube")
    g.add_argument("--sp", help="this per-pixel file instead of the one found next to the cube")
    ap.add_argument("--moves", type=int, default=12, help="with --no-window: cursor moves in the walk (default 12)")
    ap.add_argument("--x11", choices=("auto", "native", "bridge"), default="auto",
                    help="over ssh -Y: Qt's own X11 (native) or the X11 bridge; auto decides (the bridge over ssh)")
    ap.add_argument("--axes", help="what the leading axes are, slowest first, e.g. t,l or s,l (l is lambda); "
                                   "for cubes whose header does not say it")
    from .ui.app import window_options

    window_options(ap)
    a = ap.parse_args(argv)
    cube = a.cube or synthetic_cube()
    kind = "synthetic" if a.cube is None else "given"
    print(f"{APP_NAME} {__version__} demo on the {kind} cube {cube}", flush=True)
    print("  implemented so far: doctor (environment, numba, Qt, the cube's header), the data layer and the core "
          "(cursor walk with --no-window), and the viewer's image window", flush=True)
    from . import doctor

    if not a.no_window:                                 # the viewer first, as the prototype's demo: doctor's checks
        from .ui.app import run  # (numba, Qt in its own process) cost 4.1 s over ssh -Y

        rc = run(cube, sp=a.sp, no_sp=a.nosp, axes=a.axes, x11=a.x11, theme=a.theme, look=a.look,
                 reset_layout=a.reset_layout, traces=a.log)
        if rc or a.doctor:                              # the window could not open: say why
            rc = doctor.main([cube]) or rc
        return rc
    rc = doctor.main([cube])
    if a.moves > 0:
        cursor_walk(cube, sp=a.sp, no_sp=a.nosp, moves=a.moves, axes=a.axes)
        cursor_walk(cube, sp=a.sp, no_sp=a.nosp, moves=a.moves, drag=True, axes=a.axes)
    return rc


if __name__ == "__main__":
    sys.exit(main())

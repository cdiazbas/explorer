"""Opening a cube in a window: the display plan, the application, the Dataset and the Shell. Used by `explorer
cube.fits` and by the demo."""
import os
import sys
import time

from .._name import APP_NAME
from ..obs import get_logger

log = get_logger("ui")


def process_age() -> float | None:
    """Seconds since this process started (Linux: /proc), so the time to the first image includes Python's own start
    and imports; None where it is not known."""
    try:
        start_ticks = int(open("/proc/self/stat").read().rsplit(")", 1)[1].split()[19])
        uptime = float(open("/proc/uptime").read().split()[0])
        return uptime - start_ticks / os.sysconf("SC_CLK_TCK")
    except (OSError, ValueError, IndexError):
        return None


def run(path, *, sp=None, no_sp=False, axes=None, x11="auto", quit_after: float | None = None) -> int:
    """Open path and run the event loop until the window closes; returns the exit code. quit_after: seconds after the
    first image, then quit (measurements, as the prototype's --quit-after)."""
    t0 = time.perf_counter()
    before = process_age()                              # Python's start and the imports up to here
    phases: dict[str, float] = {}
    from ..platform.display import NoDisplay, for_plan
    from ..platform.plan import choose_display

    plan = choose_display(os.environ, sys.platform, x11)
    for note in plan.notes:
        print(f"[{APP_NAME}] {note}", file=sys.stderr)
    disp = for_plan(plan)
    try:
        disp.prepare_env()
        q = time.perf_counter()
        app = disp.make_app()
        phases["Qt"] = time.perf_counter() - q
    except NoDisplay as e:
        print(e, file=sys.stderr)
        return 1
    from ..data.dataset import Dataset
    from .shell import Shell

    q = time.perf_counter()
    ds = Dataset.open(path, sp=sp, no_sp=no_sp, axes=axes)
    phases["cube"] = time.perf_counter() - q
    try:
        q = time.perf_counter()
        shell = Shell(ds, title=f"{os.path.basename(str(path))} — {APP_NAME}", t0=t0)
        phases["window"] = time.perf_counter() - q
        shown = "X11 bridge" if plan.bridge else plan.platform
        shell.breakdown = (before, phases, shown, plan.remote)
        geo = app.primaryScreen().availableGeometry()
        shell.resize(int(geo.width() * 0.8), int(geo.height() * 0.8))
        disp.attach(app, shell)
        log.info("%s; %s", ds.describe(), disp.stats())
        if quit_after is not None:
            shell.after_first_image(quit_after, app.quit)
        return app.exec()                           # 1 when the X display went away under the bridge
    finally:
        ds.close()
        disp.close()

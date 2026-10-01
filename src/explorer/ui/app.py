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


def themed_app(disp, theme: str = "auto"):
    """The QApplication with its theme (ui.style), before any window builds its plots; returns (app, theme applied).
    Through the X11 bridge auto is dark: the bridge shows what Qt draws, wherever the display is (the prototype's
    make_app)."""
    from . import style

    app = disp.make_app()
    return app, style.apply_theme(app, "dark" if disp.plan.bridge and theme == "auto" else theme)


def run(path, *, sp=None, no_sp=False, axes=None, x11="auto", theme="auto", look="classic", reset_layout=False,
        quit_after: float | None = None) -> int:
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
        app, theme = themed_app(disp, theme)
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
        from ..look import get_look

        shell = Shell(ds, title=f"{os.path.basename(str(path))} — {APP_NAME}", t0=t0, look=get_look(look))
        phases["window"] = time.perf_counter() - q
        shown = "X11 bridge" if plan.bridge else plan.platform
        shell.breakdown = (before, phases, shown, plan.remote)
        from . import titlebar

        ops = shell.window_ops = disp.ops(shell)        # before show: our title bar makes the window frameless
        shell.title_bar = titlebar.chrome(app, shell, ops, disp.ops, bridge=plan.bridge)
        from .layout import LayoutStore

        shell.layout = LayoutStore(plan.kind)
        if reset_layout:
            shell.layout.forget()
        if shell.layout.restore(shell, app):            # the last session's panels, their sizes with them
            shell._sized = True
        disp.attach(app, shell, ops)
        from . import termkeys

        shell.terminal_keys = termkeys.attach(shell)     # over ssh -Y the keyboard stays in the terminal until a click
        if shell.terminal_keys is not None:
            print(f"[{APP_NAME}] keys typed in this terminal also reach the window ({termkeys.ENV}=0: off)",
                  file=sys.stderr, flush=True)
        link = disp.link()
        if plan.remote and link.bytes_per_px is not None:
            shell.start_link_probe(link)                # the default playback rate from what the link carries
        log.info("%s; %s", ds.describe(), disp.stats())
        if quit_after is not None:
            shell.after_first_image(quit_after, app.quit)
        return app.exec()                           # 1 when the X display went away under the bridge
    finally:
        ds.close()
        disp.close()

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


def chrome(app, shell, ops, ops_for, bridge: bool):
    """titlebar.chrome on a window that already wears its look: the dock titles it puts on are the panels' own, and
    the glass look's are put back over them (the prototype puts the titles on first, startup.py:145, then the
    look)."""
    from . import titlebar

    bar = titlebar.chrome(app, shell, ops, ops_for, bridge=bridge)
    if shell.glass is not None:
        shell.glass.titles_changed()
    return bar


def window_options(ap) -> None:
    """--theme, --look and --reset-layout on an argparse parser: the window's options, for `explorer` and
    `explorer demo` alike (run() takes them by these names)."""
    ap.add_argument("--theme", choices=("auto", "dark", "light", "native"), default="auto",
                    help="dark or light everywhere; native: the system's (macOS); auto: native on a Mac, else dark")
    ap.add_argument("--look", choices=("classic", "modern", "glass"), default=None,
                    help="classic: red cursor and markers; modern: reticle, accent marks, cards, Stokes drop-down, "
                         "colour maps on C (EXPLORER_LOOK_OFF=part,...: leave parts out); glass: the image to the "
                         "window's edges, the controls on a bar over it, the panels floating beside it. M switches "
                         "while it runs; "
                         "without --look, the one worn at the last close")
    ap.add_argument("--reset-layout", action="store_true",
                    help="start with the first window's size and panels (the saved layout of this display is dropped)")


def run(path, *, sp=None, no_sp=False, axes=None, x11="auto", theme="auto", look=None, reset_layout=False,
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
    try:
        ds = Dataset.open(path, sp=sp, no_sp=no_sp, axes=axes)
    except (ValueError, OSError) as e:                  # a file it cannot read as a cube: say so, no traceback
        print(f"[{APP_NAME}] cannot open {path}: {e}", file=sys.stderr)
        return 1
    phases["cube"] = time.perf_counter() - q
    try:
        q = time.perf_counter()
        from ..look import LOOKS, get_look
        from .layout import LayoutStore

        store = LayoutStore(plan.kind)
        if reset_layout:
            store.forget()
        if look is None:                                # the one worn at the last close, else classic
            look = store.look() if store.look() in LOOKS else "classic"
        from . import geomtrace

        tracer = geomtrace.install_from_env()           # EXPLORER_GEOMETRY_TRACE=1: before the window, to see it all
        shell = Shell(ds, title=f"{os.path.basename(str(path))} — {APP_NAME}", t0=t0, look=get_look(look))
        phases["window"] = time.perf_counter() - q
        shown = "X11 bridge" if plan.bridge else plan.platform
        shell.breakdown = (before, phases, shown, plan.remote)
        ops = shell.window_ops = disp.ops(shell)        # before show: our title bar makes the window frameless
        shell.title_bar = chrome(app, shell, ops, disp.ops, bridge=plan.bridge)
        shell.layout_store = store
        if store.for_look(look).restore(shell, app):    # the last session's panels (the glass look's own), sizes too
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
        code = app.exec()                           # 1 when the X display went away under the bridge
        if tracer is not None:
            tracer.stop()
        return code
    finally:
        ds.close()
        disp.close()

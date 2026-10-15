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
    app_icon(app)                                       # first: on a Mac the Dock shows a blank icon until then
    return app, style.apply_theme(app, "dark" if disp.plan.bridge and theme == "auto" else theme)


def chrome(app, shell, ops, ops_for, bridge: bool):
    """titlebar.chrome on a window that already wears its look: the dock titles it puts on are the panels' own, and
    the glass look's are put back over them (the prototype puts the titles on first, startup.py:145, then the
    look)."""
    from . import titlebar

    bar = titlebar.chrome(app, shell, ops, ops_for, bridge=bridge)
    shell.title_bar = bar                               # before the look hears of it: glass recolours it
    if shell.glass is not None:
        shell.glass.titles_changed()
    return bar


def app_icon(app) -> None:
    """ui.appicon on the application as soon as it exists. An unbundled Python on a Mac enters the Dock with Qt's
    application, under the blank icon of a bare executable, and keeps it until this is set: anything run before it
    (the theme, the cube, the window) is that much longer with the blank icon. Started through the app bundle of
    scripts/run.sh, the Dock has the icon from launch and this leaves it."""
    from . import appicon

    appicon.install(app)


def window_options(ap) -> None:
    """--theme, --look, --reset-layout and --log on an argparse parser: the window's options, for `explorer` and
    `explorer demo` alike (run() takes them by these names)."""
    ap.add_argument("--theme", choices=("auto", "dark", "light", "native"), default=None,
                    help="dark or light everywhere; native: the system's (macOS); auto: native on a Mac, else dark. "
                         "T switches dark and light while it runs; without --theme, the one in use at the last "
                         "close on this way of displaying, else auto")
    ap.add_argument("--look", choices=("classic", "modern", "glass"), default=None,
                    help="classic: red cursor and markers; modern: reticle, accent marks, cards, Stokes drop-down, "
                         "colour maps on C (EXPLORER_LOOK_OFF=part,...: leave parts out); glass: the image to the "
                         "window's edges, the controls on a bar over it, the panels floating beside it. M switches "
                         "while it runs; "
                         "without --look, the one worn at the last close")
    ap.add_argument("--reset-layout", action="store_true",
                    help="start with the first window's size and panels (the saved layout of this display is dropped)")
    ap.add_argument("--log", action="store_true",
                    help="keep traces of this session, to send with a problem: every move and resize of the window "
                         "and its panels and, through the X11 bridge, what goes to the X server and its errors "
                         "(~/.cache/explorer/logs, named at the close; the newest 30 of each kind kept)")


class Started:
    """A window up as `explorer cube` shows it (start()): the application, the Shell, its Dataset and display.
    t0: when start() began (the Shell's first_image_s counts from it); app_ready: when the application existed (the
    prototype's self-test counts from there); theme: the one applied; linked: the cubes linked to it. close() lets go
    of the cubes and the display."""

    def __init__(self, app, shell, ds, disp, plan, tracer, t0, app_ready, theme, linked=(), mask=None):
        self.app, self.shell, self.ds, self.disp, self.plan, self.tracer = app, shell, ds, disp, plan, tracer
        self.t0, self.app_ready, self.theme, self.linked, self.mask = t0, app_ready, theme, list(linked), mask

    def close(self) -> None:
        if self.tracer is not None:
            self.tracer.stop()
            print(f"[geometry] the trace of this session: {self.tracer.path}", file=sys.stderr)
        for d in [*self.linked, self.ds]:               # the long reads in flight stop first: no close waits for one
            d.abort()
        for d in self.linked:                           # first: they run on the main cube's threads
            d.close()
        if self.mask is not None:
            self.mask.close()
        self.ds.close()
        self.disp.close()


TRACES = ("EXPLORER_GEOMETRY_TRACE", "EXPLORER_BRIDGE_TRACE")      # what --log turns on (ui.geomtrace, xbridge.trace)


def plan_links(path, others, axes=None) -> list:
    """data.link's plan for each of the other cubes against the first (path, read with axes): the ones that link,
    in order; each refused one's reason, and how each linked one's axes were read, on stderr."""
    from ..data.link import describe, plan

    main = describe(path, axes)
    links = []
    for p in others:
        link = plan(main, p)
        if link.ok:
            print(f"[{APP_NAME}] linked {os.path.basename(str(p))}: {link.how}", file=sys.stderr)
            links.append(link)
        else:
            print(f"[{APP_NAME}] not linked: {link.why}", file=sys.stderr)
    return links


def open_mask(path, main):
    """data.mask's Mask at path over the first cube (main, a Dataset), how its frames follow t on stderr; None, and
    why, when it cannot be drawn on it (the window opens without it, as a cube that cannot be linked)."""
    from ..data.mask import Mask, MaskRefused

    try:
        mask = Mask.open(path, main)
    except MaskRefused as e:
        print(f"[{APP_NAME}] no mask: {e}", file=sys.stderr)
        return None
    print(f"[{APP_NAME}] {mask.describe()}", file=sys.stderr)
    return mask


def given_cubes(path, sp, no_sp, linked) -> tuple[str, str | None, list[str], dict[str, str]]:
    """The cubes to open for those given: a per-pixel file given as a cube becomes its image cube, opened with it
    (formats.opening), said in one line on stderr; (first cube, its per-pixel file, the linked cubes, their
    per-pixel files by path). A FITS per-pixel file without its image cube opens alone (its images read from it).
    The first cube's ValueError (an LP per-pixel file without its image cube, --sp naming an image cube) is the
    caller's; a linked one's leaves that cube out, with the reason, as data.link's refusals, and so does a linked
    per-pixel file alone. A linked per-pixel file of the first cube is taken as its per-pixel file, not linked to
    it."""
    from ..data.formats import opening

    first = opening(path, sp, no_sp)
    if first.note:
        print(f"[{APP_NAME}] {first.note}", file=sys.stderr)
    path, sp = first.path, first.sp
    others: list[str] = []
    sps: dict[str, str] = {}
    for p in linked:
        try:
            o = opening(p, None, no_sp)
        except (ValueError, OSError) as e:
            print(f"[{APP_NAME}] not linked: {e}", file=sys.stderr)
            continue
        if o.sp is not None and o.path == o.sp:        # a per-pixel file alone: an image is a pass over it
            print(f"[{APP_NAME}] not linked: {os.path.basename(str(p))} is a per-pixel file without its image cube "
                  f"beside it", file=sys.stderr)
            continue
        if o.sp is not None and os.path.realpath(o.path) == os.path.realpath(path):
            if sp is None:
                sp = o.sp
                print(f"[{APP_NAME}] {os.path.basename(str(p))} is the per-pixel file of {os.path.basename(path)}: "
                      f"opened with it, not linked to it", file=sys.stderr)
            else:
                print(f"[{APP_NAME}] not linked: {os.path.basename(str(p))} is a per-pixel file of "
                      f"{os.path.basename(path)}, which --sp gives one already", file=sys.stderr)
            continue
        if o.note:
            print(f"[{APP_NAME}] {o.note}", file=sys.stderr)
        others.append(o.path)
        if o.sp is not None:
            sps[o.path] = o.sp
    return path, sp, others, sps


def start(path, *, sp=None, no_sp=False, axes=None, x11="auto", theme=None, look=None, reset_layout=False, traces=False,
          saved_layout=True, linked=(), mask=None, series=None) -> Started | None:
    """Everything `explorer cube` does before its event loop: the display plan, the themed application, the cube,
    the Shell with its title bar, its saved layout, the display's attachment, the terminal's keys and the link probe.
    The self-test (bench/explorer_selftest.py) goes through it too, so it measures the window as it is shown (as the
    prototype's app/startup.py, audit F4). saved_layout False: the user's saved layout is neither read, nor written
    at the close, nor dropped. theme None: the one in use at the last close on this way of displaying, else auto.
    traces: the session's traces (TRACES: the geometry's and, through the bridge, the bridge's), as --log asks.
    linked: other cubes, linked to this one (ROADMAP E8.1) where data.link finds they can be, each with its own
    per-pixel file unless no_sp; sp and axes are the first cube's. mask: a mask file outlined on every image
    (ROADMAP E8.2, data.mask), left out with the reason when it does not fit the first cube. series: FITS files,
    one image each, opened as one cube along t (data.formats.series_layout) instead of path. None (and why, on
    stderr) when there is no display or the first cube cannot be read."""
    t0 = time.perf_counter()
    if traces:                                          # before the bridge and the window, which read them once
        for name in TRACES:
            os.environ[name] = "1"
    before = process_age()                              # Python's start and the imports up to here
    phases: dict[str, float] = {}
    from ..platform.display import NoDisplay, for_plan
    from ..platform.plan import choose_display

    plan = choose_display(os.environ, sys.platform, x11)
    for note in plan.notes:
        print(f"[{APP_NAME}] {note}", file=sys.stderr)
    disp = for_plan(plan)
    from .layout import LayoutStore
    from .style import THEMES

    q = time.perf_counter()
    try:
        path, sp, linked, linked_sp = (given_cubes(path, sp, no_sp, linked) if series is None
                                       else (path, None, [], {}))
    except (ValueError, OSError) as e:                  # a per-pixel file without its image cube: what is needed
        print(f"[{APP_NAME}] {e}", file=sys.stderr)
        return None
    try:
        links = plan_links(path, linked, axes) if linked else []
    except (ValueError, OSError) as e:                  # the first cube: reported as below, when opened
        print(f"[{APP_NAME}] cannot open {path}: {e}", file=sys.stderr)
        return None
    if links:
        phases["links"] = time.perf_counter() - q
    store = LayoutStore(plan.kind, linked=bool(links)) if saved_layout else None
    if theme is None:                                   # the one in use at the last close, else auto
        kept = store.theme() if store is not None else None
        theme = kept if kept in THEMES else "auto"
    try:
        disp.prepare_env()
        q = time.perf_counter()
        app, theme = themed_app(disp, theme)
        app_ready = time.perf_counter()
        phases["Qt"] = app_ready - q
    except NoDisplay as e:
        print(e, file=sys.stderr)
        return None
    from ..data.dataset import Dataset
    from ..data.policy import GuardShare, MemoryGuard
    from .shell import Shell

    q = time.perf_counter()
    # linked cubes: one memory budget shared, the first cube's threads (one runs parallel numba for all)
    guard = GuardShare(MemoryGuard(), 1 + len(links)) if links else None
    try:
        ds = Dataset.open(path, sp=sp, no_sp=no_sp, axes=axes, guard=guard, series=series)
    except (ValueError, OSError) as e:                  # a file it cannot read as a cube: say so, no traceback
        print(f"[{APP_NAME}] cannot open {'the series' if series is not None else path}: {e}", file=sys.stderr)
        return None
    if series is not None:
        for note in getattr(ds.layout, "notes", ()):
            print(f"[{APP_NAME}] {note}", file=sys.stderr)
    others: list = []
    try:
        for link in links:
            others.append(Dataset.open(link.path, sp=linked_sp.get(link.path), no_sp=no_sp, axes=link.axes,
                                       guard=guard, executors=ds.executors))
    except (ValueError, OSError) as e:
        print(f"[{APP_NAME}] cannot open {link.path}: {e}", file=sys.stderr)
        for d in others:
            d.close()
        ds.close()
        return None
    masked = open_mask(mask, ds) if mask is not None else None
    phases["cube"] = time.perf_counter() - q
    try:
        q = time.perf_counter()
        from ..look import LOOKS, get_look

        if reset_layout and store is not None:
            store.forget()
        if look is None:                                # the one worn at the last close, else classic
            look = store.look() if store is not None and store.look() in LOOKS else "classic"
        from . import geomtrace

        tracer = geomtrace.install_from_env()           # EXPLORER_GEOMETRY_TRACE=1: before the window, to see it all
        series_paths: tuple[str, ...] = getattr(ds.layout, "paths", ())
        names = (" + ".join(os.path.basename(str(p)) for p in [path, *(lk.path for lk in links)]) if series is None
                 else f"{os.path.basename(ds.path)} … {os.path.basename(series_paths[-1])} "
                      f"({len(series_paths)} files)")
        shell = Shell(ds, title=f"{names} — {APP_NAME}", t0=t0, look=get_look(look), linked=others, mask=masked)
        phases["window"] = time.perf_counter() - q
        shown = "X11 bridge" if plan.bridge else plan.platform
        shell.breakdown = (before, phases, shown, plan.remote)
        ops = shell.window_ops = disp.ops(shell)        # before show: our title bar makes the window frameless
        shell.title_bar = chrome(app, shell, ops, disp.ops, bridge=plan.bridge)
        shell.layout_store = store
        shell.theme = theme
        if store is not None and store.for_look(look).restore(shell, app):   # the last session's panels, sizes too
            shell._sized = True
        if store is not None:                           # each cube's limits and gamma, by its file name
            shell.restore_scale(store.scale())
        disp.attach(app, shell, ops)
        shell.session.pace.offer = disp.screen()        # held for once the link probe finds it slow (core.pace)
        from . import termkeys

        shell.terminal_keys = termkeys.attach(shell)     # over ssh -Y the keyboard stays in the terminal until a click
        if shell.terminal_keys is not None:
            print(f"[{APP_NAME}] keys typed in this terminal also reach the window ({termkeys.ENV}=0: off)",
                  file=sys.stderr, flush=True)
        link = disp.link()
        if plan.remote and link.bytes_per_px is not None:
            shell.start_link_probe(link)                # the default playback rate from what the link carries
        log.info("%s; %s", ds.describe(), disp.stats())
        return Started(app, shell, ds, disp, plan, tracer, t0, app_ready, theme, others, masked)
    except BaseException:
        for d in others:
            d.close()
        if masked is not None:
            masked.close()
        ds.close()
        disp.close()
        raise


def run(path, *, sp=None, no_sp=False, axes=None, x11="auto", theme=None, look=None, reset_layout=False, traces=False,
        quit_after: float | None = None, linked=(), mask=None, series=None) -> int:
    """Open path (and the cubes linked to it) and run the event loop until the window closes; returns the exit
    code. quit_after: seconds after the first image, then quit (measurements, as the prototype's --quit-after)."""
    s = start(path, sp=sp, no_sp=no_sp, axes=axes, x11=x11, theme=theme, look=look, reset_layout=reset_layout,
              traces=traces, linked=linked, mask=mask, series=series)
    if s is None:
        return 1
    try:
        if quit_after is not None:
            s.shell.after_first_image(quit_after, s.app.quit)
        return s.app.exec()                             # 1 when the X display went away under the bridge
    finally:
        s.close()

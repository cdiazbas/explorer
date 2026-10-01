"""The prototype's smoke test (its app/smoke.py: ~100 quick checks of start-up, units, cursor, keys, controls,
padlocks, playback, zoom, panels, the window and the X side), run unchanged against explorer's window (ROADMAP
E4.11): the functions first, then speed (bench/selftest_vs_prototype.py).

    python bench/proto_smoke.py <cube_im.fits> [--mode offscreen|xcb|bridge] [--out r.json] [--no-sp]

smoke.py builds its viewer through app/startup.py and reads app/viewer.py; here those two are stand-ins that open
the cube with explorer's Dataset and its Shell, seen through bench/protoface.py under the prototype's names, and
its style module is explorer's (ui.style). Every other module of the prototype is kept out: a check that imports
one (its title bar) would test the prototype, so it fails with "not in explorer yet" instead. The table at the end
adds a status, NOT YET, never counted as PASS or FAIL: a check that failed on something explorer has no
counterpart for, and every check of a feature explorer has not yet (NOT_YET_CHECKS), whatever it gave, SKIP
included.

The prototype is found at $EXPLORER_PROTOTYPE, else ../prototype next to this repository. Nothing is written into
it: no bytecode, and smoke.py's own settings file is never used (explorer does not save a layout yet).
"""
import importlib.abc
import os
import runpy
import sys
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True


class _KeepOut(importlib.abc.MetaPathFinder):
    """No module of the prototype's app/ folder but the stand-ins: a check that imports one fails, named."""

    def __init__(self, app_dir, allow=()):
        self.app_dir, self.allow = app_dir, set(allow)

    def find_spec(self, name, path=None, target=None):
        if "." not in name and name not in self.allow and os.path.exists(os.path.join(self.app_dir, name + ".py")):
            from protoface import LATER

            what = {"titlebar": LATER["title"], "style": LATER["look"], "look": LATER["look"]}.get(name, name)
            raise ImportError(f"not in explorer yet: the prototype's {name}.py ({what})")
        return None


def startup_module():
    """A stand-in for the prototype's app/startup.py: prepare, make_app, open_cube, make_viewer, show."""
    from protoface import BridgeView, adopt

    from explorer.platform import display as xdisplay

    def prepare(x11_choice="auto", backend="auto"):
        from explorer.platform.plan import choose_display

        choice = {"native": "native", "bridge": "bridge"}.get(x11_choice, "auto")
        plan = choose_display(os.environ, sys.platform, choice)
        disp = xdisplay.for_plan(plan)
        disp.prepare_env()
        return SimpleNamespace(plan=plan, disp=disp, bridge=None)

    def make_app(s, theme="auto"):
        from explorer.ui.app import themed_app

        app, applied = themed_app(s.disp, theme)
        b = getattr(s.disp, "bridge", None)
        s.bridge = BridgeView(b) if b is not None else None
        return app, applied

    def open_cube(path, sp_path=None, no_sp=False):
        from explorer.data.dataset import Dataset

        ds = Dataset.open(path, sp=sp_path, no_sp=no_sp)
        return ds, ds.probe, ds.guard, ds.pixel, None

    def make_viewer(app, s, cube, sp, probe, guard, kind=None):
        from explorer._name import APP_NAME
        from explorer.ui.shell import Shell

        w = Shell(cube, title=f"{os.path.basename(str(cube.path))} — {APP_NAME}")
        from explorer.ui import docks

        w.setGeometry(docks.first_geometry(app))
        return adopt(w)

    def show(app, s, v, size=None):
        if size is not None:                            # the prototype's show: a size given, no restore(), so its
            v.resize(*size)                             # docks keep Qt's own sizes; explorer's first-show sizing
            v._sized = True                             # (the fresh start's) is skipped the same way
        s.ops = s.disp.attach(app, v)

    return SimpleNamespace(prepare=prepare, make_app=make_app, open_cube=open_cube, make_viewer=make_viewer, show=show,
                           _OFFSCREEN_NOISE=xdisplay.OFFSCREEN_NOISE, _quiet_offscreen=xdisplay._quiet_offscreen)


# checks of what explorer has not yet, by a word of their name: NOT YET whatever they gave. The last ones need the
# prototype's own title bar, edges and dock titles, and are SKIP without them: a silent SKIP would hide the gap
NOT_YET_CHECKS = (("slit", "slit (E7)"), ("persist:", "layout persistence (E5)"),
                  ("edgeresizer", "window edges (E5)"), ("minimum size by the edges", "window edges (E5)"),
                  ("title docks it back", "own dock titles (E5)"), ("window: zoom", "own title bar (E5)"),
                  ("window: minimise", "own title bar (E5)"))


def table(path, rc):
    """smoke.py's checks from its report, with NOT YET apart from FAIL; returns the number of real FAILs."""
    import json

    r = json.load(open(path))
    for c in r["checks"]:
        # a check of the slit or of the saved layout means nothing before explorer has them, even when it passes
        # (with no slit, "the wheel still zooms in slit mode" holds for nothing); the rest, NOT YET when it failed
        # on a name explorer has no counterpart for
        feature = next((what for key, what in NOT_YET_CHECKS if key in c["check"].lower()), None)
        skipped_by_both = c["check"].startswith("window: minimise") and r["mode"] == "xcb"   # the prototype's too
        if feature is not None and not (c["status"] == "SKIP" and skipped_by_both):
            c["status"], c["value"] = "NOT YET", f"not in explorer yet: {feature}; {c['value']}"
        elif c["status"] == "FAIL" and "not in explorer yet" in c["value"]:
            c["status"] = "NOT YET"
    w = min(70, max(len(c["check"]) for c in r["checks"]))
    print(f"\nexplorer under the prototype's smoke.py  mode={r['mode']}  platform={r['platform']}  cube={r['cube']}"
          f"  sp={r['sp']}  {r['seconds']} s")
    for c in r["checks"]:
        print(f"  {c['check'][:w]:{w}s}  {c['status']:7s}  {c['ms']:7.1f} ms  {c['value']}")
    n = {k: sum(c["status"] == k for c in r["checks"]) for k in ("PASS", "FAIL", "NOT YET", "SKIP")}
    print(f"{len(r['checks'])} checks: " + ", ".join(f"{v} {k}" for k, v in n.items()) + f"  (smoke.py exit {rc})")
    json.dump(r, open(path, "w"), indent=1, ensure_ascii=False)
    return n["FAIL"]


def main():
    if "--child" not in sys.argv:                       # smoke.py ends with os._exit: run it in a child, then the table
        import subprocess
        import tempfile

        args = sys.argv[1:]
        out = args[args.index("--out") + 1] if "--out" in args else None
        if out is None:
            out = os.path.join(tempfile.mkdtemp(prefix="proto_smoke_"), "smoke.json")
            args += ["--out", out]
        with open(out + ".log", "w") as log:              # smoke.py's own table and output (no NOT YET column)
            rc = subprocess.call([sys.executable, "-P", os.path.abspath(__file__), "--child"] + args, stdout=log)
        if not os.path.exists(out):
            sys.exit(f"smoke.py left no report (exit {rc})")
        sys.exit(min(table(out, rc), 255))
    sys.argv.remove("--child")
    proto = os.path.abspath(os.environ.get("EXPLORER_PROTOTYPE", os.path.join(ROOT, "..", "prototype")))
    app_dir = os.path.join(proto, "app")
    smoke = os.path.join(app_dir, "smoke.py")
    if not os.path.exists(smoke):
        sys.exit(f"no {smoke}: set EXPLORER_PROTOTYPE to the prototype's folder")
    sys.path.insert(0, os.path.join(ROOT, "src"))
    import protoface

    sys.modules["startup"] = startup_module()
    sys.modules["viewer"] = protoface.viewer_module()
    from explorer.ui import style

    sys.modules["style"] = style                        # the theme check imports it: explorer's own
    sys.meta_path.insert(0, _KeepOut(app_dir))
    sys.argv = [smoke] + sys.argv[1:]
    runpy.run_path(smoke, run_name="__main__")


if __name__ == "__main__":
    main()

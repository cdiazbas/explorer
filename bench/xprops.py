"""The X properties of every window explorer and the prototype show through their X11 bridges, side by side
(ROADMAP E6.5): each program is driven unchanged by the prototype's conformance suite (its app/conformance.py, and
bench/proto_conformance.py for explorer), one step at a time, on an X display of its own (a private Xvfb), while an
independent X client (python-xlib) records every top-level window mapped on that display and reads what a window
manager reads: override-redirect, the window type, the Motif hints, WM_TRANSIENT_FOR, WM_NORMAL_HINTS (flags, gravity,
sizes), WM_HINTS and WM_PROTOCOLS.

    EXPLORER_TEST_XDISPLAY=:N python bench/xprops.py <cube_im.fits> --out xprops.json [--steps a,b] [--md report.md]

The windows are put in classes by what X shows and the step that made them: main (the first managed window),
panel (managed, transient for another), popup (override-redirect, opened by combo_open: the combo's list) and
tooltip (override-redirect, opened by the tooltip step). Within a class the two programs must agree; the report
lists each property that differs.
"""
import argparse
import json
import os
import select
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
STEPS = ("combo_open", "tooltip", "panel_float_api", "dock_title_drag_float")
GRAVITY = {1: "NorthWest", 5: "Center", 10: "Static"}
HINT_FLAGS = ((1, "USPosition"), (2, "USSize"), (4, "PPosition"), (8, "PSize"), (16, "PMinSize"),
              (32, "PMaxSize"), (64, "PResizeInc"), (128, "PAspect"), (256, "PBaseSize"), (512, "PWinGravity"))


class Watcher(threading.Thread):
    """Every window mapped as a child of the root, with its properties read at once (both bridges set them before
    the map)."""

    def __init__(self, name):
        super().__init__(daemon=True)
        from Xlib import X, display

        self.X, self.d = X, display.Display(name)
        self.root = self.d.screen().root
        self.root.change_attributes(event_mask=X.SubstructureNotifyMask)
        self.d.sync()
        self.seen: list[dict] = []
        self.names: dict[int, str] = {}
        self.stop = threading.Event()

    def run(self):
        while not self.stop.is_set():
            if not self.d.pending_events():
                select.select([self.d.fileno()], [], [], 0.05)
                if not self.d.pending_events():
                    continue
            e = self.d.next_event()
            if e.type == self.X.MapNotify and e.event == self.root:
                r = self.read(e.window)
                if r is not None:
                    self.seen.append(r)

    def atoms(self, w, name):
        p = w.get_full_property(self.d.intern_atom(name), self.X.AnyPropertyType)
        return [self.d.get_atom_name(a) for a in p.value] if p is not None else None

    def read(self, w):
        from Xlib import error

        try:
            a, g = w.get_attributes(), w.get_geometry()
            p = w.get_full_property(self.d.intern_atom("_NET_WM_NAME"), self.d.intern_atom("UTF8_STRING"))
            name = p.value.decode("utf-8", "replace") if p is not None else (w.get_wm_name() or "")
            self.names[w.id] = name
            motif = w.get_full_property(self.d.intern_atom("_MOTIF_WM_HINTS"), self.X.AnyPropertyType)
            tf = w.get_wm_transient_for()
            nh = w.get_wm_normal_hints()
            wh = w.get_wm_hints()
            r = dict(xid=w.id, t=time.monotonic(), name=name, override_redirect=bool(a.override_redirect),
                     size=(g.width, g.height),
                     type=self.atoms(w, "_NET_WM_WINDOW_TYPE"),
                     motif=list(motif.value) if motif is not None else None,
                     transient_for=None if tf is None else self.names.get(tf.id, hex(tf.id)),
                     protocols=self.atoms(w, "WM_PROTOCOLS"),
                     wm_hints=None if wh is None else dict(flags=wh.flags, input=wh.input),
                     normal_hints=None)
            if nh is not None:
                r["normal_hints"] = dict(
                    flags=[n for b, n in HINT_FLAGS if nh.flags & b],
                    gravity=GRAVITY.get(nh.win_gravity, nh.win_gravity) if nh.flags & 512 else None,
                    min=(nh.min_width, nh.min_height) if nh.flags & 16 else None,
                    max=(nh.max_width, nh.max_height) if nh.flags & 32 else None)
            return r
        except (error.BadWindow, error.BadDrawable, error.BadMatch):
            return None                                 # gone before it was read (a tool tip can be that quick)


def run_step(program, step, cube, display_name, out_dir):
    env = {k: v for k, v in os.environ.items() if k not in ("QT_QPA_PLATFORM", "XAUTHORITY")}
    env.update(DISPLAY=display_name, XDG_CONFIG_HOME=os.path.join(out_dir, f"cfg_{program}"),
               PYTHONDONTWRITEBYTECODE="1")
    os.makedirs(env["XDG_CONFIG_HOME"], exist_ok=True)
    proto = os.path.abspath(os.environ.get("EXPLORER_PROTOTYPE", os.path.join(ROOT, "..", "prototype")))
    out = os.path.join(out_dir, f"{program}_{step}.json")
    if program == "prototype":
        cmd = [os.path.join(proto, ".venv", "bin", "python"), os.path.join(proto, "app", "conformance.py")]
        cwd = proto
    else:
        cmd = [sys.executable, os.path.join(HERE, "proto_conformance.py")]
        env["EXPLORER_PROTOTYPE"] = proto
        cwd = ROOT
    cmd += [cube, "--mode", "bridge", "--out", out, "--only", step]
    w = Watcher(display_name)
    w.start()
    p = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=600)
    time.sleep(0.3)
    w.stop.set()
    w.join(2)
    return dict(program=program, step=step, exit=p.returncode, windows=w.seen,
                log=(p.stdout + p.stderr)[-1500:] if p.returncode else "")


def classify(run):
    """(class, record) for each window of one step's run."""
    out, main = [], None
    for r in run["windows"]:
        if r["override_redirect"]:
            cls = {"combo_open": "popup", "tooltip": "tooltip"}.get(run["step"], "override-redirect")
        elif r["transient_for"] is None and main is None:
            cls, main = "main", r
        elif r["transient_for"] is not None:
            cls = "panel"
        else:
            cls = "managed, not transient"
        out.append((cls, r))
    return out


KEYS = ("override_redirect", "type", "motif", "transient_for", "protocols", "wm_hints", "normal_hints")


def compare(runs):
    """{class: {key: {program: set of values}}} over every step; and the classes each program showed."""
    by: dict = {}
    for run in runs:
        for cls, r in classify(run):
            for k in KEYS:
                v = r[k]
                if k == "transient_for" and v is not None:
                    v = "main" if v in {x["name"] for c, x in classify(run) if c == "main"} else "other"
                by.setdefault(cls, {}).setdefault(k, {}).setdefault(run["program"], set()).add(json.dumps(v))
    return by


def report(by) -> str:
    lines = ["| class | property | prototype | explorer |", "|---|---|---|---|"]
    for cls in sorted(by):
        for k, per in by[cls].items():
            a, b = per.get("prototype", set()), per.get("explorer", set())
            mark = "" if a == b else " **≠**"
            lines.append(f"| {cls} | {k}{mark} | {'; '.join(sorted(a)) or '—'} | {'; '.join(sorted(b)) or '—'} |")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cube")
    ap.add_argument("--out", required=True)
    ap.add_argument("--md")
    ap.add_argument("--steps", default=",".join(STEPS))
    ap.add_argument("--first", choices=("prototype", "explorer"), default="prototype",
                    help="which program runs each step first: the second starts with the pointer where the first "
                         "left it (one display for both)")
    a = ap.parse_args(argv)
    disp = os.environ.get("EXPLORER_TEST_XDISPLAY")
    if not disp:
        sys.exit("EXPLORER_TEST_XDISPLAY=:N (a private Xvfb) is needed: never the user's display")
    out_dir = os.path.splitext(os.path.abspath(a.out))[0] + "_runs"
    os.makedirs(out_dir, exist_ok=True)
    runs = []
    for step in a.steps.split(","):
        for program in (("prototype", "explorer") if a.first == "prototype" else ("explorer", "prototype")):
            r = run_step(program, step, os.path.abspath(a.cube), disp, out_dir)
            print(f"{program:9s} {step:24s} exit {r['exit']}  {len(r['windows'])} windows mapped", flush=True)
            runs.append(r)
    with open(a.out, "w") as f:
        json.dump(runs, f, indent=1)
    md = report(compare(runs))
    if a.md:
        with open(a.md, "w") as f:
            f.write(md + "\n")
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())

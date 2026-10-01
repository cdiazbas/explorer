"""The prototype's input conformance suite (its app/conformance.py: ~150 steps of real X input through XTEST, each
recording what every widget received and the state the window ends in), run unchanged against explorer's window
(ROADMAP E4.12), and the two runs compared step by step.

    python bench/proto_conformance.py <cube_im.fits> --mode xcb|bridge --out explorer.json [--only a,b] [--skip c]
    python bench/proto_conformance.py --compare prototype.json explorer.json [--md report.md]

A run needs an X display with XTEST (the private Xvfb, as the prototype's own runs). The prototype's run is its own
script: python app/conformance.py <cube> --mode ... --out prototype.json, with its settings in a scratch folder.

The run goes through the stand-ins of bench/proto_smoke.py: explorer's Dataset and Shell under the prototype's
names (bench/protoface.py), and no other module of the prototype. The comparison is the prototype's own (compare():
events in order without moves, moves as a set per widget, the end state exact), on both runs put in common terms
first: the names the two programs give the same widget (NAMES), and the steps of what explorer has not yet
(NOT_YET: the slit), which are listed apart and not compared.
"""
import collections
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True

# the same widget under each program's name: explorer's -> the prototype's
NAMES = (("ProtoViewer", "Viewer"), ("Shell", "Viewer"), ("QWidget#gutter", "QWidget#crispex_gutter"))
# state of what explorer has not yet, left out of every state
NOT_YET_STATE: tuple = ()
# steps of what explorer has not yet: prefix -> the task that brings it
NOT_YET = (("slit_", "slit (E7)"),)


def _prototype_app():
    proto = os.path.abspath(os.environ.get("EXPLORER_PROTOTYPE", os.path.join(os.path.dirname(HERE), "..",
                                                                              "prototype")))
    app_dir = os.path.join(proto, "app")
    if not os.path.exists(os.path.join(app_dir, "conformance.py")):
        sys.exit(f"no {app_dir}/conformance.py: set EXPLORER_PROTOTYPE to the prototype's folder")
    return app_dir


def _common(x):
    """A run's strings in common terms (NAMES)."""
    if isinstance(x, dict):
        return {k: _common(v) for k, v in x.items() if k not in NOT_YET_STATE}
    if isinstance(x, list):
        return [_common(v) for v in x]
    if isinstance(x, str):
        for a, b in NAMES:
            x = x.replace(a, b)
    return x


def not_yet(name):
    return next((what for key, what in NOT_YET if name.startswith(key)), None)


def compare(fa, fb, md=None):
    app_dir = _prototype_app()
    sys.path.insert(0, app_dir)
    import conformance

    tmp = tempfile.mkdtemp(prefix="proto_conf_")
    runs, apart, loaded = [], [], []
    for f, who in ((fa, "prototype"), (fb, "explorer")):
        r = _common(json.load(open(f)))
        r["mode"] = who                                 # compare() names each side by its mode: both may be xcb
        loaded.append(r)
    # events only on widgets both programs have: one that exists in one of them (the prototype's own title bar,
    # dock titles and separators, the slit's button and tab bar) gets every window event, at every step
    widgets = [{e["w"] for s in r["steps"] for e in s["events"]} for r in loaded]
    only = [collections.Counter(), collections.Counter()]
    for i, r in enumerate(loaded):
        for s in r["steps"]:
            kept = []
            for e in s["events"]:
                if e["w"] and e["w"] not in widgets[1 - i]:
                    only[i][e["w"]] += 1
                else:
                    kept.append(e)
            s["events"] = kept
    for f, who, r in zip((fa, fb), ("prototype", "explorer"), loaded, strict=True):
        keep = []
        for s in r["steps"]:
            what = not_yet(s["name"])
            if what is None:
                keep.append(s)
            elif f is fb:
                apart.append(f"{s['name']} ({what})")
        r["steps"] = keep
        p = os.path.join(tmp, f"{who}.json")
        json.dump(r, open(p, "w"))
        runs.append(p)
    n = conformance.compare(*runs, md=md)
    note = f"Not compared, not in explorer yet ({len(apart)}): " + ", ".join(apart)
    for who, c in zip(("prototype", "explorer"), only, strict=True):
        note += (f"\nEvents on widgets only the {who} has, left out ({sum(c.values())} events, {len(c)} widgets): "
                 + ", ".join(f"{w} {k}" for w, k in c.most_common(12)) + (" ..." if len(c) > 12 else ""))
    print(note)
    if md:
        open(md, "a").write(note + "\n")
    return n


def main():
    if "--compare" in sys.argv:
        i = sys.argv.index("--compare")
        md = sys.argv[sys.argv.index("--md") + 1] if "--md" in sys.argv else None
        sys.exit(1 if compare(sys.argv[i + 1], sys.argv[i + 2], md) else 0)
    app_dir = _prototype_app()
    root = os.path.dirname(HERE)
    sys.path.insert(0, os.path.join(root, "src"))
    import proto_smoke
    import protoface

    sys.modules["startup"] = proto_smoke.startup_module()
    sys.modules["viewer"] = protoface.viewer_module()
    from explorer.ui import style, titlebar

    sys.modules["style"] = style
    sys.modules["titlebar"] = titlebar
    sys.meta_path.insert(0, proto_smoke._KeepOut(app_dir, allow=("conformance",)))
    sys.path.insert(0, app_dir)
    import conformance

    sys.argv = [os.path.join(app_dir, "conformance.py")] + sys.argv[1:]
    conformance.main()


if __name__ == "__main__":
    main()

"""A step in t with the 2x2 Stokes view on (I, Q, U, V side by side), explorer against the prototype, each through its
own start-up, offscreen, one process per run (ROADMAP E5.19): from the step until all four quadrants have the new t,
and one more pass of the event loop (painted, as the prototype's self-test settles).

    QT_QPA_PLATFORM=offscreen python bench/grid_step.py proto|explorer <cube_im.fits> <out.json> [--steps 20]

The prototype runs with its own Python (its .venv); its view is the glass look's (G), explorer's the Stokes control's
All (set_grid). Five steps first, not counted: numba and the caches warm. For explorer the JSON also has the image
levels of the counted steps: computed in all, computed ahead (off the UI thread), and found cached or waited for by
the UI thread (obs counters core.levels.*).
"""
import json
import os
import sys
import tempfile
import time

which, cube, out = sys.argv[1], sys.argv[2], sys.argv[3]
steps = int(sys.argv[sys.argv.index("--steps") + 1]) if "--steps" in sys.argv else 20
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
os.environ["EXPLORER_TERMINAL_KEYS"] = "0"
done: list = []                                         # the quadrants (or refreshes) seen since the step

if which == "proto":
    import importlib

    proto = os.path.abspath(os.environ.get("EXPLORER_PROTOTYPE", "../prototype"))
    sys.path.insert(0, os.path.join(proto, "app"))
    sys.argv = sys.argv[:1]
    import viewer  # noqa: F401  (first: it sets up the prototype's import paths, Qt, pyqtgraph)

    startup = importlib.import_module("startup")        # after viewer, on the paths it set
    look = importlib.import_module("look")
    s = startup.prepare("auto", "pgr")
    app, _ = startup.make_app(s, "auto")
    c, probe, guard, sp_file, cal = startup.open_cube(cube, None, False)
    w = startup.make_viewer(app, s, c, sp_file, probe, guard, kind="grid")
    startup.show(app, s, w, size=(1400, 900))

    def first_image():
        return True

    def grid_on():
        look.apply(w, app, "glass")
        w._glass_set_grid(True)
        g = w._glass_grid
        orig = g.refresh

        def refresh(_o=orig):
            _o()
            done.append(1)
        g.refresh = refresh

    def step():
        w._step(w.ta, 1, wrap=True)

    def ready():
        return len(done) >= 1
else:
    from explorer.ui.app import start

    st = start(cube, look="classic", saved_layout=False)
    app, w = st.app, st.shell
    w.resize(1400, 900)

    def first_image():
        return w.first_image_s is not None

    def grid_on():
        w.set_grid(True)
        g = w.grid
        orig = g.set_image

        def set_image(s, img, levels, _o=orig):
            _o(s, img, levels)
            done.append(s)
        g.set_image = set_image

    def step():
        w.session.step("t", 1, wrap=True)

    def ready():
        return len(set(done)) >= 4


def levels_counters():
    if which == "proto":
        return {}
    from explorer.obs import summary

    c = summary().get("counters", {})
    return {k: c.get(f"core.levels.{k}", 0) for k in ("computed", "ahead", "cached", "waited")}


def spin(until, timeout=30.0):
    end = time.perf_counter() + timeout
    while not until() and time.perf_counter() < end:
        app.processEvents()
    return until()


spin(first_image)
for _ in range(100):
    app.processEvents()
    time.sleep(0.01)
grid_on()
for _ in range(100):
    app.processEvents()
    time.sleep(0.01)
ms = []
for k in range(5 + steps):
    if k == 5:
        lev0 = levels_counters()
    done.clear()
    q = time.perf_counter()
    step()
    ok = spin(ready)
    app.processEvents()
    if k >= 5 and ok:
        ms.append((time.perf_counter() - q) * 1e3)
lev = {k: v - lev0[k] for k, v in levels_counters().items()}
ms.sort()
res = dict(program=which, steps=len(ms), median_ms=round(ms[len(ms) // 2], 2) if ms else None,
           p95_ms=round(ms[int(len(ms) * 0.95) - 1], 2) if ms else None, all_ms=[round(v, 1) for v in ms],
           levels=lev or None)
json.dump(res, open(out, "w"), indent=1)
print(f"{which}: step in t with the 2x2 view, median {res['median_ms']} ms, p95 {res['p95_ms']} ms ({len(ms)} steps)"
      + (f", levels {lev}" if lev else ""))
app.quit()

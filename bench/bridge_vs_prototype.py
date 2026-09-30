"""The two X11 bridges on the same window: explorer's, shown by the prototype's bridge (its app/xbridge.py, imported
from the prototype without changing it) or by the rewritten one (platform/xbridge2), each in its own process,
alternating (ABBA). What reaches the X server is measured from outside the bridges, by another X connection that
reads the window's pixels back (GetImage) until they are Qt's:

- first image: from the start of the process to the image on the X server;
- steps in t and lambda, Stokes changes: from the call until Qt has the new image, and until the X server has it;
- bytes: through bench/xlink.py when DISPLAY goes through it (EXPLORER_XLINK_STATS: its counters), the same count
  for both, and each bridge's own count of pixel bytes per update.

    python bench/bridge_vs_prototype.py <cube_im.fits> [--rounds 4] [--pin CPUS] [--out F]
    python bench/bridge_vs_prototype.py <cube_im.fits> --one proto|bridge2 --out r.json      (one process)

DISPLAY and XAUTHORITY: the X server to measure on (a private Xvfb; never a screen someone looks at), directly or
through bench/xlink.py (an emulated ssh link); EXPLORER_BENCH_OBSERVE: the display the pixels are read back from
(default DISPLAY; the X server itself when DISPLAY goes through the link, so reading costs nothing there). The prototype
is EXPLORER_PROTOTYPE (default ../prototype); its numba cache goes where NUMBA_CACHE_DIR says, and Python writes no
bytecode there (PYTHONDONTWRITEBYTECODE=1 is set here for the children).
"""
import argparse
import json
import os
import socket
import statistics
import subprocess
import sys
import tempfile
import time

T_START = time.perf_counter()
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
KEYS = ["first_qt_s", "first_x_s", "step in t", "step in λ", "change Stokes"]
PATCH = 64


def link_bytes() -> tuple[int, int]:
    """(up, down) bytes through bench/xlink.py so far; (0, 0) without it."""
    p = os.environ.get("EXPLORER_XLINK_STATS")
    if not p:
        return 0, 0
    for _ in range(50):
        try:
            d = json.load(open(p))
            return d["up"], d["down"]
        except (OSError, ValueError):
            time.sleep(0.002)
    return 0, 0


def link_settled(timeout=5.0) -> tuple[int, int]:
    """The link's counters once they stop moving (what was sent has gone through)."""
    last, end = link_bytes(), time.perf_counter() + timeout
    while time.perf_counter() < end:
        time.sleep(0.05)
        now = link_bytes()
        if now == last:
            return now
        last = now
    return last


def process_age() -> float | None:
    try:
        start_ticks = int(open("/proc/self/stat").read().rsplit(")", 1)[1].split()[19])
        uptime = float(open("/proc/uptime").read().split()[0])
        return uptime - start_ticks / os.sysconf("SC_CLK_TCK")
    except (OSError, ValueError, IndexError):
        return None


def one(cube: str, which: str, out: str) -> int:
    age0 = process_age() or 0.0
    link0 = link_bytes()                                # the link's counters are the link's, not this process's
    import numpy as np

    res: dict = dict(bridge=which, cube=os.path.basename(cube), display=os.environ.get("DISPLAY"))
    if which == "proto":
        proto = os.path.abspath(os.environ.get("EXPLORER_PROTOTYPE", os.path.join(ROOT, "..", "prototype")))
        sys.path.insert(0, os.path.join(proto, "app"))
        import xbridge  # the prototype's bridge, read-only

        t = time.perf_counter()
        b = xbridge.XBridge()
        res["connect_s"] = round(time.perf_counter() - t, 3)
        os.environ["QT_QPA_PLATFORM"] = b.qpa()
        from explorer.platform.display import Display
        from explorer.platform.plan import DisplayPlan

        disp = Display(DisplayPlan("offscreen"))
        app = disp.make_app()
        b.sync_cursor()
    else:
        from explorer.platform.display import for_plan
        from explorer.platform.plan import choose_display

        t = time.perf_counter()
        disp = for_plan(choose_display(os.environ, sys.platform, "bridge"))
        disp.prepare_env()
        res["connect_s"] = round(time.perf_counter() - t, 3)
        app = disp.make_app()
    from PySide6 import QtGui

    from explorer.data.dataset import Dataset
    from explorer.ui.shell import Shell

    ds = Dataset.open(cube)
    w = Shell(ds, title="bridge comparison", t0=T_START)
    w.resize(1400, 900)                                 # the self-tests' size
    if which == "proto":
        w.show()
        b.attach(app, w)
        xid = b.wins[w]["x"].id

        def summary():
            return b.summary()

        def bridge_bytes():
            return b.stats["bytes"], b.stats["frames"]
    else:
        disp.attach(app, w)
        br = disp.bridge
        xid = br.windows.get(w).xid

        def summary():
            return br.summary()

        def bridge_bytes():
            return br.transport.stats["bytes"], br.transport.stats["updates"]

    from Xlib import X, display

    obs = display.Display(os.environ.get("EXPLORER_BENCH_OBSERVE") or None)
    xwin = obs.create_resource_object("window", xid)

    def spin(until, timeout=30.0):
        end = time.perf_counter() + timeout
        while not until() and time.perf_counter() < end:
            app.processEvents()
        return until()

    def patch_xy():
        vb = w.view.vb
        r = vb.mapRectToScene(vb.boundingRect()).toRect()
        vp = w.view.widget.viewport()
        c = vp.mapTo(w, w.view.widget.mapFromScene(r.center()))
        return c.x() - PATCH // 2, c.y() - PATCH // 2

    def qt_patch(x, y):
        img = w.screen().grabWindow(w.winId(), x, y, PATCH, PATCH).toImage().convertToFormat(
            QtGui.QImage.Format.Format_RGB32)
        a = np.frombuffer(img.constBits(), np.uint32).reshape(PATCH, img.bytesPerLine() // 4)[:, :PATCH]
        return a & 0xFFFFFF

    def x_patch(x, y):
        try:
            img = xwin.get_image(x, y, PATCH, PATCH, X.ZPixmap, 0xFFFFFFFF)
        except Exception:                               # not viewable yet
            return None
        return np.frombuffer(img.data, np.uint32).reshape(PATCH, PATCH) & 0xFFFFFF

    def until_on_x(want, x, y, timeout=30.0):
        end = time.perf_counter() + timeout
        while time.perf_counter() < end:
            got = x_patch(x, y)
            if got is not None and (got == want).all():
                return True
            app.processEvents()
            time.sleep(0.0005)
        return False

    spin(lambda: w.first_image_s is not None)
    app.processEvents()
    res["first_qt_s"] = round(time.perf_counter() - T_START + age0, 3)
    px, py = patch_xy()
    want = qt_patch(px, py)
    ok = until_on_x(want, px, py)
    res["first_x_s"] = round(time.perf_counter() - T_START + age0, 3) if ok else None
    res["age_at_start_s"] = round(age0, 3)
    res["first_link_up_MB"] = round((link_bytes()[0] - link0[0]) / 1e6, 3)
    for _ in range(50):                                 # settle: the spectra, the y-range sample, the bridge
        app.processEvents()
        time.sleep(0.01)
    res["actions"] = {}

    def series(name, axis, n):
        qt_ms, x_ms = [], []
        (l0, _), (b0, u0) = link_settled(), bridge_bytes()
        for _ in range(n):
            q = time.perf_counter()
            w.session.step(axis, 1, wrap=True)
            target = w.session.index()
            spin(lambda target=target: w.scheduler.img_idx == target)
            app.processEvents()
            qt_ms.append((time.perf_counter() - q) * 1e3)
            want = qt_patch(px, py)
            if until_on_x(want, px, py):
                x_ms.append((time.perf_counter() - q) * 1e3)
        for _ in range(30):
            app.processEvents()
            time.sleep(0.005)
        b1, u1 = bridge_bytes()
        l1, _ = link_settled()
        res["actions"][name] = dict(qt_ms=round(statistics.median(qt_ms), 2),
                                    x_ms=round(statistics.median(x_ms), 2) if x_ms else None,
                                    x_p95_ms=round(float(np.percentile(x_ms, 95)), 2) if x_ms else None,
                                    n=n, on_x=len(x_ms), link_kB_per_step=round((l1 - l0) / n / 1e3, 1),
                                    pixel_kB_per_update=round((b1 - b0) / max(1, u1 - u0) / 1e3, 1),
                                    updates=u1 - u0)
        a = res["actions"][name]
        print(f"  {which:8s} {name:14s} Qt {a['qt_ms']:7.2f} ms   X {a['x_ms']} ms   link "
              f"{a['link_kB_per_step']} kB/step   pixels {a['pixel_kB_per_update']} kB/update", flush=True)

    r = ds.roles
    if r.t is not None and r.nt > 1:
        series("step in t", "t", 10)
    if r.l is not None and r.nl > 1:
        series("step in λ", "l", 10)
    if r.s is not None and r.ns > 1:
        series("change Stokes", "s", 2 * r.ns)
    res["summary"] = summary()
    res["host"] = socket.gethostname().split(".")[0]
    print(f"  {which:8s} first image: Qt {res['first_qt_s']} s, X {res['first_x_s']} s since the process started "
          f"(bridge connect {res['connect_s']} s)", flush=True)
    json.dump(res, open(out, "w"), indent=1)
    w.close()
    ds.close()
    obs.close()
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cube")
    ap.add_argument("--one", choices=("proto", "bridge2"))
    ap.add_argument("--rounds", type=int, default=4)
    ap.add_argument("--pin", help="CPUs to pin both to (taskset -c), e.g. one NUMA node")
    ap.add_argument("--out")
    a = ap.parse_args()
    if a.one:
        return one(a.cube, a.one, a.out)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    env.pop("QT_QPA_PLATFORM", None)
    env.pop("EXPLORER_X11", None)
    pin = ["taskset", "-c", a.pin] if a.pin else []
    tmp = tempfile.mkdtemp(prefix="bridges_")
    res = dict(host=socket.gethostname().split(".")[0], date=time.strftime("%Y-%m-%dT%H:%M:%S"),
               cube=os.path.basename(a.cube), pin=a.pin, load_before=os.getloadavg(),
               display=os.environ.get("DISPLAY"), rounds=[])
    for rd in range(a.rounds):
        order = ["proto", "bridge2"] if rd % 2 == 0 else ["bridge2", "proto"]
        row = {"order": order}
        for which in order:
            out = os.path.join(tmp, f"{which}_{rd}.json")
            p = subprocess.run(pin + [sys.executable, os.path.abspath(__file__), a.cube, "--one", which, "--out", out],
                               env=env, capture_output=True, text=True, timeout=900)
            sys.stdout.write(p.stdout)
            if p.returncode or not os.path.exists(out):
                raise RuntimeError(f"{which} failed ({p.returncode}): {p.stderr[-1500:]}")
            row[which] = json.load(open(out))
        res["rounds"].append(row)
    res["load_after"] = os.getloadavg()

    def val(r, k):
        if k.endswith("_s"):
            return r.get(k)
        a_ = r["actions"].get(k)
        return a_["x_ms"] if a_ else None

    summary = {}
    for k in KEYS + [f"{k} Qt" for k in KEYS[2:]] + [f"{k} bytes" for k in KEYS[2:]]:
        base = k.removesuffix(" Qt").removesuffix(" bytes")
        pv, ev = [], []
        for row in res["rounds"]:
            if k.endswith(" Qt"):
                g = [row[x]["actions"].get(base, {}).get("qt_ms") for x in ("proto", "bridge2")]
            elif k.endswith(" bytes"):
                g = [row[x]["actions"].get(base, {}).get("link_kB_per_step") for x in ("proto", "bridge2")]
            else:
                g = [val(row[x], k) for x in ("proto", "bridge2")]
            if None not in g:
                pv.append(g[0])
                ev.append(g[1])
        if not pv:
            continue
        ratio = [e / p for p, e in zip(pv, ev, strict=True) if p]
        if not ratio:                                   # no link counters (a direct display): no bytes
            continue
        summary[k] = dict(prototype=round(statistics.median(pv), 3), bridge2=round(statistics.median(ev), 3),
                          paired=round(statistics.median(ratio), 3), bridge2_better=sum(r < 1 for r in ratio),
                          n=len(ratio))
        s = summary[k]
        print(f"{k:22s} prototype {s['prototype']:9.3f}  bridge2 {s['bridge2']:9.3f}  paired {s['paired']:.3f} "
              f"({s['bridge2_better']}/{s['n']} rounds better)", flush=True)
    res["summary"] = summary
    if a.out:
        os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
        json.dump(res, open(a.out, "w"), indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())

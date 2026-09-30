"""explorer's window against the prototype's, each in its own process, alternating (ROADMAP E3.7, E6).

    python bench/selftest_vs_prototype.py <cube_im.fits> [--rounds 4] [--modes offscreen,xcb] [--pin CPUS] [--out F]

For each round, mode and with and without the per-pixel file, the prototype's app/selftest.py and
bench/explorer_selftest.py run one after the other, which goes first alternating between rounds (ABBA). Each in the
environment it runs in by itself: the prototype with its Python, its .qtlibs and NUMBA_NUM_THREADS=64 as its
baseline (bench/prototype_baseline.sh); explorer with its own. Window layouts go to a temporary XDG_CONFIG_HOME. The
prototype never writes into its own folder: no bytecode, numba's cache in a temporary NUMBA_CACHE_DIR (so one
unmeasured run of each program and configuration goes first, to fill the caches: without it, a kernel compiled during
the first run without the per-pixel file stalled the bridge's sender ~0.6 s).
Modes:
- offscreen: no X;
- xcb: Qt's own X11 on the private Xvfb (EXPLORER_XVFB_DISPLAY, default :97, cookie in EXPLORER_XVFB_AUTH);
- bridge: each program's X11 bridge on that Xvfb (explorer: EXPLORER_X11=bridge; the prototype: CRISPEX_XBRIDGE=1,
  through bench/prototype_bridge_selftest.py, which notes its bridge's traffic);
- bridge-ab: explorer's window through the prototype's bridge (A, "prototype") and through explorer's (B), each step
  waiting until it is on X: the two bridges and nothing else.
Compared: the time from the application to the first image, steps in t and lambda, Stokes changes (their medians per
run, then the median over rounds, and the paired ratio explorer / prototype). On X (xcb and the bridges) also
first_on_x_s, from the command to the image seen on the Xvfb by another X client (8 rows of the window read every
20 ms; the image is there when they hold at least FIRST_LEVELS distinct values: the interface alone has a few dozen);
through the bridges, the bytes per step of each phase (explorer_selftest.phase_traffic).
"""
import argparse
import json
import os
import platform
import socket
import statistics
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from explorer_selftest import phase_traffic  # noqa: E402

KEYS = ["open_to_first_frame_s", "first_x_s", "first_on_x_s", "step in t", "step in λ", "change Stokes",
        "step in t on X", "step in λ on X", "change Stokes on X", "bytes/step t", "bytes/step l", "bytes/step s",
        "bytes/update t", "bytes/update l", "bytes/update s"]
FIRST_LEVELS = 120
X_MODES = ("xcb", "bridge", "bridge-ab")


def watch_first_image(proc, t_launch, disp):
    """Seconds from t_launch until a window of at least 600x400 on disp shows the image (see FIRST_LEVELS); None if
    the process ends first. disp: an Xlib Display of the Xvfb (another client, as the user's eyes)."""
    import numpy as np
    from Xlib import X

    root = disp.screen().root
    while proc.poll() is None:
        try:
            for c in root.query_tree().children:
                a = c.get_attributes()
                if a.map_state != X.IsViewable or a.win_class != X.InputOutput:
                    continue
                g = c.get_geometry()
                if g.width < 600 or g.height < 400:
                    continue
                seen = set()
                for k in range(8):
                    y = g.height * (k + 1) // 10
                    im = c.get_image(0, y, g.width, 1, X.ZPixmap, 0xFFFFFFFF)
                    seen.update(np.frombuffer(im.data, np.uint32, count=g.width) & 0xFFFFFF)
                if len(seen) >= FIRST_LEVELS:
                    return time.perf_counter() - t_launch
        except Exception:                               # a window gone between the listing and the reading
            pass
        time.sleep(0.02)
    return None


def run(cmd, env, out, xdisp=None):
    t_launch = time.perf_counter()
    p = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    first_on_x = watch_first_image(p, t_launch, xdisp) if xdisp is not None else None
    try:
        so, se = p.communicate(timeout=600)
    except subprocess.TimeoutExpired:
        p.kill()
        raise
    if p.returncode or not os.path.exists(out):
        raise RuntimeError(f"{cmd[1]} failed ({p.returncode}): {se[-800:]}")
    r = json.load(open(out))
    got = {"open_to_first_frame_s": r["open_to_first_frame_s"]}
    if r.get("first_x_s") is not None:
        got["first_x_s"] = r["first_x_s"]
    if first_on_x is not None:
        got["first_on_x_s"] = round(first_on_x, 3)
    for k in KEYS:
        if k in r.get("actions", {}):
            got[k] = r["actions"][k]["median"]
    if r.get("bridge_log") and r.get("marks"):
        for ax, d in phase_traffic(r["bridge_log"], r["marks"]).items():
            if ax in ("t", "l", "s"):
                got[f"bytes/step {ax}"] = d["bytes_per_step"]
                got[f"bytes/update {ax}"] = d["bytes_per_update"]
    if r.get("xbridge"):
        got["xbridge"] = r["xbridge"]
    return got


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cube")
    ap.add_argument("--rounds", type=int, default=4)
    ap.add_argument("--modes", default="offscreen,xcb")
    ap.add_argument("--pin", help="CPUs to pin both to (taskset -c), e.g. one NUMA node")
    ap.add_argument("--no-warmup", action="store_true", help="skip the unmeasured first run of each program")
    ap.add_argument("--out")
    a = ap.parse_args()
    proto = os.path.abspath(os.environ.get("EXPLORER_PROTOTYPE", os.path.join(ROOT, "..", "prototype")))
    plat = f"{platform.system()}-{platform.machine()}"
    ppy = next(p for p in (f"{proto}/.venv/bin/python", f"{proto}/.venv-{plat}/bin/python") if os.path.exists(p))
    epy = sys.executable
    xdisp = os.environ.get("EXPLORER_XVFB_DISPLAY", ":97")
    xauth = os.environ.get("EXPLORER_XVFB_AUTH", "/tmp/crispex_xvfb/auth")
    cfg = tempfile.mkdtemp(prefix="selftest_cfg_")
    tmp = tempfile.mkdtemp(prefix="selftest_out_")
    numba_cache = tempfile.mkdtemp(prefix="selftest_numba_")
    base = {k: v for k, v in os.environ.items() if k not in ("LD_LIBRARY_PATH", "DISPLAY", "QT_QPA_PLATFORM",
                                                             "NUMBA_NUM_THREADS", "XAUTHORITY", "EXPLORER_X11",
                                                             "CRISPEX_X11", "CRISPEX_XBRIDGE", "NUMBA_CACHE_DIR")}
    base["XDG_CONFIG_HOME"] = cfg
    pin = ["taskset", "-c", a.pin] if a.pin else []
    modes = a.modes.split(",")
    observer = None
    if any(m in X_MODES for m in modes):
        from Xlib import display as xdisplay

        os.environ["XAUTHORITY"] = xauth                # the observer's cookie, never the user's display
        observer = xdisplay.Display(xdisp)
    res = dict(host=socket.gethostname().split(".")[0], date=time.strftime("%Y-%m-%dT%H:%M:%S"),
               cube=os.path.basename(a.cube), pin=a.pin, load=os.getloadavg(), rounds=[], first_levels=FIRST_LEVELS)

    def env_for(impl, mode):
        e = dict(base)
        runs_proto = impl == "prototype" and mode != "bridge-ab"
        qtlibs = f"{proto if runs_proto else ROOT}/.qtlibs/only"
        if os.path.isdir(qtlibs):
            e["LD_LIBRARY_PATH"] = qtlibs
        if mode in X_MODES:
            e["DISPLAY"], e["XAUTHORITY"] = xdisp, xauth
        if mode in ("offscreen", "xcb"):
            e["QT_QPA_PLATFORM"] = mode
        elif runs_proto:
            e["CRISPEX_XBRIDGE"] = "1"
        else:
            e["EXPLORER_X11"] = "bridge"
        if runs_proto:
            e["NUMBA_NUM_THREADS"] = "64"
            e["PYTHONDONTWRITEBYTECODE"] = "1"          # nothing written into the prototype's folder
            e["NUMBA_CACHE_DIR"] = numba_cache
        if mode == "bridge-ab":
            e["EXPLORER_PROTOTYPE"] = proto
            e["NUMBA_CACHE_DIR"] = numba_cache
        return e

    def command(impl, mode, sp, out):
        nosp_e, nosp_p = ([], []) if sp else (["--nosp"], ["--no-sp"])
        if mode == "bridge-ab":
            return [epy, f"{HERE}/explorer_selftest.py", a.cube, "--out", out, "--wait-x", "--bridge-impl", impl,
                    *nosp_e]
        if impl == "explorer":
            return [epy, f"{HERE}/explorer_selftest.py", a.cube, "--out", out, *nosp_e]
        if mode == "bridge":
            return [ppy, f"{HERE}/prototype_bridge_selftest.py", proto, a.cube, "--out", out, *nosp_p]
        return [ppy, f"{proto}/app/selftest.py", a.cube, "--out", out, *nosp_p]

    def one(impl, mode, sp, out):
        return run(pin + command(impl, mode, sp, out), env_for(impl, mode), out, observer if mode in X_MODES else None)

    configs = [(m, sp) for m in modes for sp in (True, False)]
    if not a.no_warmup:                                 # every configuration: numba compiles what each path uses
        for mode, sp in configs:
            for impl in ("prototype", "explorer"):
                one(impl, mode, sp, os.path.join(tmp, f"warmup_{impl}_{mode}_{sp}.json"))
        print("warm-up done", flush=True)
    n = 0
    for rd in range(a.rounds):
        row = {}
        for mode, sp in configs:
            order = ["prototype", "explorer"] if (rd + n) % 2 == 0 else ["explorer", "prototype"]
            n += 1
            key = f"{mode}/{'sp' if sp else 'nosp'}"
            row[key] = {"order": order}
            for impl in order:
                row[key][impl] = one(impl, mode, sp, os.path.join(tmp, f"{impl}_{rd}_{mode}_{sp}.json"))
            p, e = row[key]["prototype"], row[key]["explorer"]
            print(f"round {rd + 1} {key:16s} ({order[0]} first): " + "  ".join(
                f"{k.replace('open_to_first_frame_s', 'first')} {p.get(k)} / {e.get(k)}" for k in KEYS if k in p),
                flush=True)
        res["rounds"].append(row)
    summary = {}
    for mode, sp in configs:
        key = f"{mode}/{'sp' if sp else 'nosp'}"
        rows = [r[key] for r in res["rounds"]]
        summary[key] = {}
        for k in KEYS:
            if not all(k in r["prototype"] and k in r["explorer"] for r in rows):
                continue
            pv = [r["prototype"][k] for r in rows]
            ev = [r["explorer"][k] for r in rows]
            ratio = [b / x for x, b in zip(pv, ev, strict=True) if x]
            summary[key][k] = dict(prototype=round(statistics.median(pv), 3), explorer=round(statistics.median(ev), 3),
                                   paired=round(statistics.median(ratio), 3), faster=sum(x < 1 for x in ratio),
                                   n=len(ratio))
        print(f"{key}: " + "; ".join(f"{k}: prototype {v['prototype']}, explorer {v['explorer']}, paired "
                                      f"{v['paired']} ({v['faster']}/{v['n']})" for k, v in summary[key].items()),
              flush=True)
    res["summary"] = summary
    res["load_end"] = os.getloadavg()
    if a.out:
        os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
        json.dump(res, open(a.out, "w"), indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())

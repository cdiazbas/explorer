"""explorer's window against the prototype's, each in its own process, alternating (ROADMAP E3.7).

    python bench/selftest_vs_prototype.py <cube_im.fits> [--rounds 4] [--modes offscreen,xcb] [--pin CPUS] [--out F]

For each round, mode (offscreen; xcb on the private Xvfb, EXPLORER_XVFB_DISPLAY default :97, cookie in
EXPLORER_XVFB_AUTH) and with and without the per-pixel file, the prototype's app/selftest.py and
bench/explorer_selftest.py run one after the other, which goes first alternating between rounds (ABBA). Each in the
environment it runs in by itself: the prototype with its Python, its .qtlibs and NUMBA_NUM_THREADS=64 as its
baseline (bench/prototype_baseline.sh); explorer with its own. Window layouts go to a temporary XDG_CONFIG_HOME.
Compared: the time from the application to the first image, steps in t and lambda, Stokes changes (their medians
per run, then the median over rounds, and the paired ratio explorer / prototype).
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
KEYS = ["open_to_first_frame_s", "step in t", "step in λ", "change Stokes"]


def run(cmd, env, out):
    p = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=600)
    if p.returncode or not os.path.exists(out):
        raise RuntimeError(f"{cmd[1]} failed ({p.returncode}): {p.stderr[-800:]}")
    r = json.load(open(out))
    got = {"open_to_first_frame_s": r["open_to_first_frame_s"]}
    for k in KEYS[1:]:
        if k in r.get("actions", {}):
            got[k] = r["actions"][k]["median"]
    return got


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cube")
    ap.add_argument("--rounds", type=int, default=4)
    ap.add_argument("--modes", default="offscreen,xcb")
    ap.add_argument("--pin", help="CPUs to pin both to (taskset -c), e.g. one NUMA node")
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
    base = {k: v for k, v in os.environ.items() if k not in ("LD_LIBRARY_PATH", "DISPLAY", "QT_QPA_PLATFORM",
                                                             "NUMBA_NUM_THREADS", "XAUTHORITY")}
    base["XDG_CONFIG_HOME"] = cfg
    pin = ["taskset", "-c", a.pin] if a.pin else []
    res = dict(host=socket.gethostname().split(".")[0], date=time.strftime("%Y-%m-%dT%H:%M:%S"),
               cube=os.path.basename(a.cube), pin=a.pin, load=os.getloadavg(), rounds=[])

    def env_for(impl, mode):
        e = dict(base)
        qtlibs = f"{proto if impl == 'prototype' else ROOT}/.qtlibs/only"
        if os.path.isdir(qtlibs):
            e["LD_LIBRARY_PATH"] = qtlibs
        e["QT_QPA_PLATFORM"] = mode
        if mode == "xcb":
            e["DISPLAY"], e["XAUTHORITY"] = xdisp, xauth
        if impl == "prototype":
            e["NUMBA_NUM_THREADS"] = "64"
        return e

    configs = [(m, sp) for m in a.modes.split(",") for sp in (True, False)]
    n = 0
    for rd in range(a.rounds):
        row = {}
        for mode, sp in configs:
            order = ["prototype", "explorer"] if (rd + n) % 2 == 0 else ["explorer", "prototype"]
            n += 1
            key = f"{mode}/{'sp' if sp else 'nosp'}"
            row[key] = {"order": order}
            for impl in order:
                out = os.path.join(tmp, f"{impl}_{rd}_{mode}_{sp}.json")
                if impl == "prototype":
                    cmd = [ppy, f"{proto}/app/selftest.py", a.cube, "--out", out] + ([] if sp else ["--no-sp"])
                else:
                    cmd = [epy, f"{HERE}/explorer_selftest.py", a.cube, "--out", out] + ([] if sp else ["--nosp"])
                row[key][impl] = run(pin + cmd, env_for(impl, mode), out)
            p, e = row[key]["prototype"], row[key]["explorer"]
            print(f"round {rd + 1} {key:14s} ({order[0]} first): " + "  ".join(
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
    if a.out:
        os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
        json.dump(res, open(a.out, "w"), indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())

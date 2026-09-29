"""Cost of one span (explorer.obs), to decide whether spans can stay on in the viewer (ROADMAP E0.4).

    python bench/obs_overhead.py [--out bench/results/obs_overhead_<host>.json]

Criterion: a user action (cursor move, t step) will open ~20 spans; the prototype's cursor takes 6-15 ms, so a
span must cost <= 5 us for all of them to stay <= 0.1 ms (<= 1 %). Each case runs N spans in a loop, minus the same
loop without spans, 7 times; the median ns per span is reported.
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
import threading
import time

from explorer import __version__, obs
from explorer.obs import spans, trace

N = 200_000


def loop_empty(n):
    t = time.perf_counter_ns()
    for _ in range(n):
        pass
    return time.perf_counter_ns() - t


def loop_flat(n):
    span = obs.span
    t = time.perf_counter_ns()
    for _ in range(n):
        with span("bench.flat"):
            pass
    return time.perf_counter_ns() - t


def loop_nested(n):                                    # n spans: n/2 parents, each with one child
    span = obs.span
    t = time.perf_counter_ns()
    for _ in range(n // 2):
        with span("bench.parent"):
            with span("bench.child"):
                pass
    return time.perf_counter_ns() - t


def per_span(fn, n=N, reps=7):
    out = []
    for _ in range(reps):
        spans.reset()
        out.append((fn(n) - loop_empty(n)) / n)
    return statistics.median(out), min(out), max(out)


def threaded(nthreads=4, n=N // 4):
    """ns per span with nthreads opening spans at the same time (wall time / total spans)."""
    bar = threading.Barrier(nthreads + 1)
    def work():
        bar.wait()
        loop_flat(n)
    ts = [threading.Thread(target=work) for _ in range(nthreads)]
    [t.start() for t in ts]
    t0 = time.perf_counter_ns()
    bar.wait()
    [t.join() for t in ts]
    return (time.perf_counter_ns() - t0) / (nthreads * n)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    a = ap.parse_args()
    res = dict(host=socket.gethostname().split(".")[0], date=time.strftime("%Y-%m-%dT%H:%M:%S"), version=__version__,
               python=platform.python_version(), machine=platform.machine(), load=os.getloadavg(), N=N, cases={})
    try:
        res["commit"] = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                                       cwd=os.path.dirname(os.path.abspath(__file__))).stdout.strip()
    except OSError:
        pass

    def rec(name, v):
        med, lo, hi = v if isinstance(v, tuple) else (v, v, v)
        res["cases"][name] = dict(ns_per_span=round(med, 1), min=round(lo, 1), max=round(hi, 1))
        print(f"  {name:34s} {med:8.1f} ns/span   (min {lo:.1f}, max {hi:.1f})", flush=True)

    print(f"obs span cost on {res['host']} ({res['machine']}, Python {res['python']}, load {res['load'][0]:.1f})")
    spans.set_enabled(False)
    rec("disabled", per_span(loop_flat))
    spans.set_enabled(True)
    rec("enabled, flat", per_span(loop_flat))
    rec("enabled, nested (parent+child)", per_span(loop_nested))
    obs.budget("bench.flat", 1000)
    rec("enabled, with a budget (not hit)", per_span(loop_flat))
    obs.budget("bench.flat", None)
    with tempfile.TemporaryDirectory() as d:
        trace.start(os.path.join(d, "t.json"))
        rec("enabled, recording a trace", per_span(loop_flat, reps=3))
        trace.stop(write=False)
    rec("enabled, 4 threads at once", threaded())
    worst = max(c["ns_per_span"] for k, c in res["cases"].items() if k != "disabled")
    res["per_action_us_at_20_spans"] = round(20 * worst / 1e3, 2)
    res["criterion"] = "<= 5000 ns per span"
    res["pass"] = worst <= 5000
    print(f"  worst enabled case x 20 spans per action = {res['per_action_us_at_20_spans']} us "
          f"(criterion <= 100 us): {'PASS' if res['pass'] else 'FAIL'}")
    if a.out:
        os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
        json.dump(res, open(a.out, "w"), indent=1)
    return 0 if res["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())

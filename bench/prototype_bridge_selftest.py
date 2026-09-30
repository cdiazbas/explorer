"""Run the prototype's app/selftest.py and note what its X11 bridge sent, and when, without changing the prototype
(ROADMAP E6: explorer's bridge against the prototype's).

    NUMBA_CACHE_DIR=<dir> <prototype python> bench/prototype_bridge_selftest.py <prototype dir> <selftest arguments...>

Adds to the self-test's JSON, on one clock: bridge_log, [time, bytes] for every update its sender finished, and marks,
[time, axis] for every step the self-test asked (t, l or s), so that explorer_selftest.phase_traffic gives the bytes
per step of each phase as it does for explorer. The self-test runs as it is (runpy, as bench/prototype_selftest.py);
XBridge.__init__ and startup.show are wrapped only to hand those two lists over. Nothing is written into the
prototype: no bytecode, and numba's cache goes to NUMBA_CACHE_DIR, which is required. Must run with the prototype's
own Python environment.
"""
import json
import os
import runpy
import sys
import time


class FrameLog(dict):
    """The bridge's stats dict, noting when each update's bytes were counted (by its sender thread, at the end)."""

    def __init__(self, d):
        super().__init__(d)
        self.log: list = []

    def __setitem__(self, k, v):
        if k == "bytes":
            self.log.append((time.perf_counter(), v - self.get("bytes", 0)))
        super().__setitem__(k, v)


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    if not os.environ.get("NUMBA_CACHE_DIR"):
        sys.exit("NUMBA_CACHE_DIR is not set: numba would write its cache into the prototype")
    sys.dont_write_bytecode = True
    proto, rest = os.path.abspath(sys.argv[1]), sys.argv[2:]
    app = os.path.join(proto, "app")
    sys.path.insert(0, app)
    import startup  # the prototype's app/startup.py and app/xbridge.py
    import xbridge

    bridges, marks = [], []
    init = xbridge.XBridge.__init__

    def logged_init(self, *a, **k):
        init(self, *a, **k)
        self.stats = FrameLog(self.stats)
        bridges.append(self)

    xbridge.XBridge.__init__ = logged_init
    show = startup.show

    def logged_show(app_, s, v, size=None):
        names = {v.ta: "t", v.la: "l", v.sa: "s"}
        step = v._step

        def logged_step(axis, *a, **k):
            marks.append((time.perf_counter(), names.get(axis, str(axis))))
            return step(axis, *a, **k)

        v._step = logged_step
        return show(app_, s, v, size)

    startup.show = logged_show
    sys.argv = [os.path.join(app, "selftest.py")] + rest
    runpy.run_path(sys.argv[0], run_name="__main__")
    out = rest[rest.index("--out") + 1] if "--out" in rest else None
    if out and bridges:
        r = json.load(open(out))
        r["bridge_log"] = [[round(t, 5), n] for t, n in bridges[0].stats.log]
        r["marks"] = [[round(t, 5), ax] for t, ax in marks]
        json.dump(r, open(out, "w"), indent=1)


if __name__ == "__main__":
    main()

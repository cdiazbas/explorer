"""The first moves of a window through the bridge, as the probe of ROADMAP E6.14 made them on XQuartz: a Shell built
by hand, 900x600, moved to (X0, Y0) before it is shown, then six moves of (STEP_X, STEP_Y) 0.5 s apart; where Qt and
X have it after each, and the places Qt went through in each step (test_bridge_first_moves.py). One JSON line.

    python tests/xvfb/first_moves_app.py <cube_im.fits> [X0 Y0 STEP_X STEP_Y]
"""
import json
import os
import sys
import tempfile
import time


def main():
    os.environ.setdefault("XDG_CONFIG_HOME", tempfile.mkdtemp())
    a = [int(v) for v in sys.argv[2:6]] if len(sys.argv) > 5 else [200, 150, 20, 12]
    from explorer.data.dataset import Dataset
    from explorer.platform.display import for_plan
    from explorer.platform.plan import choose_display

    disp = for_plan(choose_display(os.environ, sys.platform, "bridge"))
    disp.prepare_env()
    app = disp.make_app()
    from Xlib import display as xdisplay

    from explorer.ui.shell import Shell

    ds = Dataset.open(sys.argv[1])
    w = Shell(ds, title="first moves", t0=time.perf_counter())
    w.resize(900, 600)
    w.move(a[0], a[1])
    disp.attach(app, w)
    bridge = disp.bridge
    x = xdisplay.Display(os.environ.get("EXPLORER_TEST_XDISPLAY") or os.environ["DISPLAY"])
    root = x.screen().root
    rec = next(r for r in bridge.windows if r.w is w)

    def spin(s):
        end = time.perf_counter() + s
        while time.perf_counter() < end:
            app.processEvents()
            time.sleep(0.005)

    def x_pos():
        t = x.create_resource_object("window", rec.xid).translate_coords(root, 0, 0)
        return [-t.x, -t.y]

    applied0 = bridge.stats["applied"]
    spin(2.0)
    rows = [dict(asked=[a[0], a[1]], qt=[w.x(), w.y()], x=x_pos(), applied=bridge.stats["applied"] - applied0)]
    for k in range(1, 7):
        ask = [a[0] + k * a[2], a[1] + k * a[3]]
        n0 = bridge.stats["applied"]
        if bridge.trace is not None:
            bridge.trace.write("MARK", None, f"move {k}")
        w.move(*ask)
        seen = []
        end = time.perf_counter() + 0.5
        while time.perf_counter() < end:                # Qt's place through the step: a jump back shows here
            app.processEvents()
            if not seen or seen[-1] != [w.x(), w.y()]:
                seen.append([w.x(), w.y()])
            time.sleep(0.003)
        rows.append(dict(asked=ask, qt=[w.x(), w.y()], x=x_pos(), qt_went=seen, applied=bridge.stats["applied"] - n0))
    print(json.dumps(dict(rows=rows, windows=dict(bridge.windows.stats))), flush=True)
    w.close()
    ds.close()
    disp.close()


if __name__ == "__main__":
    main()

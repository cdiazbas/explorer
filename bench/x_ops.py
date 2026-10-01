"""What one window operation costs on the X server at DISPLAY, each confirmed by a round trip (sync): the cost an
outline or a live resize pays per step, on that server. Run it where the problem is seen (ssh -Y to XQuartz): it
shows a thin line and a grey window moving on that screen for a few seconds, then closes them.

    python bench/x_ops.py [--n 60]

Rows (median and p90 ms per operation, n each):
- round trip: a sync alone (the link and the server's turnaround);
- strip move: a 2 x 900 px override-redirect window moved and resized (one strip of a four-window outline);
- four strips: the four strips of an outline moved, then one sync (one step of the outline as it is);
- shaped outline: one 1400 x 900 window with a 2-px ring as its SHAPE, moved and reshaped (one window instead of
  four);
- big resize: a 1400 x 900 window resized by 4 px, its background drawn by the server (a live resize step without
  the pixels the client sends).
"""
import argparse
import statistics
import time

from Xlib import X, display
from Xlib.ext import shape


def timed(d, n, step):
    out = []
    for i in range(n):
        q = time.perf_counter()
        step(i)
        d.sync()
        out.append((time.perf_counter() - q) * 1e3)
    out.sort()
    return statistics.median(out), out[int(0.9 * (len(out) - 1))]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--n", type=int, default=60)
    a = ap.parse_args()
    d = display.Display()
    scr = d.screen()
    root = scr.root
    print(f"X server: {d.get_display_name()}  vendor {d.display.info.vendor}  screen {scr.width_in_pixels} x "
          f"{scr.height_in_pixels}", flush=True)

    def window(x, y, w, h, pixel, override=True):
        win = root.create_window(x, y, w, h, 0, scr.root_depth, X.InputOutput, X.CopyFromParent,
                                 background_pixel=pixel, override_redirect=override)
        win.map()
        d.sync()
        time.sleep(0.2)
        return win

    blue, grey = 0x2f6fde, 0x808080
    rows = [("round trip", timed(d, a.n, lambda i: None))]

    strip = window(100, 100, 2, 900, blue)
    rows.append(("strip move", timed(d, a.n, lambda i: strip.configure(x=600 + 4 * (i % 50), y=100, width=2,
                                                                         height=900))))
    bars = [strip] + [window(100, 100, 2, 2, blue) for _ in range(3)]

    def four(i):
        x, y, w, h = 100, 100, 1200 + 4 * (i % 50), 900
        for b, g in zip(bars, ((x, y, w, 2), (x, y + h - 2, w, 2), (x, y, 2, h), (x + w - 2, y, 2, h)), strict=True):
            b.configure(x=g[0], y=g[1], width=g[2], height=g[3])
    rows.append(("four strips (one outline step)", timed(d, a.n, four)))
    for b in bars:
        b.destroy()

    ring = window(100, 100, 1400, 900, blue)

    def reshape(i):
        w, h = 1200 + 4 * (i % 50), 900
        ring.configure(width=w, height=h)
        outer = [(0, 0, w, 2), (0, h - 2, w, 2), (0, 0, 2, h), (w - 2, 0, 2, h)]
        ring.shape_rectangles(shape.SO.Set, shape.SK.Bounding, X.Unsorted, 0, 0, outer)
    reshape(0)
    rows.append(("shaped outline (one window)", timed(d, a.n, reshape)))
    ring.destroy()

    big = window(100, 100, 1400, 900, grey, override=False)
    rows.append(("big resize (server-drawn)", timed(d, a.n, lambda i: big.configure(width=1200 + 4 * (i % 50),
                                                                                       height=900))))
    big.destroy()
    d.sync()
    print(f"{'operation':34s} {'median ms':>10s} {'p90 ms':>8s}   (n={a.n})")
    for name, (med, p90) in rows:
        print(f"{name:34s} {med:10.2f} {p90:8.2f}")


if __name__ == "__main__":
    main()

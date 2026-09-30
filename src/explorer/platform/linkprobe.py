"""How much the X11 link carries, to choose the default playback rate over ssh -X/-Y (Qt's own X11 or the bridge):
playing faster than the link only piles up lag. From the prototype's app/linkprobe.py; playback uses it (ROADMAP E4).

Measured in the prototype, bellatrix -> XQuartz by ssh -Y, Qt's own X11, one image ~3.0 MB (image panel 754x815 x
4 B, plus spectra and lambda-t):
    asked  4 fps: played 4.0, 12.6 MB/s written, frames still arriving 0.15 s after stopping
    asked  8 fps: played 8.0, 24.8 MB/s, 0.51 s
    asked 12 fps: played 7.9, 25.1 MB/s, 0.59 s          (the link: ~25-30 MB/s)
    asked 20 fps: played 16.5, 72 MB/s swallowed by ssh, 8.3 s behind

    measure() -> dict(MBps, rtt_ms)   ~0.2 s: a few round trips, then 4 MB into an invisible pixmap
    suggest_fps(MBps, frame_bytes)    60 % of the link over one image, between 2 and 30
"""
import statistics
import time


def measure(mb: int = 4) -> dict:
    from Xlib import X

    from .xbridge import xconn

    d = xconn.connect()                                 # with the auth fallback DISPLAY=host:N needs
    try:
        s = d.screen()
        rtts = []
        for _ in range(5):
            t = time.perf_counter()
            d.get_input_focus()
            rtts.append((time.perf_counter() - t) * 1e3)
        W, H = 1024, 256                                # 1 MB at 4 B/px; nothing is shown
        pm = s.root.create_pixmap(W, H, s.root_depth)
        gc = pm.create_gc()
        rows = max(1, (d.display.info.max_request_length * 4 - 64) // (W * 4))
        buf = bytes(range(256)) * (W * H * 4 // 256)
        d.sync()
        t = time.perf_counter()
        for _ in range(mb):
            for r in range(0, H, rows):
                k = min(rows, H - r)
                pm.put_image(gc, 0, r, W, k, X.ZPixmap, s.root_depth, 0, buf[r * W * 4:(r + k) * W * 4])
        d.sync()
        mbps = mb * W * H * 4 / 1e6 / (time.perf_counter() - t)
        pm.free()
        d.sync()
        return dict(MBps=round(mbps, 1), rtt_ms=round(statistics.median(rtts), 2))
    finally:
        d.close()


def suggest_fps(mbps: float, frame_bytes: float, headroom: float = 0.6, lo: int = 2, hi: int = 30) -> int:
    """headroom 0.6: at 8 fps on a ~25 MB/s link the lag was already 0.5 s (see above)."""
    return max(lo, min(hi, int(headroom * mbps * 1e6 / max(1, frame_bytes))))

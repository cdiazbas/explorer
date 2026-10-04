"""What the X11 bridge sends and receives for each X window, for faults seen only on someone else's X server (ROADMAP
E5.25). The geometry trace (ui/geomtrace.py) sees Qt's side of the windows; this one sees the X side: the windows
made, mapped, shaped and moved, the pixels sent and copied, the server's notices and errors, and what the server
holds in each window, read back.

    EXPLORER_BRIDGE_TRACE=1 explorer cube_im.fits  ->  ~/.cache/explorer/logs/bridge-<pid>.log  and  bridge-<pid>/

One line per step, milliseconds since the trace began, the window by name (main, a panel's name, else its title) and
X id:

      390.2 CREATE  spectrum  0x400007  (2757, 55, 560, 442) managed, owner -
      390.3 ICON    spectrum  0x400007  16, 32, 48, 128 px, 19976 CARDINALs, 79928 B
      390.4 OWNER   spectrum  0x400007  transient for main 0x40000b, after its map
      402.9 SHAPE   spectrum  0x400007  41 rects in (0, 0, 560, 442)
      403.1 GRAB    spectrum  0x400007  1 rects in (0, 0, 560, 442)
      411.6 SEND    spectrum  0x400007  new back 560x442; 15 pieces, 247520 px, 263 kB; copy (0, 0, 560, 442)
      452.0 EXPOSE  spectrum  0x400007  (0, 0, 560, 442) count 0
      452.1 COPY    spectrum  0x400007  (0, 0, 560, 442)
      453.7 XERR    img       0x400007  BadDrawable on CreateGC (55.0), value 0x400007: spectrum window
     2391.0 PROBE   spectrum  0x400007  at (2757, 55) 560x442, read (0, 0, 560, 442): X != sent 136 px (0 where it
                                         shows), Qt != sent 0 px; saved p0-spectrum-x.png

GRAB is what Qt repainted, grabbed here. Out on the control connection: CREATE, OWNER, MAP, CONF (a geometry asked
of X), SHAPE, ICON (_NET_WM_ICON set, at its sizes, or deleted), DESTROY; on the image connection: SEND (an update:
pixels into the window's back pixmap, then one copy into the window), COPY (an exposure answered from the back
pixmap), MASK (the 8-bit pixmap the grey pieces of every window go through). Times are when a request left this
process: X keeps the order of the requests of one connection, not between the two. In: NOTICE (a ConfigureNotify,
and what the bridge did with it), WHERE (the answer to where a framed window is), MAPPED, UNMAPPED, REPARENT,
EXPOSE, XERR (an error of either connection: the bridge goes on without one, so it is otherwise unseen).
PROBE, at EXPLORER_BRIDGE_PROBE seconds after the window was shown (comma-separated; default 2,6): each window's
pixels read back from the X server (GetImage, on the image connection after the updates sent before it), counted
against what the bridge sent there and what Qt has now; the X image saved as PNG in bridge-<pid>/, with the other two
when they differ. Outside the window's shape, and where another window of ours lies over it (X may hold the other's
pixels there: no backing store), X's pixels are no fault: the line counts those apart ("where it shows"). SUMMARY, at
the close: per window what was sent, copied, exposed and refused. Nothing is traced unless asked for.
"""
import collections
import os
import sys
import threading
import time
from pathlib import Path

from ..._name import ENV_PREFIX
from ..._paths import cache_dir

ENV = f"{ENV_PREFIX}BRIDGE_TRACE"
PROBE_ENV = f"{ENV_PREFIX}BRIDGE_PROBE"
PROBE_S = (2.0, 6.0)
REQUESTS = {1: "CreateWindow", 2: "ChangeWindowAttributes", 4: "DestroyWindow", 8: "MapWindow", 12: "ConfigureWindow",
            18: "ChangeProperty", 19: "DeleteProperty", 40: "TranslateCoordinates", 53: "CreatePixmap",
            54: "FreePixmap", 55: "CreateGC", 60: "FreeGC", 62: "CopyArea", 72: "PutImage", 73: "GetImage"}


def wanted(env=None) -> bool:
    """EXPLORER_BRIDGE_TRACE set, and not to 0."""
    return (env if env is not None else os.environ).get(ENV, "").strip() not in ("", "0")


def probe_times(env=None) -> tuple[float, ...]:
    raw = (env if env is not None else os.environ).get(PROBE_ENV, "").strip()
    if not raw:
        return PROBE_S
    try:
        return tuple(float(v) for v in raw.split(",") if v.strip())
    except ValueError:
        return PROBE_S


def from_env(env=None) -> "Trace | None":
    if not wanted(env):
        return None
    d = cache_dir() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    t = Trace(d / f"bridge-{os.getpid()}.log", probe_times(env))
    print(f"[xbridge] tracing what the bridge sends to {t.path}", file=sys.stderr)
    return t


def rect(x, y, w, h) -> str:
    return f"({x}, {y}, {w}, {h})"


class Trace:
    """The log, written from the interface, the control reader and the sender threads alike (one lock)."""

    def __init__(self, path, probes=PROBE_S):
        self.path = Path(path)
        self.dir = self.path.with_suffix("")             # the probes' images
        self.probes = probes
        self._lock = threading.Lock()
        self._out = open(self.path, "w", buffering=1, encoding="utf-8")
        self._t0 = time.perf_counter()
        self.names: dict[int, str] = {}                 # X id -> what it is (a window, its back pixmap, its gc)
        self.counts: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
        self.write("START", None, f"pid {os.getpid()}, DISPLAY {os.environ.get('DISPLAY', '')!r}")

    def who(self, xid: int) -> str:
        return self.names.get(xid, "?").split(" ", 1)[0]

    def name(self, xid: int, what: str) -> None:
        self.names[xid] = what

    def write(self, kind: str, xid: int | None, text: str) -> None:
        with self._lock:
            if self._out.closed:
                return
            ms = (time.perf_counter() - self._t0) * 1e3
            head = f"{self.who(xid):9s} {xid:#x}" if xid is not None else f"{'':9s} {'':8s}"
            self._out.write(f"{ms:9.1f} {kind:7s} {head}  {text}\n")

    def count(self, xid: int, **kw) -> None:
        with self._lock:
            self.counts[self.who(xid)].update(kw)

    def error(self, conn: str, err) -> None:
        """An X error of the control ('ctl') or image ('img') connection, its value named when it is ours."""
        what = self.names.get(err.bad)
        req = REQUESTS.get(err.major, "")
        self.write("XERR", err.bad if what is not None else None,
                   f"{conn}: {err.NAMES.get(err.code, err.code)} on {req or 'request'} ({err.major}.{err.minor}), "
                   f"value {err.bad:#x}: {what or 'not ours'}")
        if what is not None:
            self.count(err.bad, errors=1)

    def stop(self) -> None:
        with self._lock:
            done = self._out.closed
        if done:
            return
        for who, c in sorted(self.counts.items()):
            self.write("SUMMARY", None, f"{who}: " + ", ".join(f"{k} {v}" for k, v in sorted(c.items())))
        with self._lock:
            self._out.close()
        print(f"[xbridge] the bridge's trace of this session: {self.path}", file=sys.stderr)

    # ---- the probe: what the server holds, against what was sent and what Qt has
    def probed(self, k: int, xid: int, at, size, part, x_px, sent, qt, hidden) -> None:
        """One window's probe k: at, its root position (X); size, its back pixmap's; part (x, y, w, h), the piece read
        back (on the screen); x_px, sent, qt: that piece as X has it, as the bridge sent it, as Qt has it now (uint32,
        0x00RRGGBB); hidden: where it does not show (outside its shape, or under another window of ours)."""
        import numpy as np

        x_vs_sent = x_px != sent
        qt_vs_sent = qt != sent
        bad, late = int(x_vs_sent.sum()), int(qt_vs_sent.sum())
        bad_open = int((x_vs_sent & ~hidden).sum())
        text = (f"at {at} {size[0]}x{size[1]}, read {rect(*part)}: X != sent {bad} px ({bad_open} where it shows), "
                f"Qt != sent {late} px")
        if bad_open:
            ys, xs = np.nonzero(x_vs_sent & ~hidden)
            text += f"; X differs in {rect(int(xs.min()), int(ys.min()), int(xs.max() - xs.min() + 1),
                                           int(ys.max() - ys.min() + 1))}"
        self.dir.mkdir(parents=True, exist_ok=True)
        stem = self.dir / f"p{k}-{self.who(xid)}"
        saved = [_png(x_px, f"{stem}-x.png")]
        if bad_open or late:
            saved += [_png(sent, f"{stem}-sent.png"), _png(qt, f"{stem}-qt.png")]
        self.write("PROBE", xid, text + "; saved " + ", ".join(os.path.basename(s) for s in saved if s))
        self.count(xid, probes=1, probe_x_differs=int(bad_open > 0), probe_qt_differs=int(late > 0))


def _png(a, path: str) -> str | None:
    """A 0x00RRGGBB array as a PNG (QImage is reentrant: safe on the sender thread)."""
    import numpy as np
    from PySide6 import QtGui

    a = np.ascontiguousarray(a.astype(np.uint32) | 0xFF000000)
    h, w = a.shape
    img = QtGui.QImage(a.data, w, h, 4 * w, QtGui.QImage.Format.Format_RGB32)
    return path if img.save(path) else None

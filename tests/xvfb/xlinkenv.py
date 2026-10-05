"""The X tests through an emulated link (bench/xlink.py), as through ssh -Y to a Mac: EXPLORER_TEST_XLINK=DELAY,MBPS
(milliseconds each way, MB/s from the client to the server; e.g. 8,20 or 25,5). Off when unset: the applications
then talk to EXPLORER_TEST_XDISPLAY directly and nothing changes.

Only the application under test goes through the link (app_display): the window manager and the tests' own looks at
the X server (python-xlib) stay on the server's side, as quartz-wm and the screen are on the Mac. One link for the
whole session, started at its first use and stopped at the exit; each connection through it has its own pacing.

    EXPLORER_TEST_XLINK=25,5 EXPLORER_TEST_XDISPLAY=:99 pytest tests/xvfb
"""
import atexit
import os
import random
import subprocess
import sys
import tempfile
import threading

ENV = "EXPLORER_TEST_XLINK"
XLINK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "bench", "xlink.py")
_link: dict = {}
_lock = threading.Lock()


def link() -> tuple[float, float] | None:
    """(delay ms each way, MB/s up) asked for in EXPLORER_TEST_XLINK, or None."""
    raw = os.environ.get(ENV, "").strip()
    if not raw or raw == "0":
        return None
    delay, _, mbps = raw.partition(",")
    return float(delay), float(mbps or 0)


def describe() -> str:
    lk = link()
    return "no link" if lk is None else f"link {lk[0]:g} ms each way, {lk[1]:g} MB/s"


def app_display(xdisp: str) -> str:
    """The DISPLAY an application under test is given: xdisp itself, or the link to it (localhost:N)."""
    lk = link()
    if lk is None:
        return xdisp
    with _lock:
        if xdisp not in _link:
            _link[xdisp] = _start(xdisp, *lk)
        return _link[xdisp][0]


def own_link(xdisp: str, delay: float, mbps: float) -> str:
    """A link of its own to xdisp, for a test that needs one whatever EXPLORER_TEST_XLINK says; stopped at the
    exit."""
    key = f"{xdisp} {delay:g},{mbps:g}"
    with _lock:
        if key not in _link:
            _link[key] = _start(xdisp, delay, mbps)
        return _link[key][0]


def _start(xdisp: str, delay: float, mbps: float):
    to = xdisp.rsplit(":", 1)[1].split(".")[0]
    stats = os.path.join(tempfile.mkdtemp(prefix="xlink_"), "link.json")
    for _ in range(20):                                 # a free port: 6000 + a display number nobody uses
        n = random.randrange(600, 700)
        p = subprocess.Popen([sys.executable, XLINK, "--display", str(n), "--to", to, "--delay-ms", str(delay),
                              "--mbps", str(mbps), "--stats", stats], stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True)
        line = p.stdout.readline()
        if line.startswith("xlink:"):
            atexit.register(_stop, p)
            return f"localhost:{n}", p, stats
        p.wait(5)
    raise RuntimeError(f"no emulated link to {xdisp}: {p.stderr.read()[-2000:]}")


def _stop(p) -> None:
    p.terminate()
    try:
        p.wait(5)
    except subprocess.TimeoutExpired:
        p.kill()

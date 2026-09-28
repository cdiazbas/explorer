"""`explorer doctor`: can this user run explorer here, with this environment and this display? A few seconds.

    explorer doctor [cube_im.fits] [--show] [--out report.json]

Read-only on the cube (one header read and one small pread). Ported from the prototype's test.py, with two
changes: Qt is started in a child process, because a missing libxcb-cursor makes Qt abort the whole process
(prototype, 2026-09-26) and the doctor must survive to say so; and the report goes to the user's cache
directory (~/.cache/explorer/doctor/), not to wherever the command was run from.

Each check prints ok / WARN / FAIL with its time; the exit code is 1 if any check failed.
"""
import getpass
import json
import os
import platform
import socket
import subprocess
import sys
import time
import traceback

from . import __version__
from ._name import APP_NAME
from ._paths import cache_dir

OK, WARN, FAIL = "ok", "WARN", "FAIL"


class Report:
    def __init__(self):
        self.user = getpass.getuser()
        self.host = socket.gethostname().split(".")[0]
        self.data = dict(app=APP_NAME, version=__version__, user=self.user, host=self.host,
                         platform=platform.platform(), machine=platform.machine(), python=sys.executable,
                         date=time.strftime("%Y-%m-%dT%H:%M:%S"), checks=[])
        self.failed = False

    def check(self, name, fn):
        """Run one check; fn returns (status, info) or info (= ok). Keeps going after a failure."""
        t = time.perf_counter()
        try:
            r = fn()
            status, info = r if isinstance(r, tuple) else (OK, r)
        except Exception as e:  # a check that raises is a failure, with its traceback in the report
            status, info = FAIL, f"{type(e).__name__}: {e}"
            self.data.setdefault("tracebacks", {})[name] = traceback.format_exc()
        ms = (time.perf_counter() - t) * 1e3
        self.failed |= status == FAIL
        self.data["checks"].append(dict(name=name, status=status, ms=round(ms, 1), info=info))
        print(f"  {status:4s}  {name:22s} {ms:7.0f} ms  {info}", flush=True)


# ------------------------------------------------------------------------------------------------ checks
def c_python(rep):
    v = sys.version_info
    if sys.prefix != sys.base_prefix:
        where = "virtual environment"
    elif os.path.isdir(os.path.join(sys.prefix, "conda-meta")):
        where = "conda environment"                     # what setup_env.sh builds where there is no uv
    else:
        where = None
    info = f"Python {platform.python_version()} ({where or 'NOT an isolated environment'}: {sys.prefix})"
    if (v.major, v.minor) != (3, 12):
        return FAIL, info + "; explorer needs 3.12 (the version it was measured with)"
    return (OK if where else WARN), info


def c_packages(rep):
    """Installed versions against the pins in explorer's own metadata (the versions measured with)."""
    from importlib import metadata

    try:
        reqs = metadata.requires(APP_NAME) or []
    except metadata.PackageNotFoundError:
        return WARN, f"{APP_NAME} is not installed as a package (running from a source tree?): pins not checked"
    try:
        from packaging.requirements import Requirement
    except ImportError:
        return WARN, "'packaging' not available: pins not checked"
    found, off, missing = {}, [], []
    for line in reqs:
        r = Requirement(line)
        if r.marker is not None and not r.marker.evaluate({"extra": ""}):
            continue                                        # other platform, or an extra
        try:
            have = metadata.version(r.name)
        except metadata.PackageNotFoundError:
            missing.append(r.name)
            continue
        found[r.name] = have
        if not r.specifier.contains(have, prereleases=True):
            off.append(f"{r.name} {have} (pinned {r.specifier})")
    rep.data["versions"] = found
    if missing:
        return FAIL, "missing: " + ", ".join(missing)
    if off:
        return WARN, "not the measured versions: " + "; ".join(off)
    return OK, "  ".join(f"{k} {v}" for k, v in found.items())


def c_environment(rep):
    keys = ("DISPLAY", "WAYLAND_DISPLAY", "SSH_CONNECTION", "QT_QPA_PLATFORM", "LD_LIBRARY_PATH", "NUMBA_NUM_THREADS")
    env = {k: os.environ.get(k) for k in keys}
    rep.data["environment"] = env
    shown = ", ".join(f"{k}={v}" for k, v in env.items() if v and k != "LD_LIBRARY_PATH") or "no display variables"
    # another environment's Qt on this path breaks PySide6 (undefined symbol ... Qt_6_PRIVATE_API); our own
    # .qtlibs/only (libxcb-cursor alone, set by scripts/run.sh) is expected
    foreign = [d for d in (env["LD_LIBRARY_PATH"] or "").split(":") if d and not d.rstrip("/").endswith(".qtlibs/only")]
    if sys.platform.startswith("linux") and foreign:
        return WARN, f"LD_LIBRARY_PATH has {':'.join(foreign)}: it can load another Qt; {shown}"
    if env["LD_LIBRARY_PATH"]:
        shown += ", LD_LIBRARY_PATH=.qtlibs/only (libxcb-cursor)"
    return OK, shown


def c_files(rep):
    d = cache_dir()
    d.mkdir(parents=True, exist_ok=True)
    probe = d / f".write_test_{os.getpid()}"
    probe.write_text("ok")
    probe.unlink()
    rep.data["cache_dir"] = str(d)
    return f"cache directory writable: {d}"


def c_numba(rep):
    """Compile a serial and a parallel kernel. The parallel one tells which threading layer this machine has:
    'workqueue' aborts if two threads run parallel regions at once (prototype, 2026-09-24), so explorer runs
    every parallel kernel on one thread."""
    import numba
    import numpy as np

    t = time.perf_counter()

    @numba.njit(nogil=True)
    def serial(a):
        s = 0.0
        for v in a:
            s += v
        return s

    @numba.njit(parallel=True, nogil=True)
    def par(a):
        s = 0.0
        for i in numba.prange(a.size):
            s += a[i]
        return s

    a = np.arange(1000, dtype=np.float64)
    if serial(a) != a.sum() or par(a) != a.sum():
        return FAIL, "wrong result from a compiled kernel"
    ms = (time.perf_counter() - t) * 1e3
    layer = numba.threading_layer()
    rep.data["numba"] = dict(version=numba.__version__, threading_layer=layer, threads=numba.config.NUMBA_NUM_THREADS,
                             compile_ms=round(ms, 1))
    return f"numba {numba.__version__}: compiled in {ms:.0f} ms; threading layer {layer}, {numba.config.NUMBA_NUM_THREADS} threads"


def _libxcb_cursor():
    """Where libxcb-cursor.so.0 would come from, or None. Qt >= 6.5 needs it for X11; RHEL 9 lacks it."""
    for d in filter(None, os.environ.get("LD_LIBRARY_PATH", "").split(":")):
        p = os.path.join(d, "libxcb-cursor.so.0")
        if os.path.exists(p):
            return p
    try:
        out = subprocess.run(["/sbin/ldconfig", "-p"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        out = ""
    for line in out.splitlines():
        if "libxcb-cursor.so.0" in line:
            return line.split("=>")[-1].strip()
    return None


_QT_CHILD = r"""
import json, sys, time
from PySide6 import QtWidgets, QtCore
app = QtWidgets.QApplication(sys.argv[:1])
d = dict(platform=app.platformName(), qt=QtCore.qVersion(),
         screens=[dict(geometry=s.geometry().getRect(), dpr=s.devicePixelRatio()) for s in app.screens()])
if len(sys.argv) > 1 and app.platformName() != "offscreen":
    w = QtWidgets.QLabel("  " + sys.argv[1] + "  ")
    w.setWindowTitle(sys.argv[1]); w.resize(460, 80); w.show()
    t = time.perf_counter()
    while time.perf_counter() - t < 2:
        app.processEvents(); time.sleep(0.02)
    w.close(); d["shown"] = True
print("QTJSON" + json.dumps(d))
"""


def c_qt(rep, show):
    env = dict(os.environ)
    note = ""
    linux = sys.platform.startswith("linux")
    has_display = bool(env.get("DISPLAY") or env.get("WAYLAND_DISPLAY"))
    if not env.get("QT_QPA_PLATFORM"):
        if linux and not has_display:
            env["QT_QPA_PLATFORM"], note = "offscreen", " (no display: Qt checked offscreen)"
        elif sys.platform == "darwin" and env.get("SSH_CONNECTION") and not env.get("DISPLAY"):
            env["QT_QPA_PLATFORM"], note = "offscreen", " (Mac over ssh: no window server here; Qt checked offscreen)"
    if linux and env.get("DISPLAY") and env.get("QT_QPA_PLATFORM") in (None, "xcb") and _libxcb_cursor() is None:
        return FAIL, ("libxcb-cursor.so.0 not found: Qt cannot use X11 (ssh -Y) without it. Run scripts/setup_env.sh "
                      "(it installs it from conda-forge, no root), or: conda install -c conda-forge xcb-util-cursor")
    title = f"{APP_NAME} doctor: {rep.user}@{rep.host} {time.strftime('%H:%M:%S')}"
    cmd = [sys.executable, "-c", _QT_CHILD] + ([title] if show else [])
    r = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=60)
    line = next((x for x in r.stdout.splitlines() if x.startswith("QTJSON")), None)
    if r.returncode or line is None:
        why = f"signal {-r.returncode}" if r.returncode < 0 else f"exit {r.returncode}"
        err = (r.stderr.strip().splitlines() or [""])[-1]
        rep.data["qt_stderr"] = r.stderr[-4000:]
        hint = ""
        if "Qt_6_PRIVATE_API" in r.stderr or "undefined symbol" in r.stderr:
            hint = ("; another Qt was loaded, most likely through LD_LIBRARY_PATH: run explorer with "
                    "scripts/run.sh, or with LD_LIBRARY_PATH unset")
        return FAIL, f"Qt did not start ({why}): {err}{hint}"
    d = json.loads(line[len("QTJSON"):])
    rep.data["qt"] = d
    scr = ", ".join(f"{g['geometry'][2]}x{g['geometry'][3]}@{g['dpr']:g}" for g in d["screens"]) or "none"
    return OK, f"Qt {d['qt']} on '{d['platform']}', screens {scr}" + (", window shown" if d.get("shown") else "") + note


def c_cube(rep, path):
    """Header and one small read. The full read checks (image, spectrum, per-pixel file) come with the data
    layer (ROADMAP E1)."""
    from astropy.io import fits

    st = os.stat(path)
    t = time.perf_counter()
    with fits.open(path, memmap=False, lazy_load_hdus=True) as h:
        hdr, off = h[0].header, h[0]._data_offset
    t_hdr = (time.perf_counter() - t) * 1e3
    n = hdr["NAXIS"]
    shape = tuple(hdr[f"NAXIS{i}"] for i in range(n, 0, -1))
    axes = [str(hdr.get(f"CTYPE{i}", "?")) for i in range(n, 0, -1)]
    fd = os.open(path, os.O_RDONLY)
    try:
        t = time.perf_counter()
        b = os.pread(fd, 4096, off)
        t_read = (time.perf_counter() - t) * 1e3
    finally:
        os.close(fd)
    comp = path.replace("_im.", "_sp.")
    sp = [p for p in (comp, comp.rsplit(".", 1)[0] + ".icube") if p != path and os.path.exists(p)]
    d = dict(path=os.path.realpath(path), size_gb=round(st.st_size / 1e9, 2), shape=shape, axes=axes,
             bitpix=hdr["BITPIX"], header_ms=round(t_hdr, 1), small_read_ms=round(t_read, 2), per_pixel=sp)
    rep.data["cube"] = d
    if len(b) < 4096:
        return FAIL, f"short read at the data offset ({len(b)} B)"
    return (f"{os.path.basename(path)[:40]}: {d['size_gb']} GB, numpy shape {shape}, axes {axes}; header "
            f"{t_hdr:.0f} ms, first 4 KB {t_read:.2f} ms; per-pixel file: {'yes' if sp else 'no'}")


# ------------------------------------------------------------------------------------------------ entry
def main(argv=None) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog=f"{APP_NAME} doctor", description="check that this user can run explorer here")
    ap.add_argument("cube", nargs="?", help="a cube to read (header and one small read)")
    ap.add_argument("--show", action="store_true", help="open a small window for 2 s (checks the display)")
    ap.add_argument("--out", help="report file (default: ~/.cache/explorer/doctor/)")
    a = ap.parse_args(argv)

    t0 = time.perf_counter()
    rep = Report()
    print(f"{APP_NAME} {__version__} doctor: {rep.user}@{rep.host}, {platform.system()} {platform.machine()}", flush=True)
    rep.check("python", lambda: c_python(rep))
    rep.check("packages", lambda: c_packages(rep))
    rep.check("environment", lambda: c_environment(rep))
    rep.check("files", lambda: c_files(rep))
    rep.check("numba", lambda: c_numba(rep))
    rep.check("Qt", lambda: c_qt(rep, a.show))
    if a.cube:
        rep.check("cube", lambda: c_cube(rep, a.cube))
    rep.data["total_s"] = round(time.perf_counter() - t0, 1)
    rep.data["ok"] = not rep.failed

    out = a.out
    if out is None:
        d = cache_dir() / "doctor"
        try:
            d.mkdir(parents=True, exist_ok=True)
            out = str(d / f"doctor_{rep.user}_{rep.host}_{time.strftime('%Y%m%dT%H%M%S')}.json")
        except OSError:
            out = None
    if out:
        with open(out, "w") as f:
            json.dump(rep.data, f, indent=1, default=str)
    print(f"{'OK' if not rep.failed else 'FAILED'} in {rep.data['total_s']} s; report: {out or '(nowhere writable)'}",
          flush=True)
    return 1 if rep.failed else 0

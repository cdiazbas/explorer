"""The bridge's trace (platform/xbridge/trace.py), without an X server: asked for by its variable only (explorer --log
sets it), the probes only when asked for too, its lines, the errors named by what they hit, a probe's counts and
images, and the old sessions removed."""
import numpy as np


def test_off_unless_asked_and_the_probes_only_when_asked(monkeypatch, tmp_path):
    """A probe brings a whole window back over the link: the trace reads nothing back unless the probes are asked
    for."""
    from explorer.platform.xbridge import trace

    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    assert trace.from_env({}) is None and trace.from_env({trace.ENV: "0"}) is None
    assert not list(tmp_path.rglob("*.log"))
    for env, probes in (({trace.ENV: "1"}, ()), ({trace.ENV: "1", trace.PROBE_ENV: "3"}, (3.0,))):
        t = trace.from_env(env)
        try:
            assert t is not None and t.path.parent == tmp_path / "explorer" / "logs" and t.probes == probes, env
        finally:
            t.stop()
    assert trace.probe_times({trace.PROBE_ENV: "1.5, 4,9"}) == (1.5, 4.0, 9.0)
    assert trace.probe_times({trace.PROBE_ENV: "soon"}) == trace.PROBE_S


def test_lines_name_the_window_and_errors_name_what_they_hit(tmp_path):
    from explorer.platform.xbridge import trace
    from explorer.platform.xbridge.xproto import XError

    t = trace.Trace(tmp_path / "bridge.log")
    t.name(0x400007, "lambda_t window")
    t.name(0x60000E, "grey mask 560x408 pixmap")
    t.write("CREATE", 0x400007, "(2757, 509, 560, 408) managed, owner -")
    t.error("img", XError(9, 23, 0x60000E, 72, 0))
    t.error("ctl", XError(3, 40, 0x123, 12, 0))
    t.count(0x400007, updates=1, px=228480)
    t.stop()
    t.write("SEND", 0x400007, "after the close: dropped")
    lines = (tmp_path / "bridge.log").read_text().splitlines()
    assert lines[1].split()[1:4] == ["CREATE", "lambda_t", "0x400007"], lines
    assert "img: BadDrawable on PutImage (72.0), value 0x60000e: grey mask 560x408 pixmap" in lines[2], lines
    assert "ctl: BadWindow on ConfigureWindow (12.0), value 0x123: not ours" in lines[3], lines
    assert any("SUMMARY" in ln and "lambda_t: px 228480, updates 1" in ln for ln in lines), lines
    assert not any("dropped" in ln for ln in lines), lines


def test_a_probe_counts_what_x_lost_where_the_window_shows(qapp, tmp_path):
    """X lost a block that shows and a corner outside the shape: only the block is the bridge's fault; Qt has
    repainted one pixel since. The X image is saved, and with a fault the other two as well."""
    from explorer.platform.xbridge import trace

    t = trace.Trace(tmp_path / "bridge.log")
    t.name(7, "lambda_t window")
    sent = np.full((40, 60), 0x808080, np.uint32)
    got = sent.copy()
    got[10:20, 5:25] = 0                                # a grey block never drawn
    got[0, 0] = 0                                       # outside the rounded shape
    qt = sent.copy()
    qt[39, 59] = 0x101010
    hidden = np.zeros(sent.shape, bool)
    hidden[0, 0] = True
    t.probed(0, 7, (2757, 509), (60, 40), (0, 0, 60, 40), got, sent, qt, hidden)
    t.stop()
    text = (tmp_path / "bridge.log").read_text()
    assert "X != sent 201 px (200 where it shows), Qt != sent 1 px; X differs in (5, 10, 20, 10)" in text, text
    assert sorted(p.name for p in (tmp_path / "bridge").iterdir()) == [
        "p0-lambda_t-qt.png", "p0-lambda_t-sent.png", "p0-lambda_t-x.png"]
    from PySide6 import QtGui

    img = QtGui.QImage(str(tmp_path / "bridge" / "p0-lambda_t-x.png"))
    assert (img.width(), img.height()) == (60, 40) and img.pixel(5, 10) & 0xFFFFFF == 0
    assert img.pixel(40, 30) & 0xFFFFFF == 0x808080


def test_only_the_newest_sessions_are_kept(monkeypatch, tmp_path):
    """On by default, the traces would pile up: the oldest beyond KEEP_LOGS go, a probe's image folder with its log."""
    import os

    from explorer import _paths

    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    d = tmp_path / "explorer" / "logs"
    d.mkdir(parents=True)
    for k in range(_paths.KEEP_LOGS + 5):
        p = d / f"bridge-{1000 + k}.log"
        p.write_text("x")
        os.utime(p, (k, k))                             # the oldest first
    (d / "bridge-1000").mkdir()                         # the oldest one's probe images
    (d / "geometry-1.log").write_text("another kind: not counted")
    new = _paths.trace_log("bridge")
    left = sorted(d.glob("bridge-*.log"))
    assert len(left) == _paths.KEEP_LOGS - 1 and new.name == f"bridge-{os.getpid()}.log"
    assert not (d / "bridge-1000.log").exists() and not (d / "bridge-1000").exists()
    assert (d / "bridge-1034.log").exists() and (d / "geometry-1.log").exists()

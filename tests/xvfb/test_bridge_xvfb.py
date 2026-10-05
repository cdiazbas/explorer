"""The rewritten X11 bridge against a real X server (a private Xvfb, no window manager): explorer's window runs in its
own process (bridge_app.py) and this test is another X client (python-xlib, an independent implementation of the
protocol) that looks at its windows, reads their pixels back, types and clicks through XTEST, and uses the
clipboard.

    EXPLORER_TEST_XDISPLAY=:99 XAUTHORITY=<its cookie file> pytest tests/xvfb

Skipped without EXPLORER_TEST_XDISPLAY: never on anyone's screen. Xvfb has no window manager: what a manager does
(frames, activation requests, iconify) is not tested here.
"""
import json
import os
import subprocess
import sys
import threading
import time

import numpy as np
import pytest
from xlinkenv import app_display

from explorer.testing import synth

XDISP = os.environ.get("EXPLORER_TEST_XDISPLAY")
pytestmark = pytest.mark.skipif(not XDISP, reason="needs EXPLORER_TEST_XDISPLAY (a private Xvfb)")
HERE = os.path.dirname(os.path.abspath(__file__))
SHAPE = (3, 4, 5, 96, 80)


class App:
    def __init__(self, cube, size="800x600", *extra):
        env = dict(os.environ, DISPLAY=app_display(XDISP))
        env.pop("QT_QPA_PLATFORM", None)
        env.pop("EXPLORER_X11", None)
        self.p = subprocess.Popen([sys.executable, os.path.join(HERE, "bridge_app.py"), str(cube), "--size", size,
                                   *extra],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=env, text=True)
        self.hello = self._read(60)
        assert self.hello.get("ready"), self.hello

    def _read(self, timeout=20):
        box = []
        th = threading.Thread(target=lambda: box.append(self.p.stdout.readline()), daemon=True)
        th.start()
        th.join(timeout)
        if not box or not box[0]:
            raise AssertionError(f"no answer from the bridge app (exit {self.p.poll()})")
        return json.loads(box[0])

    def __call__(self, cmd, timeout=20):
        self.p.stdin.write(cmd + "\n")
        self.p.stdin.flush()
        return self._read(timeout)

    def close(self):
        if self.p.poll() is None:
            try:
                self("quit", 5)
            except (AssertionError, BrokenPipeError, OSError):
                pass
            try:
                self.p.wait(10)
            except subprocess.TimeoutExpired:
                self.p.kill()


@pytest.fixture(scope="module")
def cube(tmp_path_factory):
    return synth.write_dataset(tmp_path_factory.mktemp("xb2"), "c", shape=SHAPE, icube=False)["im"]


@pytest.fixture(scope="module")
def x():
    from Xlib import display

    d = display.Display(XDISP)
    yield d
    d.close()


@pytest.fixture(scope="module")
def app(cube):
    a = App(cube)
    yield a
    a.close()


def wait(fn, timeout=5.0, step=0.02):
    end = time.perf_counter() + timeout
    while time.perf_counter() < end:
        v = fn()
        if v:
            return v
        time.sleep(step)
    return fn()


def x_pixels(x, xid, w, h):
    from Xlib import X

    win = x.create_resource_object("window", xid)
    img = win.get_image(0, 0, w, h, X.ZPixmap, 0xFFFFFFFF)
    return np.frombuffer(img.data, np.uint32).reshape(h, w) & 0xFFFFFF


def same_as_qt(x, app, xid, which=""):
    """Pixels of the X window that differ from Qt's, where no other window of the app covers it (GetImage returns
    what is on the screen there: X keeps no hidden pixels without backing store)."""
    g = app("grab " + which if which else "grab")
    qt = np.load(g["path"]) & 0xFFFFFF
    os.remove(g["path"])
    got = x_pixels(x, xid, g["w"], g["h"])
    wins = app("state")["windows"]
    me = next(w for w in wins if w["xid"] == xid)
    seen = np.ones(got.shape, bool)
    above = False
    for w in wins:                                      # created later = above, without a window manager
        if w["xid"] == xid:
            above = True
            continue
        if above:
            x0, y0 = w["geometry"][0] - me["geometry"][0], w["geometry"][1] - me["geometry"][1]
            seen[max(0, y0):max(0, y0 + w["geometry"][3]), max(0, x0):max(0, x0 + w["geometry"][2])] = False
    return int(((got != qt) & seen).sum()), got.shape


def looked(x, app, step):
    """What the test saw at a step that failed: explorer's state, where X has the pointer and the focus, and the
    bridge's counts (a failure in CI cannot be watched again)."""
    root = x.screen().root
    p = root.query_pointer()
    st = app("state")
    seen = dict(step=step, cursor=st["cursor"], locked=st["locked"], popup=st["popup"], active=st["active"],
                pointer=(p.root_x, p.root_y), pointer_on=p.child, focus=x.get_input_focus().focus.id,
                windows=[(w["title"], w["xid"], w["geometry"], w["popup"]) for w in st["windows"]],
                bridge=st["summary"])
    return "\n".join(f"  {k}: {v}" for k, v in seen.items())     # text: pytest shortens a dict's repr


def main_window(app):
    return next(w for w in app("state")["windows"] if w["title"] == "bridge test λ")


def keycode(x, name):
    from Xlib import XK

    return x.keysym_to_keycode(XK.string_to_keysym(name))


def fake(x, kind, detail=0, xy=None):
    from Xlib import X
    from Xlib.ext import xtest

    if xy is not None:
        xtest.fake_input(x, X.MotionNotify, x=xy[0], y=xy[1])
    if kind is not None:
        xtest.fake_input(x, kind, detail)
    x.sync()


def test_the_window_is_mapped_with_the_image_and_its_properties(x, app):
    from Xlib import X, Xatom

    st = app("state")
    assert st["first_image"] is not None
    mw = main_window(app)
    win = x.create_resource_object("window", mw["xid"])
    assert win.get_attributes().map_state == X.IsViewable
    name = win.get_full_property(x.intern_atom("_NET_WM_NAME"), x.intern_atom("UTF8_STRING")).value
    assert name.decode() == "bridge test λ"
    assert win.get_wm_class() == ("explorer", "Explorer")
    assert win.get_full_property(x.intern_atom("_NET_WM_PID"), Xatom.CARDINAL).value[0] == app.hello["pid"]
    protocols = {x.get_atom_name(a) for a in win.get_wm_protocols()}
    assert protocols == {"WM_DELETE_WINDOW", "WM_TAKE_FOCUS", "_NET_WM_PING"}
    assert app("idle")["idle"]
    bad, shape = same_as_qt(x, app, mw["xid"])
    assert bad == 0, f"{bad} of {shape[0] * shape[1]} pixels differ from Qt's"


def test_keys_work_without_a_click(x, app):
    """No window manager: the bridge sets the X focus on the new window once it is viewable, so the first key goes
    to the viewer (ROADMAP E6.1; with a manager, the request goes through _NET_ACTIVE_WINDOW)."""
    mw = main_window(app)
    assert wait(lambda: x.get_input_focus().focus.id == mw["xid"])
    t0 = app("state")["t"]
    fake(x, 2, keycode(x, "Up"))                       # KeyPress
    fake(x, 3, keycode(x, "Up"))
    assert wait(lambda: app("state")["t"] == t0 + 1)
    assert app("state")["active"] == "bridge test λ"


def test_the_pointer_moves_the_cursor_and_a_click_locks_it(x, app):
    mw = main_window(app)
    gx, gy, gw, gh = mw["geometry"]
    c0 = app("state")["cursor"]
    fake(x, None, xy=(gx + gw // 2 - 40, gy + gh // 2 - 30))
    assert wait(lambda: app("state")["cursor"] != c0), looked(x, app, f"first move: the cursor still {c0}")
    c1 = app("state")["cursor"]
    fake(x, None, xy=(gx + gw // 2 + 30, gy + gh // 2 + 20))
    assert wait(lambda: app("state")["cursor"] != c1), looked(x, app, f"second move: the cursor still {c1}")
    fake(x, 4, 1)                                       # ButtonPress, left
    fake(x, 5, 1)
    assert wait(lambda: app("state")["locked"]), looked(x, app, "a left click: not locked")
    fake(x, 4, 3)                                       # right: release the cursor
    fake(x, 5, 3)
    assert wait(lambda: not app("state")["locked"]), looked(x, app, "a right click: still locked")
    # a right click opens no menu, as in the prototype (app/viewer.py:1018-1028)
    assert not wait(lambda: app("state")["popup"], timeout=0.5), looked(x, app, "a right click opened a menu")
    # a menu holds the pointer, and Escape, typed while the X focus is on the main window, closes it
    app("popup")
    assert app("state")["popup"], looked(x, app, "the menu did not open")
    fake(x, 2, keycode(x, "Escape"))
    fake(x, 3, keycode(x, "Escape"))
    assert wait(lambda: not app("state")["popup"] and not any(w["popup"] for w in app("state")["windows"])), \
        looked(x, app, "Escape: the menu still open")


def test_a_panel_is_transient_for_its_window_and_takes_its_shape(x, app):
    from Xlib import Xatom
    from Xlib.ext import shape

    app("panel")
    mw = main_window(app)
    pw = next(w for w in app("state")["windows"] if w["title"] == "panel λ–t")
    win = x.create_resource_object("window", pw["xid"])
    assert win.get_full_property(Xatom.WM_TRANSIENT_FOR, Xatom.WINDOW).value[0] == mw["xid"]
    # a normal window, not a utility one: quartz-wm puts its own 16-px title strip on a utility window even without
    # decorations, and keeps a transient window of any type above its owner (the prototype's xbridge.py:676-690)
    kind = win.get_full_property(x.intern_atom("_NET_WM_WINDOW_TYPE"), Xatom.ATOM).value[0]
    assert x.get_atom_name(kind) == "_NET_WM_WINDOW_TYPE_NORMAL"
    assert app("idle")["idle"]
    bad, _ = same_as_qt(x, app, pw["xid"], "panel")
    assert bad == 0
    app("mask")
    rects = wait(lambda: len(win.shape_get_rectangles(shape.SK.Bounding).rectangles) > 1)
    assert rects


def test_a_popup_takes_the_pointer_and_a_click_picks_an_item(x, app):
    r = app("popup")
    gx, gy, _, _ = r["geometry"]
    st = app("state")
    assert st["popup"]
    pop = next(w for w in st["windows"] if w["popup"])
    assert x.create_resource_object("window", pop["xid"]).get_attributes().override_redirect
    ix, iy = r["items"][1]
    fake(x, None, xy=(gx + ix, gy + iy))
    fake(x, 4, 1)
    fake(x, 5, 1)
    assert wait(lambda: app("state")["hits"] == ["two"])
    assert wait(lambda: not any(w["popup"] for w in app("state")["windows"])), app("state")["windows"]
    app("popup")                                        # a press outside, on no window of ours, closes it
    fake(x, None, xy=(3000, 900))
    fake(x, 4, 1)
    fake(x, 5, 1)
    assert wait(lambda: not app("state")["popup"])


class ClipboardClient:
    """Another X client: owns CLIPBOARD with a text (INCR in pieces when asked), or reads it (INCR too)."""

    def __init__(self):
        from Xlib import X, display

        self.d = display.Display(XDISP)
        self.X = X
        self.win = self.d.screen().root.create_window(0, 0, 1, 1, 0, 0, X.InputOnly, X.CopyFromParent,
                                                      event_mask=X.PropertyChangeMask)
        self.A = {n: self.d.intern_atom(n) for n in ("CLIPBOARD", "UTF8_STRING", "INCR", "TARGETS", "OUT")}

    def owned(self) -> bool:
        """Someone owns CLIPBOARD on the server."""
        o = self.d.get_selection_owner(self.A["CLIPBOARD"])
        return getattr(o, "id", o) != self.X.NONE

    def read(self, timeout=10.0):
        X, d, A = self.X, self.d, self.A
        self.win.convert_selection(A["CLIPBOARD"], A["UTF8_STRING"], A["OUT"], X.CurrentTime)
        d.flush()
        end = time.time() + timeout
        parts, incr = [], False
        while time.time() < end:
            if not d.pending_events():
                time.sleep(0.005)
                continue
            e = d.next_event()
            if e.type == X.SelectionNotify:
                if e.property == X.NONE:
                    return None
                p = self.win.get_full_property(A["OUT"], X.AnyPropertyType)
                self.win.delete_property(A["OUT"])
                d.flush()
                if p.property_type == A["INCR"]:
                    incr = True
                    continue
                return p.value.decode(), False
            if incr and e.type == X.PropertyNotify and e.atom == A["OUT"] and e.state == X.PropertyNewValue:
                p = self.win.get_full_property(A["OUT"], X.AnyPropertyType)
                self.win.delete_property(A["OUT"])
                d.flush()
                if not p.value:
                    return b"".join(parts).decode(), True
                parts.append(bytes(p.value))
        raise AssertionError("no clipboard answer")

    def own(self, text, chunk=None):
        """Own CLIPBOARD; serve text on a thread (INCR with pieces of `chunk` bytes when given)."""
        X, d, A = self.X, self.d, self.A
        self.win.set_selection_owner(A["CLIPBOARD"], X.CurrentTime)
        d.flush()
        data = text.encode()
        self.stop = False

        def serve():
            from Xlib.protocol import event as XE

            pending = None
            while not self.stop:
                if not d.pending_events():
                    time.sleep(0.005)
                    continue
                e = d.next_event()
                if e.type == X.SelectionRequest:
                    req = e.requestor
                    if chunk is None:
                        req.change_property(e.property, A["UTF8_STRING"], 8, data)
                    else:
                        req.change_attributes(event_mask=X.PropertyChangeMask)
                        req.change_property(e.property, A["INCR"], 32, [len(data)])
                        pending = (req, e.property, 0)
                    req.send_event(XE.SelectionNotify(time=e.time, requestor=req, selection=e.selection,
                                                      target=e.target, property=e.property))
                    d.flush()
                elif e.type == X.PropertyNotify and pending and e.state == X.PropertyDelete \
                        and e.atom == pending[1] and e.window.id == pending[0].id:
                    req, prop, off = pending
                    piece = data[off:off + chunk]
                    req.change_property(prop, A["UTF8_STRING"], 8, piece)
                    d.flush()
                    pending = (req, prop, off + len(piece)) if piece else None
        self.thread = threading.Thread(target=serve, daemon=True)
        self.thread.start()

    def close(self):
        self.stop = True
        self.d.close()


def test_the_stokes_drop_down_opens_and_picks_with_real_clicks(x, app):
    """The modern look's Stokes: a click drops the segments in a popup of their own, a click on V picks it and closes
    them; no nested event loop, so the bridge keeps painting."""
    app("look modern")
    try:
        st = app("stokes")
        assert not st["open"] and st["label"].startswith("Stokes ")
        fake(x, None, xy=st["button"])
        fake(x, 4, 1)
        fake(x, 5, 1)
        assert wait(lambda: app("stokes")["open"])
        assert wait(lambda: any(w["popup"] for w in app("state")["windows"]))
        fake(x, None, xy=app("stokes")["items"][3])
        fake(x, 4, 1)
        fake(x, 5, 1)
        assert wait(lambda: app("state")["s"] == 3)
        assert wait(lambda: not app("stokes")["open"] and not app("state")["popup"])
        assert app("stokes")["label"] == "Stokes V ▾"
    finally:
        app("look classic")


def test_the_panels_menu_with_a_slow_release_and_a_click_in_it(x, app):
    """Panels opens its menu with QMenu::exec, a nested event loop, on the press. On XQuartz the release comes
    later, while that loop runs, and the bridge never woke for it: the viewer hung (the user, 2026-10-01). XTEST
    sends press and release at once unless told otherwise: here they are 0.3 s apart, as a hand makes them, and the
    menu must then take a click on an item through X."""
    def click(xy, hold=0.3):
        fake(x, None, xy=xy)
        time.sleep(0.15)                                # the pointer there first, as a hand brings it
        fake(x, 4, 1)
        time.sleep(hold)
        fake(x, 5, 1)

    assert app("state")["docks"]["spectrum"]
    for want in (False, True):                          # hide the spectrum panel, then show it again
        click(app("where panels")["centre"])
        assert wait(lambda: app("state")["popup"])
        items = app("menu")["items"]
        spec = next(i for i in items if "pectrum" in i["text"])
        click(spec["centre"], hold=0.15)
        assert wait(lambda w=want: app("state")["docks"]["spectrum"] == w and not app("state")["popup"])


def test_clipboard_both_ways_with_incr(app):
    cc = ClipboardClient()
    try:
        app("copy hello from explorer ñ")
        # the application answers when Qt has the text; through a link (EXPLORER_TEST_XLINK) its claim on CLIPBOARD
        # reaches the server a delay later, and a request before that finds no owner
        assert wait(cc.owned)
        assert cc.read() == ("hello from explorer ñ", False)
        app("bigcopy 600000")                            # larger than one request: INCR
        text, incr = cc.read()
        assert incr and len(text) == 600000 and text.endswith("λ")
        cc.own("from another client ñ")
        assert wait(lambda: app("state")["clipboard"] == "from another client ñ")
        cc2 = ClipboardClient()
        try:
            cc2.own("z" * 700000, chunk=65536)
            assert wait(lambda: app("state")["clipboard_len"] == 700000, 10.0)
        finally:
            cc2.close()
        s = app("state")["summary"]["clipboard"]
        assert s["served_incr"] >= 1 and s["received_incr"] >= 1
    finally:
        cc.close()


def test_traffic_is_counted_and_an_expose_costs_no_pixels(x, app):
    from Xlib import X

    app("idle")
    s0 = app("state")["summary"]
    assert s0["updates"] > 0 and s0["acked"] == s0["updates"]
    assert s0["grey_fraction"] > 0.5 and s0["grey"]                        # the viewer is mostly grey
    mw = main_window(app)
    gx, gy, gw, gh = mw["geometry"]
    cover = x.screen().root.create_window(gx, gy, gw, gh, 0, x.screen().root_depth, X.InputOutput,
                                          X.CopyFromParent, background_pixel=x.screen().white_pixel,
                                          override_redirect=True)
    cover.map()
    x.sync()
    time.sleep(0.2)
    cover.destroy()                                     # the viewer's window is exposed again
    x.sync()
    app("idle")
    s1 = app("state")["summary"]
    assert s1["MB"] == s0["MB"]                         # copied again on the server, not sent
    bad, _ = same_as_qt(x, app, mw["xid"])
    assert bad == 0


def test_the_link_probe_measures_the_display():
    """The default playback rate over ssh comes from linkprobe.measure, on the bridge's own X11 client."""
    from explorer.platform import linkprobe

    r = linkprobe.measure(mb=1, display=app_display(XDISP))
    assert r["MBps"] > 0 and r["rtt_ms"] >= 0
    assert 2 <= linkprobe.suggest_fps(r["MBps"], 1.3 * 772 * 803) <= 30


def test_glass_panels_ask_the_manager_for_no_frame(x, app):
    """In glass the panels float with a title of their own: a window manager's frame above it was a second title
    (quartz-wm's grey bar, seen by the user through XQuartz), and its 16 px moved the panel down at every round
    trip. Each floating panel's X window asks for none, and is a normal window: quartz-wm frames a utility window
    whatever it asks."""
    from Xlib import Xatom

    motif = x.intern_atom("_MOTIF_WM_HINTS")
    try:
        app("look glass")
        titles = {"Spectrum", "λ–t"}
        wins = wait(lambda: [w for w in app("state")["windows"] if w["title"] in titles and not w["popup"]]
                    if len({w["title"] for w in app("state")["windows"]} & titles) == 2 else None)
        assert wins
        for w in wins:
            hints = x.create_resource_object("window", w["xid"]).get_full_property(motif, motif)
            assert hints is not None and hints.value[0] & 2 and hints.value[2] == 0, (w["title"], hints)
            kind = x.create_resource_object("window", w["xid"]).get_full_property(
                x.intern_atom("_NET_WM_WINDOW_TYPE"), Xatom.ATOM).value[0]
            assert x.get_atom_name(kind) == "_NET_WM_WINDOW_TYPE_NORMAL", w["title"]
    finally:
        app("look classic")


def test_panels_floating_before_their_window_are_normal_and_transient_for_it(x, cube):
    """A saved glass layout floats the panels before the main window is shown, so their X windows came first, with
    no owner: utility windows (quartz-wm's 16-px strip, the panels placed by the manager at 0,16) and not kept above
    the window. They are normal, and transient for the window once it is there."""
    from Xlib import Xatom

    a = App(cube, "800x600", "--float-first")
    try:
        st = a("state")
        mw = next(w for w in st["windows"] if w["title"].startswith("bridge test"))
        for w in (w for w in st["windows"] if w["title"] in ("Spectrum", "λ–t")):
            win = x.create_resource_object("window", w["xid"])
            kind = win.get_full_property(x.intern_atom("_NET_WM_WINDOW_TYPE"), Xatom.ATOM).value[0]
            assert x.get_atom_name(kind) == "_NET_WM_WINDOW_TYPE_NORMAL", w["title"]
            owner = wait(lambda win=win: win.get_full_property(Xatom.WM_TRANSIENT_FOR, Xatom.WINDOW))
            assert owner is not None and owner.value[0] == mw["xid"], w["title"]
    finally:
        a.close()


def test_the_wheel_gives_the_stokes_and_fps_boxes_the_focus(x, app):
    """Qt gives the focus to a widget with Qt::WheelFocus (QComboBox, QSpinBox) that a wheel turns, but only for a
    spontaneous wheel event; the bridge sends its wheel events itself (non-spontaneous), so through the bridge the
    boxes changed without taking the focus, where xcb gives it (conformance steps combo_wheel and spin_wheel,
    ROADMAP E6.10)."""
    app("activate")                                     # the window of the module's own app, not the last test's
    assert wait(lambda: app("state")["active"] == "bridge test λ")
    for name, kind in (("stokes", "QComboBox"), ("fps", "QSpinBox")):
        cx, cy = app(f"where {name}")["centre"]
        assert kind not in app("state")["focus"]          # the focus widget and its parent (a box's line edit)
        fake(x, None, xy=(cx, cy))
        fake(x, 4, 5)                                   # a wheel step down, then back up: the value as it was
        fake(x, 5, 5)
        fake(x, 4, 4)
        fake(x, 5, 4)
        assert wait(lambda k=kind: k in app("state")["focus"]), looked(x, app, f"the wheel over {name}: no focus")
        assert app("state")["summary"]["input"]["wheel"] >= 2
        fake(x, None, xy=(main_window(app)["geometry"][0] + 200, main_window(app)["geometry"][1] + 300))
        app("idle")


def test_a_window_manager_reads_the_size_hints_with_static_gravity(x, app):
    """WM_NORMAL_HINTS is of type WM_SIZE_HINTS (ICCCM 4.1.2.3), and a window manager asks for that type: written
    with the type WM_NORMAL_HINTS, the hints were there but no manager read them, so the static gravity that keeps a
    framed window from creeping down on XQuartz (audit F23c) did nothing (ROADMAP E6.5, found by bench/xprops.py)."""
    from Xlib import X, Xatom

    if not any(w["title"] == "panel λ–t" for w in app("state")["windows"]):
        app("panel")                                    # a tool window of the main one
    for title in ("bridge test λ", "panel λ–t"):
        rec = next(w for w in app("state")["windows"] if w["title"] == title)
        win = x.create_resource_object("window", rec["xid"])
        raw = win.get_full_property(Xatom.WM_NORMAL_HINTS, X.AnyPropertyType)
        assert raw is not None and raw.property_type == Xatom.WM_SIZE_HINTS, \
            f"{title}: WM_NORMAL_HINTS of type {x.get_atom_name(raw.property_type) if raw else None}"
        hints = win.get_wm_normal_hints()
        assert hints is not None and hints.flags & 512 and hints.win_gravity == X.StaticGravity, title

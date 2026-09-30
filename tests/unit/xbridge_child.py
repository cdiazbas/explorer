"""One bridged window on a private X server, driven through real X input (XTEST) and read back by another X client.
Run by tests/unit/test_xbridge_x11.py in a process of its own, because the bridge must connect before QApplication
exists (its screens are the X monitors) and the tests' shared QApplication is plain offscreen.

    python tests/unit/xbridge_child.py <work dir> [--input-only]

DISPLAY and XAUTHORITY: the private server's. Prints one JSON line with what it saw; the test asserts on it.
"""
import json
import math
import os
import sys
import time


def main():
    work, input_only = sys.argv[1], "--input-only" in sys.argv
    from explorer.platform import xbridge
    from explorer.platform.display import for_plan
    from explorer.platform.plan import choose_display

    plan = choose_display(os.environ, sys.platform, "bridge", bridge_available=xbridge.available())
    disp = for_plan(plan)
    disp.prepare_env()
    app = disp.make_app()
    b = disp.bridge

    from PySide6 import QtCore, QtGui, QtWidgets
    from Xlib import XK, X, Xatom
    from Xlib.ext import shape, xtest  # noqa: F401  (registers the requests on the display)

    from explorer.data.dataset import Dataset
    from explorer.platform.xbridge import xconn
    from explorer.testing import synth
    from explorer.ui.shell import Shell

    res: dict = {"plan": plan.kind, "qpa": os.environ.get("QT_QPA_PLATFORM", "")[:9], "input": disp.stats()["input"]}

    def pump(s=0.0):
        end = time.perf_counter() + s
        while True:
            app.processEvents()
            if time.perf_counter() >= end:
                return
            time.sleep(0.002)

    def spin(until, timeout=10.0):
        end = time.perf_counter() + timeout
        while not until() and time.perf_counter() < end:
            pump(0.005)
        return bool(until())

    XD = xconn.connect()                                # the observer: another X client

    def idle(quiet=0.25, timeout=5.0):
        end, q = time.perf_counter() + timeout, None
        while time.perf_counter() < end:
            pump(0.02)
            if b.inflight == 0 and all(r["dirty"].isEmpty() for r in b.wins.values()):
                q = q or time.perf_counter()
                if time.perf_counter() - q > quiet:
                    break
            else:
                q = None
        XD.sync()
        pump(0.05)

    def fake(kind, detail=0, **kw):
        XD.xtest_fake_input(kind, detail, **kw)
        XD.sync()

    def xwin(w):
        return XD.create_resource_object("window", b.wins[w]["x"].id)

    cube = synth.write_dataset(work, "c", shape=(3, 4, 5, 48, 40), icube=False)["im"]
    ds = Dataset.open(cube)
    w = Shell(ds)
    w.resize(640, 480)
    ops = disp.attach(app, w)
    res["first_image"] = spin(lambda: w.first_image_s is not None)
    idle()
    xw = xwin(w)
    g = xw.get_geometry()
    res["mapped"] = int(xw.get_attributes().map_state) == X.IsViewable
    res["x_size"], res["qt_size"] = [g.width, g.height], [w.width(), w.height()]
    t = xw.translate_coords(XD.screen().root, 0, 0)
    origin = (-t.x, -t.y)
    res["x_origin_is_qt_pos"] = list(origin) == [w.x(), w.y()]

    def x_vs_qt(win):
        idle()
        import numpy as np

        W, H = win.width(), win.height()
        qi = win.screen().grabWindow(win.winId(), 0, 0, W, H).toImage()
        qi = qi.convertToFormat(QtGui.QImage.Format.Format_RGB32)
        q = np.frombuffer(qi.constBits(), np.uint32, count=W * H).reshape(H, W) & 0xFFFFFF
        xi = xwin(win).get_image(0, 0, W, H, X.ZPixmap, 0xFFFFFFFF)
        x = np.frombuffer(xi.data, np.uint32, count=W * H).reshape(H, W) & 0xFFFFFF
        return int((q != x).sum())

    res["differing_px"] = x_vs_qt(w)

    # ---- input: the X focus on the window (a window manager would give it), the pointer over the image
    XD.set_input_focus(xw, X.RevertToParent, X.CurrentTime)
    XD.sync()
    view = w.view.widget
    c = view.mapTo(w, view.rect().center())
    fake(X.MotionNotify, x=origin[0] + c.x(), y=origin[1] + c.y())
    pump(0.2)
    s0, st0 = dict(b.stats), w.session.state
    kc = XD.keysym_to_keycode(XK.string_to_keysym("Up"))
    fake(X.KeyPress, kc)
    fake(X.KeyRelease, kc)
    res["key_moves_t"] = spin(lambda: w.session.state.t == st0.t + 1, 5.0)
    res["key_image_shown"] = spin(lambda: w.scheduler.img_idx is not None and w.scheduler.img_idx[0] == st0.t + 1)
    idle()
    s1 = dict(b.stats)
    res["step_traffic"] = dict(updates=s1["frames"] - s0["frames"], bytes=s1["bytes"] - s0["bytes"],
                               panel_px=view.width() * view.height(), grey=b.grey_on)
    res["differing_px_after_step"] = x_vs_qt(w)

    # a motion to another point of the image moves the cursor to the data pixel under it
    p = view.mapTo(w, QtCore.QPoint(view.width() // 3, view.height() // 3))
    before = w.session.state.cursor
    fake(X.MotionNotify, x=origin[0] + p.x(), y=origin[1] + p.y())
    moved = spin(lambda: w.session.state.cursor != before, 5.0)
    vp = w.view.vb.mapSceneToView(view.mapToScene(view.mapFrom(w, p)))
    res["motion_moves_cursor"] = moved
    res["cursor"], res["cursor_expected"] = list(w.session.state.cursor), [math.floor(vp.y()), math.floor(vp.x())]
    res["cursor_pos_follows_x"] = [QtGui.QCursor.pos().x(), QtGui.QCursor.pos().y()] == [origin[0] + p.x(),
                                                                                           origin[1] + p.y()]
    if input_only:
        print(json.dumps(res), flush=True)
        return 0

    # ---- a floating panel: its own X window, transient for the main one, a utility window (the manager's frames)
    dock = QtWidgets.QDockWidget("panel λ–t", w)
    dock.setWidget(QtWidgets.QLabel("panel"))
    w.addDockWidget(QtCore.Qt.DockWidgetArea.RightDockWidgetArea, dock)
    dock.setFloating(True)
    dock.resize(200, 150)
    dock.show()
    res["panel_has_x_window"] = spin(lambda: dock in b.wins, 3.0)
    if res["panel_has_x_window"]:
        dw = xwin(dock)
        tr = dw.get_full_property(Xatom.WM_TRANSIENT_FOR, Xatom.WINDOW)
        res["panel_transient_for_main"] = bool(tr) and tr.value[0] == b.wins[w]["x"].id
        ty = dw.get_full_property(XD.intern_atom("_NET_WM_WINDOW_TYPE"), Xatom.ATOM)
        res["panel_type"] = XD.get_atom_name(ty.value[0]) if ty else None
        nm = dw.get_full_property(XD.intern_atom("_NET_WM_NAME"), XD.intern_atom("UTF8_STRING"))
        res["panel_title"] = nm.value.decode() if nm else None
        res["panel_differing_px"] = x_vs_qt(dock)
    dock.close()
    res["panel_gone_with_hide"] = spin(lambda: dock not in b.wins, 3.0)

    # ---- a popup: override-redirect, placed by us
    menu = QtWidgets.QMenu(w)
    menu.addAction("one")
    menu.addAction("two")
    menu.popup(QtCore.QPoint(origin[0] + 50, origin[1] + 60))
    res["popup_has_x_window"] = spin(lambda: menu in b.wins, 3.0)
    if res["popup_has_x_window"]:
        res["popup_override_redirect"] = bool(xwin(menu).get_attributes().override_redirect)
    menu.close()
    spin(lambda: menu not in b.wins, 3.0)

    # ---- shape: a rounded outline through WindowOps, then back to a rectangle
    path = QtGui.QPainterPath()
    path.addRoundedRect(QtCore.QRectF(w.rect()), 16, 16)
    ops.set_shape(QtGui.QRegion(path.toFillPolygon().toPolygon()))
    idle()
    res["shape_rects"] = len(xw.shape_get_rectangles(shape.SK.Bounding).rectangles)
    ops.set_shape(None)
    idle()
    rr = xw.shape_get_rectangles(shape.SK.Bounding).rectangles
    res["shape_cleared"] = len(rr) == 1 and (rr[0].width, rr[0].height) == (w.width(), w.height())

    # ---- clipboard, both ways
    A = {n: XD.intern_atom(n) for n in ("CLIPBOARD", "UTF8_STRING", "OBS_PROP")}
    obs = XD.screen().root.create_window(0, 0, 1, 1, 0, 0, X.InputOnly, X.CopyFromParent,
                                         event_mask=X.PropertyChangeMask)
    QtWidgets.QApplication.clipboard().setText("explorer ñ")
    pump(0.1)
    owner = XD.get_selection_owner(A["CLIPBOARD"])
    res["clip_owner_is_bridge"] = b.clip is not None and getattr(owner, "id", owner) == b.clip.win.id
    obs.convert_selection(A["CLIPBOARD"], A["UTF8_STRING"], A["OBS_PROP"], X.CurrentTime)
    XD.flush()
    got = None
    end = time.perf_counter() + 5
    while got is None and time.perf_counter() < end:
        pump(0.01)
        while XD.pending_events():
            e = XD.next_event()
            if e.type == X.SelectionNotify and e.property:
                got = obs.get_full_property(A["OBS_PROP"], X.AnyPropertyType).value.decode()
    res["clip_qt_to_x"] = got
    obs.set_selection_owner(A["CLIPBOARD"], X.CurrentTime)
    XD.flush()
    end = time.perf_counter() + 5
    while QtWidgets.QApplication.clipboard().text() != "from X" and time.perf_counter() < end:
        pump(0.01)
        while XD.pending_events():
            e = XD.next_event()
            if e.type == X.SelectionRequest:              # the bridge asks us: answer as any X client would
                from Xlib.protocol import event as xev

                e.requestor.change_property(e.property, A["UTF8_STRING"], 8, b"from X")
                e.requestor.send_event(xev.SelectionNotify(time=e.time, requestor=e.requestor, selection=e.selection,
                                                           target=e.target, property=e.property))
                XD.flush()
    res["clip_x_to_qt"] = QtWidgets.QApplication.clipboard().text()

    # ---- traffic statistics and the link
    res["summary"] = b.summary()
    res["link"] = [disp.link().bytes_per_px, disp.link().fps_cap]

    # ---- the X display going away: the application closes with 1, once
    import socket as so

    QtCore.QTimer.singleShot(5000, lambda: app.exit(99))    # a guard: never hang the test
    b.ev.display.socket.shutdown(so.SHUT_RDWR)
    res["exit_when_x_gone"] = app.exec()
    ds.close()
    print(json.dumps(res), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

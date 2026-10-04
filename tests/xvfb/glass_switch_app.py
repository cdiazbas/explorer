"""explorer through its real start-up (ui.app.start, the bridge), switched from classic to glass as M does, and where
Qt and the X server have the window and the spectrum's panel 2.5 s later, as one JSON line (test_bridge_latewm.py).

    python tests/xvfb/glass_switch_app.py <cube_im.fits>
"""
import json
import os
import sys
import tempfile


def main() -> int:
    os.environ.setdefault("XDG_CONFIG_HOME", tempfile.mkdtemp())
    from PySide6 import QtCore
    from Xlib import display

    from explorer.look import get_look
    from explorer.ui.app import start

    s = start(sys.argv[1], look="classic", saved_layout=False, x11="bridge")
    if s is None:
        return 1
    w = s.shell
    x = display.Display(os.environ["DISPLAY"])

    def where(widget):
        rec = next(r for r in s.disp.bridge.windows if r.w is widget)
        t = x.create_resource_object("window", rec.xid).translate_coords(x.screen().root, 0, 0)
        return [-t.x, -t.y]

    def report():
        fg, sp = w.frameGeometry(), w.spec_dock.frameGeometry()
        print(json.dumps(dict(main=[fg.x(), fg.y(), fg.width(), fg.height()], main_right=fg.right(),
                              spec_qt=[sp.x(), sp.y()], spec_x=where(w.spec_dock))), flush=True)
        s.app.quit()

    QtCore.QTimer.singleShot(3000, lambda: w.set_look(get_look("glass")))
    QtCore.QTimer.singleShot(5500, report)
    try:
        return s.app.exec()
    finally:
        s.close()


if __name__ == "__main__":
    sys.exit(main())

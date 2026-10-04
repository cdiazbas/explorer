"""explorer through its real start-up (ui.app.start, the bridge), as `explorer cube` starts it: the look given, or the
one of the saved layout when '-'; the window closed after QUIT s, so the layout is saved as at a user's close
(test_bridge_glass_start.py).

    python tests/xvfb/glass_start_app.py <cube_im.fits> [look|-] [quit_s]
"""
import sys


def main() -> int:
    from PySide6 import QtCore

    from explorer.ui.app import start

    look = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] != "-" else None
    quit_s = float(sys.argv[3]) if len(sys.argv) > 3 else 5.0
    s = start(sys.argv[1], look=look, x11="bridge")
    if s is None:
        return 1
    QtCore.QTimer.singleShot(int(quit_s * 1000), s.shell.close)
    QtCore.QTimer.singleShot(int(quit_s * 1000) + 2000, s.app.quit)     # should the close not end it
    try:
        return s.app.exec()
    finally:
        s.close()


if __name__ == "__main__":
    sys.exit(main())

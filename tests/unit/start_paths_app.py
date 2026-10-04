"""explorer started as ui.app.run starts it (the saved layout at EXPLORER_LAYOUT, the chrome, the look), then M round
the looks and back to the first: what the window and its panels are at each step, one JSON line per step, for
tests/unit/test_start_paths.py (ROADMAP E5.15). It closes the window at the end, so the layout is saved as on a
user's close.

    python tests/unit/start_paths_app.py CUBE LOOK|-        (-: the look the saved layout says)
"""
import json
import sys
import time

from PySide6 import QtCore, QtWidgets

from explorer.look import LOOKS
from explorer.platform.screens import monitor_rect
from explorer.ui import app as appmod
from explorer.ui.shell import Shell

SETTLE_S = 0.8                                          # a look's deferred placing and fitting are done by then
QUIT_AFTER = 0.1                                        # run()'s quit_after: the call the scenario takes over


def snapshot(w: Shell, step: str) -> dict:
    app = QtWidgets.QApplication.instance()
    view = w.view.widget
    docks = {}
    for d in (w.spec_dock, w.lt_dock):
        t = d.titleBarWidget()
        docks[d.objectName()] = dict(floating=d.isFloating(), visible=d.isVisible(), geometry=d.geometry().getRect(),
                                     title=type(t).__name__ if t is not None else None)
    tb = w.nav.tb
    return dict(step=step, look=w.look.name, platform=app.platformName(), geometry=w.geometry().getRect(),
                frame=w.frameGeometry().getRect(), monitor=monitor_rect(app, w.frameGeometry().center()).getRect(),
                image=(view.width(), view.height()), docks=docks, toolbar=tb.isVisible(),
                toolbar_actions=len([a for a in tb.actions() if a.isVisible()]),
                glass_bar=w.glass is not None and w.glass.bar.isVisible())


def scenario(w: Shell, quit) -> None:
    app = QtWidgets.QApplication.instance()

    def settle():
        end = time.perf_counter() + SETTLE_S
        while time.perf_counter() < end:
            app.processEvents()
            time.sleep(0.005)

    settle()
    print(json.dumps(snapshot(w, "start")), flush=True)
    for k in range(len(LOOKS)):                         # M round every look, back to the first
        w.toggle_look()
        settle()
        print(json.dumps(snapshot(w, f"M{k + 1}")), flush=True)
    w.close()                                           # saves the layout, as a user's close does
    quit()


def main() -> int:
    cube, look = sys.argv[1], sys.argv[2]
    after = Shell.after_first_image
    # run()'s wait to quit runs the scenario instead, which quits at its end; the others (the app's icon) are kept
    Shell.after_first_image = lambda self, s, fn: (QtCore.QTimer.singleShot(0, lambda: scenario(self, fn))
                                                   if s == QUIT_AFTER else after(self, s, fn))
    return appmod.run(cube, look=None if look == "-" else look, quit_after=QUIT_AFTER)


if __name__ == "__main__":
    sys.exit(main())

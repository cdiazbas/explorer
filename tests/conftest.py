"""Every test runs with its own cache and config directories and without a log file, so that nothing a test logs
or writes (a budget warning, a doctor report, a window's layout) reaches the user's ~/.cache or ~/.config."""
import pytest


@pytest.fixture(autouse=True)
def _isolated_cache(monkeypatch, tmp_path_factory):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path_factory.mktemp("cache")))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path_factory.mktemp("config")))
    monkeypatch.delenv("EXPLORER_LAYOUT", raising=False)
    from explorer.obs import log

    log.setup(to_file=False)                            # console only, until a test asks for more
    yield
    log.setup(to_file=False)


@pytest.fixture(scope="session")
def qapp():
    """One QApplication for the tests that need Qt, always offscreen: no test opens a window on anyone's screen."""
    import os

    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6 import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture(autouse=True)
def _no_windows_left():
    """The main windows a test creates are deleted after it (once its own fixtures have closed them), and what they
    own goes with them. Left alive, they keep their timers and readers, and each change of the application's style
    re-polishes every widget of every one of them: 8425 widgets after the unit tests, 0.82 s per setStyle through
    the Python style (ui.style). Only main windows: pyqtgraph's menus are parentless but held by its plots, and
    deleting one before its plot crashes the plot's own deletion."""
    import sys

    qt = sys.modules.get("PySide6.QtWidgets")
    app = qt.QApplication.instance() if qt is not None else None
    before = {id(w) for w in qt.QApplication.topLevelWidgets()} if app is not None else set()
    yield
    qt = sys.modules.get("PySide6.QtWidgets")
    app = qt.QApplication.instance() if qt is not None else None
    if app is None:
        return
    from PySide6 import QtCore

    for w in qt.QApplication.topLevelWidgets():
        if id(w) not in before and isinstance(w, qt.QMainWindow):
            w.close()
            w.deleteLater()
    QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
    app.processEvents()
    # widgets a test left in Python reference cycles (pyqtgraph's) are freed now, not whenever the collector runs:
    # inside a Python callback of Qt's (the style's polish while a palette change walks every widget) it freed one
    # Qt was still walking, and the suite crashed about one run in four
    import gc

    gc.collect()
    QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)

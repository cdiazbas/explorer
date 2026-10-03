"""The window's layout across sessions (ROADMAP E5.3): its geometry and its panels, one per way of displaying (a
local Mac, Qt's own X11, the bridge, ...), as the prototype keeps them (app/viewer.py: GEOMETRY_KEY 2304, closeEvent
2306, forget_layout 2386, restore 2392).

- Kept: where things are and how big, never what is missing. A panel closed at exit is open at the next start.
- On close the geometry is kept unless the window is zoomed (the last normal size stays, as macOS does), and the
  panels' state always.
- At start the last geometry if it still fits one monitor, else the first window's size (ui.docks.first_geometry).
- The schema has a version: the groups are app/v<SCHEMA>.<kind>/, and those of another version are discarded.
- The look the window wore (classic or modern), the same for every way of displaying.
- One INI file per user (config_dir()/layout.ini, never next to the code); EXPLORER_LAYOUT names another one.
"""
import os

from PySide6 import QtCore, QtWidgets

from .._paths import config_dir

SCHEMA = 1
ENV = "EXPLORER_LAYOUT"
FITS = 1.02                     # a saved window may be this much larger than its monitor and still be used


def layout_path() -> str:
    return os.environ.get(ENV) or str(config_dir() / "layout.ini")


class LayoutStore:
    def __init__(self, kind: str, path: str | None = None):
        self.base = kind
        self.kind = f"v{SCHEMA}.{kind}"
        self.path = path or layout_path()
        self.geometry_key = f"app/{self.kind}/geometry"
        self.state_key = f"app/{self.kind}/state"

    def _settings(self) -> QtCore.QSettings:
        st = QtCore.QSettings(self.path, QtCore.QSettings.Format.IniFormat)
        st.beginGroup("app")
        for g in st.childGroups():                      # another schema: discarded
            if not g.startswith(f"v{SCHEMA}."):
                st.remove(g)
        st.endGroup()
        return st

    LOOK_KEY = f"ui/v{SCHEMA}/look"

    def for_look(self, look: str | None) -> "LayoutStore":
        """The glass look keeps a layout of its own (its panels float beside the window, its toolbar is hidden):
        the same file, its own group (the prototype's v.kind + "-glass", app/look_glass.py:618)."""
        if look == "glass" and not self.base.endswith("-glass"):
            return LayoutStore(self.base + "-glass", self.path)
        if look != "glass" and self.base.endswith("-glass"):
            return LayoutStore(self.base[:-len("-glass")], self.path)
        return self

    def save(self, window: QtWidgets.QMainWindow, zoomed: bool = False, look: str | None = None) -> None:
        st = self._settings()
        if not (zoomed or window.isMaximized() or window.isFullScreen()):
            st.setValue(self.geometry_key, window.saveGeometry())
        st.setValue(self.state_key, window.saveState())
        if look is not None:
            st.setValue(self.LOOK_KEY, look)
        st.sync()

    def look(self) -> str | None:
        """The look the window wore when it last closed; None if none was kept."""
        v = self._settings().value(self.LOOK_KEY)
        return str(v) if v else None

    def restore(self, window: QtWidgets.QMainWindow, app) -> bool:
        """The last geometry if it still fits one monitor, else the first window's; the panels' places and sizes.
        True when a panel layout was restored (its sizes with it)."""
        from ..platform.screens import monitor_rect
        from . import docks

        st = self._settings()
        g, s = st.value(self.geometry_key), st.value(self.state_key)
        ok = bool(g) and window.restoreGeometry(g)
        if ok:                                          # e.g. saved when two monitors were taken as one screen
            f = window.frameGeometry()
            m = monitor_rect(app, f.center())
            ok = f.width() <= m.width() * FITS and f.height() <= m.height() * FITS
        if not ok:
            window.setGeometry(docks.first_geometry(app))
        restored = bool(s) and window.restoreState(s)
        for d in window.findChildren(QtWidgets.QDockWidget):     # places and sizes, never absences
            if d.isHidden():
                d.show()
        # the toolbar as the look this layout is for wants it, not as the state says: hidden in glass (its controls
        # are on the glass bar), shown in the others (the prototype's viewer.py:2413-2415, look_glass.py:618-622).
        # Decided by the layout, not by the window's look: leaving glass restores the classic layout while the window
        # still wears glass
        glass = self.base.endswith("-glass")
        for tb in window.findChildren(QtWidgets.QToolBar):
            tb.setVisible(not glass)
        return restored

    def forget(self) -> None:
        """Back to the first window's size and panel layout, for this way of displaying only (--reset-layout)."""
        st = self._settings()
        st.remove(self.geometry_key)
        st.remove(self.state_key)
        st.sync()

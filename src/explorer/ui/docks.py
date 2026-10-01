"""The panels round the image: docks on the right, their margin, their sizes and the way back to the start (ROADMAP
E4.2). From the prototype's app/viewer.py: _gutter (622), _dock (1088), reset_panels (2342), _reset_sizes (2359),
and the window's first size from restore (2392, ASPECT and FILL at 2314).

A dock that is closed or hidden reads nothing: its visibility goes to Session.show, and the scheduler skips a hidden
panel (the prototype's skipped_hidden); shown again, it is filled for the cursor as it is.
"""
from PySide6 import QtCore, QtWidgets

PANEL_GUTTER = 5            # px round each panel: flush against the window's edge the plots read as cut off
PANELS_W = 0.434            # the panels' share of the window's width at a fresh start (640 of 1476 px)
ASPECT = 1.6                # the window: the image (square) and a right-hand column of ~0.6 of its width
FILL = 0.855                # of the monitor's height


def gutter(widget: QtWidgets.QWidget) -> QtWidgets.QWidget:
    """widget inside a PANEL_GUTTER margin (the prototype's _gutter; its look reuses this box as a card)."""
    box = QtWidgets.QWidget()
    box.setObjectName("gutter")
    lay = QtWidgets.QVBoxLayout(box)
    lay.setContentsMargins(*(PANEL_GUTTER,) * 4)
    lay.setSpacing(0)
    lay.addWidget(widget)
    return box


def dock(window: QtWidgets.QMainWindow, title: str, widget: QtWidgets.QWidget, name: str,
         area=QtCore.Qt.DockWidgetArea.RightDockWidgetArea) -> QtWidgets.QDockWidget:
    """A movable, floatable and closable dock (closing one costs nothing: its reads are skipped). name: the fixed
    key for saved layouts, so translating a title never loses where the user put it."""
    F = QtWidgets.QDockWidget.DockWidgetFeature
    d = QtWidgets.QDockWidget(title, window)
    d.setObjectName(name)
    d.setWidget(gutter(widget))
    d.setFeatures(F.DockWidgetMovable | F.DockWidgetFloatable | F.DockWidgetClosable)
    window.addDockWidget(area, d)
    d._home = DockHome(d)
    return d


class DockHome(QtCore.QObject):
    """A dock docked again by setFloating(False) (its float button) stayed where it had floated, as a child of the
    window: lambda-t at 590,466 in a 1200-px window, then 40 px further at each float and dock (Qt 6.11, xcb and
    offscreen). The layout's place for it had not changed, so Qt did not set it again; neither invalidate() nor the
    layout's own geometry again moved it. Where Qt leaves it so, it goes back to where it was last docked: only the
    dock moves (moving the whole layout one pixel and back repainted the window, 1.26 Mpx against 0.51). Where its
    place did change (the window resized meanwhile, another area), Qt has set it, and it is left alone."""

    def __init__(self, dock: QtWidgets.QDockWidget):
        super().__init__(dock)
        self.d = dock
        self.home = QtCore.QRect()                       # where it was last docked
        self.floated = QtCore.QRect()                    # where it last floated, in the screen's coordinates
        dock.installEventFilter(self)
        dock.topLevelChanged.connect(self._changed)

    def eventFilter(self, obj, e):
        if e.type() in (QtCore.QEvent.Type.Move, QtCore.QEvent.Type.Resize):
            if self.d.isFloating():
                self.floated = self.d.geometry()
            else:
                self.home = self.d.geometry()
        return False

    def _changed(self, floating: bool) -> None:
        if not floating:
            QtCore.QTimer.singleShot(0, self, self._back)

    def _back(self) -> None:
        """Only a dock still exactly where it floated, now as a child: one Qt placed (a double click on its title,
        a drag onto the window) is in its new place already, and home may be stale there."""
        if not self.d.isFloating() and self.home.isValid() and self.d.geometry() == self.floated != self.home:
            self.d.setGeometry(self.home)


def reset_sizes(window: QtWidgets.QMainWindow, docks) -> None:
    """Explicit sizes, as at a fresh start: the docked panels PANELS_W of the width, equal heights. After
    restoreState alone Qt kept whatever sizes it had (a closed lambda-t came back 517/311 px instead of 414/414)."""
    docked = [d for d in docks if d.isVisible() and not d.isFloating()]
    if not docked:
        return
    window.resizeDocks([docked[0]], [int(window.width() * PANELS_W)], QtCore.Qt.Orientation.Horizontal)
    if len(docked) > 1:
        h = sum(d.height() for d in docked)
        window.resizeDocks(docked, [h // 2, h - h // 2], QtCore.Qt.Orientation.Vertical)


def first_geometry(app: QtWidgets.QApplication) -> QtCore.QRect:
    """The window at a first start: FILL of the height of the monitor under the pointer, at most ASPECT times as
    wide as high, centred on it (the prototype's restore without a saved geometry)."""
    from ..platform.screens import monitor_rect

    mon = monitor_rect(app)
    h = int(mon.height() * FILL)
    w = min(int(mon.width() * FILL), int(h * ASPECT))
    return QtCore.QRect(mon.x() + (mon.width() - w) // 2, mon.y() + (mon.height() - h) // 2, w, h)

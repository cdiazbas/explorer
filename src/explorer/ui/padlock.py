"""The padlock in a panel's top-right corner (ROADMAP E4.7), the same on the image and on the spectra: closed = the
scale is fixed, open = automatic; a click switches, a right click fits it to what is shown now and fixes it. On the
panel itself, next to what it acts on, not in the toolbar.

Drawn as vectors (an emoji padlock is missing from some Linux fonts, and the X11 bridge shows what Qt draws),
repainted only when its state or hover changes. No focus: it never takes the keys. From the prototype's
app/viewer.py: PanelLock (632), its wiring (1052-1063).

zoom: the padlock drawn that many times its size (SIZE and its drawing in its own units), the button rounded up so
that a click anywhere on what it draws takes: a panel of the 2x2 view has GRID_LOCK_ZOOM.
"""
import math

from PySide6 import QtCore, QtGui, QtWidgets

GRID_LOCK_ZOOM = 0.75                                   # a panel of the 2x2 view's padlock: 17 px for 22


class PanelLock(QtWidgets.QToolButton):
    refit = QtCore.Signal()
    SIZE, MARGIN = 22, 8

    def __init__(self, view: QtWidgets.QWidget, tip: str, light: bool = False, backed: bool = True,
                 zoom: float = 1.0):
        """backed: a dark (light) square under it, needed over an image; over a plot's plain background it stood out
        as a hole in the glass look's panel, so there only on hover. zoom: see the module."""
        super().__init__(view)
        self.light, self.backed, self.zoom = light, backed, float(zoom)
        self.setCheckable(True)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.setAutoRaise(True)
        self.setCursor(QtCore.Qt.CursorShape.ArrowCursor)   # a button: the panel's own pointer does not apply here
        side = math.ceil(self.SIZE * self.zoom)
        self.resize(side, side)
        self.setToolTip(tip)
        view.installEventFilter(self)
        self._place(view)
        self.raise_()

    def set_light(self, light: bool) -> None:
        self.light = light
        self.update()

    def set_closed(self, on: bool) -> None:
        """Show the state without acting on it (the scale was fixed by a key or a refit)."""
        if self.isChecked() != on:
            self.blockSignals(True)
            self.setChecked(on)
            self.blockSignals(False)
            self.update()

    def eventFilter(self, obj, e):
        if e.type() == QtCore.QEvent.Type.Resize:
            self._place(obj)
        return False

    def _place(self, view):
        self.move(view.width() - self.width() - self.MARGIN, self.MARGIN)

    def mousePressEvent(self, e):
        if e.button() == QtCore.Qt.MouseButton.RightButton:
            self.refit.emit()
            e.accept()
            return
        super().mousePressEvent(e)

    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        p.scale(self.zoom, self.zoom)                   # from here on in its own units (zoom)
        box = QtCore.QRectF(0, 0, self.SIZE, self.SIZE)
        bg = QtGui.QColor(255, 255, 255, 200) if self.light else QtGui.QColor(0, 0, 0, 140)
        if not self.backed:
            bg = QtGui.QColor(0, 0, 0, 0)
            if self.underMouse():
                bg = QtGui.QColor(0, 0, 0, 22) if self.light else QtGui.QColor(255, 255, 255, 28)
        elif self.underMouse():
            bg.setAlpha(min(255, bg.alpha() + 50))
        p.setPen(QtCore.Qt.PenStyle.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(box.adjusted(0.5, 0.5, -0.5, -0.5), 6, 6)
        pal = self.palette()
        role = getattr(QtGui.QPalette.ColorRole, "Accent", QtGui.QPalette.ColorRole.Highlight)
        on = self.isChecked()
        off = QtGui.QColor(0, 0, 0, 170) if self.light else QtGui.QColor(255, 255, 255, 200)
        ink = pal.color(role) if on else off
        cx = box.width() / 2
        pen = QtGui.QPen(ink, 1.6)
        pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
        path = QtGui.QPainterPath()
        if on:                                          # closed: both legs of the shackle in the body
            path.moveTo(cx - 3.2, 10.5)
            path.lineTo(cx - 3.2, 8.0)
            path.arcTo(QtCore.QRectF(cx - 3.2, 4.2, 6.4, 7.6), 180, -180)
            path.lineTo(cx + 3.2, 10.5)
        else:                                           # open: the left leg lifted out
            path.moveTo(cx - 3.2, 5.5)
            path.arcTo(QtCore.QRectF(cx - 3.2, 1.7, 6.4, 7.6), 180, -180)
            path.lineTo(cx + 3.2, 10.5)
        p.setPen(pen)
        p.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        p.setPen(QtCore.Qt.PenStyle.NoPen)
        p.setBrush(ink)
        p.drawRoundedRect(QtCore.QRectF(cx - 5, 10.5, 10, 7.5), 1.5, 1.5)
        p.end()

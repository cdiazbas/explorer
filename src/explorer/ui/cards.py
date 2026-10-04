"""Rounded panels (ROADMAP E5.5), from the prototype's app/look.py (_Corner, _Rounder, _MacSeams, _cards: 476-570):
the classic look rounds the panels' corners, the modern one also puts them on cards."""
from PySide6 import QtCore, QtGui, QtWidgets

RADIUS = 6
CARD = QtGui.QColor(0, 0, 0)                            # plot cards: black, as the image's (a grey 20, 20, 22 parted
                                                        # them from the image beside them)
CARD_LIGHT = QtGui.QColor(255, 255, 255)                # light theme: white plot cards on the #ececec window


class _Corner(QtWidgets.QWidget):
    """One rounded corner over a panel: the window's colour outside a quarter circle, antialiased. Four small widgets
    rather than a mask: a mask's edge is 1-bit and jagged, and these repaint only when their corner does."""

    def __init__(self, target, which):
        super().__init__(target)
        self.which = which
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.resize(RADIUS, RADIUS)

    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        r = float(RADIUS)
        cx = 0.0 if "r" in self.which else r              # the circle's centre, in this widget
        cy = 0.0 if "b" in self.which else r
        path = QtGui.QPainterPath()
        path.addRect(QtCore.QRectF(0, 0, r, r))
        arc = QtGui.QPainterPath()
        arc.addEllipse(QtCore.QPointF(cx, cy), r, r)
        p.fillPath(path.subtracted(arc), self.window().palette().color(QtGui.QPalette.ColorRole.Window))
        p.end()


class Rounder(QtCore.QObject):
    def __init__(self, target: QtWidgets.QWidget):
        super().__init__(target)
        self.corners = [_Corner(target, w) for w in ("tl", "tr", "bl", "br")]
        target.installEventFilter(self)
        if isinstance(target, QtWidgets.QStackedWidget):
            # the spectra's stack swaps in its resize snapshot and back without a resize: the page shown again came
            # up over the corners
            target.currentChanged.connect(lambda _i: QtCore.QTimer.singleShot(0, self, lambda: self._place(target)))
        self._place(target)

    def eventFilter(self, obj, e):
        if e.type() in (QtCore.QEvent.Type.Resize, QtCore.QEvent.Type.Show):
            self._place(obj)
        return False

    def _place(self, t):
        w, h = t.width(), t.height()
        for c in self.corners:
            c.move(w - RADIUS if "r" in c.which else 0, h - RADIUS if "b" in c.which else 0)
            c.raise_()


class MacSeams(QtWidgets.QProxyStyle):
    """On a local Mac's native style, the seams between the panels in the window's own colour: Qt's macOS style draws
    the dock separators and a line under each dock title in light greys even in dark mode, and next to the dark
    panels they read as bright frames. The gutters already part the panels. Set on the main window and its docks
    only, in both looks (ui.style draws no such line either)."""

    def __init__(self):
        super().__init__(QtWidgets.QStyleFactory.create("macos"))

    def drawPrimitive(self, pe, opt, p, w=None):
        if pe == QtWidgets.QStyle.PrimitiveElement.PE_IndicatorDockWidgetResizeHandle:
            p.fillRect(opt.rect, opt.palette.color(QtGui.QPalette.ColorRole.Window))
            return
        super().drawPrimitive(pe, opt, p, w)

    def drawControl(self, ce, opt, p, w=None):
        super().drawControl(ce, opt, p, w)
        if ce == QtWidgets.QStyle.ControlElement.CE_DockWidgetTitle:      # the title's bottom line, painted over
            r = opt.rect
            p.fillRect(QtCore.QRectF(r.left(), r.bottom() - 0.5, r.width(), 1.5),
                       opt.palette.color(QtGui.QPalette.ColorRole.Window))

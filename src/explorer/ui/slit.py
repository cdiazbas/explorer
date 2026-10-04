"""The slit drawn on the image (ROADMAP E7.1). S, or the toolbar's slit button, turns the slit mode on: a click adds a
point (on the pixel's centre), a double click finishes the slit, a right click removes the last point (with none
left, the mode ends), Esc or S again leave the mode and the unfinished slit with it; ⌫ (or Delete) removes the
finished one. Two points give a straight slit, more a curve through every point (data.slits.slit_path). Drag still
pans and the wheel still zooms: only the click changes. The mode shows that it is on three ways: the button on, a
pencil for the pointer and a line inside the image saying how to draw; with a slit drawn, that line says how to
remove it. The finished slit is the session's (ViewState.path, the points clicked); the slit being drawn is too, with
the pixel under the pointer as its free end (ViewState.draft, once per pixel the pointer enters), and the slit panel
(ui.slitpanel, core.slitreads) shows its slices while it is drawn.

This is the prototype's variant D (its audit's F74): A's drawing and erasing, with C's live slices while drawing. From
the prototype's app/viewer.py: SlitHint (836), the class comment on the variants (869-875), the slit's items
(1224-1243), _escape (1355), _image_click (1419), _image_pointer to _slit_backspace (1486-1619), the free end of
_slit_hover (1596-1604), _slit_draw_band to _slit_style (1721-1739); app/icons.py pencil_cursor (219).

    tool = SlitTool(session, view, hint)        view: the ImageView to draw on; attach() adds the 2x2 view's
    tool.set_mode(True); tool.click(ev, vb); tool.hover(y, x); tool.clear()
"""
import math

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtGui, QtWidgets

from ..data.slits import slit_path

BAND_STEP = 2.0                                         # px between the samples of the slit being drawn


def pencil_cursor(widget: QtWidgets.QWidget | None = None) -> QtGui.QCursor:
    """The image's pointer while a slit is drawn: a pencil, its tip on the pixel (hot spot). Drawn here, for Qt has no
    pencil shape; the X11 bridge shows the X cursor font's pencil for a pixmap cursor (xbridge.windows.CURSORS). At
    the device pixel ratio of the screen the widget is on: xcb does not scale a cursor pixmap, and a 2x one came out
    48 x 48 with its hot spot at (1, 23), the middle of the left edge instead of the tip (the prototype's F69a)."""
    scr = widget.screen() if widget is not None else None
    scr = scr or QtGui.QGuiApplication.primaryScreen()
    dpr = max(1.0, scr.devicePixelRatio()) if scr is not None else 1.0
    n = 24
    pm = QtGui.QPixmap(int(n * dpr), int(n * dpr))
    pm.fill(QtCore.Qt.GlobalColor.transparent)
    pm.setDevicePixelRatio(dpr)
    p = QtGui.QPainter(pm)
    p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    P = QtCore.QPointF
    body = QtGui.QPolygonF([P(1, 23), P(3, 16), P(17, 2), P(22, 7), P(8, 21)])
    p.setPen(QtGui.QPen(QtGui.QColor(0, 0, 0), 1.6, QtCore.Qt.PenStyle.SolidLine, QtCore.Qt.PenCapStyle.RoundCap,
                        QtCore.Qt.PenJoinStyle.RoundJoin))
    p.setBrush(QtGui.QColor(255, 255, 255))
    p.drawPolygon(body)
    p.setPen(QtGui.QPen(QtGui.QColor(0, 0, 0), 1.2))
    p.drawLine(P(3, 16), P(8, 21))
    p.drawLine(P(14, 5), P(19, 10))
    p.end()
    return QtGui.QCursor(pm, 1, 23)


class SlitHint(QtWidgets.QWidget):
    """What the slit mode does, inside the image, top left, while the mode is on; with a slit drawn, how to remove it.
    No mouse: it never takes a click meant for the image. Light or dark with the theme (set_light)."""
    MARGIN = 8

    def __init__(self, view: QtWidgets.QWidget, light: bool = False):
        super().__init__(view)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.text = ""
        self.light = light
        self.move(self.MARGIN, self.MARGIN)
        self.hide()

    def set_text(self, text: str) -> None:
        self.text = text
        fm = self.fontMetrics()
        self.resize(fm.horizontalAdvance(text) + 20, fm.height() + 10)
        self.update()

    def set_light(self, light: bool) -> None:
        self.light = bool(light)
        self.update()

    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        p.setPen(QtCore.Qt.PenStyle.NoPen)
        p.setBrush(QtGui.QColor(255, 255, 255, 215) if self.light else QtGui.QColor(0, 0, 0, 160))
        p.drawRoundedRect(QtCore.QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 6, 6)
        p.setPen(QtGui.QColor(0, 0, 0, 220) if self.light else QtGui.QColor(255, 255, 255, 230))
        p.drawText(self.rect(), QtCore.Qt.AlignmentFlag.AlignCenter, self.text)
        p.end()


class SlitMarks:
    """The slit's items in one image view: the finished slit, the one being drawn (to the pointer, dashed) and the
    points clicked as small rings. Over the image, and they take no clicks."""
    Z = 20

    def __init__(self, vb: pg.ViewBox, colour: QtGui.QColor):
        self.line = pg.PlotCurveItem()
        self.band = pg.PlotCurveItem()
        self.dots = pg.ScatterPlotItem(size=7)
        self.dots.setAcceptedMouseButtons(QtCore.Qt.MouseButton.NoButton)
        for it in (self.line, self.band, self.dots):
            it.setZValue(self.Z)
            vb.addItem(it, ignoreBounds=True)
        self.set_colour(colour)

    def set_colour(self, c: QtGui.QColor) -> None:
        """Pens made through pg.mkPen: their widths at the screen's ratio (ui.pens)."""
        c = QtGui.QColor(c)
        self.line.setPen(pg.mkPen(c, width=1.5))
        self.band.setPen(pg.mkPen(c, width=1.2, style=QtCore.Qt.PenStyle.DashLine))
        self.dots.setPen(pg.mkPen(c, width=1.5))
        self.dots.setBrush(pg.mkBrush(0, 0, 0, 0))

    def colour(self) -> QtGui.QColor:
        return self.line.opts["pen"].color()


def _xy(a) -> tuple[np.ndarray, np.ndarray]:
    a = np.asarray(a, dtype=np.float64).reshape(-1, 2)
    return a[:, 0], a[:, 1]


class SlitTool(QtCore.QObject):
    """The slit mode and the slit drawn, on the main image and on the 2x2 view's panels once it is made."""
    modeChanged = QtCore.Signal(bool)

    def __init__(self, session, view, hint: SlitHint, colour: QtGui.QColor | None = None):
        """session: the Session whose path the finished slit becomes; view: the ImageView it is drawn on."""
        super().__init__(view.widget)
        self.session = session
        self.ny, self.nx = int(session.main.ny), int(session.main.nx)
        self.hint = hint
        self.mode = False
        self.pts: list[tuple[float, float]] = []        # the slit being drawn: points clicked, view coordinates (x, y)
        self.free: tuple[float, float] | None = None     # its free end: the centre of the pixel under the pointer
        self.colour = QtGui.QColor(colour) if colour is not None else QtGui.QColor(255, 80, 80)
        self.views: list = []
        self.marks: list[SlitMarks] = []
        self._pencil: QtGui.QCursor | None = None
        self.attach(view)

    @property
    def path(self):
        """The finished slit: the points clicked, or None (the session's state)."""
        return self.session.state.path

    def attach(self, view) -> None:
        """Draw on view too (an ImageView of the 2x2 view): the slit as it is now, the pointer as the mode says."""
        self.views.append(view)
        self.marks.append(SlitMarks(view.vb, self.colour))
        self.show_path(self.path)
        self._draw_band()
        view.widget.viewport().setCursor(self.pointer())

    # ---------------------------------------------------------------- the mode
    def pointer(self) -> QtGui.QCursor:
        """The image's pointer at rest: a cross (a pixel to pick), or the pencil while a slit is drawn."""
        if not self.mode:
            return QtGui.QCursor(QtCore.Qt.CursorShape.CrossCursor)
        if self._pencil is None:
            self._pencil = pencil_cursor(self.views[0].widget if self.views else None)
        return self._pencil

    def set_mode(self, on: bool) -> None:
        """On: each click on the image adds a point until a double click ends the slit. Off: the slit being drawn is
        dropped; a finished one stays."""
        on = bool(on)
        if on == self.mode:
            return
        self.mode = on
        self.pts = []
        self.free = None
        self.session.set_draft(() if on else None)
        self._draw_band()
        self.hint_text()
        for v in self.views:
            v.widget.viewport().setCursor(self.pointer())
        self.modeChanged.emit(on)

    def hint_text(self, extra: str = "") -> None:
        """The line inside the image: how to draw while the mode is on; with a slit drawn, how to remove it. The key's
        name as the system writes it: ⌫ on a Mac, Backspace on Linux."""
        if self.mode:
            n = len(self.pts)
            text = extra or ("Slit: click adds a point · double click ends it · right click removes the last "
                             "· Esc cancels" + (f"   ({n} point{'s' * (n != 1)})" if n else ""))
        elif self.path is not None:
            key = QtGui.QKeySequence(QtCore.Qt.Key.Key_Backspace).toString(QtGui.QKeySequence.SequenceFormat.NativeText)
            text = f"{key} remove · S new slit"
        else:
            text = ""
        if text:
            self.hint.set_text(text)
        self.hint.setVisible(bool(text))
        self.hint.raise_()

    # ---------------------------------------------------------------- the gestures
    def click(self, ev, vb) -> bool:
        """A click on an image view (pyqtgraph's scene event) while the mode is on: left adds a point, double finishes,
        right removes the last. False when the mode is off: the click is the cursor's."""
        if not self.mode:
            return False
        B = QtCore.Qt.MouseButton
        if ev.button() == B.RightButton:
            self.undo()
        elif ev.button() == B.LeftButton:
            if ev.double():                             # its first click already added the point under it
                self.finish()
            elif vb.sceneBoundingRect().contains(ev.scenePos()):
                p = vb.mapSceneToView(ev.scenePos())
                self.add(p.x(), p.y())
        return True

    def add(self, x: float, y: float) -> None:
        """A point on the centre of the pixel under (x, y); the same pixel twice in a row counts once (the double
        click's second press)."""
        p = (float(np.clip(math.floor(x), 0, self.nx - 1)) + 0.5, float(np.clip(math.floor(y), 0, self.ny - 1)) + 0.5)
        if self.pts and self.pts[-1] == p:
            return
        self.pts.append(p)
        self.free = p
        self._push_draft()
        self._draw_band()
        self.hint_text()

    def undo(self) -> None:
        """The last point off; with none left, out of the mode."""
        if not self.pts:
            self.set_mode(False)
            return
        self.pts.pop()
        self._push_draft()
        self._draw_band()
        self.hint_text()

    def finish(self) -> None:
        """The slit drawn becomes the session's; with fewer than two points the mode stays and says so."""
        if not self.mode:
            return
        if len(self.pts) < 2:
            self.hint_text("A slit needs two points at least: click another one")
            return
        pts, self.pts = tuple(self.pts), []
        self.session.set_path(pts)
        self.set_mode(False)
        self.show_path(self.path)                      # now, not at the state's notice a pass later

    def clear(self) -> None:
        """⌫: the finished slit off the image and out of the session."""
        if self.path is None:
            return
        self.session.set_path(None)
        self.show_path(None)

    def hover(self, y: float, x: float) -> None:
        """The pointer over an image view, in data pixels: the slit being drawn reaches to it, and its slices to the
        pixel under it, once per pixel entered (the prototype's _slit_hover, 1592-1604)."""
        if not (self.mode and self.pts):
            return
        self._draw_band((float(np.clip(x, 0, self.nx)), float(np.clip(y, 0, self.ny))))
        free = (float(np.clip(math.floor(x), 0, self.nx - 1)) + 0.5,
                float(np.clip(math.floor(y), 0, self.ny - 1)) + 0.5)
        if free != self.free:
            self.free = free
            self._push_draft()

    def _push_draft(self) -> None:
        """The points so far and the free end, when it is not the last point, to the session (its slices follow)."""
        pts = list(self.pts)
        if pts and self.free is not None and self.free != pts[-1]:
            pts.append(self.free)
        self.session.set_draft(tuple(pts))

    # ---------------------------------------------------------------- drawing
    def show_path(self, path) -> None:
        """The finished slit (the points clicked, or None) as a line through them, sampled every pixel."""
        x, y = _xy(slit_path(path)) if path is not None else _xy([])
        for m in self.marks:
            m.line.setData(x, y)
        self._show_dots()
        self.hint_text()

    def _draw_band(self, to: tuple[float, float] | None = None) -> None:
        pts = list(self.pts) + ([to] if to is not None else [])
        x, y = _xy(slit_path(pts, step=BAND_STEP) if len(pts) > 1 else [])
        for m in self.marks:
            m.band.setData(x, y)
        self._show_dots()

    def _show_dots(self) -> None:
        pts = self.pts if self.mode else list(self.path or ())
        pos = np.asarray(pts, dtype=float).reshape(-1, 2)
        for m in self.marks:
            m.dots.setData(pos=pos)

    def set_colour(self, c: QtGui.QColor) -> None:
        """The slit in the markers' colour: the cursor's in the classic look, the accent in the others."""
        self.colour = QtGui.QColor(c)
        for m in self.marks:
            m.set_colour(self.colour)

    def set_light(self, light: bool) -> None:
        self.hint.set_light(light)


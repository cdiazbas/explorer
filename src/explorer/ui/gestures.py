"""One interaction model on every panel, with a pointer that names the action (ROADMAP E4.8):
- the image, the only view that navigates: click locks the cursor (pointer: a cross), drag pans (a closed hand
  while it does), wheel zooms, double click shows the whole image again;
- the spectra, a control: click or drag picks lambda along x, no zoom, no pan (pointer: horizontal arrows);
- lambda-t, a control: click or drag picks (t, lambda), no zoom, no pan (pointer: arrows in four directions);
- right click, or Esc, releases the cursor from any panel.
A drag picks the latest position once per pass of the event loop, so a fast drag reads one image per pass, not one
per mouse event.

From the prototype's app/viewer.py: _Gestures (574), _install_gestures (1790), _spectrum_click to _pick_flush
(1270-1317). The button is seen on the panel itself: QApplication.mouseButtons() depends on how each platform (xcb,
the X11 bridge, offscreen) delivers its input.
"""
from PySide6 import QtCore, QtGui

DRAG_PX = 3                                             # a press on the image that moves farther is a pan


class Gestures(QtCore.QObject):
    """Event filter on the panels' viewports. picks: {viewport: pick(scene_pos, now)}; image: the image's viewport."""

    def __init__(self, parent, picks: dict, image=None):
        super().__init__(parent)
        self.picks, self.image = picks, image
        self.held: set = set()
        self.press: dict = {}
        # the image's pointer at rest, back after a pan: a cross, or the pencil while a slit is drawn (ui.slit)
        self.rest = QtGui.QCursor(QtCore.Qt.CursorShape.CrossCursor)

    def eventFilter(self, obj, e):
        E = QtCore.QEvent.Type
        t = e.type()
        if t not in (E.MouseButtonPress, E.MouseButtonRelease, E.MouseMove):
            return False
        left = t in (E.MouseButtonPress, E.MouseButtonRelease) and e.button() == QtCore.Qt.MouseButton.LeftButton
        if obj is self.image:                           # the closed hand while it pans
            if t == E.MouseButtonPress and left:
                self.press[obj] = e.position()
            elif t == E.MouseMove and obj in self.press and e.buttons() & QtCore.Qt.MouseButton.LeftButton:
                if (e.position() - self.press[obj]).manhattanLength() > DRAG_PX:
                    obj.setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
            elif t == E.MouseButtonRelease and left:
                self.press.pop(obj, None)
                obj.setCursor(self.rest)
            return False
        pick = self.picks.get(obj)
        if pick is None:
            return False
        view = obj.parent()
        if t == E.MouseButtonPress and left:            # the press already picks, as a scrubber does
            self.held.add(obj)
            pick(view.mapToScene(e.position().toPoint()), True)
        elif t == E.MouseMove and obj in self.held:
            if e.buttons() & QtCore.Qt.MouseButton.LeftButton:
                pick(view.mapToScene(e.position().toPoint()), False)
            else:
                self.held.discard(obj)                  # released outside the panel
        elif t == E.MouseButtonRelease and left:
            self.held.discard(obj)
        return False

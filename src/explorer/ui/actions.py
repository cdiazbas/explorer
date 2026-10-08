"""What the keys and the mouse do, in one table (ROADMAP E5.4): the rows register the shortcuts, reach the terminal
keys (ui.termkeys) and write the ? sheet, so the sheet never says something the keys do not do. From the prototype's
app/viewer.py: _key_table (1131), MOUSE (1121), _sheet_html (1175), KeySheet (472), toggle_sheet and _escape
(1186-1196).

    actions = ActionRegistry(rows, mouse)       rows: (keys as shown, what they do, ((key sequence, slot), ...))
    actions.install(window)                     a QShortcut per key sequence
    KeySheet(window, actions.sheet_html(palette))

An action that fails is said, not lost: Qt only prints what a shortcut's slot raises, so the key seemed to do
nothing. Every binding (the shortcuts, the terminal's keys) goes through one guard: the error and its traceback in
explorer's log, a line in the window's status bar.
"""
import html
import sys

from PySide6 import QtCore, QtGui, QtWidgets

from ..obs import get_logger

log = get_logger("ui.actions")


def mod_key() -> str:
    """How the sheet writes the control key: Qt reads Ctrl as the command key on a Mac."""
    return "⌘" if sys.platform == "darwin" else "Ctrl+"


CREDIT = "Designed and implemented by C. J. Díaz Baso"     # the last line of the ? sheet

class ActionRegistry:
    def __init__(self, rows, mouse=()):
        """rows: (keys as shown, what they do, ((key sequence, slot), ...)); a row with no binding is only shown (a
        key the system handles itself, such as the command key and Q on a Mac). mouse: (gesture, what it does)."""
        self.rows = [tuple(r) for r in rows]
        self.mouse = [tuple(m) for m in mouse]
        self.window = None                              # set by install(): where a failed action is said

    def binds(self):
        """(key sequence, action): each action guarded (_guarded), for the shortcuts and the terminal's keys alike."""
        for keys, _what, binds in self.rows:
            for seq, fn in binds:
                yield seq, self._guarded(keys, fn)

    def _guarded(self, keys: str, fn):
        def run(*_args) -> None:
            try:
                fn()
            except Exception as e:
                log.exception("the key %s failed", keys)
                bar = getattr(self.window, "statusBar", None)
                if bar is not None:
                    bar().showMessage(f"{keys}: failed ({type(e).__name__}: {e}); the log has the details", 10000)
        return run

    def install(self, window) -> list:
        """A QShortcut for every key sequence of the table, on window."""
        self.window = window
        out = []
        for seq, fn in self.binds():
            sc = QtGui.QShortcut(QtGui.QKeySequence(seq), window)
            sc.activated.connect(fn)
            out.append(sc)
        return out

    def sheet_html(self, palette: QtGui.QPalette) -> str:
        dim = palette.color(QtGui.QPalette.ColorRole.PlaceholderText).name()

        def row(k, w):
            return (f'<tr><td align="right"><b>{html.escape(k)}</b></td><td>&nbsp;&nbsp;&nbsp;</td>'
                    f'<td>{html.escape(w)}</td></tr>')

        def head(t):
            return f'<tr><td colspan="3" style="color:{dim}">{t}</td></tr>'
        return ('<table cellspacing="0" cellpadding="2">' + head("Keys")
                + "".join(row(k, w) for k, w, _b in self.rows)
                + '<tr><td colspan="3">&nbsp;</td></tr>' + head("Mouse")
                + "".join(row(k, w) for k, w in self.mouse) + "</table>"
                + f'<p style="color:{dim}">? or Esc closes this</p>'
                + f'<p align="right" style="color:{dim}"><i>{CREDIT}</i></p>')


class KeySheet(QtWidgets.QLabel):
    """The ? sheet over the image, until ? or Esc (a click on it closes it too). Non-modal: a child label on a rounded,
    slightly translucent card, painted when shown; nothing in it follows the mouse or animates (over X11 every
    repainted pixel is paid). Translucent, what changes under it while it is open (the image, playing) is repainted
    under it too: a cost only while it is being read. Never a dialog's exec(): a nested event loop inside the X11
    bridge's timer hung the prototype."""
    RADIUS = 10
    OPACITY = 0.88

    def __init__(self, window: QtWidgets.QMainWindow, text: str):
        super().__init__(window)
        self.window_ = window
        self.setTextFormat(QtCore.Qt.TextFormat.RichText)
        self.setText(text)
        self.setForegroundRole(QtGui.QPalette.ColorRole.Text)
        self.setAutoFillBackground(False)               # the card is painted, with its corners and its opacity
        self.setMargin(16)
        self.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.hide()

    def set_shown(self, on: bool) -> None:
        cw = self.window_.centralWidget()
        if on:
            if cw is not None:
                cw.installEventFilter(self)             # it follows the image panel while shown
            self.adjustSize()
            self._place()
            self.raise_()
            self.show()
        else:
            if cw is not None:
                cw.removeEventFilter(self)
            self.hide()

    def toggle(self) -> None:
        self.set_shown(not self.isVisible())

    def _place(self) -> None:
        cw = self.window_.centralWidget()
        if cw is None:
            return
        g = cw.geometry()                               # in the window's coordinates, as this child's
        self.move(max(g.left(), g.center().x() - self.width() // 2), max(g.top(), g.center().y() - self.height() // 2))

    def eventFilter(self, obj, e):
        if e.type() in (QtCore.QEvent.Type.Resize, QtCore.QEvent.Type.Move):
            self._place()
        return False

    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        pal = self.palette()
        fill = QtGui.QColor(pal.color(QtGui.QPalette.ColorRole.Base))
        fill.setAlphaF(self.OPACITY)
        edge = QtGui.QColor(pal.color(QtGui.QPalette.ColorRole.WindowText))
        edge.setAlphaF(0.18)
        p.setPen(QtGui.QPen(edge, 1))
        p.setBrush(fill)
        p.drawRoundedRect(QtCore.QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), self.RADIUS, self.RADIUS)
        p.end()
        super().paintEvent(e)                           # the text

    def mousePressEvent(self, e):
        self.set_shown(False)
        e.accept()

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

from .._name import APP_NAME
from ..obs import get_logger
from .overlays import GAMMA, GAMMA_FAMILIES

log = get_logger("ui.actions")


def mod_key() -> str:
    """How the sheet writes the control key: Qt reads Ctrl as the command key on a Mac."""
    return "⌘" if sys.platform == "darwin" else "Ctrl+"


CREDIT = "Designed and implemented by C. J. Díaz Baso"     # the ? sheet's last line, the version's under it
FOOT_GAP = 8                                            # px between the key and mouse lists and the foot under them

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

    def sheet_html(self, palette: QtGui.QPalette, version: str = "", newer: bool = False) -> str:
        """The keys on the left, the mouse on the right, a line per row: short enough to read at a glance and to fit a
        laptop's window without scrolling; under them, how it closes and the credit, and a last line with version
        (update_check.version_line; none while it is not known) and, when origin has a newer one, the command that
        brings it and the one that stops the reminders (the note over the image has no room for it)."""
        dim = palette.color(QtGui.QPalette.ColorRole.PlaceholderText).name()
        foot = html.escape(version) if version else ""
        if version and newer:
            foot += f' · <span style="color:{palette.color(QtGui.QPalette.ColorRole.Text).name()}">newer version ' \
                    f"available: <b>{html.escape(APP_NAME)} update</b></span> " \
                    f"({html.escape(APP_NAME)} update --no-notice: no reminders)"

        def column(title, rows):
            return ('<table cellspacing="0" cellpadding="2">'
                    f'<tr><td colspan="3" style="color:{dim}">{title}</td></tr>'
                    + "".join(f'<tr><td align="right"><b>{text_html(k)}</b></td><td>&nbsp;&nbsp;</td>'
                              f'<td>{text_html(w)}</td></tr>' for k, w in rows) + "</table>")
        return ('<table cellspacing="0" cellpadding="0"><tr>'
                f'<td valign="top">{column("Keys", [(k, w) for k, w, _b in self.rows])}</td>'
                '<td>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;</td>'
                f'<td valign="top">{column("Mouse", self.mouse)}</td></tr></table>'
                f'<table width="100%" cellspacing="0" cellpadding="2" style="margin-top:{FOOT_GAP}px; color:{dim}"><tr>'
                f'<td>? or Esc closes this</td><td align="right"><i>{CREDIT}</i></td></tr>'
                + (f'<tr><td colspan="2">{foot}</td></tr>' if foot else "") + "</table>")


def text_html(text: str) -> str:
    """text escaped for the sheet, its γ in an italic serif (overlays.GAMMA_FAMILIES): in the interface's sans at the
    sheet's size it reads as a y."""
    fams = ", ".join(f"'{f}'" for f in GAMMA_FAMILIES)
    gamma = f'<span style="font-family:{fams}, serif; font-style:italic">{GAMMA}</span>'
    return html.escape(text).replace(GAMMA, gamma)


def _seconds(s: float) -> str:
    if s < 1e-3:
        return "under 1 ms"
    return f"{s * 1e3:.0f} ms" if s < 1 else f"{s:.1f} s" if s < 60 else f"{s / 60:.1f} min"


def _size(n: float) -> str:
    return f"{n / 1e12:.1f} TB" if n >= 1e12 else f"{n / 1e9:.1f} GB" if n >= 1e9 else f"{n / 1e6:.0f} MB"


def per_pixel_sheet_html(est, name: str, palette: QtGui.QPalette) -> str:
    """The sheet shown over the window when the images come from a per-pixel file alone (data.transpose.Estimate
    est): what an image costs here and how that was found, what a transposed copy would take and give (an
    estimate, said so), and the command that writes it. Written as the ? sheet."""
    dim = palette.color(QtGui.QPalette.ColorRole.PlaceholderText).name()
    free = "" if est.free_bytes is None else f" ({_size(est.free_bytes)} free there)"
    after = est.image_s / max(1, est.factor)
    return (f"<p><b>Images from a per-pixel file</b></p>"
            f"<p>{html.escape(name)} holds each pixel's spectra together, and its image cube (_im) is not beside it: "
            f"each image is read from all of the file.<br>"
            f"Here an image takes about <b>{_seconds(est.image_s)}</b> "
            f'<span style="color:{dim}">({html.escape(est.how)})</span>.<br>'
            f"Spectra, λ–t and slits are as fast as usual.</p>"
            f"<p>Consider a transposed copy (_im): <b>{_size(est.copy_bytes)}</b> on disk{free}; each image then about "
            f"<b>{est.factor}× faster</b> ({_seconds(after)} an image) "
            f'<span style="color:{dim}">(an estimate: an image of the copy is one of its {est.frames} images, '
            f"1/{est.factor} of the bytes read now)</span>.<br>"
            f"Written by reading this file once, with:</p>"
            f'<p><code>{html.escape(est.command)}</code></p>'
            f'<p style="color:{dim}">or into another directory of yours with room (never beside the per-pixel file '
            f"nor where its data are); then open the copy. Esc or a click closes this</p>")


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

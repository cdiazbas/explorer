"""The window's theme (ROADMAP E5.1): macOS dark or light mode drawn over Fusion, the same on a Linux desktop,
over ssh -Y and through the X11 bridge. A local Mac keeps its native style.

    theme = style.apply_theme(app, "auto")      auto | dark | light | native; returns the one applied

auto is native on macOS and dark elsewhere (over X11 there is no desktop theme, and Qt's default there is light).
EXPLORER_STYLE=0 keeps plain Fusion with the theme's palette (to measure what the style costs).
The interface's font is chosen, in every theme (ui_font): on a Mac the system's (SF); elsewhere Noto Sans, then
DejaVu Sans and Liberation Sans, at UI_PX pixels; tabular figures everywhere.
What it styles (no behaviour, one metric on the main window only; toolbar, dock titles and status bar keep Fusion's
heights, so the plots keep their size):
- a proxy style paints
  - QSlider: thin track, accent fill up to the knob, round white knob with a soft shadow;
  - QComboBox / QSpinBox: 6 px corners, faint border with a lighter top edge (dark) or a shadow along the
    bottom (light), up-down chevrons (pop-up) and stepper chevrons, accent ring when focused;
  - QToolButton: flat and rounded, hover / pressed, accent with a white label when on (playing);
  - QCheckBox: rounded square, accent when on, white tick, focus ring round the box only;
  - QToolBar: flat, no grip drawn (the grip still drags), faint short separators;
  - QDockWidget title bars: flat, semibold title, no line below (the panel's gutter parts it from the title),
    square.on.square float button;
  - QStatusBar: hairline on top, size grip not drawn (it still resizes);
  - the separators between docked panels (separators(window)): 8 px to grab, a 1-px hairline to see;
  - tool tips, and the rows of the pop-up list (rounded accent row);
- small style sheets set on popups themselves, never on the application: QMenu (rounded, accent row), the
  pop-up list, QScrollBar (thin, no arrows). Menus, tool tips and the pop-up list get a rounded 1-bit mask, which
  every X server honours, XQuartz included (it has no alpha channel).
No application style sheet: with any sheet on the application, Qt sizes spin boxes itself (73 x 26 -> 89 x 22 px,
toolbar 34 -> 30 px) and skips the base style's arrows.
Colours: macOS dark mode (separator white 10 %, accent #0A84FF, label white 85 %) and light mode (separator black
10 %, accent #007AFF, label black 85 %). Every blue comes from the accent; rows and buttons that carry white text
use it darkened (SELECTED), so white text keeps a contrast of 4.5:1 or more.

Cost: every drawPrimitive / drawControl / drawComplexControl of the application goes through Python; in the
prototype a cursor move went 1.6 -> 1.9 ms and a Stokes change 2.6 -> 3.1 ms (offscreen, Mac). Metrics are
Fusion's: a pixelMetric override on the application style cost 1.3 ms per cursor move.

From the prototype's app/style.py (all of it) and apply_theme / _plot_theme (app/viewer.py:2491-2543).
"""
import os
import sys

import pyqtgraph as pg
from PySide6 import QtCore, QtGui, QtWidgets

from . import icons

THEMES = ("auto", "dark", "light", "native")
UI_PX = 12                                              # px: the interface's text away from a Mac
ACCENT = "#0a84ff"
C = QtGui.QColor
P = QtWidgets.QStyle
S = QtWidgets.QStyle.StateFlag
PE = QtWidgets.QStyle.PrimitiveElement
CE = QtWidgets.QStyle.ControlElement
CC = QtWidgets.QStyle.ComplexControl
SC = QtWidgets.QStyle.SubControl
Qt = QtCore.Qt


def _rgba(r, g, b, a):
    return C(r, g, b, int(round(a * 255)))


def WHITE(a):
    return _rgba(255, 255, 255, a)


def BLACK(a):
    return _rgba(0, 0, 0, a)


SEPARATOR = WHITE(0.10)                            # NSColor.separatorColor, dark
LABEL = WHITE(0.85)                                # labelColor, dark

# One blue at several brightnesses. ACCENT fills what carries no text: slider fill, checkbox, focus rings. A selected
# menu or list row and a toggled tool button carry white text, and white on ACCENT is 3.65:1 (WCAG asks 4.5 for
# text); macOS darkens the accent there too (selectedContentBackgroundColor: the accent at 0.81 of its brightness in
# dark mode). darker(123) keeps the hue and gives #086bcf, white 5.21:1; hover and pressed are it lighter and darker.
_A = C(ACCENT)
SELECTED = _A.darker(123)                          # #086bcf: menu row, list row, toggle that is on
SELECTED_HOVER = SELECTED.lighter(110)             # #0976e4, white 4.44:1 while the pointer is on it
SELECTED_DOWN = SELECTED.darker(115)               # #075db4, white 6.47:1

# Light mode: the accent is systemBlue of the same macOS generation as #0A84FF (light #007AFF). Label and separator
# alphas are the dark ones (0.85, 0.10) in black; selectedContentBackgroundColor is the accent at 0.88 of its
# brightness there, so SELECTED_LIGHT is darker(114): #006be0, white 5.02:1 (white on #007AFF: 4.02:1). The window
# is #ececec.
ACCENT_LIGHT = "#007aff"
_AL = C(ACCENT_LIGHT)
SELECTED_LIGHT = _AL.darker(114)                   # #006be0
SELECTED_LIGHT_HOVER = SELECTED_LIGHT.lighter(110)  # #0076f6
SELECTED_LIGHT_DOWN = SELECTED_LIGHT.darker(115)   # #005dc3, white 6.26:1
LABEL_LIGHT_HEX = "#262626"                        # labelColor (black 85 %) on white, opaque for palettes and sheets
DISABLED_LIGHT_HEX = "#848484"                     # 3.17:1 on the #ececec window, as #7a7a7a is 3.21:1 on dark

# Menu rows: the tick 7 px into the rounded row and the text 5 px after it, as in macOS; Qt keeps the tick's column
# for rows that cannot be ticked, so every text starts in one place. The outline is the separator colour: where no
# shadow is drawn (most X11 desktops, XQuartz) it is the only edge between the menu (#2a2a2a) and the window
# (#2d2d2d). Light: black 10 % over white is only 6 levels darker than the #ececec window, so the outline is 18 %.
_MENU_QSS = """
QMenu { background-color: %(bg)s; color: %(fg)s; border: 1px solid %(border)s;
    border-radius: 8px; padding: 5px 0; }
QMenu::item { padding: 3px 18px 3px 10px; margin: 0 5px; border-radius: 4px; background: transparent; }
QMenu::item:selected { background-color: %(sel)s; color: #ffffff; }
QMenu::item:disabled { color: %(dis)s; }
QMenu::separator { height: 1px; background: %(sep)s; margin: 5px 12px; }
QMenu::indicator { width: 12px; height: 12px; left: 6px; }
"""
_POPUP_QSS = """
QAbstractItemView { background-color: %(bg)s; color: %(fg)s; border: none; outline: 0; padding: 4px;
    selection-background-color: %(sel)s; selection-color: #ffffff; }
QAbstractItemView::item { min-height: 20px; padding: 0 6px; border-radius: 4px; }
QAbstractItemView::item:selected { background-color: %(sel)s; color: #ffffff; }
"""
_SCROLL_QSS = """
QScrollBar:vertical { background: transparent; width: 10px; margin: 0; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 0; }
QScrollBar::handle { background: %(ink)s,0.28); border-radius: 3px; }
QScrollBar::handle:hover { background: %(ink)s,0.42); }
QScrollBar::handle:vertical { min-height: 24px; margin: 2px; }
QScrollBar::handle:horizontal { min-width: 24px; margin: 2px; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; border: none; background: none; }
QScrollBar::add-page, QScrollBar::sub-page { background: none; }
"""
_DARK_SHEET = dict(bg="#2a2a2a", fg="#e4e4e4", border="rgba(255,255,255,0.10)", sel=SELECTED.name(), dis="#7a7a7a",
                   sep="rgba(255,255,255,0.10)", ink="rgba(255,255,255")
_LIGHT_SHEET = dict(bg="#ffffff", fg=LABEL_LIGHT_HEX, border="rgba(0,0,0,0.18)", sel=SELECTED_LIGHT.name(),
                    dis=DISABLED_LIGHT_HEX, sep="rgba(0,0,0,0.10)", ink="rgba(0,0,0")
MENU_QSS, POPUP_QSS, SCROLL_QSS = (q % _DARK_SHEET for q in (_MENU_QSS, _POPUP_QSS, _SCROLL_QSS))
MENU_QSS_LIGHT, POPUP_QSS_LIGHT, SCROLL_QSS_LIGHT = (q % _LIGHT_SHEET for q in (_MENU_QSS, _POPUP_QSS, _SCROLL_QSS))
# the sheets polish may replace: none, or ours in either theme (a switch of theme while running: Shell.set_theme)
_OURS = {"", MENU_QSS, POPUP_QSS, SCROLL_QSS, MENU_QSS_LIGHT, POPUP_QSS_LIGHT, SCROLL_QSS_LIGHT}


def dark_palette() -> QtGui.QPalette:
    """macOS dark mode's colours on Fusion's roles. Always this one for dark: Qt's colour scheme is only a request
    to the platform theme, which nothing answers over X11 or offscreen (Fusion stays light), and a desktop that does
    answer brings its own accent and text colours."""
    Q = QtGui.QPalette.ColorRole
    pal = QtGui.QPalette()
    for role, col in ((Q.Window, "#2d2d2d"), (Q.WindowText, "#e4e4e4"), (Q.Base, "#1e1e1e"),
                      (Q.AlternateBase, "#282828"), (Q.Text, "#e4e4e4"), (Q.Button, "#3a3a3a"),
                      (Q.ButtonText, "#e4e4e4"), (Q.BrightText, "#ffffff"), (Q.PlaceholderText, "#8a8a8a"),
                      (Q.Light, "#4a4a4a"), (Q.Midlight, "#404040"), (Q.Mid, "#2a2a2a"),
                      (Q.Dark, "#1a1a1a"), (Q.Shadow, "#000000"),
                      (Q.Highlight, "#0a84ff"), (Q.HighlightedText, "#ffffff"), (Q.Link, "#4ea1ff"),
                      (Q.ToolTipBase, "#3a3a3a"), (Q.ToolTipText, "#e4e4e4")):
        pal.setColor(role, C(col))
    if hasattr(Q, "Accent"):                            # Qt >= 6.6: else the system's accent stays in this role
        pal.setColor(Q.Accent, C(ACCENT))
    G = QtGui.QPalette.ColorGroup
    for role in (Q.WindowText, Q.Text, Q.ButtonText):
        pal.setColor(G.Disabled, role, C("#7a7a7a"))
    pal.setColor(G.Disabled, Q.Highlight, C("#3a3a3a"))
    return pal


def light_palette() -> QtGui.QPalette:
    """The light twin of dark_palette: macOS light mode where it has a value; the bevel roles (Midlight, Mid, Dark,
    Shadow) are Fusion's own light ones. Highlight carries white text, so it is SELECTED_LIGHT (5.02:1), not the
    bare accent (4.02:1); Accent is the accent."""
    Q = QtGui.QPalette.ColorRole
    pal = QtGui.QPalette()
    for role, col in ((Q.Window, "#ececec"), (Q.WindowText, LABEL_LIGHT_HEX), (Q.Base, "#ffffff"),
                      (Q.AlternateBase, "#f4f5f5"), (Q.Text, LABEL_LIGHT_HEX), (Q.Button, "#ffffff"),
                      (Q.ButtonText, LABEL_LIGHT_HEX), (Q.BrightText, "#ffffff"), (Q.PlaceholderText, "#808080"),
                      (Q.Light, "#ffffff"), (Q.Midlight, "#cacaca"), (Q.Mid, "#b8b8b8"),
                      (Q.Dark, "#9f9f9f"), (Q.Shadow, "#767676"),
                      (Q.Highlight, SELECTED_LIGHT.name()), (Q.HighlightedText, "#ffffff"), (Q.Link, "#0068da"),
                      (Q.ToolTipBase, "#fafafa"), (Q.ToolTipText, LABEL_LIGHT_HEX)):
        pal.setColor(role, C(col))
    if hasattr(Q, "Accent"):
        pal.setColor(Q.Accent, C(ACCENT_LIGHT))
    G = QtGui.QPalette.ColorGroup
    for role in (Q.WindowText, Q.Text, Q.ButtonText):
        pal.setColor(G.Disabled, role, C(DISABLED_LIGHT_HEX))
    pal.setColor(G.Disabled, Q.Highlight, C("#dcdcdc"))  # unemphasizedSelectedContentBackgroundColor
    return pal


def _chevron(p, c, w, h, up, col, pen_w):
    """An open chevron (v or ^) centred at c, w wide and h tall."""
    icons.glyph_pen(p, col, pen_w)
    s = -1 if up else 1
    p.drawPolyline(QtGui.QPolygonF([c + QtCore.QPointF(-w / 2, -s * h / 2), c + QtCore.QPointF(0, s * h / 2),
                                    c + QtCore.QPointF(w / 2, -s * h / 2)]))


def _enabled(opt):
    return bool(opt.state & S.State_Enabled)


def _focus_shown(opt):
    """A focus ring only for focus that came from the keyboard (Tab), as macOS and browsers draw it: after a click a
    combo kept its ring until something else took the focus."""
    return bool(opt.state & S.State_HasFocus and opt.state & S.State_KeyboardFocusChange)


class _RoundMask(QtCore.QObject):
    """Rounded corners for top-level popups (menus, tool tips, the pop-up list) without an alpha channel: a 1-bit
    window shape, which every X server honours."""

    def __init__(self, radius, parent):
        super().__init__(parent)
        self.r = radius

    def eventFilter(self, w, e):
        if e.type() in (QtCore.QEvent.Type.Resize, QtCore.QEvent.Type.Show):
            path = QtGui.QPainterPath()
            path.addRoundedRect(QtCore.QRectF(w.rect()), self.r, self.r)
            w.setMask(QtGui.QRegion(path.toFillPolygon().toPolygon()))
        return False


TOOLBAR_SPACING = 6                                     # px between toolbar items (Fusion: 3)


class MacDarkStyle(QtWidgets.QProxyStyle):
    """Fusion with macOS dark-mode primitives. Only paints: every metric and hint is Fusion's (no pixelMetric,
    styleHint or sizeFromContents override; sizes are set once in polish). Every draw call of the application comes
    through Python: keep these paths short. The colours are class attributes; MacLightStyle changes them and nothing
    else (_PRIM points at this class's methods, so a method overridden in a subclass would not be called from it)."""

    THEME = "dark"
    INK = staticmethod(WHITE)                       # overlays and glyphs: white at an alpha (light: black)
    ACC, SEL, SEL_HOVER, SEL_DOWN = _A, SELECTED, SELECTED_HOVER, SELECTED_DOWN
    CTRL = None                                     # the controls' (ACC, SEL, SEL_HOVER, SEL_DOWN), if not those
    SEP, LABEL = SEPARATOR, LABEL
    MENU, POPUP, SCROLL = MENU_QSS, POPUP_QSS, SCROLL_QSS
    TIP_BG, TIP_FG = C("#3a3a3a"), C("#e4e4e4")
    TOOL_HOVER, TOOL_DOWN = WHITE(0.10), WHITE(0.18)                     # flat tool button, off
    COMBO_FILL = (WHITE(0.18), WHITE(0.13), WHITE(0.10), WHITE(0.04))   # open, hover, normal, disabled
    SPIN_FILL = (WHITE(0.05), WHITE(0.02))                              # enabled, disabled
    BOX_BORDER = (WHITE(0.15), WHITE(0.09), WHITE(0.05))                # hover, enabled, disabled
    BOX_EDGE, BOX_EDGE_TOP = WHITE(0.07), True                          # top edge catches the light
    CHECK_PEN = (WHITE(0.35), WHITE(0.12))                              # off: enabled (3.0:1 on the window), disabled
    CHECK_FILL = (WHITE(0.20), WHITE(0.10), WHITE(0.04))                # off: pressed, enabled, disabled
    TRACK = (WHITE(0.16), WHITE(0.08))                                  # slider track: enabled, disabled
    KNOB = (C("#d6d6d6"), C("#f2f2f2"), C("#6a6a6a"))                   # pressed, enabled, disabled
    KNOB_SHADOW, KNOB_EDGE = (BLACK(0.18), BLACK(0.22)), BLACK(0.30)
    GLYPH = (0.60, 0.90, 0.30)                                          # dock buttons: normal, hover, disabled

    def __init__(self):
        super().__init__(QtWidgets.QStyleFactory.create("Fusion"))
        self._icons: dict = {}

    def _ctl(self, k):
        """The controls' accent (k 0) and their fill when on (1 normal, 2 hover, 3 pressed): CTRL, a look's (the
        classic look's red: set_controls), or the theme's."""
        return (self.CTRL or (self.ACC, self.SEL, self.SEL_HOVER, self.SEL_DOWN))[k]

    def set_controls(self, colour, sel=None, accent=False) -> None:
        """The controls in colour (a QColor; None: the theme's accent): focus rings, a toggle that is on, the chosen
        row of a menu or a pop-up list, whose sheets hold the colour they were made with. sel: the fill under white
        text; by default colour.darker(130), white on it 4.5:1 or more as on the blue (the classic red: 5.11:1).
        accent: accent() and selected() take them too, as attributes of the instance (glass: its markers' colour
        everywhere); else they stay the theme's, as the classic look's markers and the mask's outline keep it."""
        for a in ("ACC", "SEL", "SEL_HOVER", "SEL_DOWN"):   # the class's again
            if a in vars(self):
                delattr(self, a)
        if colour is None:
            self.CTRL = None
            menu, popup = type(self).MENU, type(self).POPUP
        else:
            sel = C(sel) if sel is not None else C(colour).darker(130)
            self.CTRL = (C(colour), sel, sel.lighter(110), sel.darker(115))
            if accent:
                self.ACC, self.SEL, self.SEL_HOVER, self.SEL_DOWN = self.CTRL
            sheet = dict(_LIGHT_SHEET if self.THEME == "light" else _DARK_SHEET, sel=sel.name())
            menu, popup = _MENU_QSS % sheet, _POPUP_QSS % sheet
            _OURS.update((menu, popup))                 # polish may replace them, as the theme's
        if (menu, popup) == (self.MENU, self.POPUP):
            return
        self.MENU, self.POPUP = menu, popup
        for w in QtWidgets.QApplication.allWidgets():   # the menus and pop-up lists made already
            if isinstance(w, (QtWidgets.QMenu, QtWidgets.QComboBox)):
                self.polish(w)

    def _acc(self, a):                                 # the controls' accent at an alpha: focus rings
        c = self._ctl(0)
        return C(c.red(), c.green(), c.blue(), int(round(a * 255)))

    # ---- popups: rounded masks, their own sheets; sizes set once
    def polish(self, arg):
        if isinstance(arg, QtWidgets.QWidget):
            name = arg.metaObject().className()
            r = {"QMenu": 8, "QTipLabel": 6, "QComboBoxPrivateContainer": 7}.get(name)
            if r and not arg.property("_explorer_mask"):
                arg.setProperty("_explorer_mask", True)
                arg.installEventFilter(_RoundMask(r, arg))
            sheet = (self.MENU if isinstance(arg, QtWidgets.QMenu) else
                     self.SCROLL if isinstance(arg, QtWidgets.QScrollBar) else None)
            if sheet and arg.styleSheet() in _OURS and arg.styleSheet() != sheet:   # never over the application's
                arg.setStyleSheet(sheet)
            # set here, not through pixelMetric: Qt asks for metrics ~230 times per cursor move (dock layouts)
            if isinstance(arg, QtWidgets.QToolBar) and (lay := arg.layout()) is not None:
                lay.setSpacing(TOOLBAR_SPACING)
            if name == "QTipLabel" and isinstance(arg, QtWidgets.QLabel):
                arg.setMargin(5)                       # room round the tool tip's text
            if isinstance(arg, QtWidgets.QComboBox) and arg.view().styleSheet() in _OURS - {self.POPUP}:
                arg.view().setStyleSheet(self.POPUP)
        return super().polish(arg)

    # ---- dock float / close buttons: macOS-like glyphs
    def standardIcon(self, sp, opt=None, w=None):
        SP = QtWidgets.QStyle.StandardPixmap
        if sp in (SP.SP_TitleBarNormalButton, SP.SP_DockWidgetCloseButton, SP.SP_TitleBarCloseButton):
            if sp not in self._icons:
                self._icons[sp] = self._glyph_icon(sp)
            return self._icons[sp]
        return super().standardIcon(sp, opt, w)

    def _glyph_icon(self, sp):
        icon = QtGui.QIcon()
        normal, active, disabled = self.GLYPH
        M = QtGui.QIcon.Mode
        for dpr in (1, 2, 3):
            for mode, col in ((M.Normal, self.INK(normal)), (M.Active, self.INK(active)),
                              (M.Disabled, self.INK(disabled))):
                pm = QtGui.QPixmap(16 * dpr, 16 * dpr)
                pm.setDevicePixelRatio(dpr)
                pm.fill(Qt.GlobalColor.transparent)
                p = QtGui.QPainter(pm)
                p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
                icons.glyph_pen(p, col, 1.4)
                if sp == QtWidgets.QStyle.StandardPixmap.SP_TitleBarNormalButton:      # detach: square.on.square
                    p.drawRoundedRect(QtCore.QRectF(1.5, 5.0, 9.5, 9.5), 2, 2)
                    p.drawPolyline(QtGui.QPolygonF([QtCore.QPointF(5.0, 1.5), QtCore.QPointF(14.5, 1.5),
                                                    QtCore.QPointF(14.5, 11.0)]))
                else:                                  # close: xmark
                    p.drawLine(QtCore.QPointF(3, 3), QtCore.QPointF(13, 13))
                    p.drawLine(QtCore.QPointF(3, 13), QtCore.QPointF(13, 3))
                p.end()
                icon.addPixmap(pm, mode)
        return icon

    # ---- primitives
    def drawPrimitive(self, pe, opt, p, w=None):
        f = self._PRIM.get(pe)
        if f is None or f(self, opt, p, w) is False:
            super().drawPrimitive(pe, opt, p, w)

    def _nothing(self, opt, p, w):
        return None

    def _toolbar_panel(self, opt, p, w):             # flat: the toolbar continues the title bar
        p.fillRect(opt.rect, opt.palette.color(QtGui.QPalette.ColorRole.Window))

    def _toolbar_separator(self, opt, p, w):
        r = opt.rect
        horizontal = bool(opt.state & S.State_Horizontal)
        p.save()
        p.setPen(QtGui.QPen(self.INK(0.14), 1))
        if horizontal:                                 # a vertical hairline, 60 % of the bar
            x, m = r.center().x(), int(r.height() * 0.2)
            p.drawLine(x, r.top() + m, x, r.bottom() - m)
        else:
            y, m = r.center().y(), int(r.width() * 0.2)
            p.drawLine(r.left() + m, y, r.right() - m, y)
        p.restore()

    def _status_panel(self, opt, p, w):
        p.fillRect(opt.rect, opt.palette.color(QtGui.QPalette.ColorRole.Window))
        p.save()
        p.setPen(QtGui.QPen(self.SEP, 1))
        p.drawLine(opt.rect.topLeft(), opt.rect.topRight())
        p.restore()

    def _panel_button_tool(self, opt, p, w):         # dock float button, autoraise tool buttons
        st = opt.state
        if not (st & S.State_On) and (not _enabled(opt) or not (st & (S.State_Sunken | S.State_MouseOver))):
            return
        rect = QtCore.QRectF(opt.rect).adjusted(0.5, 0.5, -0.5, -0.5)
        p.save()
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        if st & S.State_On and not _enabled(opt):
            p.setBrush(self.INK(0.10))
        elif st & S.State_On:                          # a toggle that is on (playing): the accent
            p.setBrush(self._ctl(3 if st & S.State_Sunken else 2 if st & S.State_MouseOver else 1))
        else:
            p.setBrush(self.TOOL_DOWN if st & S.State_Sunken else self.TOOL_HOVER)
        p.drawRoundedRect(rect, 4, 4)
        p.restore()

    def _checkbox(self, opt, p, w):
        st = opt.state
        r = QtCore.QRectF(opt.rect)
        d = min(r.width(), r.height(), 14.0)
        box = QtCore.QRectF(0, 0, d, d)
        box.moveCenter(r.center())
        box.adjust(0.5, 0.5, -0.5, -0.5)
        on, partial = bool(st & S.State_On), bool(st & S.State_NoChange)
        en, down = _enabled(opt), bool(st & S.State_Sunken)
        p.save()
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        if (on or partial) and en:
            p.setPen(QtGui.QPen(BLACK(0.25), 1))
            p.setBrush(self._ctl(1 if down else 0))
        elif on or partial:
            p.setPen(QtGui.QPen(self.INK(0.08), 1))
            p.setBrush(self.INK(0.12))
        else:
            p.setPen(QtGui.QPen(self.CHECK_PEN[0 if en else 1], 1))       # 3:1 on the window (WCAG 1.4.11)
            p.setBrush(self.CHECK_FILL[(0 if down else 1) if en else 2])
        p.drawRoundedRect(box, 3.5, 3.5)
        if _focus_shown(opt):
            p.setPen(QtGui.QPen(self._acc(0.55), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(box.adjusted(-1.5, -1.5, 1.5, 1.5), 4.5, 4.5)
        col = C("#ffffff") if en else self.INK(0.40)
        icons.glyph_pen(p, col, 1.7 * d / 14)
        x, y, k = box.left(), box.top(), box.width()
        if partial:
            p.drawLine(QtCore.QPointF(x + 0.28 * k, y + 0.5 * k), QtCore.QPointF(x + 0.72 * k, y + 0.5 * k))
        elif on:
            p.drawPolyline(QtGui.QPolygonF([QtCore.QPointF(x + 0.26 * k, y + 0.53 * k),
                                            QtCore.QPointF(x + 0.43 * k, y + 0.70 * k),
                                            QtCore.QPointF(x + 0.75 * k, y + 0.30 * k)]))
        p.restore()

    def _menu_check(self, opt, p, w):                  # a plain tick, as in macOS menus
        if not opt.state & S.State_On:
            return
        r = QtCore.QRectF(opt.rect)
        k = min(r.width(), r.height(), 12.0)
        c = r.center()
        col = C("#ffffff") if opt.state & S.State_Selected else (self.LABEL if _enabled(opt) else self.INK(0.35))
        p.save()
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        icons.glyph_pen(p, col, 1.6)
        p.drawPolyline(QtGui.QPolygonF([c + QtCore.QPointF(-0.36 * k, 0.02 * k),
                                        c + QtCore.QPointF(-0.10 * k, 0.28 * k),
                                        c + QtCore.QPointF(0.36 * k, -0.30 * k)]))
        p.restore()

    @staticmethod
    def _arrow(direction):
        def draw(self, opt, p, w):
            r = QtCore.QRectF(opt.rect)
            col = self.LABEL if _enabled(opt) else self.INK(0.30)
            p.save()
            p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
            if direction == "down" and isinstance(w, QtWidgets.QComboBox):
                # pop-up button: up and down chevrons stacked (NSPopUpButton)
                cw = min(r.width(), 7.0)
                ch = cw * 0.45
                c = r.center()
                _chevron(p, c + QtCore.QPointF(0, -ch * 0.95), cw, ch, True, col, 1.4)
                _chevron(p, c + QtCore.QPointF(0, ch * 0.95), cw, ch, False, col, 1.4)
            else:
                s = min(r.width(), r.height())
                cw, ch = min(8.0, s * 0.9), min(8.0, s * 0.9) * 0.5
                if direction in ("up", "down"):
                    _chevron(p, r.center(), cw, ch, direction == "up", col, 1.4)
                else:                                  # left / right: the same chevron, rotated
                    p.translate(r.center())
                    p.rotate(-90 if direction == "right" else 90)
                    _chevron(p, QtCore.QPointF(0, 0), cw, ch, False, col, 1.4)
            p.restore()
        return draw

    def _focus_rect(self, opt, p, w):
        if isinstance(w, (QtWidgets.QCheckBox, QtWidgets.QRadioButton)):
            return                                     # the ring goes round the box (_checkbox), not the text
        if not opt.state & S.State_KeyboardFocusChange:
            return                                     # focus from a click: no ring (_focus_shown)
        p.save()
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        p.setPen(QtGui.QPen(self._acc(0.60), 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QtCore.QRectF(opt.rect).adjusted(0.75, 0.75, -0.75, -0.75), 4, 4)
        p.restore()

    def _tip_panel(self, opt, p, w):                 # tool tip: faint border, rounded (masked)
        p.save()
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        p.fillRect(opt.rect, self.TIP_BG)
        p.setPen(QtGui.QPen(self.INK(0.18), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QtCore.QRectF(opt.rect).adjusted(0.5, 0.5, -0.5, -0.5), 6, 6)
        p.restore()

    def _line_edit_panel(self, opt, p, w):
        if isinstance(w, QtWidgets.QLineEdit) and isinstance(w.parent(), QtWidgets.QAbstractSpinBox):
            return                                     # the spin box's rounded field shows through
        return False

    def _dock_resize_handle(self, opt, p, w):
        p.fillRect(opt.rect, opt.palette.color(QtGui.QPalette.ColorRole.Window))

    _PRIM: dict = {}

    # ---- controls
    def drawControl(self, ce, opt, p, w=None):
        if ce == CE.CE_SizeGrip:
            return                                     # invisible, still resizes
        if ce == CE.CE_DockWidgetTitle and isinstance(opt, QtWidgets.QStyleOptionDockWidget):
            return self._dock_title(opt, p, w)
        if ce == CE.CE_ToolBar:
            return self._toolbar_panel(opt, p, w)
        if (ce == CE.CE_MenuItem and isinstance(opt, QtWidgets.QStyleOptionMenuItem) and opt.state & S.State_Selected
                and opt.menuItemType == QtWidgets.QStyleOptionMenuItem.MenuItemType.Normal and _enabled(opt)):
            p.save()
            p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(self._ctl(1))
            p.drawRoundedRect(QtCore.QRectF(opt.rect).adjusted(3.5, 0.5, -3.5, -0.5), 4, 4)
            p.restore()
            o = QtWidgets.QStyleOptionMenuItem(opt)      # rounded accent row, white text (pop-up list)
            o.state &= ~S.State_Selected
            o.palette = QtGui.QPalette(opt.palette)
            R = QtGui.QPalette.ColorRole
            for role in (R.Text, R.WindowText, R.ButtonText):
                o.palette.setColor(role, C("#ffffff"))
            return super().drawControl(ce, o, p, w)
        super().drawControl(ce, opt, p, w)

    def _dock_title(self, opt, p, w):
        r = opt.rect
        p.save()
        p.fillRect(r, opt.palette.color(QtGui.QPalette.ColorRole.Window))   # no line under it: the gutter parts
        if opt.title:
            f = QtGui.QFont(w.font() if w is not None else p.font())
            f.setWeight(QtGui.QFont.Weight.DemiBold)
            p.setFont(f)
            tr = self.subElementRect(QtWidgets.QStyle.SubElement.SE_DockWidgetTitleBarText, opt, w)
            if not tr.isValid():
                tr = r
            tr = tr.adjusted(4, 0, 0, 0)
            text = QtGui.QFontMetrics(f).elidedText(opt.title, Qt.TextElideMode.ElideRight, tr.width())
            p.setPen(self.LABEL if _enabled(opt) else self.INK(0.35))
            p.drawText(tr, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text)
        p.restore()

    def drawComplexControl(self, cc, opt, p, w=None):
        if cc == CC.CC_Slider and isinstance(opt, QtWidgets.QStyleOptionSlider):
            return self._slider(opt, p, w)
        if cc == CC.CC_ComboBox and isinstance(opt, QtWidgets.QStyleOptionComboBox) and not opt.editable:
            return self._combo(opt, p, w)
        if cc == CC.CC_SpinBox and isinstance(opt, QtWidgets.QStyleOptionSpinBox):
            return self._spin(opt, p, w)
        if cc == CC.CC_ToolButton and isinstance(opt, QtWidgets.QStyleOptionToolButton) and opt.state & S.State_On:
            o = QtWidgets.QStyleOptionToolButton(opt)   # on: white label on the accent
            o.palette = QtGui.QPalette(opt.palette)
            o.palette.setColor(QtGui.QPalette.ColorRole.ButtonText, C("#ffffff") if _enabled(opt) else self.INK(0.45))
            return super().drawComplexControl(cc, o, p, w)
        super().drawComplexControl(cc, opt, p, w)

    def _box(self, p, r, fill, opt):
        """The rounded box of pop-up buttons and fields: faint border, a lighter top edge (dark) or a shadow along
        the bottom (light), the accent when focused."""
        en, focus = _enabled(opt), _focus_shown(opt)
        r = QtCore.QRectF(r).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(fill)
        p.drawRoundedRect(r, 6, 6)
        if focus and en:
            p.setPen(QtGui.QPen(self._ctl(0), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(r, 6, 6)
            p.setPen(QtGui.QPen(self._acc(0.35), 1))
            p.drawRoundedRect(r.adjusted(1, 1, -1, -1), 5, 5)
            return
        hover = en and opt.state & S.State_MouseOver
        p.setPen(QtGui.QPen(self.BOX_BORDER[0 if hover else 1 if en else 2], 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(r, 6, 6)
        if en:
            y = r.top() + 1 if self.BOX_EDGE_TOP else r.bottom() - 1
            p.setPen(QtGui.QPen(self.BOX_EDGE, 1))
            p.drawLine(QtCore.QPointF(r.left() + 6, y), QtCore.QPointF(r.right() - 6, y))

    def _combo(self, opt, p, w):
        en = _enabled(opt)
        p.save()
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        on = opt.state & (S.State_On | S.State_Sunken)
        fill = self.COMBO_FILL[(0 if on else 1 if opt.state & S.State_MouseOver else 2) if en else 3]
        if opt.frame:
            self._box(p, opt.rect, fill, opt)
        ar = QtCore.QRectF(self.subControlRect(CC.CC_ComboBox, opt, SC.SC_ComboBoxArrow, w))
        col = self.LABEL if en else self.INK(0.30)
        cw = 7.0
        ch = cw * 0.45
        c = ar.center() - QtCore.QPointF(1, 0)
        _chevron(p, c + QtCore.QPointF(0, -ch * 0.95), cw, ch, True, col, 1.4)
        _chevron(p, c + QtCore.QPointF(0, ch * 0.95), cw, ch, False, col, 1.4)
        p.restore()

    def _spin(self, opt, p, w):
        en = _enabled(opt)
        p.save()
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        if opt.frame:
            self._box(p, opt.rect, self.SPIN_FILL[0 if en else 1], opt)
        A = QtWidgets.QAbstractSpinBox
        if opt.buttonSymbols != A.ButtonSymbols.NoButtons:
            for sc, up, flag in ((SC.SC_SpinBoxUp, True, A.StepEnabledFlag.StepUpEnabled),
                                 (SC.SC_SpinBoxDown, False, A.StepEnabledFlag.StepDownEnabled)):
                r = QtCore.QRectF(self.subControlRect(CC.CC_SpinBox, opt, sc, w))
                can = en and bool(opt.stepEnabled & flag)
                active = can and opt.activeSubControls & sc
                if active and opt.state & (S.State_Sunken | S.State_MouseOver):
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(self.INK(0.20 if opt.state & S.State_Sunken else 0.10))
                    p.drawRoundedRect(r.adjusted(1, 1 if up else 0, -2, 0 if up else -1), 3, 3)
                c = r.center() + QtCore.QPointF(-0.5, 1.0 if up else -1.0)
                _chevron(p, c, 7.0, 3.5, up, self.LABEL if can else self.INK(0.28), 1.3)
        p.restore()

    def _slider(self, opt, p, w):
        groove = QtCore.QRectF(self.subControlRect(CC.CC_Slider, opt, SC.SC_SliderGroove, w))
        handle = QtCore.QRectF(self.subControlRect(CC.CC_Slider, opt, SC.SC_SliderHandle, w))
        horiz = opt.orientation == Qt.Orientation.Horizontal
        en = _enabled(opt)
        c = handle.center()
        d = min(handle.width(), handle.height(), 18.0) - 1
        t = 4.0                                         # track thickness
        p.save()
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        if horiz:
            track = QtCore.QRectF(groove.left() + 1, c.y() - t / 2, groove.width() - 2, t)
            filled = QtCore.QRectF(track.left(), track.top(), c.x() - track.left(), t)
            if opt.upsideDown:
                filled = QtCore.QRectF(c.x(), track.top(), track.right() - c.x(), t)
        else:
            track = QtCore.QRectF(c.x() - t / 2, groove.top() + 1, t, groove.height() - 2)
            filled = QtCore.QRectF(track.left(), c.y(), t, track.bottom() - c.y())
            if opt.upsideDown:
                filled = QtCore.QRectF(track.left(), track.top(), t, c.y() - track.top())
        p.setBrush(self.TRACK[0 if en else 1])
        p.drawRoundedRect(track, t / 2, t / 2)
        p.setBrush(self._ctl(0) if en else self.INK(0.22))
        p.drawRoundedRect(filled, t / 2, t / 2)
        knob = QtCore.QRectF(0, 0, d, d)
        knob.moveCenter(c)
        if en:                                          # soft shadow: two faint discs, slightly low
            p.setBrush(self.KNOB_SHADOW[0])
            p.drawEllipse(knob.adjusted(-1, -0.5, 1, 1.5))
            p.setBrush(self.KNOB_SHADOW[1])
            p.drawEllipse(knob.adjusted(-0.5, 0, 0.5, 1))
        down = bool(opt.state & S.State_Sunken) and opt.activeSubControls & SC.SC_SliderHandle
        p.setBrush(self.KNOB[0 if down else 1 if en else 2])
        p.setPen(QtGui.QPen(self.KNOB_EDGE, 0.5))
        p.drawEllipse(knob)
        if _focus_shown(opt) and en:
            p.setPen(QtGui.QPen(self._acc(0.55), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(knob.adjusted(-1.5, -1.5, 1.5, 1.5))
        p.restore()


MacDarkStyle._PRIM = {
    PE.PE_IndicatorToolBarHandle: MacDarkStyle._nothing,      # no grip drawn; dragging it still works
    PE.PE_PanelToolBar: MacDarkStyle._toolbar_panel,
    PE.PE_IndicatorToolBarSeparator: MacDarkStyle._toolbar_separator,
    PE.PE_PanelStatusBar: MacDarkStyle._status_panel,
    PE.PE_FrameStatusBarItem: MacDarkStyle._nothing,
    PE.PE_PanelButtonTool: MacDarkStyle._panel_button_tool,
    PE.PE_IndicatorCheckBox: MacDarkStyle._checkbox,
    PE.PE_IndicatorMenuCheckMark: MacDarkStyle._menu_check,
    PE.PE_IndicatorArrowDown: MacDarkStyle._arrow("down"),
    PE.PE_IndicatorArrowUp: MacDarkStyle._arrow("up"),
    PE.PE_IndicatorArrowLeft: MacDarkStyle._arrow("left"),
    PE.PE_IndicatorArrowRight: MacDarkStyle._arrow("right"),
    PE.PE_IndicatorSpinUp: MacDarkStyle._arrow("up"),
    PE.PE_IndicatorSpinDown: MacDarkStyle._arrow("down"),
    PE.PE_IndicatorSpinPlus: MacDarkStyle._arrow("up"),
    PE.PE_IndicatorSpinMinus: MacDarkStyle._arrow("down"),
    PE.PE_FrameFocusRect: MacDarkStyle._focus_rect,
    PE.PE_IndicatorDockWidgetResizeHandle: MacDarkStyle._dock_resize_handle,
    PE.PE_PanelTipLabel: MacDarkStyle._tip_panel,
    PE.PE_PanelLineEdit: MacDarkStyle._line_edit_panel,
}


class MacLightStyle(MacDarkStyle):
    """The same look in macOS light mode: only colours change. Controls are white with a faint border on the #ececec
    window, where dark ones are white overlays. Values that macOS gives are its own; the rest are estimates."""

    THEME = "light"
    INK = staticmethod(BLACK)
    ACC, SEL, SEL_HOVER, SEL_DOWN = _AL, SELECTED_LIGHT, SELECTED_LIGHT_HOVER, SELECTED_LIGHT_DOWN
    SEP, LABEL = BLACK(0.10), BLACK(0.85)                                # separatorColor, labelColor (Aqua)
    MENU, POPUP, SCROLL = MENU_QSS_LIGHT, POPUP_QSS_LIGHT, SCROLL_QSS_LIGHT
    TIP_BG, TIP_FG = C("#fafafa"), C(LABEL_LIGHT_HEX)                    # estimate
    TOOL_HOVER, TOOL_DOWN = BLACK(0.07), BLACK(0.13)                     # estimate: lighter than the dark alphas
    COMBO_FILL = (C("#e6e6e6"), C("#fbfbfb"), C("#ffffff"), WHITE(0.55))  # controlColor white; others estimates
    SPIN_FILL = (C("#ffffff"), WHITE(0.55))
    BOX_BORDER = (BLACK(0.24), BLACK(0.16), BLACK(0.08))                # estimate
    BOX_EDGE, BOX_EDGE_TOP = BLACK(0.06), False                          # a shadow along the bottom (estimate)
    CHECK_PEN = (BLACK(0.43), BLACK(0.12))                               # 3.0:1 on #ececec, as the dark 0.35
    CHECK_FILL = (C("#e6e6e6"), C("#ffffff"), WHITE(0.55))
    TRACK = (BLACK(0.12), BLACK(0.06))                                   # light grey (estimate)
    KNOB = (C("#ececec"), C("#ffffff"), C("#f6f6f6"))
    KNOB_SHADOW, KNOB_EDGE = (BLACK(0.08), BLACK(0.12)), BLACK(0.22)     # estimate
    GLYPH = (0.50, 0.85, 0.26)                        # secondaryLabel, label, tertiaryLabel (Aqua)


# The separators between docked panels: what is seen and what can be grabbed is one width,
# PM_DockWidgetSeparatorExtent, 6 px in Fusion and hard to grab. Here 8 px to grab and a 1-px hairline in the
# middle to see: a drag 3 px from the middle pixel moves the separator with 8 px, not with 6 (the prototype's
# conformance steps separator_grab_*).
SEPARATOR_GRAB = 8


class _MainWindowStyle(MacDarkStyle):
    """The main window's own style: QWidget.setStyle does not reach its children, so only the main window's metric
    queries come through Python (on the application style, a pixelMetric override cost 1.3 ms per cursor move)."""

    def pixelMetric(self, m, opt=None, w=None):
        if m == QtWidgets.QStyle.PixelMetric.PM_DockWidgetSeparatorExtent:
            return SEPARATOR_GRAB
        return super().pixelMetric(m, opt, w)

    def drawPrimitive(self, pe, opt, p, w=None):
        if pe != PE.PE_IndicatorDockWidgetResizeHandle:
            return super().drawPrimitive(pe, opt, p, w)
        r = opt.rect
        p.fillRect(r, opt.palette.color(QtGui.QPalette.ColorRole.Window))
        if w is not None and getattr(w.window(), "plain_separators", False):   # glass between images: no hairline
            return
        if r.width() < r.height():                    # between side-by-side areas: a vertical line
            p.fillRect(QtCore.QRect(r.left() + (r.width() - 1) // 2, r.top(), 1, r.height()), self.SEP)
        else:
            p.fillRect(QtCore.QRect(r.left(), r.top() + (r.height() - 1) // 2, r.width(), 1), self.SEP)


class _MainWindowLightStyle(_MainWindowStyle, MacLightStyle):
    """The same, light colours."""


def separators(window: QtWidgets.QMainWindow):
    """Wider separators between the window's docked panels, when the application has this look (not on a local
    Mac: its native style is left alone). Call after apply(): the hairline takes the application's theme."""
    app_style = QtWidgets.QApplication.style()
    if not isinstance(app_style, MacDarkStyle):
        return None
    cls = _MainWindowLightStyle if app_style.THEME == "light" else _MainWindowStyle
    window._explorer_separator_style = st = cls()  # type: ignore[attr-defined]  # setStyle does not keep it
    window.setStyle(st)
    return st


def apply(app, theme: str = "dark") -> bool:
    """Style an application already set to Fusion and its palette, dark or light. Returns True if the look is on,
    False if the application is not on Fusion (a local Mac's native style: left alone)."""
    cls = {"dark": MacDarkStyle, "light": MacLightStyle}[theme]
    if type(app.style()) is cls:
        return True
    if not isinstance(app.style(), MacDarkStyle) and (app.style().name() or "").lower() != "fusion":
        return False
    pal = QtGui.QPalette(app.palette())
    style = cls()
    app._explorer_style = style                           # keep the Python side alive
    app.setStyle(style)
    if app.palette() != pal:                             # setStyle resets the palette to the style's own
        app.setPalette(pal)
    # the toolbars polished before (a switch of theme): Qt's StyleChange, which comes after the polish, set their
    # spacing back to the style's
    for tb in app.allWidgets():
        if isinstance(tb, QtWidgets.QToolBar) and (lay := tb.layout()) is not None:
            lay.setSpacing(TOOLBAR_SPACING)
    tip = QtGui.QPalette(QtWidgets.QToolTip.palette())
    tip.setColor(QtGui.QPalette.ColorRole.ToolTipBase, cls.TIP_BG)
    tip.setColor(QtGui.QPalette.ColorRole.ToolTipText, cls.TIP_FG)
    QtWidgets.QToolTip.setPalette(tip)
    return True


def ui_font(app) -> QtGui.QFont:
    """The interface's font, chosen rather than left to the platform. On a Mac the system's (SF), as Qt has it.
    Elsewhere Qt asked fontconfig for "Sans Serif" at 9 pt and took DejaVu Sans (bellatrix), wide and with a minus
    1.32 digits wide: Noto Sans first, then DejaVu and Liberation, sized in pixels (a point is a pixel on a Mac, 72
    dpi, and 1.33 px offscreen and over X11, 96 dpi). Tabular figures: SF's digits are proportional (5.8 to 7.9 px
    at 12 px), so every readout that changes jittered; with tnum all are 7.8 px."""
    f = QtGui.QFont(app.font())
    if sys.platform != "darwin":
        f.setFamilies(["Noto Sans", "DejaVu Sans", "Liberation Sans"])
        f.setPixelSize(UI_PX)
    if hasattr(QtGui.QFont, "setFeature"):              # Qt >= 6.7
        f.setFeature(QtGui.QFont.Tag("tnum"), 1)
    app.setFont(f)
    return f


def apply_theme(app, theme: str = "auto") -> str:
    """auto: native on macOS (it follows the system's dark mode), dark elsewhere; dark / light: Fusion with this
    look, the same everywhere. Returns the theme applied. Before the window builds its plots: their colours follow
    the window's (plot_theme)."""
    if theme == "auto":
        theme = "native" if sys.platform == "darwin" else "dark"
    if theme not in THEMES:
        raise ValueError(f"theme {theme!r}: one of {', '.join(THEMES)}")
    ui_font(app)
    from . import pens

    scr = app.primaryScreen()
    pens.set_ratio(scr.devicePixelRatio() if scr is not None else 1.0)     # before the plots exist
    if theme != "native":
        app.setStyle("Fusion")
        hints = app.styleHints()
        if hasattr(hints, "setColorScheme"):            # Qt >= 6.8: Fusion's own scheme; the palette decides below
            hints.setColorScheme(Qt.ColorScheme.Dark if theme == "dark" else Qt.ColorScheme.Light)
        app.setPalette(dark_palette() if theme == "dark" else light_palette())
        if os.environ.get("EXPLORER_STYLE", "1") != "0":
            apply(app, theme)
    plot_theme(app)
    return theme


def plot_theme(app) -> bool:
    """pyqtgraph's colours follow the window's: its defaults (black plots, grey ink) sit as black boxes in a light
    window. Returns whether the window is light (also kept as the application's property explorer_light)."""
    light = app.palette().color(QtGui.QPalette.ColorRole.Window).lightness() > 128
    pg.setConfigOptions(background="w" if light else "k", foreground=(70, 70, 74) if light else "d")
    app.setProperty("explorer_light", light)
    return light


def default_axes(view) -> None:
    """The axes of a pyqtgraph view in its default pens again, the ones plot_theme chose: an axis takes the foreground
    when it is made and keeps it."""
    for it in view.scene().items():
        if isinstance(it, pg.AxisItem):
            it.setPen()
            it.setTextPen()


def is_light() -> bool:
    app = QtWidgets.QApplication.instance()
    return bool(app is not None and app.property("explorer_light"))


def accent() -> QtGui.QColor:
    """The accent our own drawings use: the style's (dark or light); under a Mac's native style the system's, which
    its controls take whatever is set, so the window keeps one accent."""
    app = QtWidgets.QApplication.instance()
    if not isinstance(app, QtWidgets.QApplication):
        return QtGui.QColor(ACCENT)
    if app.style().name() == "macos":
        role = getattr(QtGui.QPalette.ColorRole, "Accent", QtGui.QPalette.ColorRole.Highlight)
        return QtGui.QColor(app.palette().color(role))
    acc = getattr(app.style(), "ACC", None)
    return QtGui.QColor(acc) if acc is not None else QtGui.QColor(ACCENT)


def selected() -> QtGui.QColor:
    """The fill of anything on, with white text on it: the accent darkened as macOS does for selected content."""
    app = QtWidgets.QApplication.instance()
    sel = getattr(app.style(), "SEL", None) if isinstance(app, QtWidgets.QApplication) else None
    return QtGui.QColor(sel) if sel is not None else accent().darker(123)

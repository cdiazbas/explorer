"""The navigation toolbar (ROADMAP E4.5): t and lambda sliders with their labels, the Stokes combo, play with its
rate (playback itself: E4.9), the slit button (E7.1), the Panels menu and the reset button, right-aligned. The
sliders give way first when the window narrows, so the whole toolbar stays visible.

From the prototype's app/viewer.py: the toolbar (913-960), JumpSlider (364), _slider_text (1106), _fit_toolbar
(2323), set_index's keeping of sliders, labels and combo in step (1843-1848).
"""
from PySide6 import QtCore, QtGui, QtWidgets

from ..data.axes import STOKES, fmt_signed
from . import icons

SLIDER_W = (86, 209)                                    # px, 0.95 of the prototype's: the sliders give way first
FPS = (1, 120, 20)                                      # the rate box: minimum, maximum, default
ALL = "All"                                             # every Stokes side by side (the 2x2 view, ui.stokesgrid)


class StokesSegments(QtWidgets.QWidget):
    """I Q U V as a segmented control (the prototype's app/look.py _stokes, 581), in the modern look's drop-down."""

    def __init__(self, ns: int, current: int, pick):
        super().__init__()
        self.setObjectName("stokes_segments")
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground)
        self.restyle()
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.group = QtWidgets.QButtonGroup(self)
        self.group.setExclusive(True)
        for k in range(ns + 1):                         # and All: every Stokes side by side
            b = QtWidgets.QToolButton()
            b.setText(STOKES[k] if k < ns else ALL)
            b.setCheckable(True)
            b.setToolTip(f"Stokes {STOKES[k]} in the image (key {k + 1})" if k < ns else
                         f"{' '.join(STOKES[:ns])} side by side, zoom linked (key {ns + 1})")
            self.group.addButton(b, k)
            lay.addWidget(b)
        self.group.button(current).setChecked(True)
        self.group.idClicked.connect(pick)

    def restyle(self) -> None:
        """Its sheet, from the application's palette and selection colour: a sheet keeps the colours it was made
        with, so a new theme makes it again."""
        from . import style

        text = QtWidgets.QApplication.palette().color(QtGui.QPalette.ColorRole.ButtonText)
        hover, track = QtGui.QColor(text), QtGui.QColor(text)
        hover.setAlphaF(0.10)
        track.setAlphaF(0.07)
        H = QtGui.QColor.NameFormat.HexArgb
        self.setStyleSheet(
            f"#stokes_segments {{ background: {track.name(H)}; border-radius: 7px; }}"
            f"QToolButton {{ border: none; border-radius: 5px; padding: 2px 10px; margin: 2px;"
            f" color: {text.name()}; background: transparent; }}"
            f"QToolButton:hover:!checked {{ background: {hover.name(H)}; }}"
            f"QToolButton:checked {{ background: {style.selected().name()}; color: white; }}")

    def set(self, s: int) -> None:
        """s: a Stokes, or ns for All."""
        if self.group.checkedId() != s:
            self.group.button(s).setChecked(True)


class StokesDrop(QtWidgets.QToolButton):
    """The modern look's Stokes: a button as narrow as the classic combo ("Stokes V ▾") that drops the segments
    below it; a pick closes them. The segments in the toolbar took 165 px, which the sliders gave up in a narrow
    window. Shown with show(), never a menu's exec(): a nested event loop inside the X11 bridge's timer hung the
    prototype."""

    def __init__(self, ns: int, current: int, pick):
        super().__init__()
        self.setObjectName("stokes_drop")
        self.setAutoRaise(True)
        self.setToolTip("Stokes shown in the image: keys " + ", ".join(f"{k + 1} {STOKES[k]}" for k in range(ns)))
        self.panel = QtWidgets.QFrame(self, QtCore.Qt.WindowType.Popup)
        self.panel.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.panel.setAutoFillBackground(True)
        lay = QtWidgets.QHBoxLayout(self.panel)
        lay.setContentsMargins(4, 4, 4, 4)
        self.segments = StokesSegments(ns, current, pick)
        self.segments.group.idClicked.connect(lambda _k: self.panel.hide())
        lay.addWidget(self.segments)
        self.clicked.connect(self.drop)
        self.set(current)

    def drop(self) -> None:
        self.panel.adjustSize()
        self.panel.move(self.mapToGlobal(QtCore.QPoint(0, self.height())))
        self.panel.show()

    def set(self, s: int, all_: bool = False) -> None:
        """s: the Stokes shown; all_: every Stokes side by side (All)."""
        self.setText(f"Stokes {ALL if all_ else STOKES[s]} ▾")
        self.segments.set(len(self.segments.group.buttons()) - 1 if all_ else s)


class MenuButton(QtWidgets.QToolButton):
    """A tool button with a menu, with room for its arrow beside the label, and the arrow level with the label's
    middle: the style drew it in the bottom-right corner, over the label's last letter ("Panels" with the arrow on
    its s) and its tip below the baseline. The button and its label as the style draws them, the style's own arrow."""
    ARROW = 12                                          # px: the arrow and a gap, right of the label

    def sizeHint(self):
        s = super().sizeHint()
        return QtCore.QSize(s.width() + self.ARROW, s.height())

    def minimumSizeHint(self):
        return self.sizeHint()

    def paintEvent(self, e):
        p = QtWidgets.QStylePainter(self)
        opt = QtWidgets.QStyleOptionToolButton()
        self.initStyleOption(opt)
        opt.features &= ~QtWidgets.QStyleOptionToolButton.ToolButtonFeature.HasMenu
        bevel = QtWidgets.QStyleOptionToolButton(opt)
        bevel.text = ""
        bevel.icon = QtGui.QIcon()
        p.drawComplexControl(QtWidgets.QStyle.ComplexControl.CC_ToolButton, bevel)
        opt.rect = self.rect().adjusted(0, 0, -self.ARROW, 0)
        p.drawControl(QtWidgets.QStyle.ControlElement.CE_ToolButtonLabel, opt)
        tw = self.fontMetrics().horizontalAdvance(self.text())
        a = QtWidgets.QStyleOption()
        a.initFrom(self)
        a.rect = QtCore.QRect(int(opt.rect.center().x() + tw / 2 + 4), self.height() // 2 - 4, 8, 8)
        p.drawPrimitive(QtWidgets.QStyle.PrimitiveElement.PE_IndicatorArrowDown, a)


class JumpSlider(QtWidgets.QSlider):
    """A click on the track jumps to the value under the pointer, as a macOS slider does, and a drag goes on from
    there. Qt's own click steps one page (10): on a 14-tuning slider a click anywhere left of the handle went to 0."""

    def mousePressEvent(self, e):
        if e.button() == QtCore.Qt.MouseButton.LeftButton:
            opt = QtWidgets.QStyleOptionSlider()
            self.initStyleOption(opt)
            st, cc = self.style(), QtWidgets.QStyle.ComplexControl.CC_Slider
            handle = st.subControlRect(cc, opt, QtWidgets.QStyle.SubControl.SC_SliderHandle, self)
            p = e.position().toPoint()
            if not handle.contains(p):
                groove = st.subControlRect(cc, opt, QtWidgets.QStyle.SubControl.SC_SliderGroove, self)
                span = max(1, groove.width() - handle.width())
                x = p.x() - groove.x() - handle.width() // 2
                self.setValue(QtWidgets.QStyle.sliderValueFromPosition(self.minimum(), self.maximum(), x, span,
                                                                       opt.upsideDown))
        super().mousePressEvent(e)                      # the handle is under the pointer now: Qt starts the drag


class NavBar:
    """The toolbar of a Shell: built from its session's axes, kept in step with the state (sync)."""

    def __init__(self, shell, drop: bool = False):
        """drop: Stokes as the modern look's drop-down in place of the combo, which stays, hidden."""
        self.shell, s = shell, shell.session
        self.ax = shell.dataset.axes
        r = shell.dataset.roles
        self.n = {"t": r.nt, "l": r.nl, "s": r.ns}
        tb = self.tb = shell.addToolBar("Navigation")
        tb.setObjectName("nav")
        self.sliders: dict[str, JumpSlider] = {}
        self.labels: dict[str, QtWidgets.QLabel] = {}
        st = s.state
        for name, axis in (("t", "t"), ("λ", "l")):
            if not s.present[axis] or self.n[axis] < 2:
                continue
            tb.addWidget(QtWidgets.QLabel(f" {name} "))
            sl = JumpSlider(QtCore.Qt.Orientation.Horizontal)
            sl.setRange(0, self.n[axis] - 1)
            sl.setFixedWidth(SLIDER_W[1])
            sl.setValue(getattr(st, axis))
            sl.valueChanged.connect(lambda v, axis=axis: s.set_index(axis, v))
            lab = QtWidgets.QLabel()
            lab.setMinimumWidth(110)
            if axis == "t":                             # its widest text fixes its width: no re-layout while playing
                lab.setText(self.text(axis, self.n[axis] - 1))
                lab.setFixedWidth(lab.sizeHint().width() + 8)
            lab.setText(self.text(axis, getattr(st, axis)))
            tb.addWidget(sl)
            tb.addWidget(lab)
            self.sliders[axis], self.labels[axis] = sl, lab
        self.stokes: QtWidgets.QComboBox | None = None
        self.drop: StokesDrop | None = None
        self._drop_act: QtGui.QAction | None = None
        self.all = False                                # every Stokes side by side (the 2x2 view)
        if s.present["s"] and self.n["s"] > 1:
            self._stokes_label = tb.addWidget(QtWidgets.QLabel(" Stokes "))
            self.stokes = QtWidgets.QComboBox()
            self.stokes.addItems(list(STOKES[:self.n["s"]]) + [ALL])
            self.stokes.setCurrentIndex(st.s)
            self.stokes.currentIndexChanged.connect(self._picked)
            self.stokes.setToolTip("Stokes shown in the image: keys " + ", ".join(
                f"{k + 1} {STOKES[k]}" for k in range(self.n["s"])))
            self._stokes_act = tb.addWidget(self.stokes)
        tb.addSeparator()
        self.play = QtWidgets.QToolButton()
        self.play.setText("t")
        self.play.setIcon(icons.glyph_icon("play", self.play))
        self.play.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.play.setCheckable(True)
        self.play.setEnabled(s.present["t"] and self.n["t"] > 1)
        tb.addWidget(self.play)
        self.fps = QtWidgets.QSpinBox()
        self.fps.setRange(FPS[0], FPS[1])
        self.fps.setValue(FPS[2])
        self.fps.setSuffix(" fps")
        tb.addWidget(self.fps)
        tb.addSeparator()
        # the slit (S, ui.slit), with the controls; the prototype's slit_btn (app/viewer.py:1114-1126)
        self.slit = QtWidgets.QToolButton()
        self.slit.setObjectName("slit")
        self.slit.setIcon(icons.glyph_icon("slit", self.slit))
        self.slit.setCheckable(True)
        self.slit.setAutoRaise(True)
        self.slit.setToolTip("Draw a slit on the image (S): click adds a point, double click finishes, right click "
                             "removes the last point, Esc cancels. Two points: a straight slit; more: a path through "
                             "them. \u232b removes it")
        self.slit.toggled.connect(lambda on: shell.set_slit_mode(on))
        tb.addWidget(self.slit)
        self.panels = MenuButton()
        self.panels.setObjectName("panels")
        self.panels.setText("Panels")
        self.panels.setToolTip("Show or hide the panels")
        self.panels.setPopupMode(QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QtWidgets.QMenu(self.panels)
        for d in (shell.spec_dock, shell.lt_dock, shell.slit_dock):     # the slit's: enabled with a slit
            menu.addAction(d.toggleViewAction())                       # (the prototype's viewer.py:1131)
        self.panels.setMenu(menu)
        tb.addWidget(self.panels)
        gap = QtWidgets.QWidget()
        gap.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Preferred)
        gap.setMinimumWidth(32)                         # kept even in a narrow window: the sliders give way
        tb.addWidget(gap)
        self.reset = QtWidgets.QToolButton()
        self.reset.setObjectName("reset_panels")
        self.reset.setIcon(icons.reset_panels(self.reset))
        self.reset.setAutoRaise(True)
        self.reset.setToolTip("Reset: dock every panel back where it started and show the whole image again")
        self.reset.clicked.connect(shell.reset_panels)
        tb.setIconSize(icons.size(icons.RESET))
        tb.addWidget(self.reset)
        self.help = QtWidgets.QToolButton()             # the keys and the mouse, for whoever does not know ? yet
        self.help.setObjectName("help")
        self.help.setText("?")
        self.help.setAutoRaise(True)
        self.help.setToolTip("What the keys and the mouse do (?)")
        self.help.clicked.connect(shell.toggle_sheet)
        tb.addWidget(self.help)
        if drop:
            self.set_stokes_drop(True)

    def text(self, axis: str, v: int) -> str:
        """A slider's label: t in UT with the frame index quieter beside it; lambda as delta-lambda, the continuum
        tuning marked; the index of n otherwise."""
        n = self.n[axis]
        if axis == "t":
            u = self.ax.utc_str(v) if self.ax is not None and self.ax.t_sec is not None else None
            if not u:
                return f"{v}/{n - 1}"
            # the time is what one reads, the index what one quotes
            dim = self.shell.palette().color(QtGui.QPalette.ColorRole.PlaceholderText).name()
            return f'{u}&nbsp;UT&nbsp;&nbsp;<span style="color:{dim}; font-size:small">{v}/{n - 1}</span>'
        dl = self.ax.dlam_A() if self.ax is not None else None
        if dl is not None and len(dl) == n:
            return f"Δλ {fmt_signed(dl[v], 3)}\u00a0Å" + ("  (cont.)" if v == self.ax.cont else "")
        return f"{v}/{n - 1}"

    def set_stokes_drop(self, on: bool) -> None:
        """Stokes as the modern look's drop-down in place of the combo, which stays, hidden; or the combo back."""
        if self.stokes is None:
            return
        if on and self.drop is None:
            s = self.shell.session
            self.drop = StokesDrop(self.n["s"], s.state.s, self._picked)
            self._drop_act = self.tb.insertWidget(self._stokes_label, self.drop)
        if self.drop is not None and self._drop_act is not None:     # made together
            self.drop.set(self.shell.session.state.s, self.all)
            self.drop.panel.hide()
            self._drop_act.setVisible(on)
        self._stokes_act.setVisible(not on)
        self._stokes_label.setVisible(not on)

    def sync(self, st, changed) -> None:
        """Sliders, labels and combo follow the state, without sending it back."""
        for axis in ("t", "l"):
            if axis in changed and axis in self.sliders:
                v = getattr(st, axis)
                sl = self.sliders[axis]
                if sl.value() != v:
                    sl.blockSignals(True)
                    sl.setValue(v)
                    sl.blockSignals(False)
                self.labels[axis].setText(self.text(axis, v))
        if "s" in changed and not self.all:             # All stays while a panel's click changes the Stokes
            self._show_stokes(st.s)

    def _picked(self, k: int) -> None:
        """A Stokes, or All (k = ns), from the combo or the drop-down."""
        if k == self.n["s"]:
            self.shell.set_grid(True)
        else:
            self.shell.pick_stokes(k)

    def set_all(self, on: bool) -> None:
        """The controls say All while the 2x2 view is on, the Stokes shown otherwise."""
        self.all = bool(on)
        self._show_stokes(self.shell.session.state.s)

    def _show_stokes(self, s: int) -> None:
        if self.stokes is not None:
            k = self.n["s"] if self.all else s
            if self.stokes.currentIndex() != k:
                self.stokes.blockSignals(True)
                self.stokes.setCurrentIndex(k)
                self.stokes.blockSignals(False)
        if self.drop is not None:
            self.drop.set(s, self.all)

    def restyle(self) -> None:
        """Another theme (Shell.set_theme): the Stokes segments make their sheet again."""
        if self.drop is not None:
            self.drop.segments.restyle()

    def fit(self, width: int) -> None:
        """Sliders between SLIDER_W so the whole toolbar fits `width`: at a fixed 220 px it needed 1210 px, and below
        that it hid its last items first (reset, then Panels)."""
        sl = list(self.sliders.values())
        if not sl:
            return
        cur = sl[0].width()
        others = self.tb.sizeHint().width() - len(sl) * cur        # everything but the sliders
        w = max(SLIDER_W[0], min(SLIDER_W[1], (width - others - 8) // len(sl)))
        if w != cur:
            for x in sl:
                x.setFixedWidth(w)

"""The navigation toolbar (ROADMAP E4.5): t and lambda sliders with their labels, the Stokes combo, play with its
rate (playback itself: E4.9), the Panels menu and the reset button, right-aligned. The sliders give way first when
the window narrows, so the whole toolbar stays visible.

From the prototype's app/viewer.py: the toolbar (913-960), JumpSlider (364), _slider_text (1106), _fit_toolbar
(2323), set_index's keeping of sliders, labels and combo in step (1843-1848).
"""
from PySide6 import QtCore, QtGui, QtWidgets

from ..data.axes import STOKES, fmt_signed
from . import icons

SLIDER_W = (90, 220)                                    # px: the t and lambda sliders give way first
FPS = (1, 120, 20)                                      # the rate box: minimum, maximum, default


class StokesSegments(QtWidgets.QWidget):
    """I Q U V as a segmented control, one click, instead of a drop-down, two (the modern look's stokes part; the
    prototype's app/look.py _stokes, 581)."""

    def __init__(self, ns: int, current: int, pick):
        super().__init__()
        from . import style

        self.setObjectName("stokes_segments")
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground)
        pal = self.palette()
        text = pal.color(QtGui.QPalette.ColorRole.ButtonText)
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
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.group = QtWidgets.QButtonGroup(self)
        self.group.setExclusive(True)
        for k in range(ns):
            b = QtWidgets.QToolButton()
            b.setText(STOKES[k])
            b.setCheckable(True)
            b.setToolTip(f"Stokes {STOKES[k]} in the image (key {k + 1})")
            self.group.addButton(b, k)
            lay.addWidget(b)
        self.group.button(current).setChecked(True)
        self.group.idClicked.connect(pick)

    def set(self, s: int) -> None:
        if self.group.checkedId() != s:
            self.group.button(s).setChecked(True)


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

    def __init__(self, shell, segmented: bool = False):
        """segmented: Stokes as segments (the modern look) in place of the combo, which stays, hidden."""
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
        self.stokes = self.segments = self._segments_act = None
        if s.present["s"] and self.n["s"] > 1:
            self._stokes_label = tb.addWidget(QtWidgets.QLabel(" Stokes "))
            self.stokes = QtWidgets.QComboBox()
            self.stokes.addItems(list(STOKES[:self.n["s"]]))
            self.stokes.setCurrentIndex(st.s)
            self.stokes.currentIndexChanged.connect(lambda v: s.set_index("s", v))
            self.stokes.setToolTip("Stokes shown in the image: keys " + ", ".join(
                f"{k + 1} {STOKES[k]}" for k in range(self.n["s"])))
            self._stokes_act = tb.addWidget(self.stokes)
        tb.addSeparator()
        self.play = QtWidgets.QToolButton()
        self.play.setText("▶ t")
        self.play.setCheckable(True)
        self.play.setEnabled(s.present["t"] and self.n["t"] > 1)
        tb.addWidget(self.play)
        self.fps = QtWidgets.QSpinBox()
        self.fps.setRange(FPS[0], FPS[1])
        self.fps.setValue(FPS[2])
        self.fps.setSuffix(" fps")
        tb.addWidget(self.fps)
        tb.addSeparator()
        self.panels = QtWidgets.QToolButton()
        self.panels.setObjectName("panels")
        self.panels.setText("Panels")
        self.panels.setToolTip("Show or hide the panels")
        self.panels.setPopupMode(QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QtWidgets.QMenu(self.panels)
        for d in (shell.spec_dock, shell.lt_dock):
            menu.addAction(d.toggleViewAction())
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
        if segmented:
            self.set_segmented(True)

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
            return f'{u} UT&nbsp;&nbsp;<span style="color:{dim}; font-size:small">{v}/{n - 1}</span>'
        dl = self.ax.dlam_A() if self.ax is not None else None
        if dl is not None and len(dl) == n:
            return f"Δλ {fmt_signed(dl[v], 3)} Å" + ("  (cont.)" if v == self.ax.cont else "")
        return f"{v}/{n - 1}"

    def set_segmented(self, on: bool) -> None:
        """Stokes as segments (the modern look) in place of the combo, which stays, hidden; or the combo back."""
        if self.stokes is None:
            return
        if on and self.segments is None:
            s = self.shell.session
            self.segments = StokesSegments(self.n["s"], s.state.s, lambda k: s.set_index("s", k))
            self._segments_act = self.tb.insertWidget(self._stokes_label, self.segments)
        if self.segments is not None:
            self.segments.set(self.shell.session.state.s)
            self._segments_act.setVisible(on)
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
        if "s" in changed and self.stokes is not None and self.stokes.currentIndex() != st.s:
            self.stokes.blockSignals(True)
            self.stokes.setCurrentIndex(st.s)
            self.stokes.blockSignals(False)
        if "s" in changed and self.segments is not None:
            self.segments.set(st.s)

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

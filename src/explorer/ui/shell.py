"""The window: for now the image panel, a status line and the keys that move through the cube (ROADMAP E3.6). The
spectra and lambda-t panels come in E4, playback in E4, the look in E5, the slit in E7.

It draws what explorer.core decides and turns input into core actions: the mouse over the image moves the cursor, a
click locks it there and a right click releases it (the prototype's _image_click), a double click shows the whole
image again. The keys, from the prototype's _key_table, in one table (the ? sheet and the ActionRegistry come in E5):
- Left / Right: lambda, previous / next tuning; Down / Up: t, previous / next frame (each arrow moves its line the
  way it points: lambda is horizontal on the spectra and lambda-t, t vertical on lambda-t);
- 1..ns: that Stokes, whenever the cube has Stokes (the prototype registered them only when it also had t);
- L: lock or release the cursor; Esc: release it;
- Ctrl+W close, Ctrl+M minimise, Ctrl+Q quit (Qt reads Ctrl as Cmd on a Mac, where Cmd+Q is the application menu's).
"""
import math
import sys
import time

from PySide6 import QtCore, QtGui, QtWidgets

from ..core.scheduler import Scheduler
from ..core.session import Session
from ..core.state import ViewState
from ..data.axes import STOKES
from .imageview import ImageView
from .loop import QtLoop

MEMORY_S = 1.0                                          # the caches' budget follows the machine's memory (Dataset)


class _Sink:
    """The scheduler's results on screen: the image now; the other panels come in E4 and are kept until then."""

    def __init__(self, shell: "Shell"):
        self.shell = shell

    def image(self, idx, img, levels):
        self.shell.view.set_image(img, levels)
        self.shell.update_status()
        self.shell.first_image()

    def spectra(self, spec, pixel, t):
        self.shell.last["spectra"] = (spec, pixel, t)

    def lambda_t(self, lt, pixel, s, levels):
        self.shell.last["lambda_t"] = (lt, pixel, s, levels)

    def cleared(self, pixel):
        self.shell.last.pop("spectra", None)
        self.shell.last.pop("lambda_t", None)

    def y_range(self, k, r):
        pass

    def units(self, iscale):
        pass


class Shell(QtWidgets.QMainWindow):
    def __init__(self, dataset, title: str | None = None, t0: float | None = None):
        """t0: perf_counter() when opening started, for the time to the first image."""
        super().__init__()
        self.dataset = dataset
        self.t0 = time.perf_counter() if t0 is None else t0
        self.first_image_s: float | None = None
        self._after_first: list = []
        self.loop = QtLoop(self)
        self.session = Session(self.loop, dataset)
        ex = dataset.executors
        self.view = ImageView(on_hover=self._hover, strips=ex.strips, parts=ex.n_strips)
        self.setCentralWidget(self.view.widget)
        self.status = QtWidgets.QLabel()
        self.statusBar().addWidget(self.status, 1)
        self.last: dict = {}
        self.setWindowTitle(title or str(getattr(dataset, "path", "")))
        self.view.widget.scene().sigMouseClicked.connect(self._click)
        self._keys()
        self._off = self.session.store.subscribe(self._on_state)
        self.scheduler = Scheduler(self.session, _Sink(self))
        st = self.session.state
        self.view.set_crosshair(*st.cursor)
        self._mem = QtCore.QTimer(self)
        self._mem.setInterval(int(MEMORY_S * 1000))
        self._mem.timeout.connect(self._memory)
        self._mem.start()

    # ---------------------------------------------------------------- input
    def _hover(self, y: float, x: float) -> None:
        self.session.hover(math.floor(y), math.floor(x))

    def _click(self, ev) -> None:
        if ev.button() == QtCore.Qt.MouseButton.RightButton:
            self.session.lock(False)
            return
        if ev.button() != QtCore.Qt.MouseButton.LeftButton or not self.view.vb.sceneBoundingRect().contains(
                ev.scenePos()):
            return
        if ev.double():
            self.view.show_all()
            return
        p = self.view.vb.mapSceneToView(ev.scenePos())
        self.session.lock(False)                        # move there, then lock
        self.session.hover(math.floor(p.y()), math.floor(p.x()))
        self.session.lock(True)

    def key_table(self):
        """(keys as shown, what they do, ((key sequence, action), ...)) for this cube."""
        K, s = QtCore.Qt.Key, self.session
        rows: list[tuple[str, str, tuple]] = []
        if s.present["l"]:
            rows.append(("← →", "λ: previous, next tuning",
                         ((K.Key_Left, lambda: s.step("l", -1)), (K.Key_Right, lambda: s.step("l", 1)))))
        if s.present["t"]:
            rows.append(("↓ ↑", "t: previous, next frame",
                         ((K.Key_Down, lambda: s.step("t", -1)), (K.Key_Up, lambda: s.step("t", 1)))))
        if s.present["s"] and s.sizes["s"] > 1:
            n = s.sizes["s"]
            rows.append((f"1–{n}", "Stokes " + " ".join(STOKES[:n]),
                         tuple((str(k + 1), lambda k=k: s.set_index("s", k)) for k in range(n))))
        rows += [("L", "lock, release the cursor", ((K.Key_L, lambda: s.lock(not s.state.locked)),)),
                 ("Esc", "release the cursor", ((K.Key_Escape, lambda: s.lock(False)),)),
                 ("Ctrl+W", "close the window", (("Ctrl+W", self.close),)),
                 ("Ctrl+M", "minimise", (("Ctrl+M", self.showMinimized),)),
                 ("Ctrl+Q", "quit", () if sys.platform == "darwin" else (("Ctrl+Q", self.close),))]
        return rows

    def _keys(self) -> None:
        for _keys, _what, binds in self.key_table():
            for seq, fn in binds:
                sc = QtGui.QShortcut(QtGui.QKeySequence(seq), self)
                sc.activated.connect(fn)

    # ---------------------------------------------------------------- state
    def _on_state(self, st: ViewState, changed: frozenset) -> None:
        if "cursor" in changed:
            self.view.set_crosshair(*st.cursor)
        self.update_status()

    def update_status(self) -> None:
        st = self.session.state
        y, x = st.cursor
        img = self.scheduler.img if hasattr(self, "scheduler") else None
        v = img[y, x] if img is not None else float("nan")
        parts = [f"x {x}  y {y}"]
        if self.session.present["t"]:
            parts.append(f"t {st.t}")
        if self.session.present["l"]:
            parts.append(f"λ {st.l}")
        if self.session.present["s"] and self.session.sizes["s"] > 1:
            parts.append(f"Stokes {STOKES[st.s]}")
        parts.append("no data (padding)" if not math.isfinite(v) else f"{v:.4g}")
        if st.locked:
            parts.append("locked")
        self.status.setText("   ·   ".join(parts))

    def first_image(self) -> None:
        if self.first_image_s is not None:
            return
        QtWidgets.QApplication.processEvents()          # on screen, not only handed to Qt
        self.first_image_s = time.perf_counter() - self.t0
        print(f"first image on screen {self.first_image_s:.2f} s", file=sys.stderr, flush=True)
        for seconds, fn in self._after_first:
            QtCore.QTimer.singleShot(int(seconds * 1000), fn)

    def after_first_image(self, seconds: float, fn) -> None:
        """Run fn this many seconds after the first image is on screen (or after now, if it already is)."""
        if self.first_image_s is not None:
            QtCore.QTimer.singleShot(int(seconds * 1000), fn)
        else:
            self._after_first.append((seconds, fn))

    def _memory(self) -> None:
        if hasattr(self.dataset, "update_memory"):
            self.dataset.update_memory()

    # ---------------------------------------------------------------- closing
    def closeEvent(self, ev) -> None:
        self._mem.stop()
        self._off()
        self.scheduler.close()
        super().closeEvent(ev)

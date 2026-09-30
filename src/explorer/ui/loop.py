"""The core's Loop on Qt's event loop (docs/decisions/0007): what the core asks to run soon, later, or from another
thread, runs on the thread that owns the windows.

- call_soon(fn): a 0-ms QTimer, as the prototype grouped mouse moves into one cursor update per pass of the event
  loop (Viewer._hover_timer). Main thread only, as the Store.
- call_later(seconds, fn): a QTimer with a delay (the spectra's refit at rest, the y-range sample). Main thread only.
- post(fn): from any thread; a queued signal takes fn to the main thread, where it runs. Reads finish on worker
  threads; touching a widget from one of them corrupts or hangs Qt.
A callback that raises is logged; the loop and the other callbacks go on.
"""
from collections.abc import Callable

from PySide6 import QtCore

from ..obs import get_logger

log = get_logger("ui")


def _safe(fn: Callable[[], None]) -> Callable[[], None]:
    def run():
        try:
            fn()
        except Exception:
            log.exception("callback %r failed", fn)
    return run


class QtLoop(QtCore.QObject):
    _posted = QtCore.Signal(object)

    def __init__(self, parent: QtCore.QObject | None = None):
        """Create it on the main thread: queued calls run on the thread the object lives in."""
        super().__init__(parent)
        self._posted.connect(self._run, QtCore.Qt.ConnectionType.QueuedConnection)

    def call_soon(self, fn: Callable[[], None]) -> None:
        QtCore.QTimer.singleShot(0, _safe(fn))

    def call_later(self, seconds: float, fn: Callable[[], None]) -> None:
        QtCore.QTimer.singleShot(max(0, int(round(float(seconds) * 1000))), _safe(fn))

    def post(self, fn: Callable[[], None]) -> None:
        self._posted.emit(fn)

    @QtCore.Slot(object)
    def _run(self, fn) -> None:
        _safe(fn)()

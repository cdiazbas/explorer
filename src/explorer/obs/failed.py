"""What failed inside the event loop (a posted result, a timer, a state listener), told to whoever listens: the window
says it on its status line. Logged with its traceback where it is caught (ui.loop, core.state); told here so that a
failure is seen on screen, not only written to the log. A listener that fails is left out of the telling, never
raised into the loop.

    off = failed.listen(lambda what, error: ...)    # off() to stop listening
    failed.report("state listener ...", error)
"""
from collections.abc import Callable

_listeners: list[Callable[[str, BaseException], None]] = []


def listen(fn: Callable[[str, BaseException], None]) -> Callable[[], None]:
    _listeners.append(fn)
    return lambda: _listeners.remove(fn) if fn in _listeners else None


def report(what: str, error: BaseException) -> None:
    for fn in list(_listeners):
        try:
            fn(what, error)
        except Exception:                               # the telling must not fail the loop it reports on
            pass

"""The outline of a window being resized by its edges, drawn by the X server itself (ROADMAP E5.8): one
override-redirect window, its background the outline's colour, shaped (X SHAPE) to a 2-px ring, on a connection of
its own. The window is never redrawn by the client: no pixels go over the link.

On XQuartz each X window is a macOS window, and window operations are dear (bench/x_ops.py, ssh -Y from bellatrix,
2026-10-01): a sync 1 ms, a strip moved 10 ms, the four strips of a Qt-drawn outline 57 ms a step (p90 536), one
shaped window 33 ms, a big window resized 406 ms. Asked every 25 ms, the four strips queued on the server and the
outline reached the pointer seconds late. Here a thread applies the latest size asked for and waits for the server
to have done it before the next: what the server cannot keep up with is skipped, never queued.

    o = XOutline(0x2f6fde)     # its thread connects to DISPLAY now: ready before the first drag
    o.show(x, y, w, h)          # as often as wanted: the latest wins
    o.hide()                    # at the release; shown again by the next drag
    o.close()                   # with its window: the connection closes, the thread ends

Connected once and kept: a connection per drag cost its set-up at every press (0.32 s through an emulated link of
8 ms each way, 1.42 s at 40 ms).
"""
import os
import threading

from ..obs.log import get_logger

log = get_logger("platform")
T = 2                                                   # px


def ring(w: int, h: int, t: int = T) -> list[tuple[int, int, int, int]]:
    """The four rectangles of a t-px ring inside a w x h window."""
    return [(0, 0, w, t), (0, h - t, w, t), (0, 0, t, h), (w - t, 0, t, h)]


class XServer:
    """The X side: one override-redirect window, shaped to a ring, moved and reshaped; apply() returns once the
    server has done it (a round trip)."""

    def __init__(self, colour: int, display_name: str | None = None):
        from Xlib import X, display
        from Xlib.ext import shape

        self.X, self.shape = X, shape
        self.d = display.Display(display_name)
        self.colour = colour
        self.win = None
        self.mapped = False

    def ready(self) -> None:
        self.d.shape_query_version()                    # the extension known before the first drag
        self.d.sync()

    def apply(self, r: tuple[int, int, int, int] | None) -> None:
        """r: the outline's place on the root, or None: hidden."""
        X, d = self.X, self.d
        if r is None:
            if self.mapped:
                self.win.unmap()
                self.mapped = False
                d.sync()
            return
        x, y, w, h = r
        if self.win is None:
            scr = d.screen()
            self.win = scr.root.create_window(x, y, w, h, 0, scr.root_depth, X.InputOutput, X.CopyFromParent,
                                              background_pixel=self.colour, override_redirect=True)
        else:
            self.win.configure(x=x, y=y, width=w, height=h, stack_mode=X.Above)
        self.win.shape_rectangles(self.shape.SO.Set, self.shape.SK.Bounding, X.Unsorted, 0, 0, ring(w, h))
        if not self.mapped:
            self.win.map()
            self.mapped = True
        d.sync()

    def close(self) -> None:
        if self.win is not None:
            self.win.destroy()
        self.d.close()


class XOutline:
    """The outline, on a thread of its own: show() keeps only the latest size; the thread applies it and, the server
    done, takes the next latest. server: what draws it (XServer by default; a stand-in in the tests)."""

    def __init__(self, colour: int, display_name: str | None = None, server=None):
        self.steps = 0                                  # sizes the server was given
        self._want = None
        self._new = False
        self._stop = False
        self._cv = threading.Condition()
        self._make = server or (lambda: XServer(colour, display_name or os.environ.get("DISPLAY")))
        self._thread = threading.Thread(target=self._run, name="outline", daemon=True)
        self._thread.start()

    def show(self, x: int, y: int, w: int, h: int) -> None:
        with self._cv:
            self._want, self._new = (int(x), int(y), max(int(w), 2 * T), max(int(h), 2 * T)), True
            self._cv.notify()

    def hide(self) -> None:
        with self._cv:
            self._want, self._new = None, True
            self._cv.notify()

    def close(self, wait: float = 0.0) -> None:
        with self._cv:
            self._stop = True
            self._cv.notify()
        if wait:
            self._thread.join(wait)

    def _run(self) -> None:
        try:
            srv = self._make()
            getattr(srv, "ready", lambda: None)()       # connected and answered: the first drag pays nothing
        except Exception as e:                          # no outline, the resize on release still happens
            log.warning("no outline (the X display): %r", e)
            return
        try:
            while True:
                with self._cv:
                    while not self._new and not self._stop:
                        self._cv.wait()
                    if self._stop:
                        break
                    r, self._new = self._want, False
                srv.apply(r)                            # returns when the server has done it: the backpressure
                self.steps += 1
        except Exception as e:
            log.warning("outline stopped: %r", e)
        finally:
            try:
                srv.close()
            except Exception:
                pass

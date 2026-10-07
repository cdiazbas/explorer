"""The outline of a window being resized by its edges, drawn by the X server itself (ROADMAP E5.8): one
override-redirect window the size the window will take, filled with the look's colour, its T-px border the X
server's own in the accent, the size written in its middle with a server font; on a connection of its own. The
window is never drawn by the client: no pixels go over the link.

On XQuartz each X window is a macOS window, and window operations are dear (bench/x_ops.py, ssh -Y from bellatrix,
2026-10-01): a sync 1 ms, a strip moved 10 ms, the four strips of a Qt-drawn outline 57 ms a step (p90 536), one
shaped window 33 ms, a big window resized 406 ms. Asked every 25 ms, the four strips queued on the server and the
outline reached the pointer seconds late. Here a thread applies the latest size asked for and waits for the server
to have done it before the next: what the server cannot keep up with is skipped, never queued.

A window shaped (X SHAPE) to a ring, as before, cost XQuartz 34-40 ms a step but showed white inside while it grew
and left earlier rings behind as it shrank; its shape set before its size changed nothing. Four plain windows, one
per side, were clean and cost 540-1100 ms a step, the outline far behind the pointer. One plain window: 31-34 ms
(p90 36-44), clean (through the bridge to the user's XQuartz, 2026-10-08).

    o = XOutline(0x0a84ff)     # its thread connects to DISPLAY now: ready before the first drag
    o.colours(0x0a84ff, 0x1e1e1e, 0xe4e4e4)   # border, inside, the size's ink: from the next drag
    o.show(x, y, w, h)          # as often as wanted: the latest wins
    o.hide()                    # at the release; shown again by the next drag
    o.close()                   # with its window: the connection closes, the thread ends

Connected once and kept: a connection per drag cost its set-up at every press (0.32 s through an emulated link of
8 ms each way, 1.42 s at 40 ms).
"""
import os
import threading
from typing import Any

from ..obs.log import get_logger

log = get_logger("platform")
T = 2                                                   # px: the border
INSIDE, INK = 0x1E1E1E, 0xE4E4E4                        # explorer's dark content and label, until colours() says
FONT = "fixed"                                          # a core font every X server has (XQuartz included)


def label(w: int, h: int) -> str:
    """The size written in the outline: latin-1, as a core font draws it."""
    return f"{w} × {h}"


class XServer:
    """The X side: one override-redirect window, moved and sized, its size written in it; apply() returns once the
    server has done it (a round trip)."""

    def __init__(self, colour: int, display_name: str | None = None):
        from Xlib import X

        from . import xlibauth

        self.X = X
        self.d = xlibauth.display(display_name)         # with the bridge's choice of cookie (xlibauth)
        self.border, self.inside, self.ink = colour, INSIDE, INK
        self.win: Any = None                            # an Xlib window, once made
        self.gc: Any = None
        self.font: Any = None
        self.char = (0, 0, 0)                           # a character's width, ascent, descent in FONT
        self.mapped = False

    def ready(self) -> None:
        try:
            self.font = self.d.open_font(FONT)
            q = self.font.query()
            self.char = (q.max_bounds.character_width, q.font_ascent, q.font_descent)
        except Exception as e:                          # no size written; the outline still shows
            log.info("outline: no font %r: %r", FONT, e)
            self.font = None
        self.d.sync()

    def paint(self, border: int, inside: int, ink: int) -> None:
        """The colours from the next size on (the look may have changed since the last drag)."""
        self.border, self.inside, self.ink = border, inside, ink
        if self.win is not None:
            self.win.change_attributes(background_pixel=inside, border_pixel=border)
            if self.gc is not None:
                self.gc.change(foreground=ink, background=inside)

    def apply(self, r: tuple[int, int, int, int] | None) -> None:
        """r: the outline's place on the root, its border included, or None: hidden."""
        X, d = self.X, self.d
        if r is None:
            if self.mapped:
                self.win.unmap()
                self.mapped = False
                d.sync()
            return
        x, y, w, h = r
        iw, ih = max(1, w - 2 * T), max(1, h - 2 * T)  # an X window's border is outside its size
        if self.win is None:
            scr = d.screen()
            self.win = scr.root.create_window(x, y, iw, ih, T, scr.root_depth, X.InputOutput, X.CopyFromParent,
                                              background_pixel=self.inside, border_pixel=self.border,
                                              override_redirect=True)
            if self.font is not None:
                self.gc = self.win.create_gc(foreground=self.ink, background=self.inside, font=self.font)
        else:
            self.win.configure(x=x, y=y, width=iw, height=ih, stack_mode=X.Above)
        if not self.mapped:
            self.win.map()
            self.mapped = True
        if self.gc is not None:
            text = label(w, h)
            cw, asc, desc = self.char
            self.win.clear_area(0, 0, 0, 0)            # the size before, where it was written
            self.win.poly_text(self.gc, (iw - cw * len(text)) // 2, (ih + asc - desc) // 2, [text])
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
        self._want: tuple[int, int, int, int] | None = None
        self._new = False
        self._paint: tuple[int, int, int] | None = None
        self._stop = False
        self._cv = threading.Condition()
        self._make = server or (lambda: XServer(colour, display_name or os.environ.get("DISPLAY")))
        self._thread = threading.Thread(target=self._run, name="outline", daemon=True)
        self._thread.start()

    def colours(self, border: int, inside: int, ink: int) -> None:
        """Border, inside and the size's ink (0xRRGGBB), applied before the next size."""
        with self._cv:
            self._paint = (int(border), int(inside), int(ink))

    def show(self, x: int, y: int, w: int, h: int) -> None:
        with self._cv:
            self._want, self._new = (int(x), int(y), max(int(w), 2 * T + 1), max(int(h), 2 * T + 1)), True
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
                    paint, self._paint = self._paint, None
                if paint is not None and hasattr(srv, "paint"):
                    srv.paint(*paint)
                srv.apply(r)                            # returns when the server has done it: the backpressure
                self.steps += 1
        except Exception as e:
            log.warning("outline stopped: %r", e)
        finally:
            try:
                srv.close()
            except Exception:
                pass

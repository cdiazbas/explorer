"""The mask's outline on every image (ROADMAP E8.2, `--mask file`): the main cube's, each linked cube's and the 2x2
view's four, at the mask's frame for the session's t (data.mask: its frame t, or its only one). The outline is
computed once per mask frame (Mask.outline keeps the last ones) and handed to one line item per image, drawn over
the image in data coordinates, so zoom and pan move it with the pixels. CRISPEX drew it on the main image and the
reference image (CRISPEX_DRAW_MASK_OVERLAYS, crispex.pro:7104; DRAW_MASK, 8069-8243).

A frame's outline not kept yet is read and computed on a worker thread (pool: the main cube's Executors.io) and drawn
when it comes, if its frame is still the one wanted; after each step in t the next AHEAD frames' are computed the
same way, as the image's frames are read ahead, so that playback finds them kept. On the UI thread, a step in t
with a per-t mask on a 2k cube spent ~29 ms reading and outlining the frame before the new image could be painted.
A request whose frame is no longer wanted when its turn comes is skipped.

Hidden (H, or Panels → Mask: Shell.set_mask_shown), the outline is on no image and nothing of the mask is read or
computed while t steps; shown again, it is the outline at the t of then. Not kept between sessions: each start shows it.

    outlines = MaskOutlines(session, mask, pool)    # pool None: computed on the calling thread
    outlines.attach(view)                       # an ImageView: the outline drawn now, and each one after
    outlines.set_colour(mask_colour(look))
    outlines.set_visible(False)                 # on no image, and nothing read until shown again
"""
from concurrent.futures import Executor, Future

import numpy as np
import pyqtgraph as pg
from PySide6 import QtGui

from ..obs import get_logger
from . import glass, style

log = get_logger("ui")

WIDTH = 1.5                                             # px, as the slit's line
AHEAD = 2                                               # the next t's outlines computed after each step in t


def mask_colour(look) -> QtGui.QColor:
    """The outline's colour in look (look.Look): its accent, glass's in glass and the style's otherwise. The one
    place the mask's colour is decided."""
    return glass.accent() if look.has("glass") else style.accent()


class MaskOutlines:
    def __init__(self, session, mask, pool: Executor | None = None):
        """session: whose t the outline follows; mask: a data.mask.Mask on its main cube's grid; pool: where the
        outlines not kept are computed (None: at once, on the calling thread)."""
        self.session, self.mask, self.pool = session, mask, pool
        self.loop = session.store.loop
        self.items: list[pg.PlotCurveItem] = []
        self.colour = QtGui.QColor(style.accent())
        self.frame: int | None = None                   # the mask's frame drawn
        self.want: int | None = None                    # the mask's frame at the session's t
        self._wanted: frozenset[int] = frozenset()      # that frame and the ones ahead: the jobs worth running
        self._busy: set[int] = set()                    # frames being computed on pool
        self._closed = False
        self.visible = True                             # the outline on the images (set_visible)
        self._xy: tuple[np.ndarray, np.ndarray] = (np.empty(0), np.empty(0))
        self.show(session.state.t)
        self._off = session.store.subscribe(self._on_state)

    def attach(self, view) -> None:
        """Drawn on view (an ImageView) too, from now on."""
        item = pg.PlotCurveItem(connect="pairs", pen=pg.mkPen(self.colour, width=WIDTH), antialias=False)
        item.setData(*self._xy)
        item.setVisible(self.visible)
        view.vb.addItem(item, ignoreBounds=True)        # the view's range stays the image's
        self.items.append(item)

    def set_visible(self, on: bool) -> None:
        """The outline on every image (on), or on none: then no frame is wanted, so the jobs on their way skip theirs
        and the t steps read nothing until it is shown again, at the session's t. The outline of another frame, the
        one hidden, is never shown again: the images have none until the session's comes."""
        on = bool(on)
        if on == self.visible:
            return
        self.visible = on
        t = self.session.state.t
        if not on:
            self.want, self._wanted = None, frozenset()
        elif self.frame is not None and self.mask.frame_at(t) != self.frame:
            self.frame, self._xy = None, (np.empty(0), np.empty(0))
            for item in self.items:
                item.setData(*self._xy)
        for item in self.items:
            item.setVisible(on)
        if on:
            self.show(t)

    def _on_state(self, st, changed) -> None:
        if "t" in changed and self.visible:
            self.show(st.t)

    def show(self, t: int) -> None:
        """The outline of the mask's frame at the session's t on every image: at once when it is kept (or without a
        pool), else when its job brings it; then the next AHEAD t's computed. Nothing to do while that frame is the
        one drawn (a single frame: never again)."""
        k = self.mask.frame_at(t)
        self.want = k
        if self.pool is None:
            if k != self.frame:
                self._draw(k, self.mask.outline(t))
            return
        nt = len(self.mask.t)
        ahead = [(t + d) % nt for d in range(1, AHEAD + 1)] if self.mask.n > 1 else []
        self._wanted = frozenset([k, *(self.mask.frame_at(a) for a in ahead)])
        if k != self.frame:
            seg = self.mask.kept(t)
            if seg is not None:
                self._draw(k, seg)
            else:
                self._compute(t)
        for a in ahead:
            self._compute(a)

    def _compute(self, t: int) -> None:
        """The outline at t computed on the pool, unless it is drawn, kept, or on its way already."""
        k = self.mask.frame_at(t)
        if k == self.frame or k in self._busy or self.mask.kept(t) is not None:
            return
        self._busy.add(k)
        assert self.pool is not None
        fut = self.pool.submit(self._job, t, k)
        fut.add_done_callback(lambda f: None if self._closed else self.loop.post(lambda: self._arrived(k, f)))

    def _job(self, t: int, k: int) -> np.ndarray | None:
        """On the pool: the outline at t, or None when its frame k is no longer wanted (a newer t far from it)."""
        if self._closed or k not in self._wanted:
            return None
        return self.mask.outline(t)

    def _arrived(self, k: int, fut: Future) -> None:
        """On the UI thread: frame k's outline drawn if k is still the frame wanted."""
        self._busy.discard(k)
        if self._closed or fut.cancelled():
            return
        if fut.exception() is not None:
            log.warning("mask outline of frame %d not computed: %r", k, fut.exception())
            return
        seg = fut.result()
        if seg is not None and k == self.want and k != self.frame:
            self._draw(k, seg)

    def _draw(self, k: int, seg: np.ndarray) -> None:
        self.frame = k
        self._xy = (seg[:, :, 0].ravel(), seg[:, :, 1].ravel())
        for item in self.items:
            item.setData(*self._xy)

    def set_colour(self, c: QtGui.QColor) -> None:
        self.colour = QtGui.QColor(c)
        for item in self.items:
            item.setPen(pg.mkPen(self.colour, width=WIDTH))

    def close(self) -> None:
        self._closed = True
        if self._off is not None:
            self._off()
            self._off = None

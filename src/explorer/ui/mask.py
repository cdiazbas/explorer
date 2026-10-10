"""The mask's outline on every image (ROADMAP E8.2, `--mask file`): the main cube's, each linked cube's and the 2x2
view's four, at the mask's frame for the session's t (data.mask: its frame t, or its only one). The outline is
computed once per mask frame (Mask.outline keeps the last ones) and handed to one line item per image, drawn over
the image in data coordinates, so zoom and pan move it with the pixels. CRISPEX drew it on the main image and the
reference image (CRISPEX_DRAW_MASK_OVERLAYS, crispex.pro:7104; DRAW_MASK, 8069-8243).

    outlines = MaskOutlines(session, mask)
    outlines.attach(view)                       # an ImageView; drawn at once with the current t
    outlines.set_colour(mask_colour(look))
"""
import numpy as np
import pyqtgraph as pg
from PySide6 import QtGui

from . import glass, style

WIDTH = 1.5                                             # px, as the slit's line


def mask_colour(look) -> QtGui.QColor:
    """The outline's colour in look (look.Look): its accent, glass's in glass and the style's otherwise. The one
    place the mask's colour is decided."""
    return glass.accent() if look.has("glass") else style.accent()


class MaskOutlines:
    def __init__(self, session, mask):
        """session: whose t the outline follows; mask: a data.mask.Mask on its main cube's grid."""
        self.session, self.mask = session, mask
        self.items: list[pg.PlotCurveItem] = []
        self.colour = QtGui.QColor(style.accent())
        self.frame: int | None = None                   # the mask's frame drawn
        self._xy: tuple[np.ndarray, np.ndarray] = (np.empty(0), np.empty(0))
        self.show(session.state.t)
        self._off = session.store.subscribe(self._on_state)

    def attach(self, view) -> None:
        """Drawn on view (an ImageView) too, from now on."""
        item = pg.PlotCurveItem(connect="pairs", pen=pg.mkPen(self.colour, width=WIDTH), antialias=False)
        item.setData(*self._xy)
        view.vb.addItem(item, ignoreBounds=True)        # the view's range stays the image's
        self.items.append(item)

    def _on_state(self, st, changed) -> None:
        if "t" in changed:
            self.show(st.t)

    def show(self, t: int) -> None:
        """The outline of the mask's frame at the session's t on every image; nothing to do while that frame is the
        one drawn (a single frame: never again)."""
        k = self.mask.frame_at(t)
        if k == self.frame:
            return
        seg = self.mask.outline(t)
        self.frame = k
        self._xy = (seg[:, :, 0].ravel(), seg[:, :, 1].ravel())
        for item in self.items:
            item.setData(*self._xy)

    def set_colour(self, c: QtGui.QColor) -> None:
        self.colour = QtGui.QColor(c)
        for item in self.items:
            item.setPen(pg.mkPen(self.colour, width=WIDTH))

    def close(self) -> None:
        if self._off is not None:
            self._off()
            self._off = None

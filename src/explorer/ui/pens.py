"""The plots' line widths in logical pixels, on any screen.

pyqtgraph draws every line with a cosmetic pen, and a cosmetic pen's width is in device pixels: the device pixel ratio
is a transform, and cosmetic pens ignore transforms. On a Retina screen (ratio 2) every curve, marker, grid and axis
line, and the rings round the samples, drew half as thick as at ratio 1: width 1.5 lit 1 device column at ratio 2 and
2 at ratio 1 (a QImage at ratio 2, raster engine, offscreen and cocoa alike, Qt 6.11.2). The widgets' own pens
(ui.style, the title bar, the icons) are not cosmetic and scale already. Through the X11 bridge the ratio is 1: nothing
changes.

Every pen pyqtgraph makes goes through functions.mkPen, so that one function multiplies cosmetic widths by the ratio.
A pen made before the ratio is known (a module's constants) is registered with keep(). When the window moves to a
screen with another ratio, follow() walks its plots and scales the pens they hold. One ratio for the whole
application, the main window's screen's: a panel floated onto a monitor with another ratio keeps it.
From the prototype's app/pens.py.
"""
import pyqtgraph as pg
from pyqtgraph import functions as fn
from PySide6 import QtGui

RATIO = 1.0
_kept: list[QtGui.QPen] = []
_mk = fn.mkPen


def _mkPen(*args, **kw):
    pen = _mk(*args, **kw)
    # a QPen is copied as it is (already scaled when made); a dict comes back through this function
    if args and isinstance(args[0], QtGui.QPen | dict):
        return pen
    if RATIO != 1 and pen.isCosmetic() and pen.widthF() > 0:       # width 0: one device pixel, by intent
        pen.setWidthF(pen.widthF() * RATIO)
    return pen


fn.mkPen = pg.mkPen = _mkPen


def keep(*pens: QtGui.QPen) -> None:
    """Pens kept as module constants: scaled with every later change of ratio. Not scaled here: one made after the
    ratio was set came out of mkPen scaled already (on Retina, a lambda line of 8 device px for 4)."""
    _kept.extend(pens)


def _scaled(pen, f: float):
    if not isinstance(pen, QtGui.QPen):
        return fn.mkPen(pen)                            # a colour or a tuple: made again, at the new ratio
    pen = QtGui.QPen(pen)
    if pen.isCosmetic():
        pen.setWidthF(pen.widthF() * f)
    return pen


def _rescale_item(it, f: float) -> None:
    if isinstance(it.parentItem(), pg.PlotDataItem):    # its own pens, set through it: setData would undo the child's
        return
    if isinstance(it, pg.PlotDataItem):
        o = it.opts
        it.setPen(_scaled(o["pen"], f))
        if o.get("shadowPen") is not None:
            it.setShadowPen(_scaled(o["shadowPen"], f))
        if o.get("symbolPen") is not None:
            it.setSymbolPen(_scaled(o["symbolPen"], f))
    elif isinstance(it, pg.PlotCurveItem):
        it.setPen(_scaled(it.opts["pen"], f))
        if it.opts.get("shadowPen") is not None:
            it.setShadowPen(_scaled(it.opts["shadowPen"], f))
    elif isinstance(it, pg.ScatterPlotItem):
        it.setPen(_scaled(it.opts["pen"], f))
    elif isinstance(it, pg.InfiniteLine):
        hover = _scaled(it.hoverPen, f)
        it.setPen(_scaled(it.pen, f))
        it.setHoverPen(hover)
    elif isinstance(it, pg.AxisItem):
        # no pen of its own: pen() makes the default at each paint, at the ratio of the moment
        if it._pen is not None:
            it.setPen(_scaled(it._pen, f))
        if it._tickPen is not None:
            it.setTickPen(_scaled(it._tickPen, f))


def set_ratio(ratio: float, *roots) -> None:
    """The ratio from now on; the pens already in the plots under each root widget scaled to it."""
    global RATIO
    ratio = float(ratio or 1.0)
    f = ratio / RATIO
    if f == 1:
        return
    RATIO = ratio
    for p in _kept:
        if p.isCosmetic():
            p.setWidthF(p.widthF() * f)
    seen: set[int] = set()
    for root in roots:
        views = root.findChildren(pg.GraphicsView)
        if isinstance(root, pg.GraphicsView):
            views.append(root)
        for view in views:
            sc = view.scene()
            if sc is None or id(sc) in seen:
                continue
            seen.add(id(sc))
            for it in sc.items():
                _rescale_item(it, f)


def follow(window) -> None:
    """The window's screen's ratio now, and whenever the window moves to another screen."""
    wh = window.windowHandle()
    if wh is None:
        return
    set_ratio(wh.screen().devicePixelRatio() if wh.screen() else 1.0, window)
    wh.screenChanged.connect(lambda scr: set_ratio(scr.devicePixelRatio() if scr else 1.0, window))

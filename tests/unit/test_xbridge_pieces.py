"""The bridge splits what a window repainted into pieces, in the order Qt painted them (bridge._pieces): each piece
without what an earlier one has, and what came without a Paint event last."""
from PySide6 import QtCore, QtGui

from explorer.platform.xbridge.bridge import _pieces


def R(x, y, w, h):
    return QtGui.QRegion(QtCore.QRect(x, y, w, h))


def test_pieces_in_paint_order_without_overlap_and_the_rest_last():
    image, key, panel = R(0, 0, 800, 600), R(10, 500, 300, 100), R(800, 0, 400, 300)
    moved = R(0, 700, 50, 50)                           # a child moved: dirty without a Paint event
    dirty = image + key + panel + moved
    out = _pieces(dirty, [image, key, panel])
    assert [p.boundingRect() for p in out] == [image.boundingRect(), panel.boundingRect(), moved.boundingRect()]


def test_a_piece_outside_the_window_is_left_out():
    dirty = R(0, 0, 100, 100)
    out = _pieces(dirty, [R(200, 200, 10, 10), R(0, 0, 50, 50)])
    assert [p.boundingRect() for p in out] == [QtCore.QRect(0, 0, 50, 50), QtCore.QRect(0, 0, 100, 100)]
    assert out[1].subtracted(R(0, 0, 50, 50)) == out[1]

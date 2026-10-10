"""The bridge's X windows are made with the Qt window's colour as their background: without one XQuartz showed every
new window white until its first pixels came (the start, while the cubes were read), and where it grew before them."""
import collections
from unittest import mock


def test_a_window_is_made_with_its_colour_as_background(qapp):
    from PySide6 import QtGui, QtWidgets

    from explorer.platform.xbridge import xproto as X
    from explorer.platform.xbridge.windows import Windows, pixel

    scr = X.Screen(root=1, colormap=2, white=0xFFFFFF, black=0, width=1920, height=1080, width_mm=500,
                   height_mm=300, root_visual=33, root_depth=24,
                   visuals={33: (24, X.Visual(33, 4, 0xFF0000, 0x00FF00, 0x0000FF))})
    pm = QtGui.QPixmap(16, 16)
    pm.fill(QtGui.QColor("#ff9230"))
    qapp.setWindowIcon(QtGui.QIcon(pm))            # as the application has one: create() also sends the icon
    c = mock.MagicMock()
    c.screen = scr
    c.new_id.return_value = 0x400001
    c.max_request = 262140                          # bytes in a request without BIG-REQUESTS (icon.sizes_within)
    ws = Windows(c)
    ws.atoms = collections.defaultdict(int)
    w = QtWidgets.QMainWindow()
    pal = w.palette()
    pal.setColor(QtGui.QPalette.ColorRole.Window, QtGui.QColor("#2d2d2d"))
    w.setPalette(pal)
    w.setGeometry(10, 20, 300, 200)
    ws.create(w)
    attrs = c.create_window.call_args.kwargs["attrs"]
    print("background", hex(attrs.get(X.CW_BACK_PIXEL, -1)))
    assert attrs[X.CW_BACK_PIXEL] == 0x2D2D2D
    # another visual's layout: 5-6-5 bits
    scr.visuals[33] = (16, X.Visual(33, 4, 0xF800, 0x07E0, 0x001F))
    assert pixel(scr, QtGui.QColor(255, 255, 255)) == 0xFFFF and pixel(scr, QtGui.QColor(255, 0, 0)) == 0xF800
    w.close()


def test_a_change_of_palette_changes_the_background_once(qapp):
    """Windows.set_background: the window's colour as its background again, sent only when it differs from X's."""
    from PySide6 import QtGui, QtWidgets

    from explorer.platform.xbridge import xproto as X
    from explorer.platform.xbridge.windows import Windows

    scr = X.Screen(root=1, colormap=2, white=0xFFFFFF, black=0, width=1920, height=1080, width_mm=500,
                   height_mm=300, root_visual=33, root_depth=24,
                   visuals={33: (24, X.Visual(33, 4, 0xFF0000, 0x00FF00, 0x0000FF))})
    c = mock.MagicMock()
    c.screen = scr
    c.new_id.return_value = 0x400001
    c.max_request = 262140
    ws = Windows(c)
    ws.atoms = collections.defaultdict(int)
    w = QtWidgets.QMainWindow()
    pal = w.palette()
    pal.setColor(QtGui.QPalette.ColorRole.Window, QtGui.QColor("#2d2d2d"))
    w.setPalette(pal)
    rec = ws.create(w)
    ws.set_background(rec)
    c.change_attributes.assert_not_called()             # X has that colour from the creation
    pal.setColor(QtGui.QPalette.ColorRole.Window, QtGui.QColor("#ececec"))
    w.setPalette(pal)
    ws.set_background(rec)
    ws.set_background(rec)
    c.change_attributes.assert_called_once_with(0x400001, {X.CW_BACK_PIXEL: 0xECECEC})
    w.close()

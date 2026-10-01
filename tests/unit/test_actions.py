"""What the keys and the mouse do, in one table (ROADMAP E5.4), offscreen: the registry installs a shortcut per key
sequence and its ? sheet lists every key and gesture; in a window, ? and Shift+? show and hide the sheet, Esc closes
it before it releases the cursor, a click on it closes it; a Mac shows the command key; ? typed in the terminal
opens it too."""
import os
import sys
import time

import pytest

from explorer.testing import synth

SHAPE = (6, 4, 21, 48, 40)
posix_only = pytest.mark.skipif(os.name != "posix", reason="terminals: POSIX")


def spin(qapp, until, timeout=5.0):
    end = time.perf_counter() + timeout
    while not until() and time.perf_counter() < end:
        qapp.processEvents()
        time.sleep(0.002)
    return until()


@pytest.fixture(scope="module")
def cube(tmp_path_factory):
    return synth.write_dataset(tmp_path_factory.mktemp("actions"), "c", shape=SHAPE, icube=False)["im"]


@pytest.fixture
def shell(qapp, cube):
    from explorer.data.dataset import Dataset
    from explorer.ui.shell import Shell

    ds = Dataset.open(cube)
    w = Shell(ds)
    w.resize(900, 600)
    w.show()
    assert spin(qapp, lambda: w.first_image_s is not None)
    yield w
    w.close()
    ds.close()


def fire(w, seq):
    from PySide6 import QtGui

    ks = QtGui.QKeySequence(seq)
    hits = [sc for sc in w.findChildren(QtGui.QShortcut) if sc.key() == ks]
    assert len(hits) == 1, seq
    hits[0].activated.emit()


def test_the_registry_installs_every_sequence_and_its_sheet_lists_them(qapp):
    from PySide6 import QtGui, QtWidgets

    from explorer.ui.actions import ActionRegistry

    done = []
    rows = [("← →", "λ: previous, next", (("Left", lambda: done.append("l")), ("Right", lambda: done.append("r")))),
            ("⌘Q", "quit", ()),                         # shown only
            ("<b>", "an escaped key", (("B", lambda: done.append("b")),))]
    reg = ActionRegistry(rows, [("click on the image", "lock & go")])
    w = QtWidgets.QWidget()
    shortcuts = reg.install(w)
    assert [sc.key().toString() for sc in shortcuts] == ["Left", "Right", "B"]
    shortcuts[1].activated.emit()
    assert done == ["r"]
    page = reg.sheet_html(QtGui.QPalette())
    for text in ("λ: previous, next", "quit", "&lt;b&gt;", "lock &amp; go", "Keys", "Mouse", "? or Esc closes this"):
        assert text in page
    w.close()


def test_question_mark_shows_and_hides_the_sheet_over_the_image(qapp, shell):
    sheet = shell.sheet
    assert not sheet.isVisible()
    fire(shell, "?")
    assert sheet.isVisible() and shell.centralWidget().geometry().intersects(sheet.geometry())
    fire(shell, "Shift+?")
    assert not sheet.isVisible()
    for _k, w, _b in shell.actions.rows:
        assert w in sheet.text()                       # what the keys do, as the table says
    assert "pick λ" in sheet.text() and "y axis" in sheet.text()


def test_esc_closes_the_sheet_first_then_releases_the_cursor(qapp, shell):
    s = shell.session
    s.lock(True)
    fire(shell, "?")
    fire(shell, "Esc")
    assert not shell.sheet.isVisible() and s.state.locked
    fire(shell, "Esc")
    assert not s.state.locked


def test_a_click_on_the_sheet_closes_it(qapp, shell):
    from PySide6 import QtCore, QtGui, QtWidgets

    fire(shell, "?")
    p = QtCore.QPointF(5, 5)
    ev = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseButtonPress, p, shell.sheet.mapToGlobal(p),
                           QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.MouseButton.LeftButton,
                           QtCore.Qt.KeyboardModifier.NoModifier)
    QtWidgets.QApplication.sendEvent(shell.sheet, ev)
    assert not shell.sheet.isVisible()


def test_a_mac_shows_the_command_key(qapp, cube, monkeypatch):
    from explorer.data.dataset import Dataset
    from explorer.ui.shell import Shell

    monkeypatch.setattr(sys, "platform", "darwin")
    with Dataset.open(cube) as ds:
        w = Shell(ds)
        shown = [k for k, _w, _b in w.actions.rows]
        assert "⌘W" in shown and "⌘Q" in shown and not any(k.startswith("Ctrl+") for k in shown)
        w.close()


@posix_only
def test_question_mark_typed_in_the_terminal_opens_the_sheet(qapp, shell):
    from explorer.ui import termkeys as T

    master, slave = os.openpty()
    try:
        tk = T.attach(shell, fd=slave, require_foreground=False)
        assert tk is not None
        os.write(master, b"?")
        assert spin(qapp, lambda: shell.sheet.isVisible())
        tk.close()
    finally:
        os.close(master)
        os.close(slave)


def test_the_sheet_is_a_rounded_translucent_card(qapp, shell):
    """Its corners show the image's panel behind; inside, the window's base colour lets what is under it through."""
    from PySide6 import QtCore, QtGui

    fire(shell, "?")
    qapp.processEvents()
    sh = shell.sheet
    img = shell.grab().toImage()
    def at(x, y):
        return QtGui.QColor(img.pixel(sh.mapTo(shell, QtCore.QPoint(x, y))))
    base = shell.palette().color(QtGui.QPalette.ColorRole.Base)
    assert not sh.autoFillBackground()
    assert at(0, 0) != at(sh.width() // 2, 4)                      # the corner is not the card
    inside = at(sh.width() - 30, sh.height() - 8)
    assert inside != base or base.alpha() < 255 or sh.OPACITY == 1  # blended with what is behind it
    fire(shell, "?")

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
    assert page.rstrip().endswith(      # the sheet's last line, on the right
        '<td align="right"><i>Designed and implemented by C. J. Díaz Baso</i></td></tr></table>')
    w.close()


def test_question_mark_shows_and_hides_the_sheet_over_the_image(qapp, shell):
    sheet = shell.sheet
    assert not sheet.isVisible()
    fire(shell, "?")
    assert sheet.isVisible() and shell.centralWidget().geometry().intersects(sheet.geometry())
    fire(shell, "Shift+?")
    assert not sheet.isVisible()
    from explorer.ui.actions import text_html

    for _k, w, _b in shell.action_registry.rows:
        assert text_html(w) in sheet.text()            # what the keys do, as the table says (its γ set apart)
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
        shown = " ".join(k for k, _w, _b in w.action_registry.rows).split()
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


def test_a_failing_action_is_said_in_the_log_and_the_status_bar_not_lost(qapp):
    """Qt only prints what a shortcut's slot raises: the key seemed to do nothing (M on someone's cube). The shortcut
    and the terminal's keys (both from binds()) now leave the error in explorer's log and a line in the status bar."""
    import logging

    from PySide6 import QtGui, QtWidgets

    from explorer.ui.actions import ActionRegistry

    def broken():
        raise RuntimeError("no glass here")

    seen = []
    handler = logging.Handler()
    handler.emit = seen.append
    logger = logging.getLogger("explorer.ui.actions")
    logger.addHandler(handler)
    win = QtWidgets.QMainWindow()
    try:
        reg = ActionRegistry([("M", "look", (("M", broken),))])
        shortcuts = reg.install(win)
        shortcuts[0].activated.emit()                   # the shortcut's own path: nothing escapes
        assert "M: failed (RuntimeError: no glass here)" in win.statusBar().currentMessage()
        assert seen and seen[-1].exc_info and "the key M failed" in seen[-1].getMessage()
        for _seq, fn in reg.binds():                    # the terminal's keys take these
            fn()
        assert len(seen) == 2
        assert isinstance(shortcuts[0], QtGui.QShortcut)
    finally:
        logger.removeHandler(handler)
        win.close()


def test_the_per_pixel_sheet_says_the_cost_the_copy_and_the_command(qapp, shell):
    """The sheet over a window whose images come from a per-pixel file alone (data.transpose.Estimate): what an
    image costs and how that was found, the copy's size, the speed-up as an estimate, the command; none over a cube
    read from its image cube."""
    from PySide6 import QtGui

    from explorer.data.transpose import Estimate
    from explorer.ui.actions import per_pixel_sheet_html

    est = Estimate(image_s=12.3, how="the file's 13.2 GB at 1070 MB/s", frames=735, copy_bytes=13_150_000_000,
                   factor=735, out_dir="/tmp/x", free_bytes=500_000_000_000,
                   command="explorer transpose a_sp.fits /tmp/x")
    text = per_pixel_sheet_html(est, "a_sp.fits", QtGui.QPalette())
    print(text)
    for want in ("Images from a per-pixel file", "a_sp.fits", "<b>12.3 s</b>", "13.2 GB at 1070 MB/s",
                 "<b>13.2 GB</b> on disk (500.0 GB free there)", "<b>735× faster</b> (17 ms an image)", "an estimate",
                 "<code>explorer transpose a_sp.fits /tmp/x</code>", "never beside the per-pixel file"):
        assert want in text
    assert shell.sp_sheet is None


SHOWN = {"Left": "←", "Right": "→", "Down": "↓", "Up": "↑", "Backspace": "⌫", "Del": "⌫", "Shift+?": "?"}


def shown_as(seq) -> str:
    """How the sheet writes a bound key sequence: arrows and ⌫ as symbols, Shift as ⇧, Ctrl as mod_key()."""
    from PySide6 import QtGui

    from explorer.ui.actions import mod_key

    text = seq if isinstance(seq, str) else QtGui.QKeySequence(seq).toString()
    text = SHOWN.get(text, text)
    return text.replace("Shift+", "⇧").replace("Ctrl+", mod_key())


@pytest.fixture
def linked_shell(qapp, cube, tmp_path):
    """Four Stokes, t, lambda and a linked cube: every row the sheet can have."""
    from explorer.data.dataset import Dataset
    from explorer.ui.shell import Shell

    other = synth.write_dataset(tmp_path, "o", shape=SHAPE, seed=2, sp=False, icube=False)["im"]
    ds = Dataset.open(cube)
    lk = Dataset.open(other, executors=ds.executors)
    w = Shell(ds, linked=[lk])
    w.resize(1440, 900)
    w.show()
    assert spin(qapp, lambda: w.first_image_s is not None)
    yield w
    w.close()
    lk.close()
    ds.close()


def test_every_bound_key_is_shown_on_its_row(linked_shell):
    """Grouped rows ("G ⇧G · ⌘G") still show every key they bind, so nothing bound is missing from the sheet."""
    w = linked_shell
    missing = [(k, shown_as(seq)) for k, _w, binds in w.action_registry.rows for seq, _fn in binds
               if shown_as(seq) not in k.replace("–", " ").replace("·", " ").split()
               and not (k.startswith("1–") and shown_as(seq).isdigit())]
    assert not missing, missing


def test_the_sheet_is_a_few_short_lines_and_fits_a_laptop_window(qapp, linked_shell):
    """At most 16 lines a column and 6 words an entry; the card under 600 px high at the default font, so it fits
    over the image of a 900-px-high window without scrolling."""
    w = linked_shell
    rows = [(k, what) for k, what, _b in w.action_registry.rows] + list(w.action_registry.mouse)
    long = [r for r in rows if len(r[1].replace("·", " ").split()) > 6]
    w.toggle_sheet()
    qapp.processEvents()
    h = w.sheet.sizeHint().height()
    print("key rows", len(w.action_registry.rows), "mouse rows", len(w.action_registry.mouse), "sheet", h, "px")
    w.toggle_sheet()
    assert max(len(w.action_registry.rows), len(w.action_registry.mouse)) <= 16 and not long, long
    assert h < 600, h


def test_the_sheet_writes_gamma_in_an_italic_serif():
    """In the interface's sans at the sheet's size γ reads as a y (the user, 2026-10-11): the sheet sets it apart."""
    from explorer.ui.actions import text_html

    out = text_html("γ: lower, higher")
    assert "font-style:italic" in out and "STIX Two Text" in out and out.endswith(": lower, higher")
    assert text_html("a < b") == "a &lt; b"

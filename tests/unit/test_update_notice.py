"""What the window does with the update check's answer (Shell.start_update_check, update_check.about stood in for):
a newer version said for the first time puts a note over the foot of the image, above the colour key, fading at
its end, and the ? sheet's last line says the version and the command; the same version, or one said before, no
note. The answer comes from the check's thread to the window through a queued signal."""
import threading
import time

import pytest

from explorer.testing import synth
from explorer.update_check import Found

SHAPE = (6, 4, 21, 48, 40)
LINE = "explorer 0.0.1.dev527 · 2026-10-17"
NEWER = Found(newer=True, announce=True, remote="b" * 40, local="a" * 40)
SAID = Found(newer=True, announce=False, remote="b" * 40, local="a" * 40)
SAME = Found(newer=False, announce=False, remote="a" * 40, local="a" * 40)


def spin(qapp, until, timeout=5.0):
    end = time.perf_counter() + timeout
    while not until() and time.perf_counter() < end:
        qapp.processEvents()
        time.sleep(0.002)
    return until()


@pytest.fixture(scope="module")
def cube(tmp_path_factory):
    return synth.write_dataset(tmp_path_factory.mktemp("notice"), "c", shape=SHAPE, icube=False)["im"]


@pytest.fixture
def shell(qapp, cube, monkeypatch):
    from explorer.data.dataset import Dataset
    from explorer.ui import shell as S

    monkeypatch.setattr(S, "UPDATE_AFTER_S", 0.0)
    ds = Dataset.open(cube)
    w = S.Shell(ds)
    w.resize(900, 600)
    w.show()
    assert spin(qapp, lambda: w.first_image_s is not None)
    yield w
    w.close()
    ds.close()


def answered(qapp, w, found):
    """start_update_check with found as the check's answer; the thread it ran on."""
    threads = []

    def about():
        threads.append(threading.current_thread())
        return LINE, found
    w.start_update_check(about)
    assert spin(qapp, lambda: w.version_line == LINE)
    return threads[0]


def test_a_newer_version_is_said_once_over_the_image_and_on_the_sheet(qapp, shell):
    from explorer.ui import shell as S

    ran_on = answered(qapp, shell, NEWER)
    assert ran_on is not threading.main_thread()
    note = shell._update_note
    assert note is not None and note.isVisible() and note.text() == S.UPDATE_NOTE
    assert "explorer update" in note.text() and note.parentWidget() is shell.view.widget
    key, host = shell.colour_key.geometry(), shell.view.widget.rect()
    assert host.contains(note.geometry()) and note.geometry().bottom() < key.top()      # above the colour key
    assert note._fade_ms == S.UPDATE_FADE_MS and note._timer.interval() == S.UPDATE_NOTE_MS - S.UPDATE_FADE_MS
    text = shell.sheet.text()
    assert LINE in text and "newer version available: <b>explorer update</b>" in text
    note.hide()
    shell.show_about((LINE, SAID))                              # the next start: said before, no note
    assert not note.isVisible() and "newer version available" in shell.sheet.text()


def test_the_same_version_says_its_line_and_no_note(qapp, shell):
    answered(qapp, shell, SAME)
    assert shell._update_note is None
    assert LINE in shell.sheet.text() and "newer" not in shell.sheet.text()


def test_no_answer_leaves_the_sheet_without_the_line(qapp, shell):
    answered(qapp, shell, None)                                 # not a clone, turned off, or the remote failed
    assert shell._update_note is None and "newer" not in shell.sheet.text()


def test_through_the_bridge_the_note_goes_at_once(qapp, shell):
    shell.session.pace.offer = object()                         # a screen offered: the X11 bridge
    shell.show_about((LINE, NEWER))
    assert shell._update_note.isVisible() and shell._update_note._fade_ms == 0

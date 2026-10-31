"""Keys from the terminal that started explorer (ROADMAP E6.2): the sequences terminals send, cut into keys and
decoded to Qt's combinations; and, over a pseudo-terminal, keys that move the window's cube and a terminal that
comes back as it was."""
import os
import sys
import time

import pytest

from explorer.testing import synth
from explorer.ui import termkeys as T

SHAPE = (3, 4, 5, 48, 40)
posix_only = pytest.mark.skipif(sys.platform == "win32", reason="terminals through termios")


def spin(qapp, until, timeout=10.0):
    end = time.perf_counter() + timeout
    while not until() and time.perf_counter() < end:
        qapp.processEvents()
        time.sleep(0.002)
    return until()


def test_what_terminals_send_decodes_to_the_window_keys():
    from PySide6 import QtCore

    K, M = QtCore.Qt.Key, QtCore.Qt.KeyboardModifier
    ctrl = M.MetaModifier if sys.platform == "darwin" else M.ControlModifier     # the window's Ctrl (Qt on macOS)
    cases = {
        b"\x1b[A": (K.Key_Up, M.NoModifier), b"\x1b[B": (K.Key_Down, M.NoModifier),
        b"\x1b[C": (K.Key_Right, M.NoModifier), b"\x1b[D": (K.Key_Left, M.NoModifier),
        b"\x1bOA": (K.Key_Up, M.NoModifier),                                  # application cursor mode (SS3)
        b"\x1b[1;2A": (K.Key_Up, M.ShiftModifier), b"\x1b[1;5D": (K.Key_Left, ctrl),
        b"\x1b[1;3C": (K.Key_Right, M.AltModifier), b"\x1b[5~": (K.Key_PageUp, M.NoModifier),
        b"\x1b[6;5~": (K.Key_PageDown, ctrl), b"\x1b[H": (K.Key_Home, M.NoModifier),
        b"\x1b": (K.Key_Escape, M.NoModifier), b"\r": (K.Key_Return, M.NoModifier),
        b"\t": (K.Key_Tab, M.NoModifier), b"\x7f": (K.Key_Backspace, M.NoModifier),
        b"l": (K.Key_L, M.NoModifier), b"L": (K.Key_L, M.ShiftModifier), b"2": (K.Key_2, M.NoModifier),
        b"\x17": (K.Key_W, ctrl), b"\x1bx": (K.Key_X, M.AltModifier),
        "ñ".encode(): (K.Key_Ntilde, M.NoModifier),
    }
    for seq, want in cases.items():
        assert T.decode(seq) == want, seq
    assert T.decode(b"\x1b[Z") is None                                        # a key explorer does not bind


def test_the_stream_cuts_keys_across_reads_and_waits_for_a_lone_escape():
    ks = T.KeyStream()
    assert ks.feed(b"\x1b[1;") == [] and ks.pending()                          # a sequence split between reads
    assert ks.feed(b"5Aab") == [b"\x1b[1;5A", b"a", b"b"] and not ks.pending()
    assert ks.feed(b"\x1b") == [] and ks.pending()                            # Escape, or the start of a sequence?
    assert ks.flush() == [b"\x1b"] and not ks.pending()                       # nothing followed: Escape
    assert ks.feed(b"\x1b\x1b[C") == [b"\x1b", b"\x1b[C"]
    assert ks.feed("λx".encode()) == ["λ".encode(), b"x"]                      # UTF-8, whole characters


@pytest.fixture(scope="module")
def cube(tmp_path_factory):
    return synth.write_dataset(tmp_path_factory.mktemp("termkeys"), "c", shape=SHAPE, icube=False)["im"]


@pytest.fixture
def shell(qapp, cube):
    from explorer.data.dataset import Dataset
    from explorer.ui.shell import Shell

    ds = Dataset.open(cube)
    w = Shell(ds)
    w.resize(640, 480)
    w.show()
    assert spin(qapp, lambda: w.first_image_s is not None)
    yield w
    w.close()
    ds.close()


@posix_only
def test_keys_typed_in_the_terminal_move_the_cube_and_the_terminal_comes_back(qapp, shell):
    import termios

    master, slave = os.openpty()
    try:
        before = termios.tcgetattr(slave)
        tk = T.attach(shell, fd=slave, require_foreground=False)
        assert tk is not None
        assert not termios.tcgetattr(slave)[3] & termios.ICANON                # cbreak: key by key
        s = shell.session
        t0, l0 = s.state.t, s.state.l
        os.write(master, b"\x1b[A")                                            # Up: next t
        assert spin(qapp, lambda: s.state.t == t0 + 1)
        os.write(master, b"\x1b[C\x1b[C")                                      # Right twice, in one read
        assert spin(qapp, lambda: s.state.l == l0 + 2)
        os.write(master, b"2")                                                 # Stokes Q
        assert spin(qapp, lambda: s.state.s == 1)
        os.write(master, b"L")                                                 # Shift+L: not the lock (as the window)
        os.write(master, b"l")
        assert spin(qapp, lambda: s.state.locked)
        os.write(master, b"\x1b")                                              # a lone Escape: released after 50 ms
        assert spin(qapp, lambda: not s.state.locked)
        assert tk.stats["keys"] == 7 and tk.stats["bound"] == 6
        tk.close()
        after = termios.tcgetattr(slave)
        pendin = getattr(termios, "PENDIN", 0)                                # set by the kernel itself on the way
        after[3] &= ~pendin                                                    # back to canonical mode (macOS)
        before[3] &= ~pendin
        assert after == before                                                 # the terminal as it was
    finally:
        os.close(master)
        os.close(slave)


def test_not_a_terminal_or_turned_off_does_nothing(qapp, shell, monkeypatch):
    r, w = os.pipe()
    try:
        assert T.attach(shell, fd=r) is None                                   # a pipe: nothing to read keys from
    finally:
        os.close(r)
        os.close(w)
    monkeypatch.setenv(T.ENV, "0")
    assert T.attach(shell) is None



@posix_only
def test_the_terminal_s_output_stays_blocking_while_its_keys_are_read(qapp):
    """O_NONBLOCK belongs to the open file, not to the descriptor: in a terminal 0, 1 and 2 are one open file, so
    setting it on standard input made standard output and errors non-blocking too: a line to a full terminal
    (Ctrl+S) raised BlockingIOError and was lost, and after a crash the shell's next programs wrote into a
    non-blocking terminal ("Resource temporarily unavailable")."""
    master, slave = os.openpty()
    out = os.dup(slave)                                 # standard output: the same open file
    try:
        tk = T.TerminalKeys(slave, {})
        try:
            assert os.get_blocking(out) and os.get_blocking(slave)
        finally:
            tk.close()
    finally:
        for fd in (master, slave, out):
            os.close(fd)


@posix_only
def test_in_the_background_the_terminal_is_not_read(qapp, monkeypatch):
    """Sent to the background (Ctrl+Z, bg), a process that reads its terminal is stopped (SIGTTIN): explorer froze
    at the next key typed in the shell. In the background the keys are the shell's; read again once in front."""
    master, slave = os.openpty()
    reads: list[int] = []
    orig_read = os.read
    monkeypatch.setattr(T.os, "read", lambda fd, n: reads.append(fd) or orig_read(fd, n))
    try:
        tk = T.TerminalKeys(slave, {})
        try:
            monkeypatch.setattr(T.os, "tcgetpgrp", lambda fd: os.getpgrp() + 1)     # another group in front
            os.write(master, b"x")
            spin(qapp, lambda: False, 0.3)
            assert slave not in reads
            monkeypatch.setattr(T.os, "tcgetpgrp", lambda fd: os.getpgrp())         # in front again (fg)
            assert spin(qapp, lambda: slave in reads, 3.0)
        finally:
            tk.close()
    finally:
        os.close(master)
        os.close(slave)


@posix_only
@pytest.mark.parametrize("sig", ["SIGTERM", "SIGHUP"])
def test_a_terminating_signal_gives_the_terminal_back(sig):
    """The terminal was given back at exit (atexit) only: SIGTERM or SIGHUP (the ssh session gone) left it in
    cbreak mode, no echo and no line editing for the shell after."""
    import pty
    import signal
    import termios

    job = (
        "import os, sys, time\n"
        "os.environ['QT_QPA_PLATFORM'] = 'offscreen'\n"
        "from PySide6 import QtCore, QtWidgets\n"
        "from explorer.ui.termkeys import TerminalKeys\n"
        "app = QtWidgets.QApplication([])\n"
        "tk = TerminalKeys(0, {})\n"
        "print('ready', flush=True)\n"
        "QtCore.QTimer.singleShot(20000, app.quit)\n"
        "tick = QtCore.QTimer(); tick.timeout.connect(lambda: None); tick.start(100)\n"
        "app.exec()\n"
    )
    pid, master = pty.fork()
    if pid == 0:
        os.execv(sys.executable, [sys.executable, "-c", job])
    try:
        got = b""
        end = time.time() + 30
        while b"ready" not in got and time.time() < end:
            got += os.read(master, 4096)
        assert b"ready" in got, got
        assert not termios.tcgetattr(master)[3] & termios.ICANON              # cbreak while it reads
        os.kill(pid, getattr(signal, sig))
        _, st = os.waitpid(pid, 0)
        lflag = termios.tcgetattr(master)[3]
        assert lflag & termios.ICANON and lflag & termios.ECHO, "left in cbreak mode"
    finally:
        try:
            os.kill(pid, signal.SIGKILL)
            os.waitpid(pid, 0)
        except (ProcessLookupError, ChildProcessError):
            pass
        os.close(master)


def test_ctrl_from_a_mac_terminal_is_the_window_s_ctrl(monkeypatch):
    """On macOS Qt's ControlModifier is the Command key: the terminal's Ctrl+W (readline's delete-word habit) became
    Cmd+W and closed the window, where the window's own Ctrl+W (MetaModifier there) does nothing."""
    from PySide6 import QtCore

    monkeypatch.setattr(T.sys, "platform", "darwin")
    key, mods = T.decode(b"\x17")
    assert key == QtCore.Qt.Key.Key_W and mods == QtCore.Qt.KeyboardModifier.MetaModifier
    monkeypatch.setattr(T.sys, "platform", "linux")
    key, mods = T.decode(b"\x17")
    assert mods == QtCore.Qt.KeyboardModifier.ControlModifier

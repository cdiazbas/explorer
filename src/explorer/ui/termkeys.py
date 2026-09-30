"""Keys typed in the terminal that started explorer act as if typed in its window (ROADMAP E6.2).

Over ssh -Y the keyboard reaches the terminal, not the window, until the window is clicked: on macOS keys go to the
application in front, and nothing on the remote side can bring XQuartz there (Apple-WM refuses clients behind ssh;
journal 2026-09-30). The terminal forwards its keys over ssh to explorer's standard input, so they are read there
too. When standard input is a terminal and explorer runs in its foreground, the terminal goes to cbreak mode (key by
key, no echo; Ctrl+C and output as usual; restored at exit) and each key runs the action the window binds to it
(Shell.key_table). Once the window has the keyboard the terminal gets nothing, so no key acts twice.

    decode(seq)            a key's bytes (xterm sequences, which Terminal.app, iTerm2, GNOME Terminal, Konsole and
                           Windows Terminal send) to Qt's key combination, or None
    KeyStream              bytes in, whole keys out (a sequence split between reads, a lone Escape)
    attach(shell)          starts it, or None where it does not apply

EXPLORER_TERMINAL_KEYS=0 turns it off.
"""
import atexit
import os
import sys

from PySide6 import QtCore, QtGui

from .._name import APP_NAME
from ..obs import get_logger

log = get_logger("ui")

ENV = f"{APP_NAME.upper()}_TERMINAL_KEYS"
ESC = 0x1B
LONE_ESC_MS = 50                                        # the bytes of a sequence arrive together; Escape alone waits

K, M = QtCore.Qt.Key, QtCore.Qt.KeyboardModifier
FINAL = {"A": K.Key_Up, "B": K.Key_Down, "C": K.Key_Right, "D": K.Key_Left, "H": K.Key_Home, "F": K.Key_End}
TILDE = {"1": K.Key_Home, "2": K.Key_Insert, "3": K.Key_Delete, "4": K.Key_End, "5": K.Key_PageUp,
         "6": K.Key_PageDown, "7": K.Key_Home, "8": K.Key_End}
CONTROL = {0x09: K.Key_Tab, 0x0A: K.Key_Return, 0x0D: K.Key_Return, 0x08: K.Key_Backspace, 0x7F: K.Key_Backspace,
           ESC: K.Key_Escape}


def _mods(param: str) -> M:
    """xterm's modifier parameter: 1 + Shift 1, Alt 2, Ctrl 4, Meta 8."""
    try:
        bits = int(param) - 1
    except ValueError:
        return M.NoModifier
    m = M.NoModifier
    for bit, mod in ((1, M.ShiftModifier), (2, M.AltModifier), (4, M.ControlModifier), (8, M.MetaModifier)):
        if bits & bit:
            m |= mod
    return m


def _char(c: str) -> tuple[K, M] | None:
    code = ord(c)
    if code in CONTROL:
        return CONTROL[code], M.NoModifier
    if 1 <= code <= 26:                                 # Ctrl+A .. Ctrl+Z
        return K(K.Key_A.value + code - 1), M.ControlModifier
    if code < 32:
        return None
    shift = c.isalpha() and c != c.lower()             # an upper-case letter: Shift, as in the window
    try:
        return K(ord(c.upper())), M.ShiftModifier if shift else M.NoModifier
    except ValueError:                                  # a character Qt has no key for
        return None


def decode(seq: bytes) -> tuple[K, M] | None:
    """One key's bytes (as KeyStream cuts them) to (key, modifiers); None for what explorer has no key for."""
    s = seq.decode("utf-8", errors="replace")
    if not s:
        return None
    if s[0] != "\x1b" or len(s) == 1:
        return _char(s) if len(s) == 1 else None
    if s[1] in "[O" and len(s) >= 3:                    # CSI (ESC [) or SS3 (ESC O)
        params, final = s[2:-1].split(";"), s[-1]
        mods = _mods(params[1]) if len(params) > 1 else M.NoModifier
        if final in FINAL:
            return FINAL[final], mods
        if final == "~" and params[0] in TILDE:
            return TILDE[params[0]], mods
        return None
    got = _char(s[1:]) if len(s) == 2 else None         # ESC then a key: Alt with that key
    return (got[0], got[1] | M.AltModifier) if got is not None else None


class KeyStream:
    """Cuts the bytes a terminal sends into keys: one character (UTF-8), a CSI sequence up to its final byte, SS3 and
    its letter, or Escape followed by a key (Alt). An Escape with nothing after it stays pending until flush()."""

    def __init__(self):
        self.buf = bytearray()

    def feed(self, data: bytes) -> list[bytes]:
        self.buf.extend(data)
        keys = []
        while self.buf:
            n = self._length()
            if n == 0:
                break
            keys.append(bytes(self.buf[:n]))
            del self.buf[:n]
        return keys

    def pending(self) -> bool:
        return bool(self.buf)

    def flush(self) -> list[bytes]:
        """What is left as keys: a lone Escape, or a sequence that never finished (dropped)."""
        rest, self.buf = bytes(self.buf), bytearray()
        return [rest] if rest == b"\x1b" else []

    def _length(self) -> int:
        """Bytes of the first whole key in buf; 0 if it has not all arrived."""
        b = self.buf
        if b[0] != ESC:
            return _utf8_length(b, 0)
        if len(b) < 2:
            return 0
        if b[1] == ord("["):
            for i in range(2, len(b)):
                if 0x40 <= b[i] <= 0x7E:
                    return i + 1
            return 0
        if b[1] == ord("O"):
            return 3 if len(b) >= 3 else 0
        if b[1] == ESC:
            return 1                                    # Escape, then whatever the second one starts
        n = _utf8_length(b, 1)
        return n + 1 if n else 0


def _utf8_length(b: bytearray, i: int) -> int:
    lead = b[i]
    n = 1 if lead < 0x80 else 2 if lead >> 5 == 0b110 else 3 if lead >> 4 == 0b1110 else 4 if lead >> 3 == 0b11110 \
        else 1
    return n if len(b) - i >= n else 0


class TerminalKeys(QtCore.QObject):
    """Reads fd (a terminal in cbreak mode) with a QSocketNotifier and runs actions[(key, modifiers)]."""

    def __init__(self, fd: int, actions: dict, parent=None):
        import termios
        import tty

        super().__init__(parent)
        self.fd, self.actions = fd, actions
        self.stream = KeyStream()
        self.stats = dict(keys=0, bound=0)
        self._saved = termios.tcgetattr(fd)
        self._closed = False
        tty.setcbreak(fd)
        self._blocking = os.get_blocking(fd)
        os.set_blocking(fd, False)
        atexit.register(self.close)                     # the terminal back as it was, whatever ends the process
        self._esc = QtCore.QTimer(self, singleShot=True, interval=LONE_ESC_MS)
        self._esc.timeout.connect(lambda: self._run(self.stream.flush()))
        self._notifier = QtCore.QSocketNotifier(fd, QtCore.QSocketNotifier.Type.Read, self)
        self._notifier.activated.connect(self._readable)

    def _readable(self) -> None:
        try:
            data = os.read(self.fd, 4096)
        except BlockingIOError:
            return
        except OSError as e:                            # the terminal went away (ssh closed)
            log.info("terminal keys stopped: %s", e)
            self.close()
            return
        if not data:
            self.close()
            return
        self._run(self.stream.feed(data))
        if self.stream.pending():
            self._esc.start()

    def _run(self, keys: list[bytes]) -> None:
        for seq in keys:
            self.stats["keys"] += 1
            got = decode(seq)
            fn = self.actions.get(combined(*got)) if got is not None else None
            if fn is not None:
                self.stats["bound"] += 1
                fn()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        import termios

        try:
            self._notifier.setEnabled(False)
        except RuntimeError:                            # the Qt object is gone already (at exit)
            pass
        try:
            os.set_blocking(self.fd, self._blocking)
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self._saved)
        except (OSError, termios.error):
            pass


def combined(key, mods) -> int:
    return QtCore.QKeyCombination(mods, key).toCombined()


def actions_of(shell) -> dict:
    """(key, modifiers) as one int -> the action, from the window's own key table."""
    out = {}
    for _shown, _what, binds in shell.key_table():
        for seq, fn in binds:
            ks = QtGui.QKeySequence(seq)
            if ks.count() == 1:
                out[ks[0].toCombined()] = fn
    return out


def attach(shell, fd: int | None = None, require_foreground: bool = True) -> TerminalKeys | None:
    """Start reading the terminal for shell, where it applies: standard input is a terminal (not a pipe, not a
    service), explorer runs in its foreground (not started with &: reading would stop the process), POSIX, and not
    turned off by EXPLORER_TERMINAL_KEYS=0. Returns the reader (keep it) or None."""
    if os.environ.get(ENV, "1") == "0":
        return None
    try:
        import termios  # noqa: F401  (POSIX only)
    except ImportError:
        return None
    if fd is None:
        try:
            fd = sys.stdin.fileno()
        except (AttributeError, OSError, ValueError):
            return None
    if not os.isatty(fd):
        return None
    if require_foreground:
        try:
            if os.tcgetpgrp(fd) != os.getpgrp():
                return None
        except OSError:
            return None
    tk = TerminalKeys(fd, actions_of(shell), parent=shell)
    QtCore.QCoreApplication.instance().aboutToQuit.connect(tk.close)
    return tk

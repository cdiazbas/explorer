"""The X CLIPBOARD for Qt's offscreen clipboard, which lives only inside the process (without this, Ctrl+C in the
viewer never reached another X client, and a copy elsewhere never reached Ctrl+V here: audit F20e). Text only.

- Qt copies: the bridge owns CLIPBOARD and answers requests (TARGETS, TIMESTAMP, UTF8_STRING, STRING, TEXT,
  text/plain); a text larger than one request goes by INCR, piece by piece, each one after the requestor deleted
  the previous (ICCCM 2.7.2).
- Another client copies (XFixes tells; without XFixes, it is asked when a window of ours gets the focus): its text
  comes into Qt's clipboard, also by INCR.
"""
import struct

from PySide6 import QtWidgets

from ...obs import get_logger
from . import xproto as X

log = get_logger("platform.xbridge")
NAMES = ("CLIPBOARD", "TARGETS", "TIMESTAMP", "MULTIPLE", "TEXT", "text/plain;charset=utf-8", "text/plain", "INCR",
         "INTEGER", "UTF8_STRING", "XBRIDGE_CLIP")
MAX_IN = 64 << 20                                      # a text larger than this from another client is refused
PROPERTY_DELETE, PROPERTY_NEW = 1, 0


class Clipboard:
    def __init__(self, c: X.Connection, atom_cookies: dict, xtime, post):
        """xtime(): the last server time seen; post(fn, *args): run fn on the interface thread."""
        self.c, self.xtime, self.post = c, xtime, post
        self.A = {n: struct.unpack_from("<I", ck.result(), 8)[0] for n, ck in atom_cookies.items()}
        self.win = c.new_id()
        c.create_window(self.win, c.screen.root, -10, -10, 1, 1, cls=X.InputOnly,
                        attrs={X.CW_EVENT_MASK: X.PropertyChangeMask})
        self.owned, self.owned_time, self.setting = False, 0, False
        self.chunk = max(4096, min(c.max_request - 1024, 256 << 10))
        self.outgoing: dict[tuple[int, int], dict] = {}  # (requestor, property) -> INCR transfer in progress
        self.incoming: dict | None = None               # our own INCR read in progress
        self.xfixes_event = None
        ext = c.ext("XFIXES")
        if ext is not None:
            c.ext_request("XFIXES", 0, struct.pack("<II", 5, 0), reply=True)     # the version first (required)
            c.ext_request("XFIXES", 2, struct.pack("<III", self.win, self.A["CLIPBOARD"], 1))
            self.xfixes_event = ext[1]
        c.flush()
        self.stats = dict(served=0, served_incr=0, received=0, received_incr=0, refused=0)
        QtWidgets.QApplication.clipboard().dataChanged.connect(self.qt_changed)
        self.fetch()

    # ---- Qt copied
    def qt_changed(self) -> None:
        if self.setting:                                # our own copy of another client's text
            return
        self.owned_time = self.xtime() or X.CURRENT_TIME
        self.c.set_selection_owner(self.win, self.A["CLIPBOARD"], self.owned_time)
        self.c.flush()
        self.owned = True

    # ---- another client copied
    def fetch(self) -> None:
        def got(reply, err):
            if err is None:
                owner = struct.unpack_from("<I", reply, 8)[0]
                if owner and owner != self.win:
                    self.c.convert_selection(self.win, self.A["CLIPBOARD"], self.A["UTF8_STRING"],
                                             self.A["XBRIDGE_CLIP"], X.CURRENT_TIME)
                    self.c.flush()
        self.c.get_selection_owner(self.A["CLIPBOARD"]).then(got)

    def focus_in(self) -> None:
        if self.xfixes_event is None and not self.owned:
            self.fetch()

    # ---- events
    def handles(self, e) -> bool:
        A, code = self.A, e.code
        if code == X.SelectionRequest and e.owner == self.win:
            self._answer(e)
        elif code == X.SelectionClear and e.owner == self.win:
            self.owned = False
        elif code == X.SelectionNotify and e.requestor == self.win:
            self._notified(e)
        elif code == X.PropertyNotify and e.window == self.win and e.atom == A["XBRIDGE_CLIP"]:
            if e.state == PROPERTY_NEW and self.incoming is not None:
                self._read_piece()
        elif code == X.PropertyNotify and (e.window, e.atom) in self.outgoing:
            if e.state == PROPERTY_DELETE:
                self._send_piece(e.window, e.atom)
        elif self.xfixes_event is not None and code == self.xfixes_event:
            owner, selection = struct.unpack_from("<II", e.raw, 8)
            if selection == A["CLIPBOARD"]:
                self.owned = owner == self.win
                if owner and not self.owned:
                    self.fetch()
        else:
            return False
        return True

    def _answer(self, e) -> None:
        A, c = self.A, self.c
        prop = e.property or e.target                   # an obsolete client names no property
        text = QtWidgets.QApplication.clipboard().text() if self.owned and e.selection == A["CLIPBOARD"] else None
        if text is None:
            prop = X.NONE
        elif e.target == A["TARGETS"]:
            c.change_property(e.requestor, prop, X.ATOM_ATOM, 32,
                              [A["TARGETS"], A["TIMESTAMP"], A["UTF8_STRING"], X.ATOM_STRING, A["TEXT"],
                               A["text/plain;charset=utf-8"], A["text/plain"]])
        elif e.target == A["TIMESTAMP"]:
            c.change_property(e.requestor, prop, A["INTEGER"], 32, [self.owned_time])
        elif e.target in (A["UTF8_STRING"], A["text/plain;charset=utf-8"], X.ATOM_STRING, A["TEXT"],
                          A["text/plain"]):
            utf8 = e.target in (A["UTF8_STRING"], A["text/plain;charset=utf-8"])
            data = text.encode("utf-8") if utf8 else text.encode("latin-1", "replace")
            typ = e.target if utf8 else X.ATOM_STRING
            if len(data) <= self.chunk:
                c.change_property(e.requestor, prop, typ, 8, data)
            else:                                       # INCR: the size first, the pieces as they are taken
                c.change_attributes(e.requestor, {X.CW_EVENT_MASK: X.PropertyChangeMask})
                c.change_property(e.requestor, prop, A["INCR"], 32, [len(data)])
                self.outgoing[(e.requestor, prop)] = dict(data=data, off=0, type=typ)
                self.stats["served_incr"] += 1
        else:
            prop = X.NONE                               # MULTIPLE and anything else: refused
        if prop == X.NONE:
            self.stats["refused"] += 1
        else:
            self.stats["served"] += 1
        ev = struct.pack("<BxHIIIIII", X.SelectionNotify, 0, e.time, e.requestor, e.selection, e.target, prop, 0)
        c.send_event(e.requestor, 0, ev)
        c.flush()

    def _send_piece(self, requestor: int, prop: int) -> None:
        t = self.outgoing[(requestor, prop)]
        piece = t["data"][t["off"]:t["off"] + self.chunk]
        t["off"] += len(piece)
        self.c.change_property(requestor, prop, t["type"], 8, piece)
        if not piece:                                   # the empty piece ends the transfer
            del self.outgoing[(requestor, prop)]
            self.c.change_attributes(requestor, {X.CW_EVENT_MASK: 0})
        self.c.flush()

    def _notified(self, e) -> None:
        A = self.A
        if e.property == X.NONE:
            if e.target == A["UTF8_STRING"]:            # an old client: ask for Latin-1
                self.c.convert_selection(self.win, A["CLIPBOARD"], X.ATOM_STRING, A["XBRIDGE_CLIP"], X.CURRENT_TIME)
                self.c.flush()
            return
        latin1 = e.target == X.ATOM_STRING
        def got(r, err):
            if err is None:
                self._first(r, latin1)
        self.c.get_property(self.win, A["XBRIDGE_CLIP"], delete=True).then(got)

    # these three run on the reader thread, in the order of the server's answers: the start of an INCR transfer is
    # known before the event of its first piece is handled
    def _first(self, reply: bytes, latin1: bool) -> None:
        typ, fmt, val, _after = self.c.property_value(reply)
        if typ == self.A["INCR"]:
            self.incoming = dict(parts=[], size=0, latin1=latin1)
            self.stats["received_incr"] += 1
            return                                      # deleting the property asked for the first piece
        if fmt == 8:
            self.post(self._set, val, latin1)

    def _read_piece(self) -> None:
        def got(r, err):
            if err is None:
                self._piece(r)
        self.c.get_property(self.win, self.A["XBRIDGE_CLIP"], delete=True).then(got)

    def _piece(self, reply: bytes) -> None:
        t = self.incoming
        if t is None:
            return
        _typ, _fmt, val, _after = self.c.property_value(reply)
        if not val:                                     # the empty piece: done
            self.incoming = None
            self.post(self._set, b"".join(t["parts"]), t["latin1"])
            return
        t["parts"].append(val)
        t["size"] += len(val)
        if t["size"] > MAX_IN:
            self.incoming = None
            log.warning("clipboard text from another client over %d MB: not taken", MAX_IN >> 20)

    def _set(self, raw: bytes, latin1: bool) -> None:
        text = raw.decode("latin-1" if latin1 else "utf-8", "replace")
        self.setting = True
        try:
            QtWidgets.QApplication.clipboard().setText(text)
        finally:
            self.setting = False
        self.owned = False
        self.stats["received"] += 1

    def close(self) -> None:
        try:
            QtWidgets.QApplication.clipboard().dataChanged.disconnect(self.qt_changed)
        except (RuntimeError, TypeError):
            pass

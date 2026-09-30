"""The X CLIPBOARD for Qt's offscreen clipboard, which lives only inside this process: without it Ctrl+C in the viewer
never reached another X client, and a copy elsewhere never reached Ctrl+V here. Text only, up to MAX (larger texts
would need INCR transfers). From the prototype's app/xbridge.py (_Clipboard).

Qt copies -> we own CLIPBOARD and answer requests; another client copies (XFixes tells, or we ask when an X window of
ours gets the focus) -> its text goes into Qt's clipboard.
"""
from PySide6 import QtWidgets

from ..._name import APP_NAME


class Clipboard:
    PROP = f"{APP_NAME.upper()}_CLIPBOARD"                 # where a text asked from another client is delivered
    NAMES = ("CLIPBOARD", "TARGETS", "UTF8_STRING", "STRING", "TEXT", "text/plain;charset=utf-8", "text/plain",
             "ATOM", "INCR", "TIMESTAMP", PROP)
    MAX = 256 << 10

    def __init__(self, bridge):
        X, ev = bridge.X, bridge.ev
        self.b, self.X, self.ev = bridge, X, ev
        self.A = {n: ev.intern_atom(n) for n in self.NAMES}
        self.win = bridge.scr.root.create_window(-10, -10, 1, 1, 0, 0, X.InputOnly, X.CopyFromParent,
                                                 event_mask=X.PropertyChangeMask)
        self.owned = self.setting = False
        self.xfixes = None
        if ev.has_extension("XFIXES"):
            from Xlib.ext import xfixes

            ev.xfixes_query_version()
            ev.xfixes_select_selection_input(self.win, self.A["CLIPBOARD"], xfixes.XFixesSetSelectionOwnerNotifyMask)
            self.xfixes = ev.query_extension("XFIXES").first_event + xfixes.XFixesSelectionNotify
        QtWidgets.QApplication.clipboard().dataChanged.connect(self.qt_changed)
        ev.flush()
        self.fetch()

    def close(self):
        try:
            QtWidgets.QApplication.clipboard().dataChanged.disconnect(self.qt_changed)
        except (RuntimeError, TypeError):
            pass

    def qt_changed(self):
        if self.setting:                                    # our own copy of another client's text
            return
        self.win.set_selection_owner(self.A["CLIPBOARD"], self.b.xtime or self.X.CurrentTime)
        self.ev.flush()
        self.owned = True

    def fetch(self):
        owner = self.ev.get_selection_owner(self.A["CLIPBOARD"])
        oid = getattr(owner, "id", owner)
        if oid and oid != self.win.id:
            self.win.convert_selection(self.A["CLIPBOARD"], self.A["UTF8_STRING"], self.A[self.PROP],
                                       self.X.CurrentTime)
            self.ev.flush()

    def focus_in(self):
        if self.xfixes is None and not self.owned:          # without XFixes we are not told of a copy elsewhere
            self.fetch()

    def handles(self, e) -> bool:
        """Takes the X events that are the clipboard's; False for any other."""
        X = self.X
        t = e.type
        if t == X.SelectionRequest and e.owner.id == self.win.id:
            self._answer(e)
        elif t == X.SelectionClear and e.window.id == self.win.id:
            self.owned = False
            self.fetch()
        elif t == X.SelectionNotify and e.requestor.id == self.win.id:
            self._received(e)
        elif self.xfixes is not None and t == self.xfixes and getattr(e, "sub_code", None) == 0:
            oid = getattr(e.owner, "id", e.owner)
            self.owned = oid == self.win.id
            if oid and not self.owned:
                self.fetch()
        else:
            return False
        return True

    def _answer(self, e):
        from Xlib.protocol import event as xev

        X, A = self.X, self.A
        prop = e.property or e.target
        text = QtWidgets.QApplication.clipboard().text() if self.owned and e.selection == A["CLIPBOARD"] else None
        if text is None or len(text) > self.MAX:
            prop = X.NONE
        elif e.target == A["TARGETS"]:
            e.requestor.change_property(prop, A["ATOM"], 32, [A["TARGETS"], A["UTF8_STRING"], A["STRING"], A["TEXT"],
                                                             A["text/plain;charset=utf-8"], A["text/plain"]])
        elif e.target in (A["UTF8_STRING"], A["text/plain;charset=utf-8"]):
            e.requestor.change_property(prop, e.target, 8, text.encode("utf-8"))
        elif e.target in (A["STRING"], A["TEXT"], A["text/plain"]):
            e.requestor.change_property(prop, A["STRING"], 8, text.encode("latin-1", "replace"))
        else:
            prop = X.NONE
        e.requestor.send_event(xev.SelectionNotify(time=e.time, requestor=e.requestor, selection=e.selection,
                                                   target=e.target, property=prop))
        self.ev.flush()

    def _received(self, e):
        X, A = self.X, self.A
        if e.property == X.NONE:
            if e.target == A["UTF8_STRING"]:                # an old client: ask for Latin-1
                self.win.convert_selection(A["CLIPBOARD"], A["STRING"], A[self.PROP], X.CurrentTime)
                self.ev.flush()
            return
        p = self.win.get_full_property(A[self.PROP], X.AnyPropertyType)
        self.win.delete_property(A[self.PROP])
        if p is None or p.property_type == A["INCR"] or p.format != 8:
            return
        raw = p.value if isinstance(p.value, bytes) else bytes(p.value)
        text = raw.decode("latin-1" if e.target == A["STRING"] else "utf-8", "replace")
        self.setting = True
        try:
            QtWidgets.QApplication.clipboard().setText(text)
        finally:
            self.setting = False
        self.owned = False

"""A small X11 client for the bridge: the connection, the requests it uses, and replies, events and errors read on a
thread of their own. No X library is needed on either side of the ssh link, and nothing waits for the server unless
it has to:
- requests are buffered and leave on flush() (or with the next request that needs a reply);
- a request that has a reply returns a Cookie at once: many of them go out together and cost one round trip (the
  atoms, extensions and properties at start-up), where one-at-a-time libraries pay one round trip each;
- the reader thread hands events to a callback in arrival order, and replies to their cookies (or to a callback
  run on the reader thread, then()).
Little-endian requests only (the byte order is the client's choice in X11); image data follows the server's image
byte order, which the caller reads from `setup`.

    c = Connection()                         # $DISPLAY, $XAUTHORITY
    a = c.atoms("WM_PROTOCOLS", "UTF8_STRING")   # one round trip for all
    wid = c.new_id(); c.create_window(wid, ...); c.map_window(wid); c.flush()
"""
import collections
import os
import socket
import struct
import threading
from dataclasses import dataclass, field
from types import SimpleNamespace

# core event codes
KeyPress, KeyRelease, ButtonPress, ButtonRelease, MotionNotify = 2, 3, 4, 5, 6
EnterNotify, LeaveNotify, FocusIn, FocusOut = 7, 8, 9, 10
Expose, NoExpose = 12, 14
DestroyNotify, UnmapNotify, MapNotify, ReparentNotify, ConfigureNotify = 17, 18, 19, 21, 22
PropertyNotify, SelectionClear, SelectionRequest, SelectionNotify, ClientMessage, MappingNotify = 28, 29, 30, 31, 33, 34
GenericEvent = 35

# event masks
KeyPressMask, KeyReleaseMask, ButtonPressMask, ButtonReleaseMask = 0x1, 0x2, 0x4, 0x8
EnterWindowMask, LeaveWindowMask, PointerMotionMask = 0x10, 0x20, 0x40
ExposureMask, StructureNotifyMask, SubstructureNotifyMask = 0x8000, 0x20000, 0x80000
SubstructureRedirectMask, FocusChangeMask, PropertyChangeMask = 0x100000, 0x200000, 0x400000

# window attribute value-mask bits (CreateWindow, ChangeWindowAttributes), in the order the values go
CW_BACK_PIXEL, CW_BIT_GRAVITY, CW_WIN_GRAVITY, CW_OVERRIDE_REDIRECT = 0x2, 0x10, 0x20, 0x200
CW_EVENT_MASK, CW_COLORMAP, CW_CURSOR = 0x800, 0x2000, 0x4000

NONE, CURRENT_TIME = 0, 0
InputOutput, InputOnly = 1, 2
PropModeReplace, PropModeAppend = 0, 2
ATOM_ATOM, ATOM_CARDINAL, ATOM_STRING, ATOM_WINDOW, ATOM_WM_NAME = 4, 6, 31, 33, 39
ATOM_WM_HINTS, ATOM_WM_NORMAL_HINTS, ATOM_WM_SIZE_HINTS = 35, 40, 41
ATOM_WM_CLASS, ATOM_WM_TRANSIENT_FOR = 67, 68
RevertToParent = 2
NotifyNormal, NotifyGrab, NotifyUngrab = 0, 1, 2
NotifyVirtual, NotifyNonlinearVirtual, NotifyPointer = 1, 4, 5


class XError(Exception):
    """An X error: its code, the request (major, minor) and sequence, the bad value."""

    NAMES = {1: "BadRequest", 2: "BadValue", 3: "BadWindow", 4: "BadPixmap", 5: "BadAtom", 6: "BadCursor",
             7: "BadFont", 8: "BadMatch", 9: "BadDrawable", 10: "BadAccess", 11: "BadAlloc", 13: "BadGC",
             14: "BadIDChoice", 15: "BadName", 16: "BadLength", 17: "BadImplementation"}

    def __init__(self, code, seq, bad, major, minor):
        self.code, self.seq, self.bad, self.major, self.minor = code, seq, bad, major, minor
        super().__init__(f"{self.NAMES.get(code, code)} (request {major}.{minor}, value {bad:#x}, seq {seq})")


class ConnectionLost(ConnectionError):
    pass


class Cookie:
    """The reply to one request, when it comes. result() waits for it (raises XError or ConnectionLost); then(fn)
    runs fn(reply bytes or None, error or None) once, on the reader thread (or at once if the reply is in)."""
    __slots__ = ("_done", "_reply", "_error", "_cb", "_lock")

    def __init__(self):
        self._done = threading.Event()
        self._reply = self._error = self._cb = None
        self._lock = threading.Lock()

    def _set(self, reply, error):
        with self._lock:
            self._reply, self._error = reply, error
            self._done.set()
            cb, self._cb = self._cb, None
        if cb is not None:
            cb(reply, error)

    def then(self, fn):
        with self._lock:
            if not self._done.is_set():
                self._cb = fn
                return self
        fn(self._reply, self._error)
        return self

    @property
    def done(self) -> bool:
        return self._done.is_set()

    def result(self, timeout: float | None = 30.0) -> bytes:
        if not self._done.wait(timeout):
            raise TimeoutError("no reply from the X server")
        if self._error is not None:
            raise self._error
        return self._reply  # type: ignore[return-value]


# ---------------------------------------------------------------- where the server is, and its cookie
def parse_display(name: str) -> tuple[str, int, int]:
    """"host:D.S" -> (host, D, S). host "" or "unix": the local socket; a path (XQuartz's launchd socket,
    "/private/tmp/com.apple.launchd.x/org.xquartz:0"): that socket file."""
    if not name:
        raise ValueError("DISPLAY is not set")
    head, _, tail = name.rpartition(":")
    num, _, scr = tail.partition(".")
    if not num.isdigit():
        raise ValueError(f"cannot read DISPLAY {name!r}")
    return head, int(num), int(scr) if scr.isdigit() else 0


def open_socket(name: str) -> tuple[socket.socket, str, int]:
    """A connected socket; also the family name for the cookie lookup ("local" or "inet") and the display number."""
    host, dno, _ = parse_display(name)
    if host.startswith("/"):                            # a socket path: the name up to the screen
        path = name if not name.rsplit(":", 1)[1].count(".") else name.rsplit(".", 1)[0]
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect(path)
        return s, "local", dno
    if host in ("", "unix"):
        path = f"/tmp/.X11-unix/X{dno}"
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            if os.uname().sysname == "Linux":           # the abstract socket first, as libxcb
                s.connect("\0" + path)
            else:
                s.connect(path)
        except OSError:
            s.close()
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.connect(path)
        return s, "local", dno
    s = socket.create_connection((host, 6000 + dno))
    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    return s, "inet", dno


FAMILY_INET, FAMILY_INET6, FAMILY_LOCAL, FAMILY_WILD = 0, 6, 256, 65535


def read_xauthority(path: str | None = None) -> list[tuple[int, bytes, bytes, bytes, bytes]]:
    """Entries of an Xauthority file as (family, address, number, name, data); [] when there is none. Read directly:
    never through xauth, whose lock on a home shared between machines can be left behind and block every other
    xauth there."""
    path = path or os.environ.get("XAUTHORITY") or os.path.expanduser("~/.Xauthority")
    try:
        raw = open(path, "rb").read()
    except OSError:
        return []
    out, i = [], 0
    try:
        while i + 2 <= len(raw):
            fam = struct.unpack_from(">H", raw, i)[0]
            i += 2
            parts = []
            for _ in range(4):
                n = struct.unpack_from(">H", raw, i)[0]
                parts.append(raw[i + 2:i + 2 + n])
                i += 2 + n
            out.append((fam, *parts))
    except struct.error:
        pass
    return out


def choose_cookie(entries, dno: int, family: str, hostnames, peer: bytes | None = None) -> tuple[bytes, bytes]:
    """The MIT cookie for display dno: this host by name first (sshd stores it so, also for a TCP display
    "host:10" that python-xlib looked up by address only), then by address, then any host. (b"", b"") if none."""
    want = str(dno).encode()
    names = {h.lower().encode() for h in hostnames if h}
    ranked = []
    for fam, addr, num, name, data in entries:
        if num != want or name != b"MIT-MAGIC-COOKIE-1":
            continue
        if fam == FAMILY_LOCAL and (addr.lower() in names or addr.split(b".")[0].lower() in names):
            ranked.append((0, name, data))
        elif fam in (FAMILY_INET, FAMILY_INET6) and peer is not None and addr == peer:
            ranked.append((1, name, data))
        elif fam == FAMILY_WILD:
            ranked.append((2, name, data))
    if not ranked:
        return b"", b""
    ranked.sort(key=lambda r: r[0])
    return ranked[0][1], ranked[0][2]


def _pad(n: int) -> int:
    return (4 - n % 4) % 4


# ---------------------------------------------------------------- the server's description
@dataclass
class Visual:
    id: int
    cls: int
    red: int
    green: int
    blue: int


@dataclass
class Screen:
    root: int
    colormap: int
    white: int
    black: int
    width: int
    height: int
    width_mm: int
    height_mm: int
    root_visual: int
    root_depth: int
    visuals: dict = field(default_factory=dict)         # visual id -> (depth, Visual)


@dataclass
class Setup:
    release: int
    id_base: int
    id_mask: int
    max_request: int                                    # bytes
    image_lsb: bool                                     # image byte order LSBFirst
    formats: dict                                       # depth -> bits per pixel
    min_keycode: int
    max_keycode: int
    vendor: str
    screens: list


def parse_setup(d: bytes) -> Setup:
    (release, id_base, id_mask, _mbuf, vlen, max_req, nscr, nfmt, img_order, _bit_order, _su, _sp,
     min_kc, max_kc) = struct.unpack_from("<IIIIHHBBBBBBBB", d, 0)
    off = 32
    vendor = d[off:off + vlen].decode("latin-1", "replace")
    off += vlen + _pad(vlen)
    formats = {}
    for _ in range(nfmt):
        depth, bpp, _pad_ = struct.unpack_from("<BBB", d, off)
        formats[depth] = bpp
        off += 8
    screens = []
    for _ in range(nscr):
        (root, cmap, white, black, _masks, w, h, wmm, hmm, _minm, _maxm, rvis, _bs, _su2, rdepth,
         ndepths) = struct.unpack_from("<IIIIIHHHHHHIBBBB", d, off)
        off += 40
        scr = Screen(root, cmap, white, black, w, h, wmm, hmm, rvis, rdepth)
        for _ in range(ndepths):
            depth, nvis = struct.unpack_from("<BxH", d, off)
            off += 8
            for _ in range(nvis):
                vid, cls, _bits, _ents, r, g, b = struct.unpack_from("<IBBHIII", d, off)
                scr.visuals[vid] = (depth, Visual(vid, cls, r, g, b))
                off += 24
        screens.append(scr)
    return Setup(release, id_base, id_mask, max_req * 4, img_order == 0, formats, min_kc, max_kc, vendor, screens)


# ---------------------------------------------------------------- events
def decode_event(b: bytes) -> SimpleNamespace:
    """A 32-byte event as a namespace with its fields by X's names; `code` without the sent-event bit, `sent`."""
    code = b[0] & 0x7F
    e = SimpleNamespace(code=code, sent=bool(b[0] & 0x80), seq=struct.unpack_from("<H", b, 2)[0])
    if KeyPress <= code <= LeaveNotify:
        (e.detail,) = b[1:2]
        (e.time, e.root, e.window, e.child, e.root_x, e.root_y, e.x, e.y, e.state) = struct.unpack_from(
            "<IIIIhhhhH", b, 4)
        if code >= EnterNotify:
            e.mode, e.flags = b[30], b[31]
    elif code in (FocusIn, FocusOut):
        e.detail = b[1]
        e.window, e.mode = struct.unpack_from("<IB", b, 4)
    elif code == Expose:
        e.window, e.x, e.y, e.width, e.height, e.count = struct.unpack_from("<IHHHHH", b, 4)
    elif code == ConfigureNotify:
        (e.event, e.window, e.above, e.x, e.y, e.width, e.height, e.border,
         e.override) = struct.unpack_from("<IIIhhHHHB", b, 4)
    elif code in (MapNotify, UnmapNotify, DestroyNotify):
        e.event, e.window = struct.unpack_from("<II", b, 4)
    elif code == ReparentNotify:
        e.event, e.window, e.parent, e.x, e.y = struct.unpack_from("<IIIhh", b, 4)
    elif code == PropertyNotify:
        e.window, e.atom, e.time, e.state = struct.unpack_from("<IIIB", b, 4)
    elif code == SelectionClear:
        e.time, e.owner, e.selection = struct.unpack_from("<III", b, 4)
        e.window = e.owner
    elif code == SelectionRequest:
        e.time, e.owner, e.requestor, e.selection, e.target, e.property = struct.unpack_from("<IIIIII", b, 4)
        e.window = e.owner
    elif code == SelectionNotify:
        e.time, e.requestor, e.selection, e.target, e.property = struct.unpack_from("<IIIII", b, 4)
        e.window = e.requestor
    elif code == ClientMessage:
        e.format = b[1]
        e.window, e.type = struct.unpack_from("<II", b, 4)
        e.data = struct.unpack_from("<5I", b, 12) if e.format == 32 else bytes(b[12:32])
    elif code == MappingNotify:
        e.request, e.first_keycode, e.count = b[4], b[5], b[6]
    else:
        e.raw = bytes(b)
    return e


# ---------------------------------------------------------------- the connection
class Connection:
    """One connection to the X server. on_event(event) and on_error(XError) run on the reader thread; on_lost(exc)
    once, when the connection breaks. Safe to use from several threads: requests are numbered and written under one
    lock."""

    def __init__(self, display: str | None = None, *, on_event=None, on_error=None, on_lost=None, name="x",
                 auth_path: str | None = None):
        self.display_name = display or os.environ.get("DISPLAY", "")
        sock, family, dno = open_socket(self.display_name)
        self.sock = sock
        peer = None
        if family == "inet":
            try:
                peer = socket.inet_aton(sock.getpeername()[0])
            except (OSError, ValueError):
                peer = None
        host = socket.gethostname()
        auth_name, auth_data = choose_cookie(read_xauthority(auth_path), dno, family, [host, host.split(".")[0]],
                                             peer)
        self.setup = self._handshake(auth_name, auth_data)
        self.screen = self.setup.screens[_screen_no(self.display_name, len(self.setup.screens))]
        self.max_request = min(self.setup.max_request, 1 << 22)
        self.on_event, self.on_error, self.on_lost = on_event, on_error, on_lost
        self.name = name
        self._lock = threading.Lock()                   # the output buffer and the request numbers
        self._out = bytearray()
        self._seq = 0                                   # last request number written (not wrapped)
        self._pending: dict[int, Cookie] = {}           # request number -> its cookie
        self._plock = threading.Lock()
        self._next_id = 0
        self._id_shift = (self.setup.id_mask & -self.setup.id_mask).bit_length() - 1
        self._ext: dict[str, tuple[int, int, int] | None] = {}
        self._atoms: dict[str, int] = {}
        self._atom_names: dict[int, str] = {}
        self.errors = 0
        self.last_error: XError | None = None
        self.lost: BaseException | None = None
        self.bytes_out = 0
        self._reader = threading.Thread(target=self._read_loop, name=f"{name}-reader", daemon=True)
        self._reader.start()

    # ---- handshake
    def _handshake(self, auth_name: bytes, auth_data: bytes) -> Setup:
        s = self.sock
        req = struct.pack("<BxHHHHxx", 0x6C, 11, 0, len(auth_name), len(auth_data))
        req += auth_name + b"\0" * _pad(len(auth_name)) + auth_data + b"\0" * _pad(len(auth_data))
        s.sendall(req)
        head = _recv_exact(s, 8)
        status, rlen = head[0], struct.unpack_from("<H", head, 6)[0]
        body = _recv_exact(s, rlen * 4)
        if status != 1:
            reason = body[:head[1]].decode("latin-1", "replace") if status == 0 else "authentication required"
            s.close()
            raise ConnectionRefusedError(f"the X server refused the connection: {reason.strip()}")
        return parse_setup(body)

    # ---- ids
    def new_id(self) -> int:
        """A new resource id; never reused while the connection lives (a reused id met events and pictures of the
        window that had it before)."""
        with self._lock:
            self._next_id += 1
            n = self._next_id
        rid = self.setup.id_base | ((n << self._id_shift) & self.setup.id_mask)
        if n << self._id_shift > self.setup.id_mask:
            raise RuntimeError("out of X resource ids")
        return rid

    # ---- sending
    def _request(self, data: bytes, reply: bool = False) -> Cookie | None:
        return self._request_n(data, reply)[1]

    def _request_n(self, data: bytes, reply: bool = False) -> tuple[int, Cookie | None]:
        """The request's number, and its cookie when it has a reply."""
        with self._lock:
            if self.lost is not None:
                raise ConnectionLost(str(self.lost))
            self._seq += 1
            ck = None
            if reply:
                ck = Cookie()
                with self._plock:
                    self._pending[self._seq] = ck
            self._out += data
            if reply or len(self._out) > 1 << 16:
                self._flush_locked()
            return self._seq, ck

    def request(self, opcode: int, data: int, body: bytes = b"", reply: bool = False) -> Cookie | None:
        """A raw request: opcode, the data byte, the body (padded here to 4 bytes)."""
        return self._request(_encode(opcode, data, body), reply)

    def flush(self) -> None:
        with self._lock:
            self._flush_locked()

    def _flush_locked(self) -> None:
        if self._out:
            data, self._out = self._out, bytearray()
            try:
                self.sock.sendall(data)
                self.bytes_out += len(data)
            except OSError as e:
                self._broken(e)
                raise ConnectionLost(str(e)) from e

    def send_raw(self, data, nreq: int, last_reply: bool = False) -> Cookie | None:
        """Write nreq whole requests encoded by the caller (the image transport); the socket takes them without the
        GIL. last_reply: the last of them has a reply, returned as a cookie."""
        with self._lock:
            if self.lost is not None:
                raise ConnectionLost(str(self.lost))
            self._flush_locked()
            self._seq += nreq
            ck = None
            if last_reply:
                ck = Cookie()
                with self._plock:
                    self._pending[self._seq] = ck
            try:
                self.sock.sendall(data)
                self.bytes_out += len(data)
            except OSError as e:
                self._broken(e)
                raise ConnectionLost(str(e)) from e
        return ck

    @property
    def seq(self) -> int:
        """Number of the last request written (not wrapped at 16 bits)."""
        return self._seq

    # ---- reading
    def _read_loop(self):
        buf = bytearray()
        try:
            while True:
                chunk = self.sock.recv(1 << 16)
                if not chunk:
                    raise ConnectionLost("the X server closed the connection")
                buf += chunk
                off = 0
                n = len(buf)
                while n - off >= 32:
                    kind = buf[off]
                    if kind == 1 or (kind & 0x7F) == GenericEvent:
                        size = 32 + 4 * struct.unpack_from("<I", buf, off + 4)[0]
                    else:
                        size = 32
                    if n - off < size:
                        break
                    pkt = bytes(buf[off:off + size])
                    off += size
                    self._packet(pkt)
                del buf[:off]
        except BaseException as e:                      # every way out ends the connection
            self._broken(e)

    def _full_seq(self, s16: int) -> int:
        sent = self._seq
        full = (sent & ~0xFFFF) | s16
        if full > sent:
            full -= 0x10000
        return full

    def _packet(self, pkt: bytes) -> None:
        kind = pkt[0]
        if kind == 0:                                   # error
            code, s16, bad, minor, major = struct.unpack_from("<BHIHB", pkt, 1)
            seq = self._full_seq(s16)
            err = XError(code, seq, bad, major, minor)
            with self._plock:
                ck = self._pending.pop(seq, None)
            if ck is not None:
                ck._set(None, err)
            else:
                self.errors += 1
                self.last_error = err
                if self.on_error is not None:
                    self.on_error(err)
            return
        if kind == 1:                                   # reply
            seq = self._full_seq(struct.unpack_from("<H", pkt, 2)[0])
            with self._plock:
                ck = self._pending.pop(seq, None)
                # requests before it that expected a reply got none: they failed in a way X does not report
                stale = [s for s in self._pending if s < seq] if self._pending else ()
                old = [self._pending.pop(s) for s in stale]
            for o in old:
                o._set(None, XError(0, seq, 0, 0, 0))
            if ck is not None:
                ck._set(pkt, None)
            return
        if self.on_event is not None:
            self.on_event(pkt)

    def _broken(self, e: BaseException) -> None:
        with self._plock:
            first = self.lost is None
            if first:
                self.lost = e
            pend, self._pending = list(self._pending.values()), {}
        err = e if isinstance(e, ConnectionError) else ConnectionLost(str(e))
        for ck in pend:
            ck._set(None, err)
        if first and self.on_lost is not None:
            self.on_lost(e)

    def close(self) -> None:
        try:
            self.flush()
        except ConnectionError:
            pass
        with self._plock:
            if self.lost is None:
                self.lost = ConnectionLost("closed")
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.sock.close()

    # ---------------------------------------------------------------- atoms and extensions
    def atoms(self, *names: str) -> dict[str, int]:
        """Atoms by name, interned together: one round trip for all the unknown ones."""
        todo = [n for n in dict.fromkeys(names) if n not in self._atoms]
        cks = [(n, self.intern_atom(n)) for n in todo]
        for n, ck in cks:
            a = struct.unpack_from("<I", ck.result(), 8)[0]
            self._atoms[n] = a
            self._atom_names[a] = n
        return {n: self._atoms[n] for n in names}

    def atom(self, name: str) -> int:
        return self._atoms[name] if name in self._atoms else self.atoms(name)[name]

    def intern_atom(self, name: str, only_if_exists: bool = False) -> Cookie:
        b = name.encode("latin-1")
        return self.request(16, int(only_if_exists), struct.pack("<HH", len(b), 0) + b, reply=True)  # type: ignore

    def atom_name(self, atom: int) -> str:
        if atom not in self._atom_names:
            ck = self.request(17, 0, struct.pack("<I", atom), reply=True)
            assert ck is not None
            r = ck.result()
            n = struct.unpack_from("<H", r, 8)[0]
            self._atom_names[atom] = r[32:32 + n].decode("latin-1")
        return self._atom_names[atom]

    def extensions(self, *names: str) -> dict[str, tuple[int, int, int] | None]:
        """(major opcode, first event, first error) per extension, None when absent; together, one round trip."""
        todo = [n for n in names if n not in self._ext]
        cks = []
        for n in todo:
            b = n.encode()
            cks.append((n, self.request(98, 0, struct.pack("<HH", len(b), 0) + b, reply=True)))
        for n, ck in cks:
            r = ck.result()                             # type: ignore[union-attr]
            self._ext[n] = (r[9], r[10], r[11]) if r[8] else None
        return {n: self._ext[n] for n in names}

    def ext(self, name: str) -> tuple[int, int, int] | None:
        return self._ext[name] if name in self._ext else self.extensions(name)[name]

    # ---------------------------------------------------------------- core requests
    def create_window(self, wid, parent, x, y, w, h, *, depth=0, border=0, cls=InputOutput, visual=0,
                      attrs: dict[int, int] | None = None) -> None:
        mask, vals = _values(attrs or {})
        self.request(1, depth, struct.pack("<IIhhHHHHII", wid, parent, x, y, max(1, w), max(1, h), border, cls,
                                           visual, mask) + vals)

    def change_attributes(self, wid, attrs: dict[int, int]) -> None:
        mask, vals = _values(attrs)
        self.request(2, 0, struct.pack("<II", wid, mask) + vals)

    def destroy_window(self, wid) -> None:
        self.request(4, 0, struct.pack("<I", wid))

    def map_window(self, wid) -> None:
        self.request(8, 0, struct.pack("<I", wid))

    def unmap_window(self, wid) -> None:
        self.request(10, 0, struct.pack("<I", wid))

    CFG = (("x", 0x1, "<i"), ("y", 0x2, "<i"), ("width", 0x4, "<I"), ("height", 0x8, "<I"),
           ("border", 0x10, "<I"), ("sibling", 0x20, "<I"), ("stack_mode", 0x40, "<I"))

    def configure_window(self, wid, **kw) -> int:
        """ConfigureWindow; returns its request number (to tell its notices from older ones)."""
        mask, vals = 0, b""
        for name, bit, fmt in self.CFG:
            if name in kw:
                mask |= bit
                vals += struct.pack(fmt, int(kw[name]))
        return self._request_n(_encode(12, 0, struct.pack("<IHxx", wid, mask) + vals))[0]

    def change_property(self, wid, prop, type_, fmt, data, mode=PropModeReplace) -> None:
        """data: the values, or bytes already in the wire's order (little-endian) for any format."""
        if fmt == 8 or isinstance(data, (bytes, bytearray)):
            raw = bytes(data)
            n = len(raw) // (fmt // 8)
        elif fmt == 16:
            raw = struct.pack(f"<{len(data)}H", *data)
            n = len(data)
        else:
            # INT32 fields as two's complement: WM_NORMAL_HINTS' x and y of a window above or left of the screen's
            # origin (a panel dragged above its top edge) raised struct.error and the window was never created
            raw = struct.pack(f"<{len(data)}I", *(int(v) & 0xFFFFFFFF for v in data))
            n = len(data)
        self.request(18, mode, struct.pack("<IIIBxxxI", wid, prop, type_, fmt, n) + raw)

    def delete_property(self, wid, prop) -> None:
        self.request(19, 0, struct.pack("<II", wid, prop))

    def get_property(self, wid, prop, type_=0, offset=0, length=1 << 20, delete=False) -> Cookie:
        return self.request(20, int(delete), struct.pack("<IIIII", wid, prop, type_, offset, length),  # type: ignore
                            reply=True)

    @staticmethod
    def property_value(reply: bytes) -> tuple[int, int, bytes, int]:
        """(type, format, value bytes, bytes after) of a GetProperty reply."""
        fmt = reply[1]
        typ, after, n = struct.unpack_from("<III", reply, 8)
        size = n * (fmt // 8) if fmt else 0
        return typ, fmt, reply[32:32 + size], after

    def set_selection_owner(self, owner, selection, time) -> None:
        self.request(22, 0, struct.pack("<III", owner, selection, time))

    def get_selection_owner(self, selection) -> Cookie:
        return self.request(23, 0, struct.pack("<I", selection), reply=True)  # type: ignore[return-value]

    def convert_selection(self, requestor, selection, target, prop, time) -> None:
        self.request(24, 0, struct.pack("<IIIII", requestor, selection, target, prop, time))

    def send_event(self, dest, mask, event: bytes, propagate=False) -> None:
        self.request(25, int(propagate), struct.pack("<II", dest, mask) + event.ljust(32, b"\0"))

    def client_message(self, dest, window, type_, data32, mask) -> None:
        """A ClientMessage about window, of format 32, sent to dest with this event mask (EWMH: the root)."""
        d = list(data32) + [0] * (5 - len(data32))
        ev = struct.pack("<BBHII5I", ClientMessage, 32, 0, window, type_, *[v & 0xFFFFFFFF for v in d])
        self.send_event(dest, mask, ev)

    def grab_pointer(self, wid, mask, owner_events=True, cursor=0, time=0) -> Cookie:
        return self.request(26, int(owner_events), struct.pack("<IHBBIII", wid, mask, 1, 1, 0, cursor, time),  # type: ignore
                            reply=True)

    def ungrab_pointer(self, time=0) -> None:
        self.request(27, 0, struct.pack("<I", time))

    def query_pointer(self, wid) -> Cookie:
        return self.request(38, 0, struct.pack("<I", wid), reply=True)  # type: ignore[return-value]

    def get_geometry(self, drawable) -> Cookie:
        """GetGeometry: the reply has x, y (in the parent), width, height at 12, 14, 16, 18."""
        return self.request(14, 0, struct.pack("<I", drawable), reply=True)  # type: ignore[return-value]

    def translate_coordinates(self, src, dst, x=0, y=0) -> Cookie:
        return self.request(40, 0, struct.pack("<IIhh", src, dst, x, y), reply=True)  # type: ignore[return-value]

    def set_input_focus(self, wid, time=0, revert=RevertToParent) -> None:
        self.request(42, revert, struct.pack("<II", wid, time))

    def get_input_focus(self) -> Cookie:
        return self.request(43, 0, reply=True)  # type: ignore[return-value]

    def sync(self, timeout: float | None = 30.0) -> None:
        """One round trip: everything sent before has been processed by the server."""
        self.get_input_focus().result(timeout)

    def open_font(self, fid, name: str) -> None:
        b = name.encode()
        self.request(45, 0, struct.pack("<IHxx", fid, len(b)) + b)

    def create_pixmap(self, pid, drawable, w, h, depth) -> None:
        self.request(53, depth, struct.pack("<IIHH", pid, drawable, max(1, w), max(1, h)))

    def free_pixmap(self, pid) -> None:
        self.request(54, 0, struct.pack("<I", pid))

    def create_gc(self, gid, drawable, graphics_exposures=False) -> None:
        self.request(55, 0, struct.pack("<IIII", gid, drawable, 0x10000, int(graphics_exposures)))

    def free_gc(self, gid) -> None:
        self.request(60, 0, struct.pack("<I", gid))

    def copy_area(self, src, dst, gc, sx, sy, dx, dy, w, h) -> None:
        self.request(62, 0, struct.pack("<IIIhhhhHH", src, dst, gc, sx, sy, dx, dy, w, h))

    def put_image(self, drawable, gc, w, h, x, y, depth, data: bytes) -> None:
        """One ZPixmap PutImage (the caller keeps it under the request size)."""
        self.request(72, 2, struct.pack("<IIHHhhBBxx", drawable, gc, w, h, x, y, 0, depth) + bytes(data))

    def get_image(self, drawable, x, y, w, h, plane_mask=0xFFFFFFFF) -> Cookie:
        return self.request(73, 2, struct.pack("<IhhHHI", drawable, x, y, w, h, plane_mask),  # type: ignore
                            reply=True)

    def create_glyph_cursor(self, cid, font, glyph, fore=(0, 0, 0), back=(65535, 65535, 65535)) -> None:
        self.request(94, 0, struct.pack("<IIIHH6H", cid, font, font, glyph, glyph + 1, *fore, *back))

    def free_cursor(self, cid) -> None:
        self.request(95, 0, struct.pack("<I", cid))

    def keyboard_mapping(self) -> Cookie:
        lo, hi = self.setup.min_keycode, self.setup.max_keycode
        return self.request(101, 0, struct.pack("<BBxx", lo, hi - lo + 1), reply=True)  # type: ignore

    def modifier_mapping(self) -> Cookie:
        return self.request(119, 0, reply=True)  # type: ignore[return-value]

    # ---------------------------------------------------------------- extensions
    def ext_request(self, ext: str, minor: int, body: bytes = b"", reply=False) -> Cookie | None:
        info = self.ext(ext)
        if info is None:
            raise RuntimeError(f"the X server has no {ext}")
        return self.request(info[0], minor, body, reply)

    def xinerama_screens(self) -> list[tuple[int, int, int, int]]:
        """The monitors as (x, y, w, h); [] without Xinerama (XQuartz reports two monitors as one RandR screen, and
        Xinerama as two)."""
        if self.ext("XINERAMA") is None:
            return []
        r = self.ext_request("XINERAMA", 5, reply=True).result()  # type: ignore[union-attr]
        n = struct.unpack_from("<I", r, 8)[0]
        return [struct.unpack_from("<hhHH", r, 32 + 8 * i) for i in range(n)]

    def shape_rectangles(self, wid, rects, kind=0) -> None:
        body = struct.pack("<BBBxIhh", 0, kind, 0, wid, 0, 0)
        body += b"".join(struct.pack("<hhHH", *r) for r in rects)
        self.ext_request("SHAPE", 1, body)

    def shape_reset(self, wid, kind=0) -> None:
        self.ext_request("SHAPE", 2, struct.pack("<BBxxIhhI", 0, kind, wid, 0, 0, NONE))


def _encode(opcode: int, data: int, body: bytes) -> bytes:
    body = body + b"\0" * _pad(len(body))
    return struct.pack("<BBH", opcode, data, (4 + len(body)) // 4) + body


def _values(attrs: dict[int, int]) -> tuple[int, bytes]:
    mask, vals = 0, b""
    for bit in sorted(attrs):
        mask |= bit
        vals += struct.pack("<I", attrs[bit] & 0xFFFFFFFF)
    return mask, vals


def _recv_exact(s: socket.socket, n: int) -> bytes:
    out = bytearray()
    while len(out) < n:
        chunk = s.recv(n - len(out))
        if not chunk:
            raise ConnectionLost("the X server closed the connection during set-up")
        out += chunk
    return bytes(out)


def _screen_no(name: str, n: int) -> int:
    try:
        s = parse_display(name)[2]
    except ValueError:
        s = 0
    return s if s < n else 0


class EventQueue:
    """Events from the reader thread to the thread that owns the windows: appended there, taken here in order.
    wake() is called once per batch (the first event after the queue was emptied), so the owner is woken once
    however many events arrive while it is busy."""

    def __init__(self, wake):
        self._q: collections.deque = collections.deque()
        self._lock = threading.Lock()
        self._waiting = False
        self._wake = wake

    def put(self, item) -> None:
        with self._lock:
            self._q.append(item)
            call = not self._waiting
            self._waiting = True
        if call:
            self._wake()

    def take(self):
        """The next item, or None (then the next put() wakes the owner again)."""
        with self._lock:
            if self._q:
                return self._q.popleft()
            self._waiting = False
            return None

    def peek(self):
        with self._lock:
            return self._q[0] if self._q else None

    def rewake(self) -> None:
        """Before each event is handled: an event handler may start a nested event loop (a menu's exec) and never
        return to take the next. What is left wakes the owner again; with nothing left, the next event will, since
        the owner may be inside that loop by then. Otherwise a release coming after a click that opened a menu
        found the owner counted as woken and nothing read X any more (Panels hung on XQuartz; XTEST on Xvfb sends
        both at once, so the release was already queued)."""
        with self._lock:
            call = bool(self._q)
            if not call:
                self._waiting = False
        if call:
            self._wake()

    def __len__(self):
        return len(self._q)

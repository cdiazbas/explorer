"""IDL SAVE files (.idlsave, .sav), as SSTRED writes them beside an LP cube: the variables, read without IDL.

    read(path)                          # {name: value}, names lower case, as scipy.io.readsav gives them
    read(path, names={"lambda"})        # only those; the others are skipped without reading their data

The format is a series of records in XDR (big-endian), each starting with its type and the offset of the next
one, after the signature "SR" and a format word (4: plain, 6: compressed). Only VARIABLE records are decoded, the
rest are skipped by their offsets. Decoded: scalars and arrays of the numeric types and strings. Not decoded:
structures, pointers, objects, system variables and 64-bit array descriptors; they come back as Unread, so a file
that holds one still gives its other variables. Compressed files are refused (none among SSTRED's).

Values: numpy arrays in native byte order, numpy order (IDL's dimensions reversed, as readsav does); numeric scalars
as numpy scalars of their IDL type; strings as str (latin-1). Standard library and numpy only.
"""
import struct
from typing import Any, NamedTuple

import numpy as np

_VARIABLE, _END = 2, 6                  # record types
_ARRAY, _STRUCT, _SYSTEM = 4, 32, 2     # VARFLAGS bits
_STRING = 7
_DTYPE = {1: ">u1", 2: ">i2", 3: ">i4", 4: ">f4", 5: ">f8", 6: ">c8", 9: ">c16", 12: ">u2", 13: ">u4", 14: ">i8",
          15: ">u8"}
_KIND = {8: "structure", 10: "pointer", 11: "object"}


class Unread(NamedTuple):
    """A variable this reader does not decode: its IDL type code and why."""
    typecode: int
    why: str


class _Stream:
    def __init__(self, f):
        self.f = f

    def take(self, n: int) -> bytes:
        b = self.f.read(n)
        if len(b) != n:
            raise ValueError(f"IDL SAVE file ends {n - len(b)} bytes short at offset {self.f.tell()}")
        return b

    def long(self) -> int:
        return struct.unpack(">i", self.take(4))[0]

    def ulong(self) -> int:
        return struct.unpack(">I", self.take(4))[0]

    def align(self) -> None:                    # every item starts on a 4-byte boundary
        pos = self.f.tell()
        if pos % 4:
            self.f.seek(4 - pos % 4, 1)

    def text(self) -> str:                      # a name: length, characters
        n = self.long()
        s = self.take(n).decode("latin-1") if n > 0 else ""
        self.align()
        return s

    def string(self) -> str:                    # string data: length, length again, characters
        if self.long() <= 0:
            return ""
        s = self.take(self.long()).decode("latin-1")
        self.align()
        return s

    def scalar(self, code: int):
        if code == _STRING:
            return self.string()
        if code == 1:                           # a byte: a count of 1, then the byte in a 4-byte word
            if self.long() != 1:
                raise ValueError("IDL SAVE byte scalar without its count of 1")
            return np.uint8(self.take(4)[0])
        dt = np.dtype(_DTYPE[code])
        raw = self.take(4)[2:] if code in (2, 12) else self.take(max(4, dt.itemsize))   # 16-bit: low half of a word
        return np.frombuffer(raw, dt)[0].astype(dt.newbyteorder("="))

    def array(self, code: int, nelements: int, dims: list[int]):
        if code == _STRING:
            a = np.empty(nelements, object)
            for i in range(nelements):
                a[i] = self.string()
        else:
            if code == 1:                       # its length again (readsav does not rely on it either)
                self.long()
            dt = np.dtype(_DTYPE[code])
            if code in (2, 12):                 # 16-bit values, each in the low half of a 4-byte word
                a = np.frombuffer(self.take(4 * nelements), dt)[1::2]
            else:
                a = np.frombuffer(self.take(nelements * dt.itemsize), dt)
            a = a.astype(dt.newbyteorder("="))
        self.align()
        return a.reshape(dims[::-1]) if len(dims) > 1 else a


def _variable(s: _Stream, wanted):
    """(name, value) of a VARIABLE record, the stream just past its header; value None when not wanted."""
    name = s.text().lower()
    if wanted is not None and name not in wanted:
        return name, None
    code, flags = s.long(), s.long()
    if flags & _SYSTEM:
        return name, Unread(code, "system variable")
    if flags & _STRUCT or code in _KIND:
        return name, Unread(code, _KIND.get(code, "structure"))
    if code not in _DTYPE and code != _STRING:
        return name, (None if code == 0 else Unread(code, f"type code {code}"))
    dims = None
    if flags & _ARRAY:
        start = s.long()
        if start != 8:
            return name, Unread(code, f"array descriptor {start} (64-bit)")
        s.take(4)
        s.take(4)                               # bytes
        nelements, ndims = s.long(), s.long()
        s.take(8)
        dims = [s.long() for _ in range(s.long())][:ndims]
    if s.long() != 7:
        raise ValueError(f"IDL SAVE variable {name!r}: no data marker (VARSTART 7)")
    return name, (s.scalar(code) if dims is None else s.array(code, nelements, dims))


def read(path, names=None) -> dict[str, Any]:
    """The variables of an IDL SAVE file, or only those in names (lower case). ValueError when it is not one, is
    compressed, or ends early."""
    wanted = None if names is None else {n.lower() for n in names}
    out: dict[str, Any] = {}
    with open(path, "rb") as f:
        head = f.read(4)
        if head[:2] != b"SR":
            raise ValueError(f"{path}: not an IDL SAVE file (first bytes {head!r})")
        if head[2:] == b"\x00\x06":
            raise ValueError(f"{path}: a compressed IDL SAVE file, not read")
        if head[2:] != b"\x00\x04":
            raise ValueError(f"{path}: IDL SAVE format word {head[2:]!r} unknown")
        s = _Stream(f)
        while True:
            at = f.tell()
            kind = s.long()
            nxt = s.ulong() + (s.ulong() << 32)
            s.take(4)
            if kind == _END:
                return out
            if kind == _VARIABLE:
                name, value = _variable(s, wanted)
                if wanted is None or name in wanted:
                    out[name] = value
                if wanted is not None and wanted <= out.keys():
                    return out
            if nxt <= at:
                raise ValueError(f"{path}: IDL SAVE record at {at} points back to {nxt}")
            f.seek(nxt)

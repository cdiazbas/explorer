"""A file series: one FITS image (y, x) per file, the files as the t axis of one cube (t, y, x), in header time order.

    layout = series_layout(paths)       # every header read once; the frames are read elsewhere (io.SeriesReader)

Each file's image is its primary HDU, else its first image extension, its leading axes of length 1 dropped (stored as
(1, 1, y, x), it is (y, x)): a plain image is read at its data offset as a frame of a cube is; a tile-compressed one
(CompImageHDU, as JSOC serves SDO/AIA and HMI) is decompressed per read.
The time of a file is its mid-exposure where the header gives it (TIME_KEYS, the first one every file has); files
whose times cannot all be read keep their name order, and t is an index.
"""
import os
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import numpy as np

from .fits import BITPIX
from .layout import Layout

# a file's time: mid-exposure first (SDO's T_OBS, FITS's DATE-AVG), then the start of the exposure
TIME_KEYS = ("T_OBS", "DATE-AVG", "DATE-OBS", "DATE_OBS")
# what every file of a series must share, with the shape and the stored type; files that differ are refused
SAME = ("WAVELNTH", "INSTRUME", "BUNIT")
HEADER_THREADS = 16         # headers read at once
# a simulation snapshot's time, seconds of the simulation (Bifrost: "[s] Time of snapshot"), when no file has a date
ELAPSED = "ELAPSED"
_TIME = re.compile(r"^(\d{4})[-.](\d{2})[-.](\d{2})[T_ ](\d{2}):(\d{2}):(\d{2}(?:\.\d+)?)")


def _seconds(value) -> float | None:
    """A card's number of seconds (ELAPSED), None when it is not a finite number."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if np.isfinite(v) else None


def parse_time(value) -> np.datetime64 | None:
    """A header time as numpy datetime64 in microseconds: ISO (2026-06-07T06:52:01.07, a trailing Z allowed) or
    JSOC's 2026.06.07_06:52:01.07_TAI (the scale suffix is dropped: within one instrument the order is the same).
    None when it is not a time."""
    m = _TIME.match(str(value).strip())
    if m is None:
        return None
    y, mo, d, h, mi, s = m.groups()
    try:
        return np.datetime64(f"{y}-{mo}-{d}T{h}:{mi}:{float(s):09.6f}", "us")
    except ValueError:
        return None


@dataclass(frozen=True)
class SeriesLayout(Layout):
    """Layout of a series: shape (nt, ny, nx), axes (UTC, then the image's two), frame t in paths[t] at offsets[t]
    (the data of HDU hdus[t]). dtype, scale, zero and blank are every file's. compressed: every image is
    tile-compressed, read by decompressing (offsets then give where its table starts, for the storage probe)."""
    paths: tuple[str, ...] = ()
    offsets: tuple[int, ...] = ()
    hdus: tuple[int, ...] = ()
    compressed: bool = False
    t_sec: tuple[float, ...] | None = None      # seconds since dateref, per frame; None: no time in the headers
    dateref: str | None = None                  # ISO time of t_sec 0, the first frame's
    time_key: str | None = None                 # the header keyword the times come from
    notes: tuple[str, ...] = ()                 # what the reading decided, one line each, for the terminal


def _image_hdu(h, path):
    """(index, header, is compressed) of the file's image: the primary HDU when it has 2 axes or more, else the
    first image extension."""
    from astropy.io import fits

    for i, hdu in enumerate(h):
        if isinstance(hdu, fits.CompImageHDU):
            return i, hdu.header, True
        if isinstance(hdu, (fits.PrimaryHDU, fits.ImageHDU)) and int(hdu.header.get("NAXIS", 0)) >= 2:
            return i, hdu.header, False
    raise ValueError(f"{path}: no image HDU")


def _value(text: str):
    """A card's value: a string (quotes undone), T/F, an int, a float, or None when empty."""
    v = text.strip()
    if v.startswith("'"):
        out, i = [], 1
        while i < len(v):
            if v[i] == "'":
                if v[i + 1:i + 2] == "'":
                    out.append("'")
                    i += 2
                    continue
                break
            out.append(v[i])
            i += 1
        return "".join(out).rstrip()
    v = v.split("/", 1)[0].strip()
    if v in ("T", "F"):
        return v == "T"
    if not v:
        return None
    try:
        return int(v)
    except ValueError:
        return float(v.replace("D", "E"))


def _header_cards(f, at: int) -> tuple[dict, int]:
    """The valued cards of the header at byte `at` and the byte its data start at."""
    cards: dict = {}
    f.seek(at)
    while True:
        block = f.read(2880)
        if len(block) < 2880:
            raise ValueError("no END card")
        at += 2880
        for k in range(0, 2880, 80):
            card = block[k:k + 80].decode("ascii")
            key = card[:8].rstrip()
            if key == "END":
                return cards, at
            if card[8:10] == "= " and key not in cards:
                cards[key] = _value(card[10:])


def _image_cards(path) -> tuple[int, dict, bool, int]:
    """(HDU index, cards, compressed, data offset) of the file's image, from its header blocks alone (astropy
    takes 7 ms a file for the same, 30 times as long: a series of thousands opens in seconds, not minutes).
    ValueError when the file is not as expected; the caller then asks astropy."""
    with open(path, "rb") as f:
        at = 0
        for i in range(8):
            cards, data = _header_cards(f, at)
            n = int(cards.get("NAXIS", 0))
            if cards.get("ZIMAGE") is True and cards.get("XTENSION") == "BINTABLE":
                img = dict(cards)
                img["BITPIX"], img["NAXIS"] = cards["ZBITPIX"], cards["ZNAXIS"]
                for k in range(1, int(cards["ZNAXIS"]) + 1):
                    img[f"NAXIS{k}"] = cards[f"ZNAXIS{k}"]
                return i, img, True, data
            if n >= 2 and (i == 0 or cards.get("XTENSION") == "IMAGE"):
                return i, cards, False, data
            size = abs(int(cards.get("BITPIX", 8))) // 8 * int(cards.get("GCOUNT", 1)) * (
                int(np.prod([int(cards[f"NAXIS{k}"]) for k in range(1, n + 1)], dtype=np.int64)) if n else 0)
            size += int(cards.get("PCOUNT", 0)) if n else 0
            at = data + -(-size // 2880) * 2880
    raise ValueError(f"{path}: no image HDU among the first 8")


def _groups(values: list, paths: list[str]) -> str:
    """'a (3 files: x.fits, ..., z.fits); b (1 file: w.fits)': the files under each distinct value."""
    out = []
    for v in dict.fromkeys(values):
        ps = [os.path.basename(p) for p, w in zip(paths, values, strict=True) if w == v]
        shown = ", ".join(ps) if len(ps) <= 3 else f"{ps[0]}, ..., {ps[-1]}"
        out.append(f"{v!r} ({len(ps)} file{'s' * (len(ps) != 1)}: {shown})")
    return "; ".join(out)


def series_layout(paths) -> SeriesLayout:
    """The layout of the files as one cube (t, y, x), t in their header time order. ValueError for fewer than two
    files, files with another shape, stored type, scaling, WAVELNTH, INSTRUME or BUNIT (the groups listed), some
    compressed and some not, or two files at the same time (both named)."""
    from astropy.io import fits

    paths = [str(p) for p in paths]
    if len(paths) < 2:
        raise ValueError(f"a series needs two files or more, {len(paths)} given")
    if len(set(map(os.path.realpath, paths))) != len(paths):
        raise ValueError("a series lists the same file twice")

    def row(p):
        try:
            i, hdr, comp, off = _image_cards(p)
        except (ValueError, KeyError, UnicodeDecodeError):     # astropy's reading, and its message
            with fits.open(p, memmap=False, lazy_load_hdus=True, do_not_scale_image_data=True) as h:
                i, hdr, comp = _image_hdu(h, p)
                off = int(h.fileinfo(i)["datLoc"])
                hdr = dict(hdr)
        bitpix = int(hdr["BITPIX"])
        n = int(hdr["NAXIS"])
        shape = tuple(int(hdr[f"NAXIS{k}"]) for k in range(n, 0, -1))
        while len(shape) > 2 and shape[0] == 1:         # (1, 1, y, x) is one image: the same bytes, in the same order
            shape = shape[1:]
        return dict(path=p, hdu=i, offset=off, compressed=comp, bitpix=bitpix, shape=shape,
                    axes=tuple(str(hdr.get(f"CTYPE{k}", f"axis{k}")).split("-")[0] for k in (2, 1)),
                    scaling=(float(hdr.get("BSCALE", 1.0)), float(hdr.get("BZERO", 0.0)),
                             hdr.get("BLANK") if bitpix > 0 else None),
                    same={k: hdr.get(k) for k in SAME},
                    times={k: hdr.get(k) for k in TIME_KEYS}, elapsed=hdr.get(ELAPSED))

    with ThreadPoolExecutor(min(HEADER_THREADS, len(paths))) as ex:      # on network storage, latency overlapped
        rows = list(ex.map(row, paths))
    for what, get in (("shape", lambda r: r["shape"]), ("BITPIX", lambda r: r["bitpix"]),
                      ("BSCALE, BZERO, BLANK", lambda r: r["scaling"]),
                      ("tile compression", lambda r: r["compressed"]),
                      *((k, lambda r, k=k: r["same"][k]) for k in SAME)):
        vals = [get(r) for r in rows]
        if len(set(vals)) > 1:
            raise ValueError(f"not one series: {what} differs: {_groups(vals, paths)}")
    if len(rows[0]["shape"]) != 2:
        raise ValueError(f"a series needs one image (y, x) per file; {os.path.basename(paths[0])} has shape "
                         f"{rows[0]['shape']}")
    if rows[0]["bitpix"] not in BITPIX:
        raise ValueError(f"{paths[0]}: BITPIX {rows[0]['bitpix']} is not a FITS data type")
    notes = []
    key = next((k for k in TIME_KEYS if all(parse_time(r["times"][k]) is not None for r in rows)), None)
    t_sec = dateref = None
    got = [_seconds(r["elapsed"]) for r in rows] if key is None else []
    sim = [v for v in got if v is not None]
    if key is None and len(sim) == len(rows) and len(set(sim)) == len(sim):
        # a simulation's snapshots (ELAPSED): in their order, t its own seconds, no date (data.axes: sim_time)
        key = ELAPSED
        order = sorted(range(len(rows)), key=lambda i: sim[i])
        if order != sorted(range(len(rows)), key=lambda i: os.path.basename(rows[i]["path"])):
            notes.append(f"t in {key} order, which is not the files' name order")
        rows = [rows[i] for i in order]
        t_sec = tuple(float(sim[i]) for i in order)
    elif key is None:
        notes.append(f"no time in every header ({', '.join(TIME_KEYS)}, {ELAPSED}): t in name order, an index")
        rows.sort(key=lambda r: os.path.basename(r["path"]))
    else:
        ts = [np.datetime64(parse_time(r["times"][key]), "us") for r in rows]     # every one a time: key's rule
        order = sorted(range(len(rows)), key=lambda i: ts[i])
        for a, b in zip(order, order[1:], strict=False):
            if ts[a] == ts[b]:
                raise ValueError(f"two files at the same time ({key} {ts[a]}): {rows[a]['path']}, {rows[b]['path']}")
        if order != sorted(range(len(rows)), key=lambda i: os.path.basename(rows[i]["path"])):
            notes.append(f"t in {key} order, which is not the files' name order")
        rows = [rows[i] for i in order]
        ts = [ts[i] for i in order]
        ref = ts[0].astype("datetime64[ms]")
        t_sec = tuple(float((t - ref) / np.timedelta64(1, "us")) * 1e-6 for t in ts)
        dateref = str(ref)
    r0 = rows[0]
    comp = r0["compressed"]
    scale, zero, blank = r0["scaling"]
    dtype = np.dtype(BITPIX[r0["bitpix"]])
    return SeriesLayout(path=r0["path"], kind="series", offset=r0["offset"], shape=(len(rows), *r0["shape"]),
                        dtype=dtype.newbyteorder("=") if comp else dtype, axes=("UTC", *r0["axes"]), scale=scale,
                        zero=zero, blank=None if blank is None else int(blank),
                        paths=tuple(r["path"] for r in rows), offsets=tuple(r["offset"] for r in rows),
                        hdus=tuple(r["hdu"] for r in rows), compressed=comp, t_sec=t_sec, dateref=dateref,
                        time_key=key, notes=tuple(notes))

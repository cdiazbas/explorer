"""A file series: one FITS image (y, x) per file, the files as the t axis of one cube (t, y, x), in header time order.

    layout = series_layout(paths)       # every header read once; the frames are read elsewhere (io.SeriesReader)

Each file's image is its primary HDU, else its first image extension: a plain image is read at its data offset as a
frame of a cube is; a tile-compressed one (CompImageHDU, as JSOC serves SDO/AIA and HMI) is decompressed per read.
The time of a file is its mid-exposure where the header gives it (TIME_KEYS, the first one every file has); files
whose times cannot all be read keep their name order, and t is an index.
"""
import os
import re
from dataclasses import dataclass

import numpy as np

from .fits import BITPIX
from .layout import Layout

# a file's time: mid-exposure first (SDO's T_OBS, FITS's DATE-AVG), then the start of the exposure
TIME_KEYS = ("T_OBS", "DATE-AVG", "DATE-OBS", "DATE_OBS")
# what every file of a series must share, with the shape and the stored type; files that differ are refused
SAME = ("WAVELNTH", "INSTRUME", "BUNIT")
_TIME = re.compile(r"^(\d{4})[-.](\d{2})[-.](\d{2})[T_ ](\d{2}):(\d{2}):(\d{2}(?:\.\d+)?)")


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
    rows = []
    for p in paths:
        with fits.open(p, memmap=False, lazy_load_hdus=True, do_not_scale_image_data=True) as h:
            i, hdr, comp = _image_hdu(h, p)
            off = int(h.fileinfo(i)["datLoc"])
            bitpix = int(hdr["BITPIX"])
            n = int(hdr["NAXIS"])
            shape = tuple(int(hdr[f"NAXIS{k}"]) for k in range(n, 0, -1))
            rows.append(dict(path=p, hdu=i, offset=off, compressed=comp, bitpix=bitpix, shape=shape,
                             axes=tuple(str(hdr.get(f"CTYPE{k}", f"axis{k}")).split("-")[0] for k in (2, 1)),
                             scaling=(float(hdr.get("BSCALE", 1.0)), float(hdr.get("BZERO", 0.0)),
                                      hdr.get("BLANK") if bitpix > 0 else None),
                             same={k: hdr.get(k) for k in SAME},
                             times={k: hdr.get(k) for k in TIME_KEYS}))
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
    if key is None:
        notes.append(f"no time in every header ({', '.join(TIME_KEYS)}): t in name order, an index")
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

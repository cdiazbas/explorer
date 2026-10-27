"""A simulation snapshot's variables, one file each, as one cube (variable, z, y, x): Bifrost's, as helita's writefits
writes them (BIFROST_<run>_<variable>_<snapshot>.fits: a primary HDU [z, y, x] of float32, BTYPE the variable,
BUNIT its unit, a ' z-coordinate' extension of the heights).

    layout = variables_layout(paths)    # None when the files are not one snapshot's variables

The files are one snapshot's variables when every one is Bifrost's (INSTRUME), plain (no BSCALE/BZERO/BLANK), of
one shape and type, the same snapshot (OBJECT and ISNAP, else ELAPSED) and the same heights (the extension's
values, else CRVAL3 and CDELT3), each a different BTYPE. Only the headers and the heights are read here; a frame
(variable v, height z) is read where it is, from file v (io.VariablesReader), never a file whole.
"""
from dataclasses import dataclass

import numpy as np

from .series import SeriesLayout


@dataclass(frozen=True)
class VariablesLayout(SeriesLayout):
    """Layout of a snapshot's variables: shape (nvar, nz, ny, nx), axes ("VARIABLE", z's CTYPE, y's, x's); file v
    (paths[v]) holds variable v from offsets[v], its nz frames one after the other. btypes and bunits: each file's
    BTYPE and BUNIT as the header has them (BUNIT = T a logical, data.axes.unit_of)."""
    btypes: tuple[str, ...] = ()


def _same(a, b) -> bool:
    if isinstance(a, np.ndarray) or isinstance(b, np.ndarray):
        return isinstance(a, np.ndarray) and isinstance(b, np.ndarray) and bool(np.array_equal(a, b))
    return a == b


def _snapshot(path) -> dict | None:
    """What decides whether path is one of a snapshot's variables: its cards and heights; None when it is not a
    Bifrost cube of three axes."""
    from astropy.io import fits

    with fits.open(path, memmap=True, lazy_load_hdus=True, do_not_scale_image_data=True) as h:
        hd = h[0].header
        if not str(hd.get("INSTRUME", "")).strip().lower().startswith("bifrost") or int(hd.get("NAXIS", 0)) != 3:
            return None
        if hd.get("BSCALE", 1) != 1 or hd.get("BZERO", 0) != 0 or "BLANK" in hd:
            return None
        name = str(hd.get("CTYPE3", "")).split("-")[0].strip().lower() + "-coordinate"
        heights = next((np.array(e.data, float) for e in list(h)[1:]
                        if str(e.header.get("EXTNAME", "")).strip().lower() == name), None)
        btype = hd.get("BTYPE")
        return dict(path=str(path), offset=int(h.fileinfo(0)["datLoc"]), bitpix=int(hd["BITPIX"]),
                    shape=tuple(int(hd[f"NAXIS{k}"]) for k in (3, 2, 1)),
                    snap=(str(hd.get("OBJECT", "")).strip(),
                          hd.get("ISNAP") if "ISNAP" in hd else hd.get("ELAPSED")),
                    heights=heights if heights is not None else (hd.get("CRVAL3"), hd.get("CDELT3")),
                    btype=str(btype).strip() if isinstance(btype, str) and btype.strip() else None,
                    axes=tuple(str(hd.get(f"CTYPE{k}", f"axis{k}")).split("-")[0].strip() for k in (3, 2, 1)))


def variables_layout(paths) -> VariablesLayout | None:
    """The files as one snapshot's variables (see the module), in the order given; None when they are not, and
    then they open as they always did."""
    from .fits import BITPIX

    paths = [str(p) for p in paths]
    if len(paths) < 2:
        return None
    try:
        rows = [_snapshot(p) for p in paths]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if any(r is None for r in rows):
        return None
    r0 = rows[0]
    assert r0 is not None
    for key in ("bitpix", "shape", "snap", "heights", "axes"):
        if not all(r is not None and _same(r[key], r0[key]) for r in rows):
            return None
    btypes = [r["btype"] for r in rows if r is not None]
    if None in btypes or len(set(btypes)) != len(btypes) or r0["bitpix"] not in BITPIX:
        return None
    nz, ny, nx = r0["shape"]
    return VariablesLayout(path=paths[0], kind="variables", offset=r0["offset"], shape=(len(paths), nz, ny, nx),
                           dtype=np.dtype(BITPIX[r0["bitpix"]]), axes=("VARIABLE", *r0["axes"]),
                           paths=tuple(paths), offsets=tuple(r["offset"] for r in rows if r is not None),
                           hdus=(0,) * len(paths), btypes=tuple(b for b in btypes if b is not None))

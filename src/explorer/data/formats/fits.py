"""FITS primary HDU: the layout from the header alone; the data are read elsewhere (explicit preads)."""
import numpy as np

from .layout import Layout

# FITS BITPIX -> stored dtype; FITS data are big-endian
BITPIX = {8: "u1", 16: ">i2", 32: ">i4", 64: ">i8", -32: ">f4", -64: ">f8"}


def fits_layout(path) -> Layout:
    """Layout of the primary HDU. Axis names are the CTYPE up to its first dash ("WAVE-TAB" -> "WAVE", "UTC--TAB"
    -> "UTC"), as the prototype names them. BSCALE/BZERO/BLANK are read, so integer cubes can be scaled to
    physical values (the prototype ignored them)."""
    from astropy.io import fits

    with fits.open(path, memmap=False, lazy_load_hdus=True) as h:
        hdr = h[0].header
        offset = int(h.fileinfo(0)["datLoc"])
    n = int(hdr["NAXIS"])
    if n < 2:
        raise ValueError(f"{path}: the primary HDU has {n} axes; an image cube needs at least 2")
    bitpix = int(hdr["BITPIX"])
    if bitpix not in BITPIX:
        raise ValueError(f"{path}: BITPIX {bitpix} is not a FITS data type")
    shape = tuple(int(hdr[f"NAXIS{i}"]) for i in range(n, 0, -1))
    axes = tuple(str(hdr.get(f"CTYPE{i}", f"axis{i}")).split("-")[0] for i in range(n, 0, -1))
    blank = hdr.get("BLANK") if bitpix > 0 else None
    return Layout(path=str(path), kind="fits", offset=offset, shape=shape, dtype=np.dtype(BITPIX[bitpix]),
                  axes=axes, scale=float(hdr.get("BSCALE", 1.0)), zero=float(hdr.get("BZERO", 0.0)),
                  blank=None if blank is None else int(blank))

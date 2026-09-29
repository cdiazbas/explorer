"""LP (La Palma) cubes as SSTRED writes them for CRISPEX: a 512-byte ASCII header, then raw samples.

    _im.icube / _im.fcube   frames [nx, ny, nframes] (IDL order), frame index = (t * ns + s) * nl + l
    _sp.icube / _sp.fcube   the same values per pixel [nl, nt, npix * ns], pixel-major, Stokes fastest

An image cube's header does not say how its frames split into (t, s, lambda): that comes from its per-pixel
file (nl = its nx, nt = its ny), so the two are read as a pair.
"""
import re
from dataclasses import dataclass

import numpy as np

from .layout import Layout

HEADER_BYTES = 512
_DATATYPE = {"1": "u1", "2": "i2", "3": "i4", "4": "f4"}


@dataclass(frozen=True)
class LPHeader:
    text: str
    dtype: np.dtype
    nx: int
    ny: int
    nt: int
    ns: int


def lp_header(path) -> LPHeader:
    """Parse the header, e.g. "stokes=[I], ns=1 :  datatype=2 (integer), dims=3, nx=21, ny=66, nt=4068240,
    endian=l"."""
    with open(path, "rb") as f:
        raw = f.read(HEADER_BYTES)
    text = raw.rstrip(b"\0").decode("ascii", "replace")
    kv = dict(re.findall(r"(\w+)=([^,:]+)", text))
    try:
        dt = _DATATYPE[kv["datatype"].split()[0]]
        order = "<" if kv.get("endian", "l").strip() == "l" else ">"
        return LPHeader(text=text.strip(), dtype=np.dtype(order + dt), nx=int(kv["nx"]), ny=int(kv["ny"]),
                        nt=int(kv["nt"]), ns=int(kv.get("ns", 1)))
    except (KeyError, ValueError) as e:
        raise ValueError(f"{path}: not an LP cube header ({e}): {text[:80]!r}") from None


def lp_pair_layouts(im_path, sp_path) -> tuple[Layout, Layout]:
    """Layouts of an LP image cube and its per-pixel file.

    Image (nt, ns, nl, ny, nx); per-pixel (ny, nx, ns, nt, nl), Stokes before t inside a pixel as the prototype's
    SpLP reads it (not checked yet against a real multi-Stokes _sp.icube)."""
    im, sp = lp_header(im_path), lp_header(sp_path)
    nx, ny, nframes = im.nx, im.ny, im.nt
    nl, nt, ns = sp.nx, sp.ny, sp.ns
    if nl * nt * ns != nframes or sp.nt != nx * ny * ns:
        raise ValueError(f"{im_path} and {sp_path} do not describe the same cube: image {nx}x{ny}x{nframes}, "
                         f"per-pixel nl={nl} nt={nt} ns={ns} npix*ns={sp.nt}")
    image = Layout(path=str(im_path), kind="lp", offset=HEADER_BYTES, shape=(nt, ns, nl, ny, nx), dtype=im.dtype,
                   axes=("UTC", "STOKES", "WAVE", "HPLT", "HPLN"))
    per_pixel = Layout(path=str(sp_path), kind="lp", offset=HEADER_BYTES, shape=(ny, nx, ns, nt, nl), dtype=sp.dtype,
                       axes=("HPLT", "HPLN", "STOKES", "UTC", "WAVE"))
    return image, per_pixel

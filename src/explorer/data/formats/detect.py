"""Which format a file is, from its first bytes rather than its name."""
from .fits import fits_layout
from .layout import Layout
from .lp import HEADER_BYTES


def detect(path) -> str:
    """"fits" (starts with the SIMPLE card), "lp" (an LP header), or ValueError."""
    with open(path, "rb") as f:
        head = f.read(HEADER_BYTES)
    if head.startswith(b"SIMPLE  ="):
        return "fits"
    text = head.rstrip(b"\0")
    if b"datatype=" in text and b"dims=" in text and all(32 <= c < 127 for c in text):
        return "lp"
    raise ValueError(f"{path}: neither FITS nor an LP cube (first bytes {head[:20]!r})")


def open_layout(path) -> Layout:
    """Layout of an image cube. An LP image cube is split into (t, s, lambda) by its per-pixel file, looked up next
    to it (formats.lp_pair_layouts); without one, by the scans in its name (formats.lp_single_layout)."""
    kind = detect(path)
    if kind == "fits":
        return fits_layout(path)
    from .companions import companions
    from .lp import lp_pair_layouts, lp_single_layout

    sp = next((p for p in companions(path) if detect(p) == "lp"), None)
    return lp_pair_layouts(path, sp)[0] if sp is not None else lp_single_layout(path)

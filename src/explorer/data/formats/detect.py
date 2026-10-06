"""Which format a file is, from its first bytes rather than its name."""
from ...obs import get_logger
from .fits import fits_layout
from .layout import Layout
from .lp import HEADER_BYTES

log = get_logger("data")
_said: set[str] = set()     # files whose counts were reported: linking reads a layout up to three times (data.link)


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
    to it (formats.lp_pair_layouts); without one, by the scans in its name (formats.lp_single_layout). Its values are
    scaled and its padding is NaN by the IDL save file beside it (formats.lp_values); without one they are counts."""
    kind = detect(path)
    if kind == "fits":
        return fits_layout(path)
    from .companions import companions
    from .lp import lp_pair_layouts, lp_sidecar, lp_single_layout, lp_values

    sp = next((p for p in companions(path) if detect(p) == "lp"), None)
    layout = lp_pair_layouts(path, sp)[0] if sp is not None else lp_single_layout(path)
    side = lp_sidecar(path)
    if side is None:
        if layout.dtype.kind in "iu" and str(path) not in _said:    # nothing says what the counts are: shown
            _said.add(str(path))                                        # as they are; said once per file
            log.warning("%s: values in counts, padding as data: no <stem>_im_times+wvl.idlsave beside it or the "
                        "file it links to", path)
        return layout
    try:
        return lp_values(layout, side)
    except (OSError, ValueError) as e:                  # the cube still opens, in counts
        log.warning("%s not read, values of %s left as stored: %s", side, path, e)
        return layout

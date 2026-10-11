"""A per-pixel file's image cube, written once: SSTRED's _sp.fits (numpy (y, x, s, t, lambda)) transposed to the _im
layout (t, s, lambda, y, x), so that an image is one read instead of a pass over the whole file (io.PerPixelFrames).

    estimate(frames)                    what images cost from the per-pixel file, and what a copy would cost and give
    transpose(sp, out)                  write the copy, streaming: blocks of rows of pixels -> rows of every image
    output_path(sp, out)                where the copy goes (a directory given: <stem>_im<tag>.fits in it)

Never beside the per-pixel file, nor in the tree a linked one comes from (read_only_trees): the observatory's
reduced data are read, never written to.
"""
import os
import re
import shutil
import time
from dataclasses import dataclass

import numpy as np

from .formats import fits_layout
from .formats.companions import _SP
from .formats.layout import spatial_lead
from .io import PerPixelFrames, ShortRead

READ_ONLY_ENV = "EXPLORER_READ_ONLY"
BLOCK = 256 << 20           # bytes of pixel records read at a time; memory holds this and its transpose
GB = 1e9

# per-axis keywords of a FITS header, renumbered with their axis: (name, axis)(rest), (name, axis, _, other axis)
_ONE = re.compile(r"^(CTYPE|CUNIT|CRPIX|CRVAL|CDELT|CNAME|CROTA|CSYER|CRDER|CWDIS|CPERI|CZPHS|NAXIS)(\d)([A-Z]?)$")
_TWO = re.compile(r"^(PS|PV|PC|CD)(\d)_(\d+)([A-Z]?)$")


def read_only_trees(sp_path) -> list[str]:
    """Where a copy of the per-pixel file at sp_path is never written: the directory the file itself is in (links
    followed); for a file reached through a link (a cube used through a link in data/), all of the tree its target
    is in, from the first directory below what the link and its target have in common (another disk, another
    user's tree: the observatory's reduced data), while beside the link is allowed; and the directories in
    EXPLORER_READ_ONLY (separated as PATH is)."""
    given, real = os.path.abspath(str(sp_path)), os.path.realpath(str(sp_path))
    trees = [os.path.dirname(real)]
    if given != real:
        common = os.path.commonpath([os.path.dirname(given), real])
        below = os.path.relpath(real, common).split(os.sep)[0]
        trees.append(os.path.join(common, below))
    trees += [os.path.realpath(p) for p in os.environ.get(READ_ONLY_ENV, "").split(os.pathsep) if p]
    return trees


def refused_output(path, sp_path) -> str | None:
    """Why the copy of the per-pixel file at sp_path may not be written at path (under one of read_only_trees, as
    given or once links are followed), or None."""
    out = os.path.dirname(os.path.abspath(str(path)))
    where = {out, os.path.realpath(out)}
    for top in read_only_trees(sp_path):
        for p in where:
            if p == top or p.startswith(top.rstrip(os.sep) + os.sep):
                return (f"{path} is under {top}, where the per-pixel file's data are: never written there; give a "
                        f"directory of your own")
    return None


def image_name(sp_path) -> str:
    """<stem>_im<tag>.fits for <stem>_sp<tag>.<ext>; <name>_im.fits for a per-pixel file named otherwise."""
    name = os.path.basename(str(sp_path))
    m = _SP.match(name)
    return f"{m.group(1)}_im{m.group(2)}.fits" if m else os.path.splitext(name)[0] + "_im.fits"


def output_path(sp_path, out) -> str:
    """The copy's path: out itself, or <stem>_im<tag>.fits in it when out is a directory."""
    return os.path.join(out, image_name(sp_path)) if os.path.isdir(out) else str(out)


def default_directory(sp_path) -> str:
    """Where the sheet proposes the copy: beside the path given (a link's directory: the copy pairs with the link
    there), else the current directory, else the home directory; the first that this user may write and where it
    may go (refused_output)."""
    for d in (os.path.dirname(os.path.abspath(str(sp_path))), os.getcwd(), os.path.expanduser("~")):
        if os.access(d, os.W_OK) and refused_output(os.path.join(d, "x"), sp_path) is None:
            return d
    return os.path.expanduser("~")


@dataclass(frozen=True)
class Estimate:
    image_s: float          # seconds an image takes from the per-pixel file here
    how: str                # how image_s was found
    frames: int             # images in the cube
    copy_bytes: int         # the copy's size on disk
    factor: int             # images about this many times faster from the copy (estimate)
    out_dir: str            # where the command writes it
    free_bytes: int | None  # free there, None when not known
    command: str


def estimate(frames: PerPixelFrames, command: str = "explorer") -> Estimate:
    """What an image costs from the per-pixel file, and what a transposed copy costs and gives. An image is one pass
    over the file: the latest pass's time once one was made, else the file's size over the throughput of a few
    reads made now (throughput: optimistic when the file is in the page cache). The factor is an estimate: an image
    from the copy reads one image's bytes, 1 / frames of a pass (measured on Halpha 6563, 13 GB, 735 images: 7-26 s
    a pass against 9-21 ms an image from its _im, bench/sp_frames.py)."""
    sp = frames.sp
    if frames.passes:
        image_s, how = frames.passes[-1], "the latest image took this long, a pass over the file"
    else:
        bps = frames.throughput()
        image_s = sp.nbytes / bps
        how = (f"the file's {sp.nbytes / GB:.1f} GB at {bps / 1e6:.0f} MB/s, the speed of 4 reads of 8 MB made now "
               f"(less if the file is already in memory)")
    n = int(np.prod(frames.shape[:-2]))
    out = default_directory(sp.path)
    try:
        free: int | None = shutil.disk_usage(out).free
    except OSError:
        free = None
    size = os.path.getsize(sp.path)
    return Estimate(image_s, how, n, size, n, out, free,
                    f"{command} transpose {_quoted(os.path.abspath(sp.path))} {_quoted(out)}")


def _quoted(p: str) -> str:
    import shlex

    return shlex.quote(str(p))


def _image_header(sp_header):
    """The image cube's header from the per-pixel file's: its axes renumbered (FITS axis 1 = x, 2 = y, 3 = lambda,
    4 = Stokes, 5 = t, from the per-pixel file's 1 = lambda, 2 = t, 3 = Stokes, 4 = x, 5 = y), every per-axis keyword
    with them (CTYPEi, CRPIXi, PSi_j, PCi_j, ...); its checksums dropped (the bytes change, the values do not)."""
    from astropy.io import fits

    to = {4: 1, 5: 2, 1: 3, 3: 4, 2: 5}         # per-pixel file's FITS axis -> the image cube's
    out = fits.Header()
    for card in sp_header.cards:
        k = card.keyword
        if k in ("CHECKSUM", "DATASUM"):
            continue
        m = _ONE.match(k)
        if m and int(m.group(2)) in to:
            k = f"{m.group(1)}{to[int(m.group(2))]}{m.group(3)}"
        m2 = _TWO.match(k)
        if m2 and int(m2.group(2)) in to:
            j = m2.group(3)
            if m2.group(1) in ("PC", "CD") and int(j) in to:
                j = str(to[int(j)])
            k = f"{m2.group(1)}{to[int(m2.group(2))]}_{j}{m2.group(4)}"
        if k == "COMMENT":
            out.add_comment(card.value)
        elif k == "HISTORY":
            out.add_history(card.value)
        elif k == "":
            out.add_blank(card.value)
        else:
            out.append((k, card.value, card.comment), end=True)
    order = ["SIMPLE", "BITPIX", "NAXIS"] + [f"NAXIS{i}" for i in range(1, 6)]
    head = fits.Header([(k, out[k], out.comments[k]) for k in order])
    for k in order:
        del out[k]
    head.extend(out, end=True)
    return head


def transpose(sp_path, out_path, block: int = BLOCK, progress=None) -> dict:
    """Write the image cube of the per-pixel FITS file at sp_path to out_path: its header with the axes renumbered,
    the images (t, s, lambda, y, x), then the per-pixel file's extensions (WCS-TAB, ...) as they are, so that it
    pairs with the per-pixel file (formats.pairs) and reads the same times and wavelengths. Streaming: block bytes of
    pixel records at a time (rows of pixels), each written out as those rows of every image; memory holds about
    twice block. Written to out_path + ".part", renamed when complete. progress(done_bytes, total_bytes, seconds),
    after each block. ValueError: not a per-pixel FITS file, output read only or existing. Returns the timings."""
    from astropy.io import fits

    why = refused_output(out_path, sp_path)
    if why is not None:
        raise ValueError(why)
    if os.path.exists(out_path):
        raise ValueError(f"{out_path} exists: not overwritten")
    sp = fits_layout(sp_path)
    if len(sp.shape) != 5 or len(spatial_lead(sp.axes)) != 2:
        raise ValueError(f"{sp_path}: not a per-pixel FITS file (5 axes, y and x first): {sp.axes} {sp.shape}")
    ny, nx, ns, nt, nl = sp.shape
    it = sp.dtype.itemsize
    record = ns * nt * nl * it
    rows = max(1, int(block) // (nx * record))
    frame_bytes = ny * nx * it
    with fits.open(sp_path, memmap=False, lazy_load_hdus=True) as h:
        header = _image_header(h[0].header)
        header.add_history(f"images of {os.path.basename(str(sp_path))} transposed by explorer transpose")
        exts = [hdu.copy() for hdu in h[1:]]
    for k, n in enumerate((nx, ny, nl, ns, nt), 1):
        header[f"NAXIS{k}"] = n
    head = header.tostring().encode("ascii")
    data = frame_bytes * nt * ns * nl
    pad = -data % 2880
    part = str(out_path) + ".part"
    t0 = time.perf_counter()
    reading = writing = 0.0
    src = os.open(sp_path, os.O_RDONLY)
    dst = os.open(part, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        os.write(dst, head)
        os.ftruncate(dst, len(head) + data + pad)           # the data's padding: zeros, as FITS asks
        for y0 in range(0, ny, rows):
            y1 = min(ny, y0 + rows)
            q = time.perf_counter()
            n = (y1 - y0) * nx * record
            b = os.pread(src, n, sp.offset + y0 * nx * record)
            if len(b) != n:
                raise ShortRead(f"read {len(b)} of {n} bytes of rows {y0}..{y1} in {sp_path}")
            blk = np.frombuffer(b, sp.dtype).reshape(y1 - y0, nx, ns, nt, nl)
            frames = np.ascontiguousarray(blk.transpose(3, 2, 4, 0, 1)).reshape(nt * ns * nl, -1)
            del b, blk
            reading += time.perf_counter() - q
            q = time.perf_counter()
            at = len(head) + y0 * nx * it
            for k in range(frames.shape[0]):
                os.pwrite(dst, frames[k].data, at + k * frame_bytes)
            writing += time.perf_counter() - q
            if progress is not None:
                progress(y1 * nx * record, ny * nx * record, time.perf_counter() - t0)
    finally:
        os.close(src)
        os.close(dst)
    if exts:
        with fits.open(part, mode="append", memmap=False) as h:
            for e in exts:
                h.append(e)
    os.replace(part, out_path)
    return dict(seconds=time.perf_counter() - t0, reading=reading, writing=writing, bytes=data,
                block_rows=rows)

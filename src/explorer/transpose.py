"""`explorer transpose <file_sp.fits> <directory or file_im.fits>`: the image cube of a per-pixel file, written once
(data.transpose), so that its images are one read each instead of a pass over the whole per-pixel file. A link to
the per-pixel file is made beside the copy, so that `explorer <copy>` finds it there."""
import argparse
import os
import sys

from ._name import APP_NAME
from .obs import say


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog=f"{APP_NAME} transpose",
        description="Write the image cube (_im.fits) of a per-pixel FITS file (_sp.fits, numpy (y, x, s, t, lambda)), "
                    "reading it once in blocks of rows, and link the per-pixel file beside it. Never beside the "
                    "per-pixel file, nor in the tree a linked one comes from, nor under EXPLORER_READ_ONLY.")
    ap.add_argument("sp", help="the per-pixel file (_sp.fits)")
    ap.add_argument("out", help="a directory (the copy is <stem>_im.fits in it) or the copy's path")
    ap.add_argument("--block-mb", type=int, default=256, help="MB of the per-pixel file read at a time (memory: "
                                                              "about twice this; default 256)")
    ap.add_argument("--no-link", action="store_true", help="no link to the per-pixel file beside the copy")
    a = ap.parse_args(argv)
    from .data.transpose import image_name, output_path, transpose

    if not os.path.exists(a.sp):
        say.error(f"transpose: no such file: {a.sp}")
        return 2
    out = output_path(a.sp, a.out)
    last = [-1]

    def progress(done, total, seconds):
        pct = int(100 * done / total)
        if pct // 5 != last[0] // 5 or done == total:
            last[0] = pct
            rate = done / max(1e-6, seconds)
            left = (total - done) / max(1.0, rate)
            print(f"[{APP_NAME} transpose] {pct:3d} %  {done / 1e9:.2f} of {total / 1e9:.2f} GB  "
                  f"{rate / 1e6:.0f} MB/s  {seconds:.0f} s, about {left:.0f} s left", file=sys.stderr, flush=True)

    try:
        r = transpose(a.sp, out, block=a.block_mb << 20, progress=progress)
    except (ValueError, OSError) as e:
        say.error(f"transpose: {e}")
        return 1
    print(f"[{APP_NAME} transpose] {out}: {r['bytes'] / 1e9:.2f} GB in {r['seconds']:.1f} s (reading "
          f"{r['reading']:.1f} s, writing {r['writing']:.1f} s)", file=sys.stderr)
    sp_name = os.path.basename(a.sp)
    beside = os.path.join(os.path.dirname(os.path.abspath(out)), sp_name)
    if a.no_link or os.path.basename(out) != image_name(a.sp):
        say.info(f"transpose: open it with: {APP_NAME} {out} --sp {a.sp}")
    else:
        if not os.path.lexists(beside):
            os.symlink(os.path.abspath(a.sp), beside)
            say.info(f"transpose: linked {beside} -> {os.path.abspath(a.sp)}")
        say.info(f"transpose: open it with: {APP_NAME} {out}")
    return 0

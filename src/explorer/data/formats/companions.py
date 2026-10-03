"""The per-pixel files that belong to an image cube: <stem>_sp.fits, _sp.icube, _sp.fcube, best first. The same
format as the image cube comes first: an LP image cube holds counts, its FITS sibling physical values, so a FITS
per-pixel file next to an LP image cube would put the spectra and the image in different units."""
import os
import re

ORDER = ("_sp.fits", "_sp.icube", "_sp.fcube")


def companions(im_path) -> list[str]:
    """Existing per-pixel files for <stem>_im.(fits|icube|fcube): looked up next to the file itself and next to
    the path given (which may be a link from another directory), as the prototype's find_sp does."""
    real_dir, name = os.path.split(os.path.realpath(im_path))
    stem = re.sub(r"_im\.(fits|icube|fcube)$", "", name)
    ext = os.path.splitext(name)[1]
    # an LP image cube: its own kind first, then the other LP kind, the FITS one last
    order = (sorted(ORDER, key=lambda suffix: (not suffix.endswith(ext), suffix == "_sp.fits"))
             if ext in (".icube", ".fcube") else ORDER)
    dirs = [real_dir, os.path.dirname(os.path.abspath(im_path))]
    out: list[str] = []
    for d in dirs:
        for suffix in order:
            p = os.path.join(d, stem + suffix)
            if p not in out and os.path.exists(p):
                out.append(p)
    return out

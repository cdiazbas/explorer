"""The per-pixel files that belong to an image cube: <stem>_sp.fits, _sp.icube, _sp.fcube, best first."""
import os
import re

ORDER = ("_sp.fits", "_sp.icube", "_sp.fcube")


def companions(im_path) -> list[str]:
    """Existing per-pixel files for <stem>_im.(fits|icube|fcube): looked up next to the file itself and next to
    the path given (which may be a link from another directory), as the prototype's find_sp does."""
    real_dir, name = os.path.split(os.path.realpath(im_path))
    stem = re.sub(r"_im\.(fits|icube|fcube)$", "", name)
    dirs = [real_dir, os.path.dirname(os.path.abspath(im_path))]
    out: list[str] = []
    for d in dirs:
        for suffix in ORDER:
            p = os.path.join(d, stem + suffix)
            if p not in out and os.path.exists(p):
                out.append(p)
    return out

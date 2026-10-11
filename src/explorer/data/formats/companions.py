"""The per-pixel files that belong to an image cube: <stem>_sp.fits, _sp.icube, _sp.fcube, best first. The same
format as the image cube comes first: an LP image cube holds counts, its FITS sibling physical values, so a FITS
per-pixel file next to an LP image cube would put the spectra and the image in different units. A tag between _im
and the extension (SSTRED's .aligned6173, a cube aligned to another line's grid) is kept: <stem>_sp.<tag>.<ext>.

The other way round, for a per-pixel file given where an image cube is wanted (`explorer c_sp.fits`):

    per_pixel(path)                     # why the file is a per-pixel file, or None
    opening(path, sp)                   # the image cube to open and its per-pixel file, or ValueError
"""
import os
import re
from typing import NamedTuple

ORDER = ("_sp.fits", "_sp.icube", "_sp.fcube")
IMAGE_ORDER = ("_im.fits", "_im.icube", "_im.fcube")
_SP = re.compile(r"(.*)_sp((?:\.[^.]+)*?)\.(fits|icube|fcube)$")


def _ordered(suffixes, ext: str) -> tuple[str, ...]:
    """suffixes, an LP file's first: its own kind, then the other LP kind, the FITS one last."""
    if ext not in (".icube", ".fcube"):
        return tuple(suffixes)
    return tuple(sorted(suffixes, key=lambda suffix: (not suffix.endswith(ext), suffix.endswith(".fits"))))


def _next_to(path, stem: str, tag: str, mark: str, suffixes) -> list[str]:
    """Existing <stem><mark><tag><ext> for each suffix (mark + ext), next to the file itself and next to the path
    given (which may be a link from another directory)."""
    real_dir = os.path.dirname(os.path.realpath(path))
    out: list[str] = []
    for d in (real_dir, os.path.dirname(os.path.abspath(path))):
        for suffix in suffixes:
            p = os.path.join(d, stem + suffix.replace(mark, mark + tag, 1))
            if p not in out and os.path.exists(p):
                out.append(p)
    return out


def companions(im_path) -> list[str]:
    """Existing per-pixel files for <stem>_im.(fits|icube|fcube): looked up next to the file itself and next to
    the path given (which may be a link from another directory), as the prototype's find_sp does."""
    name = os.path.basename(os.path.realpath(im_path))
    m = re.match(r"(.*)_im((?:\.[^.]+)*?)\.(fits|icube|fcube)$", name)
    stem, tag = (m.group(1), m.group(2)) if m else (name, "")
    return _next_to(im_path, stem, tag, "_sp", _ordered(ORDER, os.path.splitext(name)[1]))


def images(sp_path) -> list[str]:
    """Existing image cubes <stem>_im[.tag].(fits|icube|fcube) for a per-pixel file <stem>_sp[.tag].<ext>, its own
    format first, found as companions() finds the other way; none when the name has no _sp."""
    name = os.path.basename(os.path.realpath(sp_path))
    m = _SP.match(name) or _SP.match(os.path.basename(str(sp_path)))
    if m is None:
        return []
    return _next_to(sp_path, m.group(1), m.group(2), "_im", _ordered(IMAGE_ORDER, "." + m.group(3)))


def _image_grid(path) -> tuple[int, int, int] | None:
    """(ny, nx, frames) of an image cube from its header; None when its header says it is not one."""
    from .detect import detect
    from .layout import spatial_lead

    if detect(path) == "fits":
        from .fits import fits_layout

        lay = fits_layout(path)
        if spatial_lead(lay.axes):
            return None
        frames = 1
        for n in lay.shape[:-2]:
            frames *= int(n)
        return int(lay.shape[-2]), int(lay.shape[-1]), frames
    from .lp import lp_header

    h = lp_header(path)
    return h.ny, h.nx, h.nt


def pairs(im_path, sp_path) -> bool:
    """Whether the file at sp_path holds the per-pixel values of the image cube at im_path, by their headers:
    a FITS one (ny, nx, then as many samples per pixel as the image has frames), an LP one (nx * ny * ns
    pixel-Stokes, nl * nt * ns per pixel as the image's frames). False when either cannot be read."""
    from .detect import detect

    try:
        grid = _image_grid(im_path)
        if grid is None:
            return False
        ny, nx, frames = grid
        if detect(sp_path) == "fits":
            from .fits import fits_layout

            shape = fits_layout(sp_path).shape
            per = 1
            for n in shape[2:]:
                per *= int(n)
            return len(shape) > 2 and tuple(shape[:2]) == (ny, nx) and per == frames
        from .lp import lp_header

        h = lp_header(sp_path)
        return h.nt == ny * nx * h.ns and h.nx * h.ny * h.ns == frames
    except (OSError, ValueError):
        return False


def per_pixel(path) -> str | None:
    """Why the file at path is a per-pixel file rather than an image cube, in a few words for the messages, or None
    when it reads as an image cube. A FITS file by its header first, whatever its name: spatial axes before the
    image's (SSTRED's _sp.fits: numpy HPLT, HPLN, STOKES, UTC, WAVE) are one; spatial axes last are an image cube.
    Then, for a name with _sp, by the headers of the image cube next to it (pairs); an LP file's header alone does
    not say it. Last, an LP file named _sp with more frames than pixels in a frame (SSTRED's nb_6563 _sp.icube:
    21 x 66 per frame, 4068240 frames). OSError or ValueError when the file is neither FITS nor LP."""
    from .detect import detect
    from .layout import SPATIAL, spatial_lead

    kind = detect(path)
    if kind == "fits":
        from .fits import fits_layout

        axes = fits_layout(path).axes
        first = spatial_lead(axes)
        if first:
            return f"its header puts {', '.join(first)} first"
        if all(str(a).upper() in SPATIAL for a in axes[-2:]):
            return None
    for im in images(path):
        if pairs(im, path):
            return "by its name and dims"
    if kind == "lp" and _SP.match(os.path.basename(str(path))):
        from .lp import lp_header

        h = lp_header(path)
        if h.nt > h.nx * h.ny:
            return f"named _sp, {h.nt} frames of {h.nx} x {h.ny} pixels"
    return None


class Opening(NamedTuple):
    """What to open for a file given as a cube: the image cube, its per-pixel file (None: the one found next to
    it), and what was changed and why ("" when nothing)."""
    path: str
    sp: str | None
    note: str = ""


def opening(path, sp=None, no_sp=False) -> Opening:
    """The image cube to open for the file given as one, and its per-pixel file. A per-pixel file given as the
    cube (per_pixel) opens its image cube next to it, with it; with --sp naming that image cube, the two are taken
    the right way round. A FITS per-pixel file without its image cube next to it opens alone, its images read from
    it (_alone; Opening(path, path, note)), as it does with --sp naming the file itself. --sp naming a FITS image
    cube (its spatial axes last) is refused, as is an LP per-pixel file without an image cube next to it:
    ValueError, its message naming what was given and what is needed. A file that cannot be read is passed on as
    given, for the opening to say why. no_sp: only the wording ("without it")."""
    name = os.path.basename(str(path))
    try:
        why = per_pixel(path)
    except (OSError, ValueError):
        why = None
    if why is not None:
        with_it = "without it (--nosp)" if no_sp else "with it"
        if sp is not None and os.path.realpath(str(sp)) == os.path.realpath(str(path)) and _alone(path):
            return Opening(str(path), str(path), f"{name} is a per-pixel file ({why}), and --sp names it too: "
                                                 f"opened alone, images read from it, each one a pass over the "
                                                 f"whole file")
        if sp is not None:
            if pairs(sp, path):
                return Opening(str(sp), str(path), f"{name} is the per-pixel file of {os.path.basename(str(sp))} "
                                                   f"({why}), and --sp names that one: opening it {with_it}")
            raise ValueError(f"{name} is a per-pixel file ({why}), and --sp {os.path.basename(str(sp))} is not its "
                             f"image cube: give the image cube first")
        im = next((p for p in images(path) if pairs(p, path)), None)
        if im is None:
            m = _SP.match(name)
            wanted = "its image cube (_im)" if m is None else f"its image cube {m.group(1)}_im{m.group(2)}.{m.group(3)}"
            if _alone(path):
                return Opening(str(path), str(path), f"{name} is a per-pixel file ({why}), and {wanted} is not next "
                                                     f"to it: images read from it, each one a pass over the whole "
                                                     f"file; spectra as usual")
            if m is None:
                raise ValueError(f"{name} is a per-pixel file ({why}), not an image cube: open its image cube "
                                 f"(_im) with --sp {name}")
            raise ValueError(f"{name} is a per-pixel file ({why}), not an image cube, and its image cube "
                             f"{m.group(1)}_im{m.group(2)}.{m.group(3)} is not next to it: open that one (its "
                             f"per-pixel file is found next to it; an LP per-pixel file's header does not say the "
                             f"image's size, so its images cannot be read from it alone)")
        return Opening(im, str(path), f"{name} is the per-pixel file of {os.path.basename(im)} ({why}): opening "
                                      f"that one {with_it}")
    if sp is not None and not pairs(path, sp):
        last = _image_axes(sp)
        if last:
            raise ValueError(f"--sp {os.path.basename(str(sp))} is an image cube (its header puts "
                             f"{', '.join(last)} last), not a per-pixel file")
    return Opening(str(path), None if sp is None else str(sp))


def _alone(path) -> bool:
    """Whether a per-pixel file can be opened without its image cube: a FITS one with 5 axes, spatial first (y, x,
    s, t, lambda), whose header says the image's size (io.PerPixelFrames reads its images). Not an LP one: its header
    gives only pixels times Stokes."""
    from .detect import detect
    from .fits import fits_layout
    from .layout import spatial_lead

    try:
        if detect(path) != "fits":
            return False
        lay = fits_layout(path)
    except (OSError, ValueError):
        return False
    return len(lay.shape) == 5 and len(spatial_lead(lay.axes)) == 2


def _image_axes(path) -> tuple[str, ...]:
    """The two spatial axes a FITS image cube's header puts last; empty for any other file, or one not read."""
    from .detect import detect
    from .fits import fits_layout
    from .layout import SPATIAL

    try:
        axes = fits_layout(path).axes if detect(path) == "fits" else ()
    except (OSError, ValueError):
        return ()
    last = tuple(str(a).upper() for a in axes[-2:])
    return last if len(axes) > 2 and all(a in SPATIAL for a in last) else ()

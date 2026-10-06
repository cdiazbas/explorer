"""Linking cubes to the first one (ROADMAP E8.1): which of the others can follow it, and how their leading axes are
read. The first cube leads: its grid and its times are everyone's. This first step links only what lies on the
same grid with the same times (or a single frame, shown at every t); other grids and cadences are refused with
what does not match, never linked wrong.

    link = plan(main, path)             # main: a Dataset (or describe(path)); path: another cube
    if link.ok: Dataset.open(path, axes=link.axes) ... else: print(link.why)

How a linked cube's leading axes are read, the first evidence that says it:
1. its own: the FITS header, its per-pixel file, the scans in its name (axes.roles, formats.lp_single_layout);
2. the first cube: frames that nothing names, as many as the first cube's times, are those times (a field or
   velocity map of the same series: Blos, Vlos); a single frame is shown at every t;
3. else it is not linked, and the reason says what --axes would make it.
Then the checks: the same grid (ny, nx); the same number of times; where both have times, the same times, within
half the first cube's cadence (an LP cube's are times of day: compared as such).
"""
import os
from dataclasses import dataclass

import numpy as np

from . import axes as _axes
from .formats import open_layout


@dataclass(frozen=True)
class CubeInfo:
    """What linking needs of a cube, without opening it for reading: its grid, the roles of its leading axes and
    its physical axes. A Dataset has the same attributes."""
    path: str
    ny: int
    nx: int
    roles: _axes.Roles
    axes: _axes.Axes


@dataclass(frozen=True)
class Link:
    path: str
    ok: bool
    axes: str | None = None         # what to open it with (Dataset's axes=), when its own reading would be wrong
    how: str = ""                   # how its axes were read and checked, for the start-up's log
    why: str = ""                   # when not linked: what does not match


def describe(path, axes: str | None = None) -> CubeInfo:
    layout = open_layout(path)
    ny, nx = (int(n) for n in layout.shape[-2:])
    r = _axes.roles(layout.axes, layout.shape, axes)
    ax = _axes.from_fits(path) if layout.kind == "fits" else _axes.from_lp(path, r)
    return CubeInfo(str(path), ny, nx, r, ax)


def _name(path) -> str:
    return os.path.basename(str(path))


def clock(ax: _axes.Axes) -> tuple[np.datetime64 | None, np.ndarray] | None:
    """(the day, or None for an LP cube's times of day; seconds since that day's midnight UT per t), or None
    without times."""
    if ax is None or ax.t_sec is None:
        return None
    t = np.asarray(ax.t_sec, float)
    if ax.time_of_day or ax.dateref is None:
        return None, t
    day = ax.dateref.astype("datetime64[D]")
    return day, t + (ax.dateref - day) / np.timedelta64(1, "s")


def same_times(main: _axes.Axes, other: _axes.Axes) -> tuple[bool, str]:
    """Whether two cubes' times are the same, within half the main cube's cadence; (True, "") when either has none
    (the main's are taken)."""
    a, b = clock(main), clock(other)
    if a is None or b is None:
        return True, "" if b is not None else "no times of its own: the first cube's"
    (day_a, ta), (day_b, tb) = a, b
    if len(ta) != len(tb):
        return False, f"{len(tb)} times against {len(ta)}"
    if day_a is not None and day_b is not None and day_a != day_b:
        return False, f"observed on {day_b}, the first cube on {day_a}"
    cadence = float(np.median(np.diff(ta))) if len(ta) > 1 else 0.0
    tol = 0.5 * cadence if cadence > 0 else 1.0
    worst = float(np.max(np.abs(ta - tb)))
    if worst > tol:
        return False, f"its times differ from the first cube's by up to {worst:.1f} s (half the cadence: {tol:.1f} s)"
    return True, f"the same times (within {worst:.2g} s)"


def plan(main, path) -> Link:
    """How the cube at path links to main (a Dataset or a CubeInfo): Link.ok, the axes to open it with, and how
    that was decided; or why it is not linked."""
    name, lead = _name(path), _name(main.path)
    try:
        info = describe(path)
    except (OSError, ValueError) as e:
        return Link(str(path), False, why=f"{name}: cannot be read as a cube ({e})")
    if (info.ny, info.nx) != (main.ny, main.nx):
        return Link(str(path), False, why=f"{name}: {info.nx}x{info.ny} pixels against {main.nx}x{main.ny} of "
                                           f"{lead}; other grids are not linked yet")
    r, spec = info.roles, None
    nt = main.roles.nt if main.roles.t is not None else 1
    how = f"its axes from its own {r.how}"
    if r.how == "unknown":                              # one leading axis that nothing names
        n = r.nl
        if n == 1:
            spec, how = "t", "one frame: shown at every t"
        elif n == nt:
            spec, how = "t", f"its {n} frames, named by nothing, are the {nt} times of {lead}"
        else:
            return Link(str(path), False, why=f"{name}: {n} frames that nothing names, not the {nt} times of {lead}; "
                                               f"--axes would say what they are")
        info = describe(path, spec)
        r = info.roles
    if r.t is not None and r.nt > 1:
        if r.nt != nt:
            return Link(str(path), False, why=f"{name}: {r.nt} times against {nt} of {lead}; other cadences are not "
                                               f"linked yet")
        same, note = same_times(main.axes, info.axes)
        if not same:
            return Link(str(path), False, why=f"{name}: {note}")
        how = f"{how}; {note}" if note else how
    elif r.t is None or r.nt == 1:
        how = how if "every t" in how else f"{how}; one time: shown at every t"
    return Link(str(path), True, axes=spec, how=how)

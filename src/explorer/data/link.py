"""Linking cubes to the first one (ROADMAP E8.1, E8.4): which of the others can follow it, how their leading axes are
read, and which of their times each of its times shows. The first cube leads: its grid and its times are
everyone's. What lies on the same grid links: with times on both, at its time nearest to the first cube's (another
cadence, another start, two series joined); without, only with as many times (or a single frame, shown at every t).
Other grids, and other cadences without times to match them by, are refused with what does not match, never linked
wrong.

    link = plan(main, path)             # main: a Dataset (or describe(path)); path: another cube
    if link.ok: Dataset.open(path, axes=link.axes) ... else: print(link.why)

How a linked cube's leading axes are read, the first evidence that says it:
1. its own: the FITS header, its per-pixel file, the scans in its name (axes.roles, formats.lp_single_layout);
2. the first cube: frames that nothing names, as many as the first cube's times, are those times (a field or
   velocity map of the same series: Blos, Vlos); a single frame is shown at every t;
3. else it is not linked, and the reason says what --axes would make it.
Then the checks: its header against its frames, as Dataset.open checks them (axes.read: refused here what it would
refuse there); the same grid (ny, nx); its times matched to the first cube's (frames: an LP cube's are times of day,
compared as such; FITS cubes of other days are refused).
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
    """Its axes read and checked as Dataset.open reads and checks them (axes.read): ValueError where that refuses
    the cube."""
    layout = open_layout(path)
    ny, nx = (int(n) for n in layout.shape[-2:])
    r, ax = _axes.read(path, layout, axes)
    return CubeInfo(str(path), ny, nx, r, ax)


def _name(path) -> str:
    return os.path.basename(str(path))


def clock(ax: _axes.Axes | None) -> tuple[np.datetime64 | None, np.ndarray] | None:
    """(the day, or None for an LP cube's times of day; seconds since that day's midnight UT per t), or None
    without times."""
    if ax is None or ax.t_sec is None:
        return None
    t = np.asarray(ax.t_sec, float)
    if ax.time_of_day or ax.dateref is None:
        return None, t
    day = ax.dateref.astype("datetime64[D]")
    return day, t + (ax.dateref - day) / np.timedelta64(1, "s")


@dataclass(frozen=True)
class Frames:
    """Which of a linked cube's times is shown at each of the first cube's (Session.member_state reads t from it)."""
    t: np.ndarray | None            # (nt of the first,) its t at each; None: not linked (note says why)
    dt: np.ndarray | None           # its time minus the first cube's at each, s; None without times on both
    note: str                       # how they were matched (for the start-up's log), or why not


def frames(main: _axes.Axes | None, other: _axes.Axes | None, nt: int, n: int, lead: str = "the first cube") -> Frames:
    """A linked cube's t at each of the first cube's nt times (n: its own number of times; axes None: no times).
    One time: shown at every t. Times on both (the same day): its time nearest to each of the first cube's, the
    earlier of two as near, as CRISPEX's tsel_ref (crispex.pro:2898-2906); however far it is, as there, and as the
    plan of linked windows maps time (§3.3: the nearest, with its delta-t); the note says at how many of the first
    cube's times the nearest is more than half its own cadence away (outside its series, or in a gap). Without times
    on either: the first cube's t, so only with as many times; else not linked. lead: the first cube's name in the
    notes."""
    if n <= 1:
        return Frames(np.zeros(nt, int), None, "one time: shown at every t")
    a, b = clock(main), clock(other)
    a = a if a is not None and len(a[1]) == nt else None
    b = b if b is not None and len(b[1]) == n else None
    if a is None or b is None:
        if n == nt:
            return Frames(np.arange(nt), None, "no times of its own: the first cube's" if b is None else "")
        whose = "neither has times" if a is None and b is None else "it has no times" if a is not None else \
            f"{lead} has no times"
        return Frames(None, None, f"{n} times against {nt} of {lead}; {whose} to match them by")
    (day_a, ta), (day_b, tb) = a, b
    if day_a is not None and day_b is not None and day_a != day_b:
        return Frames(None, None, f"observed on {day_b}, {lead} on {day_a}")
    gap = np.abs(np.where(np.isfinite(tb), tb, np.inf)[None, :] - ta[:, None])
    t = gap.argmin(axis=1)
    dt = tb[t] - ta
    worst = float(np.max(np.abs(dt)))
    if n == nt and np.array_equal(t, np.arange(nt)):
        return Frames(t, dt, f"the same times (within {worst:.2g} s)")
    half = 0.5 * float(np.median(np.diff(tb)))
    far = np.abs(dt) > half
    note = f"its time nearest to each of {lead}'s: its t {t.min()}-{t.max()} of {n}"
    note += f", within {float(np.max(np.abs(dt[~far]))):.1f} s" if (~far).any() else ""
    if far.any():
        note += (f"; at {int(far.sum())} of the {nt} times of {lead} the nearest is more than half its cadence away "
                 f"({half:.1f} s; up to {float(np.max(np.abs(dt[far]))):.0f} s), and that frame is shown")
    return Frames(t, dt, note)


def plan(main, path) -> Link:
    """How the cube at path links to main (a Dataset or a CubeInfo): Link.ok, the axes to open it with, and how
    that was decided; or why it is not linked."""
    name, lead = _name(path), _name(main.path)

    def unread(e) -> Link:                              # as Dataset.open would refuse it (describe)
        return Link(str(path), False, why=f"{name}: cannot be read as a cube ({e})")

    try:
        info = describe(path)
    except (OSError, ValueError) as e:
        return unread(e)
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
        try:
            info = describe(path, spec)
        except (OSError, ValueError) as e:
            return unread(e)
        r = info.roles
    if r.t is not None and r.nt > 1:
        fr = frames(main.axes, info.axes, nt, r.nt, lead)
        if fr.t is None:
            return Link(str(path), False, why=f"{name}: {fr.note}")
        how = f"{how}; {fr.note}" if fr.note else how
    elif r.t is None or r.nt == 1:
        how = how if "every t" in how else f"{how}; one time: shown at every t"
    return Link(str(path), True, axes=spec, how=how)

"""The cubes being looked at and the one state they share: the cursor, the lock and the master time, and for each
cube its lambda and Stokes, linked to the main cube's or not.

From the prototype's Viewer (set_index, _step, _on_hover, set_locked, the start in __init__) and the plan of linked
windows (docs/PLAN_VENTANAS_ENLAZADAS.md in the project, §3.2, §3.3). Linked cubes (ROADMAP E8.1, E8.4) are members
on the main cube's grid (data.link decides): the cursor, the lock and t are the same state for all, each member
showing its time nearest to the main cube's t (data.link.frames: Member.t, read in member_state alone); each
member's lambda and Stokes are the main's when linked, else its own, in the state too (ViewState.own), so that a
change of either notifies as any other. Other grids (mapping pixels) come later.
"""
import dataclasses
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from ..data.axes import Roles, frame_index
from ..data.link import frames
from ..obs import counter
from .levels import GAMMA_MAX, GAMMA_MIN, RULE_DEFAULT, RULES
from .loop import Loop
from .pace import Pace
from .state import Store, ViewState

AXES = ("t", "s", "l")


class Cube(Protocol):
    """What the session needs of a cube: explorer.data's Dataset has it, and so does a stand-in in tests."""
    roles: Roles
    shape: tuple
    ny: int
    nx: int


@dataclass
class Member:
    """A cube in the session; link_l, link_s: its lambda and Stokes are the main cube's (decision D3 of the
    linked-windows plan), else its own (ViewState.own); t: its t at each of the main cube's (data.link.frames)."""
    dataset: Cube
    link_l: bool = True
    link_s: bool = True
    t: tuple[int, ...] = ()


class Session:
    def __init__(self, loop: Loop, main):
        """main: the main cube (an explorer.data Dataset). Starts as the prototype did: the middle tuning, the first t
        and Stokes, the cursor at the centre of the image."""
        r = main.roles
        self.members = [Member(main, t=tuple(range(r.nt)))]
        self.sizes = {"t": r.nt, "s": r.ns, "l": r.nl}
        self.present = {"t": r.t is not None, "s": r.s is not None, "l": r.l is not None}
        self.store = Store(loop, ViewState(l=r.nl // 2 if r.l is not None else 0, cursor=(main.ny // 2, main.nx // 2)))
        self.pace = Pace(loop)                          # the cursor's panels of every cube, as the screen keeps up

    # ---------------------------------------------------------------- the cubes
    @property
    def main(self):
        return self.members[0].dataset

    @property
    def ns(self) -> int:
        """The main cube's Stokes, 1 without them."""
        return self.sizes["s"] if self.present["s"] else 1

    @property
    def state(self) -> ViewState:
        return self.store.state

    def add(self, dataset, link_l: bool = False, link_s: bool | None = None) -> int:
        """A linked cube on the main cube's grid; returns its member number. At each of the main cube's t it shows
        its time nearest to it, by their axes' times (data.link.frames, as data.link.plan has checked); without
        times on both, the same t, so only with as many times (ValueError otherwise). Its lambda is its own by
        default (another line: lambda by index means nothing across lines); its Stokes are the main cube's when
        both have the same number, else its own."""
        if (dataset.ny, dataset.nx) != (self.main.ny, self.main.nx):
            raise ValueError(f"{dataset.nx}x{dataset.ny} pixels against {self.main.nx}x{self.main.ny}: only cubes on "
                             f"the main cube's grid are linked yet")
        r, main = dataset.roles, self.main.roles
        fr = frames(getattr(self.main, "axes", None), getattr(dataset, "axes", None), main.nt, r.nt)    # 1 without t
        if fr.t is None:
            raise ValueError(fr.note)
        if link_s is None:
            link_s = r.s is not None and main.s is not None and r.ns == main.ns
        self.members.append(Member(dataset, link_l=bool(link_l) and r.nl == main.nl, link_s=bool(link_s),
                                   t=tuple(int(k) for k in fr.t)))
        own = (r.nl // 2 if r.l is not None else 0, 0)
        k = len(self.members) - 1
        self.store.set(own=self.store.state.own + (own,), panels=self.store.state.panels | {f"image:{k}"})
        return k

    def member_state(self, member: int, state: ViewState | None = None) -> ViewState:
        """The state as member k reads it: its t nearest in time to the main cube's (Member.t; a single frame at every
        t), its lambda and Stokes (the main's when linked), its panels ("spectra:k" as "spectra"; "image:k" as
        "image", its image shown; "slit:k" as "slit", its slit tab in front), no slit (its slit reads take the slit
        from the whole state: core.slitreads). The main cube's state as it is."""
        st = state or self.store.state
        if member == 0:
            return st
        m = self.members[member]
        own_l, own_s = st.own[member - 1]
        mine = frozenset(p.split(":")[0] for p in st.panels if p.endswith(f":{member}"))
        r = m.dataset.roles
        return dataclasses.replace(st, t=m.t[st.t], l=min(st.l if m.link_l else own_l, r.nl - 1),
                                   s=min(st.s if m.link_s else own_s, r.ns - 1), panels=mine, path=None, draft=None)

    def set_member_index(self, member: int, axis: str, v: int) -> None:
        """lambda or Stokes of member k to v, clipped to its axis: the main cube's when linked (t is everyone's)."""
        if member == 0 or axis == "t":
            self.set_index(axis, v)
            return
        if axis not in ("l", "s"):
            raise ValueError(f"axis must be one of {AXES}, not {axis!r}")
        m = self.members[member]
        if (m.link_l if axis == "l" else m.link_s):
            self.set_index(axis, v)
            return
        r = m.dataset.roles
        if (r.l if axis == "l" else r.s) is None:
            return
        n = r.nl if axis == "l" else r.ns
        own = list(self.store.state.own)
        l, s = own[member - 1]  # noqa: E741
        own[member - 1] = (int(np.clip(int(v), 0, n - 1)), s) if axis == "l" else (l, int(np.clip(int(v), 0, n - 1)))
        self.store.set(own=tuple(own))

    def index(self, member: int = 0, state: ViewState | None = None) -> tuple:
        """The leading-axes index of a member's frame for the state (by default the current one), for its reads."""
        return self.index_of(member, self.member_state(member, state))

    def index_of(self, member: int, st: ViewState) -> tuple:
        """The leading-axes index of member k's frame for a state already its own (member_state)."""
        ds = self.members[member].dataset
        return frame_index(len(ds.shape) - 2, ds.roles, t=st.t, s=st.s, l=st.l)

    # ---------------------------------------------------------------- changes
    def hover(self, y: int, x: int) -> None:
        """The mouse over pixel (y, x) of the main cube: ignored while locked, clipped to the image, nothing for the
        same pixel (the prototype's _on_hover; CRISPEX redraws anyway)."""
        if self.store.state.locked:
            return
        y = int(np.clip(y, 0, self.main.ny - 1))
        x = int(np.clip(x, 0, self.main.nx - 1))
        if (y, x) == self.store.state.cursor:
            counter("core.hover.same_pixel")
            return
        self.store.set(cursor=(y, x))

    def set_index(self, axis: str, v: int) -> None:
        """t, s or l of the main cube to v, clipped to the axis; nothing for an axis the cube does not have."""
        if axis not in AXES:
            raise ValueError(f"axis must be one of {AXES}, not {axis!r}")
        if not self.present[axis]:
            return
        self.store.set(**{axis: int(np.clip(int(v), 0, self.sizes[axis] - 1))})

    def step(self, axis: str, d: int, wrap: bool = False) -> None:
        """Move an axis by d: around the ends with wrap (playback), else stopping at them (the prototype's _step)."""
        if axis not in AXES:
            raise ValueError(f"axis must be one of {AXES}, not {axis!r}")
        if not self.present[axis]:
            return
        n, v = self.sizes[axis], getattr(self.store.state, axis) + int(d)
        self.set_index(axis, v % n if wrap else v)

    def lock(self, on: bool = True) -> None:
        self.store.set(locked=bool(on))

    def lock_at(self, y: int, x: int) -> None:
        """The cursor to (y, x), clipped as hover clips it, and locked there, whether it was locked or not."""
        self.lock(False)
        self.hover(y, x)
        self.lock(True)

    def set_t_cap(self, cap: int | None) -> None:
        """The t steps the temporal panels read and show at most (data.tsample), every cube's; None: every t."""
        self.store.set(t_cap=None if cap is None else max(1, int(cap)))

    def set_path(self, points, cube: int | None = None) -> None:
        """The slit: the points clicked, (x, y) in the main cube's view coordinates (pixel centres at .5), two at
        least, each clipped to the image; None removes it. Straight through two points, a curve through more
        (data.slits.slit_path); the prototype's Viewer.slit (app/viewer.py:1228, set in _slit_finish 1571). cube: the
        member it was drawn on, whose slices the slit panel shows (the grids are the same, so the points are too);
        None leaves it as it is."""
        if points is None:
            self.store.set(path=None)
            return
        pts = self._clip(points)
        if len(pts) < 2:
            raise ValueError(f"a slit needs two points at least, not {len(pts)}")
        self.store.set(path=pts, **self._cube("path_cube", cube))

    def set_draft(self, points, cube: int | None = None) -> None:
        """The slit being drawn: the points clicked so far and the pointer's pixel, (x, y) as set_path's, any number
        (its slices follow it once it has two); None when no slit is being drawn. The prototype's variant D draws
        its live slices from the same points (_slitd_preview, app/viewer.py:1664). cube: as set_path's."""
        self.store.set(draft=None if points is None else self._clip(points), **self._cube("draft_cube", cube))

    def set_slit_tabs(self, on: bool) -> None:
        """A slit tab per cube (on), each reading its own cube's slices along the same slit, or one tab, of the cube
        the slit was drawn on (core.slitreads)."""
        self.store.set(slit_tabs=bool(on))

    def _cube(self, field: str, cube: int | None) -> dict:
        if cube is None:
            return {}
        if not 0 <= int(cube) < len(self.members):
            raise ValueError(f"no cube {cube}: the session has {len(self.members)}")
        return {field: int(cube)}

    def _clip(self, points) -> tuple:
        return tuple((float(np.clip(x, 0, self.main.nx)), float(np.clip(y, 0, self.main.ny))) for x, y in points)

    def gamma(self, member: int, s: int) -> float:
        """The gamma of cube member's Stokes s (core.levels): 1 unless set."""
        for k, ss, g in self.store.state.gamma:
            if (k, ss) == (member, s):
                return g
        return 1.0

    def set_gamma(self, member: int, s: int, g: float) -> None:
        """Gamma of cube member's Stokes s, within levels.GAMMA_MIN..GAMMA_MAX: one per cube and Stokes (Q's is not
        V's, nor another cube's). Its image, its lambda-t and the slit's slices of it at that Stokes follow."""
        if not 0 <= int(member) < len(self.members):
            raise ValueError(f"no cube {member}: the session has {len(self.members)}")
        r = self.members[member].dataset.roles
        s = int(np.clip(int(s), 0, (r.ns if r.s is not None else 1) - 1))
        g = float(np.clip(float(g), GAMMA_MIN, GAMMA_MAX))
        rest = tuple(e for e in self.store.state.gamma if (e[0], e[1]) != (int(member), s))
        self.store.set(gamma=tuple(sorted(rest + (((int(member), s, g),) if g != 1 else ()))))

    def scale(self, member: int, s: int) -> tuple[str, float, float]:
        """How cube member's image at Stokes s finds its levels: (rule, lo, hi), lo and hi the fixed levels under
        the rule "fixed" (levels.RULES); the default rule, each frame's 1-99 percentiles, unless set."""
        for k, ss, rule, lo, hi in self.store.state.scale:
            if (k, ss) == (member, s):
                return rule, lo, hi
        return RULE_DEFAULT, 0.0, 0.0

    def set_scale(self, member: int, s: int, rule: str, lo: float = 0.0, hi: float = 0.0) -> None:
        """The rule for the levels of cube member's image at Stokes s, one per cube and Stokes as gamma; "fixed" with
        its levels lo < hi, symmetric about 0 for Q U V (s > 0: -m..m, m the larger of |lo| and |hi|), as their
        automatic levels are."""
        if not 0 <= int(member) < len(self.members):
            raise ValueError(f"no cube {member}: the session has {len(self.members)}")
        if rule not in RULES:
            raise ValueError(f"no rule {rule!r}: one of {sorted(RULES)}")
        r = self.members[member].dataset.roles
        s = int(np.clip(int(s), 0, (r.ns if r.s is not None else 1) - 1))
        lo, hi = (float(lo), float(hi)) if rule == "fixed" else (0.0, 0.0)
        if rule == "fixed":
            if s > 0:
                m = max(abs(lo), abs(hi))
                lo, hi = -m, m
            if not (np.isfinite(lo) and np.isfinite(hi) and hi > lo):
                raise ValueError(f"fixed levels need lo < hi, not {lo}, {hi}")
        rest = tuple(e for e in self.store.state.scale if (e[0], e[1]) != (int(member), s))
        new = ((int(member), s, rule, lo, hi),) if rule != RULE_DEFAULT else ()
        self.store.set(scale=tuple(sorted(rest + new)))

    def set_playing(self, on: bool) -> None:
        """Playback on or off: without a per-pixel file the slit's spectral slice waits until it stops (the
        prototype's _slit_refresh and _toggle_play, app/viewer.py:1817, 2082)."""
        self.store.set(playing=bool(on))

    def show(self, panel: str, on: bool = True) -> None:
        """A panel shown or hidden: nothing is read for a hidden one (the prototype's skipped_hidden)."""
        panels = set(self.store.state.panels)
        (panels.add if on else panels.discard)(panel)
        self.store.set(panels=frozenset(panels))

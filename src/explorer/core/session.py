"""The cubes being looked at and the one state they share: the cursor, the lock and the master time, and for each
cube its lambda and Stokes, linked to the main cube's or not.

From the prototype's Viewer (set_index, _step, _on_hover, set_locked, the start in __init__) and the plan of linked
windows (docs/PLAN_VENTANAS_ENLAZADAS.md in the project, §3.2). One cube for now; the members, the master and the
links are here from the start so that several cubes (ROADMAP E8) do not reorganise it. Mapping pixels and times
between cubes of different grids and cadences is E8's; until then add() refuses a second cube.
"""
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from ..data.axes import Roles
from ..obs import counter
from .loop import Loop
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
    """A cube in the session, with what is its own: its lambda and Stokes when they are not linked to the main cube's
    (decision D3 of the linked-windows plan)."""
    dataset: Cube
    link_l: bool = True
    link_s: bool = True
    l: int = 0  # noqa: E741
    s: int = 0


class Session:
    def __init__(self, loop: Loop, main):
        """main: the main cube (an explorer.data Dataset). Starts as the prototype did: the middle tuning, the first t
        and Stokes, the cursor at the centre of the image."""
        self.members = [Member(main)]
        self.master = 0                                 # the member whose t is the time of the session
        r = main.roles
        self.sizes = {"t": r.nt, "s": r.ns, "l": r.nl}
        self.present = {"t": r.t is not None, "s": r.s is not None, "l": r.l is not None}
        self.store = Store(loop, ViewState(l=r.nl // 2 if r.l is not None else 0, cursor=(main.ny // 2, main.nx // 2)))

    # ---------------------------------------------------------------- the cubes
    @property
    def main(self):
        return self.members[0].dataset

    @property
    def state(self) -> ViewState:
        return self.store.state

    def add(self, dataset, link_l=True, link_s=True):
        raise NotImplementedError("a second cube needs the pixel and time mapping of ROADMAP E8")

    def index(self, member: int = 0, state: ViewState | None = None) -> tuple:
        """The leading-axes index of a member's frame for the state (by default the current one), for its reads."""
        st = state or self.store.state
        m = self.members[member]
        r = m.dataset.roles
        vals = {"t": st.t, "s": st.s if m.link_s else m.s, "l": st.l if m.link_l else m.l}
        idx = [0] * len(m.dataset.shape[:-2])
        for name, pos in (("t", r.t), ("s", r.s), ("l", r.l)):
            if pos is not None:
                idx[pos] = int(vals[name])
        return tuple(idx)

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

    def show(self, panel: str, on: bool = True) -> None:
        """A panel shown or hidden: nothing is read for a hidden one (the prototype's skipped_hidden)."""
        panels = set(self.store.state.panels)
        (panels.add if on else panels.discard)(panel)
        self.store.set(panels=frozenset(panels))

"""The viewer's state, and one notice per burst of changes.

ViewState is immutable: whoever holds one holds a consistent snapshot. Store.set() replaces it and, once per pass
of the loop, tells its subscribers the new state and which fields differ from the state they were last told
about. A burst (a mouse move per pixel, keys held down, a slider dragged) gives one notice, as the prototype's
0-ms timer gave one cursor update per event-loop pass (Viewer._on_hover); a field changed and changed back
within the burst is not reported. Use it from the main thread only; results from other threads come through
Loop.post.
"""
import dataclasses
from collections.abc import Callable
from dataclasses import dataclass, field

from ..obs import get_logger
from .loop import Loop

log = get_logger("core")

Path2D = tuple[tuple[float, float], ...]                # points clicked, view coordinates (x, y), pixel centres at .5
PANELS = frozenset({"spectra", "lambda_t"})           # shown at start; "slit" joins while its tab is in front


@dataclass(frozen=True)
class ViewState:
    t: int = 0                                          # indices in the main Dataset
    s: int = 0
    l: int = 0  # noqa: E741
    cursor: tuple[int, int] = (0, 0)                    # (y, x) pixel of the main Dataset
    locked: bool = False                                # the mouse no longer moves the cursor
    path: Path2D | None = None                          # the slit, when there is one
    draft: Path2D | None = None                         # the slit being drawn, to the pointer; None: not drawing
    path_cube: int = 0                                  # the member whose image the slit was drawn on: its slices
    draft_cube: int = 0                                 # are that cube's; the same for the slit being drawn
    playing: bool = False
    panels: frozenset[str] = field(default=PANELS)      # shown: nothing is read for a hidden panel ("spectra:k":
                                                        # linked cube k's)
    own: tuple[tuple[int, int], ...] = ()               # (lambda, Stokes) of each linked cube (members 1, 2...),
                                                        # its own when not linked to the main cube's
    gamma: tuple[tuple[int, int, float], ...] = ()      # (cube, Stokes, gamma) where gamma is not 1, sorted


FIELDS = frozenset(f.name for f in dataclasses.fields(ViewState))
Listener = Callable[[ViewState, frozenset], None]


class Store:
    def __init__(self, loop: Loop, state: ViewState | None = None):
        self.loop = loop
        self._state = state or ViewState()
        self._told = self._state                       # the state subscribers were last told about
        self._listeners: list[Listener] = []
        self._scheduled = False

    @property
    def state(self) -> ViewState:
        return self._state

    def subscribe(self, fn: Listener) -> Callable[[], None]:
        """fn(state, changed fields) after each burst; returns a function that unsubscribes it."""
        self._listeners.append(fn)
        return lambda: self._listeners.remove(fn) if fn in self._listeners else None

    def set(self, **fields) -> None:
        unknown = set(fields) - FIELDS
        if unknown:
            raise TypeError(f"not state fields: {sorted(unknown)}")
        new = dataclasses.replace(self._state, **fields)
        if new == self._state:
            return
        self._state = new
        if not self._scheduled:
            self._scheduled = True
            self.loop.call_soon(self._notify)

    def _notify(self) -> None:
        self._scheduled = False
        new, old = self._state, self._told
        changed = frozenset(f for f in FIELDS if getattr(new, f) != getattr(old, f))
        self._told = new
        if not changed:
            return
        for fn in list(self._listeners):
            try:
                fn(new, changed)
            except Exception:                           # one broken listener never silences the others
                log.exception("state listener %r failed", fn)

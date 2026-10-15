"""The cursor's panels at the pace the screen shows them: latest wins, and only when the screen falls behind.

Each result of the cursor's panels (spectra, lambda-t, of every cube) is shown at once, as it comes, unless the
display says the panels shown before have not reached the screen yet (Screen.behind): then it is held, a newer one
for the same panel replacing it, and everything held is shown when they have (Screen.when_shown), or after HOLD_S
whatever happens. Through the X11 bridge, "not reached" is a panel frame sent and not yet confirmed by the X server:
a frame drawn while the one before is still on the link only queues behind it, and its bytes delay the crosshair's.
Qt's own displays (xcb, cocoa, offscreen) give no Screen: every result is shown at once, as before.

Only on slow links (BELOW_MBPS, the X11 link probe at start; Pace.link): bench/bridge_link.py, Xvfb on bellatrix,
12 sweeps of 40 moves per version, the time until the cursor's last place is on the screen, with the hold against
without: 10 MB/s 152 -> 125 ms (moves 16 ms apart), 156 -> 144 (8 ms apart); 15 MB/s 112 -> 95, 101 -> 94; 20 and
30 MB/s no gain, the panels drawn half as often for nothing. Until the probe says so, every result is shown at once.
Not the UI thread's time per move: about 23 ms of CPU, more than the 16 ms between moves even on Qt's xcb, but Qt
merges the pointer moves that queue up, so no backlog grows there, and a hold would only drop frames.
"""
from collections.abc import Callable, Hashable
from typing import Protocol

from ..obs import counter
from .loop import Loop

HOLD_S = 0.5            # a frame never confirmed (a link gone) holds the panels no longer than this
BELOW_MBPS = 20.0       # the hold on links slower than this (MB/s, the link probe); faster ones gain nothing


class Screen(Protocol):
    """What a display tells of the panels drawn (platform.display: the bridge's; None for Qt's own)."""

    def behind(self) -> bool: ...                       # a frame drawn before has not reached the screen yet

    def drawn(self) -> None: ...                        # panels were drawn now: they make the next frame

    def when_shown(self, fn: Callable[[], None]) -> None: ...  # fn on the main thread once that frame is shown


class Pace:
    def __init__(self, loop: Loop):
        self.loop = loop
        self.screen: Screen | None = None               # the one held for, once the link is known to need it
        self.offer: Screen | None = None                # the display's (platform.display.screen()), if any
        self._held: dict[Hashable, Callable[[], None]] = {}
        self._wait = 0                                  # increments per hold: a stale timeout or callback sees it

    def link(self, mbps: float) -> bool:
        """The link measured (MB/s): the hold from now on when it is slower than BELOW_MBPS and the display offers
        a screen; otherwise every result shown at once. True when held for."""
        self.screen = self.offer if self.offer is not None and mbps < BELOW_MBPS else None
        return self.screen is not None

    def show(self, key: Hashable, fn: Callable[[], None]) -> None:
        """Show a panel (fn) now, or hold it under key (a cube's panel) until the screen has caught up."""
        scr = self.screen
        if scr is None:
            fn()
            return
        if scr.behind():
            counter("core.pace.held")
            if not self._held:
                self._wait += 1
                w = self._wait
                scr.when_shown(lambda: self._release(w))
                self.loop.call_later(HOLD_S, lambda: self._release(w, timeout=True))
            self._held[key] = fn
            return
        if self._held:                                  # caught up before its callback came: in order, at once
            self._release(self._wait)
        fn()
        scr.drawn()

    def drop(self, keys) -> None:
        """Forget what is held for these keys (a cube's panels cleared or closed)."""
        for k in keys:
            self._held.pop(k, None)

    def _release(self, w: int, timeout: bool = False) -> None:
        if w != self._wait or not self._held:
            return
        if timeout:
            counter("core.pace.timeout")
        self._wait += 1
        held, self._held = self._held, {}
        for fn in held.values():
            fn()
        if self.screen is not None:
            self.screen.drawn()

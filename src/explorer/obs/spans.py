"""Timed spans: where the time goes, per operation, in every thread, cheaply enough to stay on.

    with span("image.read", idx=idx):          # or @timed("levels.compute")
        ...
    budget("cursor", 33)                        # WARNING with the breakdown of child spans when a span exceeds it
    counter("reads.skipped_padding")
    summary()                                   # {name: {n, median_ms, p95_ms}} for F12, bench JSON and tests

- Durations come from time.perf_counter_ns and go to a bounded window per name (the last WINDOW spans), so
  summary() gives recent medians and p95 without growing memory.
- A span over its budget logs one WARNING with its direct children aggregated (e.g. "cursor 41.2 ms > 33 ms:
  pixel.read 30.1 ms, levels 6.0 ms, paint 4.8 ms"), at most once per second per name, so a bottleneck shows up
  in the log without being looked for.
- Root spans should be whole user actions (cursor move to spectrum shown, t step to image painted): they measure
  what the user feels, not one function.
- No spans inside numba kernels: time around them.
- set_enabled(False) makes span() return one shared no-op object (cost: a function call and a flag test).
The cost per span is measured in bench/obs_overhead.py; see docs/journal.md.
"""
import threading
import time
from collections import deque

from .log import get_logger

WINDOW = 256                                    # recent durations kept per name
_log = get_logger("obs")
_enabled = True
_local = threading.local()
_lock = threading.Lock()
_recent: dict[str, deque] = {}
_count: dict[str, int] = {}
_counters: dict[str, int] = {}
_budgets: dict[str, int] = {}                   # name -> ns
_last_warn: dict[str, float] = {}
_sink = None                                    # trace.start() puts a list here: (name, t0_ns, dur_ns, tid, attrs)
_thread_names: dict[int, str] = {}


def enabled() -> bool:
    return _enabled


def set_enabled(on: bool) -> None:
    global _enabled
    _enabled = bool(on)


def _stack():
    st = getattr(_local, "stack", None)
    if st is None:
        st = _local.stack = []
        t = threading.current_thread()
        _thread_names[t.ident] = t.name
    return st


class _Span:
    __slots__ = ("name", "attrs", "t0", "children", "parent")

    def __init__(self, name, attrs):
        self.name, self.attrs, self.children = name, attrs, None

    def __enter__(self):
        st = _stack()
        self.parent = st[-1] if st else None
        st.append(self)
        self.t0 = time.perf_counter_ns()
        return self

    def __exit__(self, *exc):
        dur = time.perf_counter_ns() - self.t0
        _local.stack.pop()
        name = self.name
        rec = _recent.get(name)
        if rec is None:
            with _lock:
                rec = _recent.setdefault(name, deque(maxlen=WINDOW))
        rec.append(dur)
        _count[name] = _count.get(name, 0) + 1    # approximate under contention; windows are exact
        if _sink is not None:
            _sink.append((name, self.t0, dur, threading.get_ident(), self.attrs))
        if self.parent is not None:
            p = self.parent
            if p.children is None:
                p.children = []
            p.children.append((name, dur))
        b = _budgets.get(name)
        if b is not None and dur > b:
            _over_budget(self, dur, b)
        return False


class _NoSpan:
    __slots__ = ()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


_NOSPAN = _NoSpan()


def span(name: str, **attrs):
    """Context manager timing the block under name; attrs go to the trace only."""
    return _Span(name, attrs) if _enabled else _NOSPAN


def timed(name: str):
    """Decorator: the whole call is one span."""
    def wrap(fn):
        def inner(*a, **k):
            with span(name):
                return fn(*a, **k)
        inner.__name__, inner.__doc__, inner.__wrapped__ = fn.__name__, fn.__doc__, fn
        return inner
    return wrap


def counter(name: str, n: int = 1) -> None:
    with _lock:
        _counters[name] = _counters.get(name, 0) + n


def budget(name: str, ms: float | None) -> None:
    """Warn when a span named name lasts more than ms; None removes the budget."""
    if ms is None:
        _budgets.pop(name, None)
    else:
        _budgets[name] = int(ms * 1e6)


def _over_budget(s, dur, b):
    now = time.monotonic()
    if now - _last_warn.get(s.name, -1e9) < 1.0:
        return
    _last_warn[s.name] = now
    parts = {}
    for n, d in s.children or ():
        parts[n] = parts.get(n, 0) + d
    detail = ", ".join(f"{n} {d / 1e6:.1f} ms" for n, d in sorted(parts.items(), key=lambda kv: -kv[1]))
    _log.warning("%s %.1f ms > %.0f ms%s", s.name, dur / 1e6, b / 1e6, (": " + detail) if detail else "")


def _pct(v, q):
    v = sorted(v)
    i = min(len(v) - 1, max(0, round(q * (len(v) - 1))))
    return v[i]


def summary() -> dict:
    """{name: {"n": total count, "median_ms", "p95_ms" over the recent window}} plus {"counters": {...}}."""
    out = {}
    for name, rec in list(_recent.items()):
        v = list(rec)
        if v:
            out[name] = dict(n=_count.get(name, len(v)), median_ms=round(_pct(v, 0.5) / 1e6, 4),
                             p95_ms=round(_pct(v, 0.95) / 1e6, 4))
    with _lock:
        out["counters"] = dict(_counters)
    return out


def reset() -> None:
    """Forget every span, counter and budget (tests)."""
    with _lock:
        _recent.clear(); _count.clear(); _counters.clear(); _budgets.clear(); _last_warn.clear()


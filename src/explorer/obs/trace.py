"""Chrome trace-event files of the spans (obs/spans.py): open them in https://ui.perfetto.dev or chrome://tracing,
one row per thread (GUI, numba reader, I/O pool, bridge sender), to see queues and waits between threads, which
cProfile mixes up in Python 3.12.

    trace.start("t.json")      # or EXPLORER_TRACE=t.json; written at stop() or at exit
    ...
    trace.stop()
"""
import atexit
import json
import os

from . import spans

MAX_EVENTS = 2_000_000                          # ~200 MB of JSON at most; later spans are dropped, and counted
_path = None
_dropped = 0


class _Sink(list):
    def append(self, ev):
        global _dropped
        if len(self) < MAX_EVENTS:
            super().append(ev)
        else:
            _dropped += 1


def start(path) -> None:
    global _path, _dropped
    if spans._sink is not None:
        stop()
    _path, _dropped = str(path), 0
    spans._sink = _Sink()
    atexit.register(stop)


def active() -> bool:
    return spans._sink is not None


def stop():
    """Write the trace (if one is being recorded) and stop recording; returns the path or None."""
    global _path
    sink, spans._sink = spans._sink, None
    if sink is None or _path is None:
        return None
    pid = os.getpid()
    t0 = min((e[1] for e in sink), default=0)
    events = [dict(name=n, ph="X", ts=(t - t0) / 1e3, dur=d / 1e3, pid=pid, tid=tid,
                   **({"args": {k: str(v) for k, v in a.items()}} if a else {}))
              for n, t, d, tid, a in sink]
    events += [dict(name="thread_name", ph="M", pid=pid, tid=tid, args=dict(name=name))
               for tid, name in spans._thread_names.items()]
    with open(_path, "w") as f:
        json.dump(dict(traceEvents=events, displayTimeUnit="ms", otherData=dict(dropped=_dropped)), f)
    path, _path = _path, None
    return path

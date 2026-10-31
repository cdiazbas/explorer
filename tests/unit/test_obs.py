"""obs: spans (stats, nesting, budgets, threads), counters, traces, logging; and that it stays light."""
import json
import logging
import subprocess
import sys
import threading
import time

import pytest

from explorer import obs
from explorer.obs import spans, trace


@pytest.fixture(autouse=True)
def clean():
    spans.reset()
    spans.set_enabled(True)
    yield
    trace.stop()
    spans.reset()
    spans.set_enabled(True)


def test_spans_are_counted_and_summarised():
    for _ in range(10):
        with obs.span("a"):
            with obs.span("b"):
                pass
    s = obs.summary()
    assert s["a"]["n"] == 10 and s["b"]["n"] == 10 and s["a"]["median_ms"] >= s["b"]["median_ms"]


def test_disabled_spans_record_nothing():
    spans.set_enabled(False)
    with obs.span("off"):
        pass
    assert "off" not in obs.summary()


def test_budget_warning_lists_children_once_per_second(caplog):
    obs.budget("action", 1)
    caplog.set_level(logging.WARNING, logger="explorer.obs")
    for _ in range(3):                                  # three slow actions in a row: one warning
        with obs.span("action"):
            with obs.span("slow.part"):
                time.sleep(0.003)
            with obs.span("fast.part"):
                pass
    msgs = [r.getMessage() for r in caplog.records if r.name == "explorer.obs"]
    assert len(msgs) == 1 and msgs[0].startswith("action") and "slow.part" in msgs[0]
    assert msgs[0].index("slow.part") < msgs[0].index("fast.part")      # biggest child first


def test_counters_are_exact_across_threads():
    def work():
        for _ in range(5000):
            obs.counter("c")
    ts = [threading.Thread(target=work) for _ in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert obs.summary()["counters"]["c"] == 40000


def test_trace_has_one_row_per_thread(tmp_path):
    p = tmp_path / "t.json"
    trace.start(p)

    def work():
        with obs.span("in.thread", k=1):
            pass
    t = threading.Thread(target=work, name="reader")
    t.start()
    t.join()
    with obs.span("in.main"):
        pass
    assert trace.stop() == str(p)
    ev = json.loads(p.read_text())["traceEvents"]
    spans_ev = {e["name"]: e for e in ev if e["ph"] == "X"}
    names = {e["tid"]: e["args"]["name"] for e in ev if e["ph"] == "M"}
    assert names[spans_ev["in.thread"]["tid"]] == "reader"
    assert spans_ev["in.thread"]["tid"] != spans_ev["in.main"]["tid"]
    assert spans_ev["in.thread"]["args"] == {"k": "1"}
    assert trace.stop() is None                         # stopping twice is harmless


def test_log_levels_per_layer(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    obs.setup(spec="data.io=DEBUG")
    obs.get_logger("data.io").debug("detail from io")
    obs.get_logger("core").debug("hidden")
    obs.get_logger("core").warning("shown")
    for h in logging.getLogger("explorer").handlers:
        h.flush()
    text = (tmp_path / "explorer" / "logs" / "explorer.log").read_text()
    assert "detail from io" in text and "shown" in text and "hidden" not in text
    obs.setup(to_file=False)                            # leave no file handler behind for other tests


def test_obs_imports_only_the_standard_library():
    code = ("import sys, explorer.obs; print(sorted(m for m in ('PySide6', 'numba', 'numpy', 'astropy') "
            "if m in sys.modules))")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout.strip()
    assert out == "[]"


def test_console_keeps_warning_for_unnamed_layers(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    obs.setup(spec="data.io=DEBUG")
    obs.get_logger("core").info("core info")            # below the console's WARNING: not on the console
    obs.get_logger("data.io").debug("io debug")         # data.io set to DEBUG: on the console
    err = capsys.readouterr().err
    assert "io debug" in err and "core info" not in err
    obs.setup(to_file=False)



def _file_handler():
    import logging

    from explorer._name import APP_NAME

    return next(h for h in logging.getLogger(APP_NAME).handlers if isinstance(h, logging.FileHandler))


def test_a_log_file_that_cannot_be_written_says_so_once_not_at_every_line(tmp_path, monkeypatch, capsys):
    """The file was checked only when its handler was made: a full disk or home quota afterwards had logging print
    "--- Logging error ---" and a traceback at every record, the user's own lines buried under them."""
    import logging

    from explorer.obs import log as log_mod

    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    log_mod.setup()
    try:
        fh = _file_handler()

        class Full:
            def write(self, _s):
                raise OSError(28, "No space left on device")

            def flush(self):
                pass
        fh.stream = Full()
        lg = logging.getLogger("explorer.data")
        for _ in range(3):
            lg.warning("a line")
        err = capsys.readouterr().err
        assert "Logging error" not in err, err[-2000:]
        assert err.count("cannot be written") == 1, err[-2000:]
    finally:
        log_mod.setup(to_file=False)


def test_sessions_at_once_share_the_log_without_rotating_it_under_each_other(tmp_path, monkeypatch):
    """One explorer.log for every session, rotated by size while written: a rotation in one session renamed the file
    under the others, which went on writing into .1, and the next rotation clobbered it. It is rotated when a
    session starts, never while one writes; each line says its process."""
    import logging
    import os

    from explorer.obs import log as log_mod

    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    log_mod.setup()
    try:
        fh = _file_handler()
        assert not isinstance(fh, logging.handlers.RotatingFileHandler)
        logging.getLogger("explorer.data").warning("from this session")
        fh.flush()
        text = open(fh.baseFilename).read()
        assert str(os.getpid()) in text
    finally:
        log_mod.setup(to_file=False)


def test_a_trace_pruned_by_another_session_meanwhile_is_passed_over(tmp_path, monkeypatch):
    """Two sessions with --log pruning at once: a file the other removed between the glob and its stat raised
    FileNotFoundError in the sort key."""
    from explorer import _paths

    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    d = tmp_path / "explorer" / "logs"
    d.mkdir(parents=True)
    for k in range(_paths.KEEP_LOGS + 3):
        (d / f"bridge-{k}.log").write_text("x")
    real = type(d).stat

    def stat(self, *a, **kw):
        if self.name == "bridge-1.log":
            raise FileNotFoundError(str(self))
        return real(self, *a, **kw)
    monkeypatch.setattr(type(d), "stat", stat)
    assert _paths.trace_log("bridge").name.startswith("bridge-")

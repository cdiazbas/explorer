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
    t.start(); t.join()
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
    obs.get_logger("data.io").debug("io debug")         # data.io asked for DEBUG: on the console
    err = capsys.readouterr().err
    assert "io debug" in err and "core info" not in err
    obs.setup(to_file=False)

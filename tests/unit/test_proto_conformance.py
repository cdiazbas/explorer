"""bench/proto_conformance.py's sorting of a comparison report's differing steps by kind."""
import importlib.util
import os

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("pc", os.path.join(HERE, "..", "..", "bench", "proto_conformance.py"))
pc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pc)

REPORT = """header
## a_step — same events, another order
  - events (2 lines differ; 5 vs 5 without moves):
    - only prototype: Enter A
    - only explorer: Enter A
## b_step — the prototype's tab bar
  - events (1 lines differ; 6 vs 5 without moves):
    - only prototype: WindowDeactivate QMainWindowTabBar[0]
## c_step — a state differs
  - state[end] `docks.spectrum.size`: prototype `[650, 347]` / explorer `[650, 353]`
## d_step — an event on one side
  - events (1 lines differ; 5 vs 6 without moves):
    - only explorer: ToolTip Viewer
**4 steps differ, 9 identical**
"""


def test_the_kinds():
    assert pc.classify(REPORT) == {"order": ["a_step"], "tab bar": ["b_step"], "other": ["c_step", "d_step"]}

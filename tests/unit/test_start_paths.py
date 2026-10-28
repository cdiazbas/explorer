"""The ways of starting (ROADMAP E5.15): each saved layout (none, one closed in classic, one closed in glass) with
each start (the saved look, or --look classic or glass), started as ui.app.run starts it, then M round every look
and back. Three faults came only from starting in glass with its layout saved, and no test started
so: classic at Qt's 640x480 on leaving glass, glass's panel titles replaced by the chrome's, panels floated before
their window. At every step: the window on its monitor, the image not crushed, the look's own panels and bars; back
at the first look, the window and the panels as they started.

Each case runs explorer in its own process (offscreen), its layout in a file of its own (EXPLORER_LAYOUT).
"""
import json
import os
import subprocess
import sys

import pytest

from explorer.testing import synth

HERE = os.path.dirname(os.path.abspath(__file__))
MIN_IMAGE = 150                                         # px: the image at 62 px wide beside 560-px panels was the fault


@pytest.fixture(scope="module")
def cube(tmp_path_factory):
    return synth.write_dataset(tmp_path_factory.mktemp("starts"), "c", shape=(4, 4, 11, 96, 80), icube=False)["im"]


def run(cube, look, layout):
    env = dict(os.environ, EXPLORER_LAYOUT=str(layout), QT_QPA_PLATFORM="offscreen", EXPLORER_TERMINAL_KEYS="0")
    env.pop("DISPLAY", None)
    p = subprocess.run([sys.executable, os.path.join(HERE, "start_paths_app.py"), str(cube), look],
                       capture_output=True, text=True, env=env, timeout=120)
    steps = [json.loads(line) for line in p.stdout.splitlines() if line.startswith("{")]
    assert p.returncode == 0 and steps, f"exit {p.returncode}\nstdout:\n{p.stdout}\nstderr:\n{p.stderr[-4000:]}"
    return steps


def problems(steps) -> list[str]:
    out = []
    for s in steps:
        at = f"{s['step']} ({s['look']})"
        fx, fy, fw, fh = s["frame"]
        mx, my, mw, mh = s["monitor"]
        if fx < mx - 1 or fy < my - 1 or fx + fw > mx + mw + 1 or fy + fh > my + mh + 1:
            out.append(f"{at}: the window {s['frame']} is off its monitor {s['monitor']}")
        if min(s["image"]) < MIN_IMAGE:
            out.append(f"{at}: the image is crushed to {s['image']}")
        shown = {k: d for k, d in s["docks"].items() if d["visible"]}
        if s["look"] == "glass":
            glassy = all(d["floating"] and d["title"] == "PanelTitle" for d in shown.values())
            if s["toolbar"] or not shown or not glassy:
                out.append(f"{at}: not glass's panels and bars: toolbar {s['toolbar']}, panels {s['docks']}")
        else:
            if not s["toolbar"] or s["toolbar_actions"] < 5 or s["glass_bar"]:
                out.append(f"{at}: the toolbar {s['toolbar']} with {s['toolbar_actions']} controls, glass bar "
                           f"{s['glass_bar']}")
            if any(d["floating"] or d["title"] == "PanelTitle" for d in shown.values()):
                out.append(f"{at}: glass's panels out of glass: {s['docks']}")
    first, last = steps[0], steps[-1]
    if last["look"] == first["look"]:
        for key in ("geometry", "image", "docks"):
            if last[key] != first[key]:
                out.append(f"back in {first['look']}: {key} {last[key]} where it started {first[key]}")
    return out


@pytest.mark.parametrize("saved", [None, "classic", "glass"])
@pytest.mark.parametrize("start", ["-", "classic", "glass"])
def test_every_start_and_back(cube, tmp_path, saved, start):
    layout = tmp_path / "layout.ini"
    if saved is not None:
        run(cube, saved, layout)                        # a session that closed in that look
    steps = run(cube, start, layout)
    if start == "-":
        assert steps[0]["look"] == (saved or "classic"), steps[0]
    found = problems(steps)
    assert not found, "\n".join(found) + "\n\nsteps:\n" + "\n".join(json.dumps(s) for s in steps)

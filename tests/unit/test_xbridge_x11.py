"""The bridge on a private X server: a window mapped with Qt's pixels, X input reaching Qt (a key moves t, a motion
moves the cursor), a floating panel transient for the main window, a popup, a shape, the clipboard both ways, the
traffic statistics, and the exit when the display goes away. Also the legacy input path.

Needs a private, local X server with XTEST (Xvfb): EXPLORER_XVFB_DISPLAY=:N and EXPLORER_XVFB_AUTH=<its cookie file>;
skipped otherwise. Only a local ":N" display is accepted, so these tests never draw on anyone's screen. Qt stays on
the offscreen platform: the bridge is what draws on the X server.
"""
import json
import os
import re
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(os.path.dirname(os.path.dirname(HERE)), "src")


def private_x():
    disp = os.environ.get("EXPLORER_XVFB_DISPLAY", "")
    if not re.fullmatch(r":\d+", disp) or not os.path.exists(f"/tmp/.X11-unix/X{disp[1:]}"):
        return None
    return disp, os.environ.get("EXPLORER_XVFB_AUTH", "")


pytestmark = pytest.mark.skipif(private_x() is None, reason="no private X server (EXPLORER_XVFB_DISPLAY=:N)")


def run_child(work, *args, **env_extra):
    disp, auth = private_x()                            # type: ignore[misc]
    env = {k: v for k, v in os.environ.items() if k not in ("QT_QPA_PLATFORM", "EXPLORER_X11", "LD_PRELOAD")
           and not k.startswith("EXPLORER_XB_")}
    env.update(DISPLAY=disp, XAUTHORITY=auth, XDG_CACHE_HOME=str(work / "cache"), XDG_CONFIG_HOME=str(work / "cfg"),
               PYTHONPATH=SRC + os.pathsep + env.get("PYTHONPATH", ""), **env_extra)
    p = subprocess.run([sys.executable, os.path.join(HERE, "xbridge_child.py"), str(work), *args], env=env,
                       capture_output=True, text=True, timeout=300)
    assert p.returncode == 0, p.stderr[-3000:]
    return json.loads(p.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def seen(tmp_path_factory):
    return run_child(tmp_path_factory.mktemp("xbridge"))


@pytest.fixture(scope="module")
def seen_legacy(tmp_path_factory):
    return run_child(tmp_path_factory.mktemp("xbridge_legacy"), "--input-only", EXPLORER_XB_INPUT="legacy")


def test_a_window_mapped_with_the_image(seen):
    assert seen["plan"] == "x11bridge" and seen["qpa"] == "offscreen" and seen["input"] == "platform"
    assert seen["first_image"] and seen["mapped"] and seen["x_size"] == seen["qt_size"] == [640, 480]
    assert seen["x_origin_is_qt_pos"]
    assert seen["differing_px"] == 0 and seen["differing_px_after_step"] == 0


def test_input_reaches_qt(seen):
    assert seen["key_moves_t"] and seen["key_image_shown"]
    assert seen["motion_moves_cursor"] and seen["cursor"] == seen["cursor_expected"]
    assert seen["cursor_pos_follows_x"]


def test_legacy_input_reaches_qt_too(seen_legacy):
    assert seen_legacy["input"] == "legacy" and seen_legacy["differing_px"] == 0
    assert seen_legacy["key_moves_t"] and seen_legacy["motion_moves_cursor"]
    assert seen_legacy["cursor"] == seen_legacy["cursor_expected"]


def test_panel_popup_and_shape(seen):
    assert seen["panel_has_x_window"] and seen["panel_transient_for_main"]
    assert seen["panel_type"] == "_NET_WM_WINDOW_TYPE_UTILITY"      # the manager's frames: no title bar of ours
    assert seen["panel_title"] == "panel λ–t" and seen["panel_differing_px"] == 0 and seen["panel_gone_with_hide"]
    assert seen["popup_has_x_window"] and seen["popup_override_redirect"]
    assert seen["shape_rects"] > 1 and seen["shape_cleared"]


def test_clipboard_both_ways(seen):
    assert seen["clip_owner_is_bridge"] and seen["clip_qt_to_x"] == "explorer ñ"
    assert seen["clip_x_to_qt"] == "from X"


def test_traffic_statistics(seen):
    st = seen["step_traffic"]
    assert st["updates"] >= 1 and 0 < st["bytes"]
    if st["grey"]:                                      # the image is grey: ~1 byte per pixel of the panel, not 4
        assert st["bytes"] < 2 * st["panel_px"]
    s = seen["summary"]
    assert s["frames"] >= 2 and s["MB"] >= 0 and s["send_ms_median"] is not None and s["grab_ms_median"] is not None
    assert seen["link"] == ([1.3, 12] if st["grey"] else [2.5, 12])


def test_exit_when_the_display_goes_away(seen):
    assert seen["exit_when_x_gone"] == 1

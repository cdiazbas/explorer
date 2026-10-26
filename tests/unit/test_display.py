"""Display: the environment before Qt, a stop with a message, the application, a window attached, the link."""
import pytest

from explorer._name import APP_NAME
from explorer.platform import plan
from explorer.platform.display import Display, NoDisplay, for_plan
from explorer.platform.plan import DisplayPlan, choose_display

SSH = {"SSH_CONNECTION": "1.2.3.4 5 6.7.8.9 22"}


@pytest.fixture(autouse=True)
def _with_xcb_cursor(monkeypatch):
    """Qt's xcb in these plans, as on a system with libxcb-cursor (test_display_plan: without it)."""
    monkeypatch.setattr(plan, "find_xcb_cursor", lambda env: "/usr/lib64/libxcb-cursor.so.0")


def test_prepare_env_sets_what_the_plan_asks_or_stops():
    env = {}
    Display(choose_display({"DISPLAY": "localhost:10.0", **SSH}, "linux", "native")).prepare_env(env)
    assert env == {"QT_QPA_PLATFORM": "xcb"}
    with pytest.raises(NoDisplay, match="ssh -Y"):
        Display(choose_display({}, "linux")).prepare_env({})


def test_the_application_and_a_window(qapp):
    from PySide6 import QtWidgets

    disp = Display(DisplayPlan("offscreen"))
    app = disp.make_app()
    assert app is qapp and app.applicationName() == APP_NAME and app.style().name().lower() == "fusion"
    w = QtWidgets.QWidget()
    ops = disp.attach(app, w)
    ops.resize(320, 200)
    qapp.processEvents()
    assert w.isVisible() and (w.width(), w.height()) == (320, 200)
    ops.activate()
    w.close()


def test_the_link_and_what_it_reports():
    remote = Display(choose_display({"DISPLAY": "localhost:10.0", **SSH}, "linux", "native"))
    assert remote.link().bytes_per_px == 4.8 and remote.link().fps_cap == 30      # Qt's own X11
    assert remote.stats()["remote"] and not remote.stats()["bridge"]
    bridged = for_plan(choose_display({"DISPLAY": "localhost:10.0", **SSH}, "linux"))
    assert bridged.link().bytes_per_px == 1.3 and bridged.link().fps_cap == 10    # the bridge, over ssh by default
    local = Display(choose_display({"DISPLAY": ":0"}, "linux"))
    assert local.link().fps_cap is None and local.kind == "xcb"

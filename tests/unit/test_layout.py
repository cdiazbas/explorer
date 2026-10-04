"""The window's layout across sessions (ROADMAP E5.3), offscreen: geometry and panel places come back; a panel closed
at exit is open at start; a zoomed close keeps the last normal size; a window that no longer fits its monitor gets
the first window's size; another schema's layout is discarded; forget starts fresh; the Shell keeps its own on
close, its theme with it, one per way of displaying; the file is the user's config, or EXPLORER_LAYOUT."""
import pytest
from PySide6 import QtCore

SHAPE = (6, 4, 21, 48, 40)


def window(qapp):
    from PySide6 import QtWidgets

    w = QtWidgets.QMainWindow()
    w.setCentralWidget(QtWidgets.QLabel("image"))
    for name in ("spectrum", "lambda_t"):
        d = QtWidgets.QDockWidget(name, w)
        d.setObjectName(name)
        d.setWidget(QtWidgets.QLabel(name))
        w.addDockWidget(QtCore.Qt.DockWidgetArea.RightDockWidgetArea, d)
    return w


@pytest.fixture
def store(tmp_path):
    from explorer.ui.layout import LayoutStore

    return LayoutStore("test", str(tmp_path / "layout.ini"))


def dock(w, name):
    from PySide6 import QtWidgets

    return w.findChild(QtWidgets.QDockWidget, name)


def test_geometry_and_places_come_back_and_a_closed_panel_is_open(qapp, store):
    a = window(qapp)
    a.setGeometry(60, 50, 600, 480)
    a.show()
    sp = dock(a, "spectrum")                            # held: out of the layout, a dock nobody holds is deleted
    a.removeDockWidget(sp)
    a.addDockWidget(QtCore.Qt.DockWidgetArea.LeftDockWidgetArea, sp)
    sp.show()
    dock(a, "lambda_t").close()
    qapp.processEvents()
    store.save(a)
    a.close()
    b = window(qapp)
    assert store.restore(b, qapp)
    b.show()
    qapp.processEvents()
    assert (b.width(), b.height()) == (600, 480)
    assert b.dockWidgetArea(dock(b, "spectrum")) == QtCore.Qt.DockWidgetArea.LeftDockWidgetArea
    assert not dock(b, "lambda_t").isHidden()            # places and sizes, never absences
    b.close()


def test_a_zoomed_close_keeps_the_last_normal_size(qapp, store):
    a = window(qapp)
    a.setGeometry(60, 50, 600, 480)
    a.show()
    store.save(a)
    a.setGeometry(0, 0, 1500, 1000)
    store.save(a, zoomed=True)
    a.close()
    b = window(qapp)
    store.restore(b, qapp)
    assert (b.width(), b.height()) == (600, 480)
    b.close()


def test_a_window_too_big_for_its_monitor_never_comes_back_larger(qapp, store):
    """Qt's restoreGeometry clamps to the screen; where it does not (two monitors taken as one screen), the first
    window's size: either way the window fits its monitor."""
    from explorer.platform.screens import monitor_rect
    from explorer.ui import layout

    a = window(qapp)
    a.setGeometry(0, 0, 9000, 6000)
    store.save(a)
    a.close()
    b = window(qapp)
    store.restore(b, qapp)
    f = b.frameGeometry()
    m = monitor_rect(qapp, f.center())
    assert f.width() <= m.width() * layout.FITS and f.height() <= m.height() * layout.FITS
    b.close()


def test_another_schema_is_discarded(qapp, store):
    from explorer.ui import layout

    st = QtCore.QSettings(store.path, QtCore.QSettings.Format.IniFormat)
    st.setValue("app/v0.test/state", b"not a state of this schema")
    st.sync()
    b = window(qapp)
    assert not store.restore(b, qapp)
    st = QtCore.QSettings(store.path, QtCore.QSettings.Format.IniFormat)
    assert not any(k.startswith("app/v0.") for k in st.allKeys())
    assert store.kind == f"v{layout.SCHEMA}.test"
    b.close()


def test_forget_starts_fresh(qapp, store):
    from explorer.ui import docks

    a = window(qapp)
    a.setGeometry(60, 50, 600, 480)
    store.save(a)
    a.close()
    store.forget()
    st = QtCore.QSettings(store.path, QtCore.QSettings.Format.IniFormat)
    assert not st.contains(store.geometry_key) and not st.contains(store.state_key)
    b = window(qapp)
    assert not store.restore(b, qapp)
    assert b.geometry() == docks.first_geometry(qapp)
    b.close()


def test_the_file_is_the_users_config_or_explorer_layout(monkeypatch, tmp_path):
    from explorer.ui import layout

    monkeypatch.delenv(layout.ENV, raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    assert layout.layout_path() == str(tmp_path / "cfg" / "explorer" / "layout.ini")
    monkeypatch.setenv(layout.ENV, str(tmp_path / "other.ini"))
    assert layout.layout_path() == str(tmp_path / "other.ini")


@pytest.fixture(scope="module")
def cube(tmp_path_factory):
    from explorer.testing import synth

    return synth.write_dataset(tmp_path_factory.mktemp("layout"), "c", shape=SHAPE, icube=False)["im"]


def test_the_shell_keeps_its_layout_on_close(qapp, cube, store):
    from explorer.data.dataset import Dataset
    from explorer.ui.shell import Shell

    ds = Dataset.open(cube)
    w = Shell(ds)
    w.layout_store = store
    w.setGeometry(70, 60, 1000, 700)
    w.show()
    qapp.processEvents()
    w.close()
    ds.close()
    st = QtCore.QSettings(store.path, QtCore.QSettings.Format.IniFormat)
    assert st.contains(store.geometry_key) and st.contains(store.state_key)


def test_the_glass_look_keeps_a_layout_of_its_own(qapp, store):
    """Its panels float and its toolbar is hidden: kept apart, the other looks never get them."""
    g = store.for_look("glass")
    assert g.kind == store.kind + "-glass" and g.path == store.path
    assert g.for_look("modern").kind == store.kind and store.for_look("classic") is store
    a = window(qapp)
    a.setGeometry(60, 50, 600, 480)
    g.save(a, look="glass")
    a.close()
    b = window(qapp)
    assert not store.restore(b, qapp)                   # nothing saved for the others
    assert g.restore(b, qapp) and (b.width(), b.height()) == (600, 480)
    b.close()


def test_a_restored_layout_leaves_the_toolbar_as_the_look_wants_it(qapp, store):
    """A saved state holds the toolbar's visibility: one saved by glass (toolbar hidden) left the other looks without
    it, and one with the toolbar shown left an empty 20-px bar over the glass look's image. After a restore the
    toolbar is shown, and hidden in glass, as the prototype does (viewer.py:2413-2415, look_glass.py:618-622;
    F81, F82; ROADMAP E5.18)."""
    from types import SimpleNamespace

    def with_toolbar(look):
        w = window(qapp)
        tb = w.addToolBar("Navigation")
        tb.setObjectName("nav")
        w.look = SimpleNamespace(name=look)
        w.show()
        return w, tb

    # the window's look may still be the other one: leaving glass restores the classic layout before the switch ends
    for saved_shown, look, wearing in ((False, "classic", "classic"), (True, "glass", "glass"),
                                       (False, "classic", "glass")):
        lay = store.for_look(look)
        a, tb = with_toolbar(look)
        tb.setVisible(saved_shown)
        lay.save(a, look=look)
        a.close()
        b, tb = with_toolbar(wearing)
        tb.setVisible(saved_shown)
        lay.restore(b, qapp)
        assert tb.isVisible() == (look != "glass"), (look, wearing)
        b.close()


def test_the_theme_is_kept_per_way_of_displaying(qapp, store):
    """Through the bridge auto is dark, on a local Mac native: light chosen in one is not the other's default. Glass
    keeps a layout of its own but not a theme of its own."""
    from explorer.ui.layout import LayoutStore

    w = window(qapp)
    w.show()
    qapp.processEvents()
    store.save(w, theme="light")
    assert store.theme() == "light" and store.for_look("glass").theme() == "light"
    assert LayoutStore("other", store.path).theme() is None
    store.save(w)                                       # no theme given: the kept one stays
    assert store.theme() == "light"
    w.close()

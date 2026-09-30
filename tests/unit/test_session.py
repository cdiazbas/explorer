"""Session: the prototype's start, hover, index changes and lock, on one cube; the index each read needs."""
import types

import pytest

from explorer.core.loop import ManualLoop
from explorer.core.session import Session
from explorer.data.axes import roles
from explorer.obs import summary


def cube(names=("UTC", "STOKES", "WAVE", "HPLT", "HPLN"), shape=(5, 4, 7, 30, 20)):
    return types.SimpleNamespace(roles=roles(names, shape), shape=shape, ny=shape[-2], nx=shape[-1])


@pytest.fixture
def session():
    return Session(ManualLoop(), cube())


def test_starts_as_the_prototype(session):
    st = session.state
    assert (st.t, st.s, st.l, st.cursor, st.locked) == (0, 0, 3, (15, 10), False)
    assert session.index() == (0, 0, 3)


def test_hover_is_clipped_ignored_when_locked_and_skipped_on_the_same_pixel(session):
    session.hover(-5, 400)
    assert session.state.cursor == (0, 19)
    before = summary().get("counters", {}).get("core.hover.same_pixel", 0)
    session.hover(0, 19)
    assert summary()["counters"]["core.hover.same_pixel"] == before + 1
    session.lock()
    session.hover(7, 7)
    assert session.state.cursor == (0, 19) and session.state.locked
    session.lock(False)
    session.hover(7, 7)
    assert session.state.cursor == (7, 7)


def test_index_changes_clip_and_step_wraps_only_when_asked(session):
    session.set_index("t", 99)
    assert session.state.t == 4
    session.step("t", 1)
    assert session.state.t == 4                          # stops at the end
    session.step("t", 1, wrap=True)
    assert session.state.t == 0                          # playback goes round
    session.step("l", -10)
    assert session.state.l == 0
    session.set_index("s", 2)
    assert session.index() == (0, 2, 0)
    with pytest.raises(ValueError):
        session.set_index("x", 1)


def test_a_burst_of_steps_is_one_notice(session):
    got = []
    session.store.subscribe(lambda st, ch: got.append((st.t, ch)))
    for _ in range(3):
        session.step("t", 1)
    session.hover(1, 1)
    session.store.loop.pump()
    assert got == [(3, {"t", "cursor"})]


def test_a_cube_without_stokes_ignores_it():
    s = Session(ManualLoop(), cube(("WAVE", "UTC", "HPLT", "HPLN"), (7, 5, 30, 20)))
    s.set_index("s", 1)
    s.set_index("t", 2)
    assert s.state.s == 0 and s.index() == (3, 2)        # (lambda, t) order of this cube


def test_panels_and_a_second_cube(session):
    session.show("lambda_t", False)
    assert session.state.panels == {"spectra"}
    session.show("lambda_t")
    assert session.state.panels == {"spectra", "lambda_t"}
    with pytest.raises(NotImplementedError):
        session.add(cube())


def test_with_a_real_dataset(tmp_path):
    import numpy as np
    from astropy.io import fits

    from explorer.data.dataset import Dataset
    from explorer.testing import synth

    d = synth.write_dataset(tmp_path, "c", shape=(3, 4, 5, 24, 20), icube=False)
    data = fits.getdata(d["im"]).astype(np.float32)
    with Dataset.open(d["im"]) as ds:
        s = Session(ManualLoop(), ds)
        s.set_index("t", 2)
        s.set_index("s", 3)
        assert s.index() == (2, 3, 2)
        np.testing.assert_array_equal(ds.image(s.index()).result(5), data[2, 3, 2])

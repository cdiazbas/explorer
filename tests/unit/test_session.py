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


def test_panels(session):
    session.show("lambda_t", False)
    assert session.state.panels == {"spectra"}
    session.show("lambda_t")
    assert session.state.panels == {"spectra", "lambda_t"}


def test_a_linked_cube_follows_t_and_the_cursor_with_its_own_lambda(session):
    k = session.add(cube(shape=(5, 4, 9, 30, 20)))       # another line: 9 tunings
    m = session.members[k]
    print("member", k, "link_l", m.link_l, "link_s", m.link_s, "own", session.state.own)
    assert (k, m.link_l, m.link_s, session.state.own) == (1, False, True, ((4, 0),))
    session.set_index("t", 3)
    session.set_index("s", 2)
    session.set_index("l", 6)                            # the main cube's lambda: not the linked one's
    session.set_member_index(k, "l", 99)                 # its own, clipped to its 9
    st = session.member_state(k)
    print("main", session.index(), "linked", session.index(k))
    assert (st.t, st.s, st.l) == (3, 2, 8) and session.index(k) == (3, 2, 8) and session.index() == (3, 2, 6)
    session.set_member_index(k, "s", 1)                  # linked Stokes: the main cube's
    assert session.state.s == 1 and session.index(k) == (3, 1, 8)


def test_a_linked_cube_reads_its_own_panels_and_no_slit(session):
    k = session.add(cube())
    session.show("spectra:1")
    session.store.set(path=((1.0, 1.0), (5.0, 5.0)))
    st = session.member_state(k)
    print("main panels", sorted(session.state.panels), "linked", sorted(st.panels))
    assert st.panels == {"spectra", "image"} and st.path is None and session.state.path is not None


def test_the_slit_records_the_cube_it_was_drawn_on(session):
    """The slit panel shows the slices of the cube the slit was drawn on: set_path and set_draft record it, None
    leaves it, a cube the session does not have is refused."""
    k = session.add(cube())
    session.set_draft(((1.5, 1.5),), k)
    session.set_path(((1.5, 1.5), (9.5, 4.5)), k)
    assert (session.state.draft_cube, session.state.path_cube) == (k, k)
    session.set_path(((2.5, 1.5), (9.5, 4.5)))
    assert session.state.path_cube == k
    session.set_path(((2.5, 1.5), (9.5, 4.5)), 0)
    assert session.state.path_cube == 0
    with pytest.raises(ValueError):
        session.set_path(((2.5, 1.5), (9.5, 4.5)), 2)


def test_a_single_frame_is_shown_at_every_t(session):
    k = session.add(cube(("HPLT", "HPLN"), (30, 20)))     # a map: no leading axes
    session.set_index("t", 4)
    st = session.member_state(k)
    assert st.t == 0 and session.index(k) == ()


def test_another_grid_is_refused(session):
    with pytest.raises(ValueError, match="pixels"):
        session.add(cube(shape=(5, 4, 7, 31, 20)))


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

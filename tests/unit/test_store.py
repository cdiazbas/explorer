"""ViewState and Store: one notice per burst, with what changed; nothing for no change; listeners isolated; the
manual loop runs nothing until pump(), and takes posts from other threads."""
import dataclasses
import threading

import pytest

from explorer.core.loop import ManualLoop
from explorer.core.state import Store, ViewState


@pytest.fixture
def store():
    return Store(ManualLoop())


def test_a_burst_gives_one_notice_with_every_field_that_changed(store):
    got = []
    store.subscribe(lambda st, ch: got.append((st, ch)))
    for x in range(10):                                  # a mouse moved over ten pixels
        store.set(cursor=(5, x))
    store.set(t=3)
    assert got == []                                     # nothing before the loop runs
    store.loop.pump()
    assert len(got) == 1 and got[0][1] == {"cursor", "t"} and got[0][0].cursor == (5, 9)


def test_no_notice_without_a_change(store):
    got = []
    store.subscribe(lambda st, ch: got.append(ch))
    store.set(t=0)                                       # already 0
    store.set(l=2)
    store.set(l=0)                                       # changed and changed back within the burst
    store.loop.pump()
    assert got == [] and store.loop.pending() == 0


def test_bursts_are_measured_against_the_last_notice(store):
    got = []
    store.subscribe(lambda st, ch: got.append(ch))
    store.set(s=1)
    store.loop.pump()
    store.set(s=1, locked=True)
    store.loop.pump()
    assert got == [{"s"}, {"locked"}]


def test_state_is_immutable_and_unknown_fields_are_refused(store):
    with pytest.raises(dataclasses.FrozenInstanceError):
        store.state.t = 4                                # type: ignore[misc]
    with pytest.raises(TypeError):
        store.set(stokes=2)
    assert ViewState().panels == {"spectra", "lambda_t"}


def test_a_listener_that_fails_does_not_silence_the_others(store, caplog):
    got = []
    store.subscribe(lambda st, ch: 1 / 0)
    store.subscribe(lambda st, ch: got.append(ch))
    store.set(t=1)
    store.loop.pump()
    assert got == [{"t"}] and any("state listener" in r.getMessage() for r in caplog.records)


def test_unsubscribe_and_changes_made_while_notifying(store):
    got = []
    off = store.subscribe(lambda st, ch: got.append(ch))

    def follow(st, ch):                                  # a listener that changes the state: next pass, not now
        if "t" in ch:
            store.set(l=st.t)

    store.subscribe(follow)
    store.set(t=2)
    store.loop.pump()                                    # runs the notice and the one it scheduled
    assert got == [{"t"}, {"l"}] and store.state.l == 2
    off()
    store.set(t=3)
    store.loop.pump()
    assert got == [{"t"}, {"l"}]


def test_posts_from_other_threads_run_on_the_pumping_thread():
    loop = ManualLoop()
    ran = []
    workers = [threading.Thread(target=lambda i=i: loop.post(lambda: ran.append((i, threading.get_ident()))))
               for i in range(8)]
    for w in workers:
        w.start()
    for w in workers:
        w.join()
    assert loop.pump() == 8 and {t for _, t in ran} == {threading.get_ident()} and len(ran) == 8

"""Executors: stale work is skipped, results are shown unless a newer one was, and parallel numba runs on one
thread with the thread count set on that thread."""
import threading
import time

from explorer.data.executors import Executors, Generations, ShownGate


def test_a_newer_request_skips_the_older_job():
    ex = Executors(gather_threads=2, io_threads=1, strips=1)
    gate = threading.Event()
    ran = []
    blocker = ex.numba.submit(gate.wait, 5)                 # keep the numba thread busy
    _, old = ex.submit_latest("cursor", lambda cur, v: ran.append(v) or v, "old")
    _, new = ex.submit_latest("cursor", lambda cur, v: ran.append(v) or v, "new")
    gate.set()
    blocker.result()
    assert old.result(5) is None and new.result(5) == "new" and ran == ["new"]
    ex.close()


def test_a_job_can_stop_between_its_steps():
    ex = Executors(gather_threads=2, io_threads=1, strips=1)
    started, steps = threading.Event(), []

    def job(still_current):
        steps.append("spectrum")
        started.set()
        time.sleep(0.05)
        if not still_current():
            return "stopped before lambda-t"
        steps.append("lambda-t")
        return "done"

    _, f = ex.submit_latest("cursor", job)
    started.wait(5)
    ex.generations.new("cursor")                            # the mouse moved on
    assert f.result(5) == "stopped before lambda-t" and steps == ["spectrum"]
    ex.close()


def test_results_are_shown_unless_a_newer_one_was():
    gate = ShownGate()
    assert gate.accept("cursor", 3)
    assert gate.accept("cursor", 5)
    assert not gate.accept("cursor", 4)                     # arrived after 5 was shown
    assert gate.accept("cursor", 5) and gate.accept("slit", 1)


def test_generations_are_per_key():
    g = Generations()
    a, b = g.new("cursor"), g.new("slit")
    assert not g.stale("cursor", a) and not g.stale("slit", b)
    g.new("cursor")
    assert g.stale("cursor", a) and not g.stale("slit", b)


def test_numba_threads_are_set_on_the_numba_thread():
    import numba

    ex = Executors(gather_threads=2, io_threads=1, strips=1)
    assert ex.numba_threads == min(2, numba.config.NUMBA_NUM_THREADS)
    assert ex.numba.submit(numba.get_num_threads).result() == ex.numba_threads
    ex.close()


def test_gather_from_many_threads_goes_through_the_numba_thread(tmp_path):
    """Requests from several threads at once: every gather runs on the numba thread, one at a time, and the
    results that run are right (two parallel regions at once abort the process with 'workqueue')."""
    from concurrent.futures import ThreadPoolExecutor

    import numpy as np
    from astropy.io import fits

    from explorer.data import formats
    from explorer.data.io import FrameReader
    from explorer.testing import synth

    ds = synth.write_dataset(tmp_path, "c", shape=(2, 4, 3, 16, 12))
    data = fits.getdata(ds["im"]).astype(np.float32)
    ex = Executors(gather_threads=4, io_threads=1, strips=1)
    names, busy, overlap = set(), [0], []
    lock = threading.Lock()
    with FrameReader(formats.open_layout(ds["im"])) as r:
        def job(still_current, y, x):
            with lock:
                busy[0] += 1
                overlap.append(busy[0] > 1)
                names.add(threading.current_thread().name)
            try:
                return (y, x), r.series(y, x, (0, 0, 0), [0, 2])
            finally:
                with lock:
                    busy[0] -= 1

        def ask(i):
            return ex.submit_latest(f"view{i % 4}", job, i % 16, i % 12)[1]

        with ThreadPoolExecutor(8) as callers:
            futs = list(callers.map(ask, range(200)))
        done = [f.result(30) for f in futs]
    ran = [d for d in done if d is not None]
    assert ran and not any(overlap) and all(n.startswith("numba") for n in names)
    for (y, x), lt in ran:
        np.testing.assert_array_equal(lt, data[:, 0, :, y, x])
    ex.close()

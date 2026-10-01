"""The Qt loop: call_soon and call_later on the main thread, posts from other threads run on the main thread, a
failing callback is logged; and a real scheduler on the synthetic cube delivers only on the main thread."""
import threading
import time

import numpy as np

from explorer.ui.loop import QtLoop


def spin(qapp, until, timeout=10.0):
    end = time.perf_counter() + timeout
    while not until() and time.perf_counter() < end:
        qapp.processEvents()
        time.sleep(0.001)
    return until()


def test_soon_later_and_posts_from_other_threads(qapp):
    loop, main, ran = QtLoop(), threading.get_ident(), []
    loop.call_later(0.05, lambda: ran.append(("later", threading.get_ident(), time.perf_counter())))
    t0 = time.perf_counter()
    loop.call_soon(lambda: ran.append(("soon", threading.get_ident(), time.perf_counter())))
    workers = [threading.Thread(target=lambda i=i: loop.post(lambda: ran.append(("post", threading.get_ident(), i))))
               for i in range(8)]
    for w in workers:
        w.start()
    for w in workers:
        w.join()
    assert spin(qapp, lambda: len(ran) == 10)
    assert {r[1] for r in ran} == {main}                                     # all on the main thread
    assert [r[0] for r in ran][0] == "soon" and [r[0] for r in ran][-1] == "later"
    later = next(r for r in ran if r[0] == "later")
    assert later[2] - t0 >= 0.045


def test_a_failing_callback_is_logged_and_the_loop_goes_on(qapp, caplog):
    loop, ran = QtLoop(), []
    loop.post(lambda: 1 / 0)
    loop.post(lambda: ran.append(1))
    assert spin(qapp, lambda: ran == [1])
    assert any("callback" in r.getMessage() for r in caplog.records)


def test_a_scheduler_on_qt_delivers_on_the_main_thread(qapp, tmp_path):
    from explorer.core.scheduler import Scheduler
    from explorer.core.session import Session
    from explorer.data.dataset import Dataset
    from explorer.testing import synth

    main, threads, got = threading.get_ident(), set(), []

    class Sink:
        def _rec(self, kind):
            threads.add(threading.get_ident())
            got.append(kind)

        def image(self, *a): self._rec("image")
        def spectra(self, *a): self._rec("spectra")
        def lambda_t(self, *a): self._rec("lambda_t")
        def cleared(self, *a): self._rec("cleared")
        def y_range(self, *a): self._rec("y_range")
        def units(self, *a): self._rec("units")

    d = synth.write_dataset(tmp_path, "c", shape=(3, 4, 5, 48, 40), icube=False)
    with Dataset.open(d["im"], no_sp=True) as ds:                            # series read on the numba thread
        sess = Session(QtLoop(), ds)
        sched = Scheduler(sess, Sink())
        assert spin(qapp, lambda: "lambda_t" in got)
        for x in range(10, 20):
            sess.hover(24, x)
        sess.set_index("t", 1)
        assert spin(qapp, lambda: got.count("image") >= 2 and got.count("lambda_t") >= 2)
        assert spin(qapp, lambda: not sched.in_flight())
        assert threads == {main} and np.all(np.isfinite(sched.img[24, 10:20]))
        sched.close()


def test_nothing_runs_after_the_loop_is_gone(qapp):
    """What is due soon or later on a loop whose window was deleted is dropped: it would act on panels that no
    longer exist (the spectra's refit at rest, 0.4 s after the last spectrum)."""
    import time

    from PySide6 import QtCore, QtWidgets

    from explorer.ui.loop import QtLoop

    owner = QtWidgets.QWidget()
    loop = QtLoop(owner)
    ran = []
    loop.call_soon(lambda: ran.append("soon"))
    loop.call_later(0.05, lambda: ran.append("later"))
    owner.deleteLater()
    QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
    end = time.perf_counter() + 0.2
    while time.perf_counter() < end:
        qapp.processEvents()
        time.sleep(0.005)
    assert ran == []

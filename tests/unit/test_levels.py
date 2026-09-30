"""Contrast levels: the image's rule and cache, the panels' rule, fixed levels per Stokes kind; and the scheduler
hands them with each image and lambda-t."""
import numpy as np

from explorer.core.levels import Levels, image_levels, panel_levels
from explorer.data.stats import limits
from explorer.obs import summary


def test_image_levels_are_the_prototype_limits():
    img = np.random.default_rng(0).normal(5, 1, (64, 64)).astype(np.float32)
    assert image_levels(img, False) == limits(img, symmetric=False)
    assert image_levels(img - 5, True) == limits(img - 5, symmetric=True)


def test_panel_levels_as_the_prototype_lambda_t_and_its_modern_look():
    rng = np.random.default_rng(1)
    lt = rng.normal(2, 1, (40, 14))
    lt[0, :] = np.nan
    f = lt[np.isfinite(lt)]
    assert panel_levels(lt, False) == tuple(float(v) for v in np.percentile(f, (1, 99)))
    m = float(np.percentile(np.abs(f), 99))
    assert panel_levels(lt, True) == (-m, m)
    assert panel_levels(np.full((3, 3), np.nan), False) == (0.0, 1.0)
    assert panel_levels(np.array([[1.0, 3.0]]), False) == (1.0, 3.0)                 # few values: min-max
    assert panel_levels(np.array([[2.0, 2.0]]), False) == (2.0, 3.0)                 # flat
    assert panel_levels(np.zeros((4, 4)), True) == (0.0, 1.0)                        # |v| all 0: not symmetric


def test_cache_per_index_and_fixed_levels_kept_apart_for_i_and_quv():
    rng = np.random.default_rng(2)
    a, b = rng.normal(5, 1, (32, 32)), rng.normal(9, 3, (32, 32))
    lv = Levels(capacity=2)
    first = lv.image((0, 0, 1), False, a)
    before = summary()["counters"].get("core.levels.cached", 0)
    assert lv.image((0, 0, 1), False, b) == first                                   # cached by index
    assert summary()["counters"]["core.levels.cached"] == before + 1
    lv.image((1, 0, 1), False, b)
    lv.image((2, 0, 1), False, b)                                                   # capacity 2: (0, 0, 1) out
    assert lv.image((0, 0, 1), False, b) == image_levels(b, False)
    fixed = lv.fix(a, False)
    assert lv.image((5, 0, 1), False, b) == fixed and lv.fixed(False) and not lv.fixed(True)
    assert lv.image((5, 1, 1), True, b - 9) == image_levels(b - 9, True)             # Q: not I's fixed levels
    lv.unfix()
    assert lv.image((6, 0, 1), False, b) == image_levels(b, False)


def test_the_scheduler_hands_levels_and_fixes_them(tmp_path):
    import concurrent.futures as cf

    from explorer.core.loop import ManualLoop
    from explorer.core.scheduler import Scheduler
    from explorer.core.session import Session
    from explorer.data.dataset import Dataset
    from explorer.testing import synth
    d = synth.write_dataset(tmp_path, "c", shape=(3, 4, 5, 48, 40), icube=False)
    got = []

    class Sink:
        def image(self, idx, img, levels):
            got.append(("image", idx, levels))

        def spectra(self, spec, pixel, t):
            pass

        def lambda_t(self, lt, pixel, s, levels):
            got.append(("lambda_t", s, levels))

        def cleared(self, pixel):
            pass

        def y_range(self, k, r):
            pass

        def units(self, iscale):
            pass

    def settle(sched):
        for _ in range(100):
            cf.wait(sched.in_flight(), timeout=5)
            if sched.loop.pump() == 0 and not sched.in_flight():
                return

    with Dataset.open(d["im"], no_sp=True) as ds:
        sess = Session(ManualLoop(), ds)
        sched = Scheduler(sess, Sink())
        settle(sched)
        img0 = ds.image((0, 0, 2)).result()
        assert got[0] == ("image", (0, 0, 2), image_levels(img0, False))
        lt_levels = [g for g in got if g[0] == "lambda_t"][-1][2]
        assert lt_levels[0] < lt_levels[1]
        sched.fix_levels(True)
        sess.set_index("t", 1)
        sess.store.loop.pump()
        settle(sched)
        assert got[-1][0] == "image" and got[-1][2] == image_levels(img0, False)       # t = 1 drawn with t = 0's
        sess.set_index("s", 3)
        sess.store.loop.pump()
        settle(sched)
        v_img = ds.image((1, 3, 2)).result()
        imgs = [g for g in got if g[0] == "image"]
        assert imgs[-1][2] == image_levels(v_img, True)                                 # V: its own, symmetric
        lts = [g for g in got if g[0] == "lambda_t"]
        assert lts[-1][1] == 3 and lts[-1][2][0] == -lts[-1][2][1]                      # V's lambda-t symmetric
        sched.close()

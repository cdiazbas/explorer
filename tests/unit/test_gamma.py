"""Gamma, without Qt: the reduce kernel's table (kernels.gamma_table), the panels' bend (levels.gamma_panel), the
step of the keys (levels.gamma_step) and the state, one gamma per cube and Stokes (Session.gamma). Gamma 1 is the
straight line byte for byte; Q U V keep the sign, x and -x mirror bytes about the middle grey."""
import types
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest

from explorer.core.levels import gamma_panel, gamma_step, symmetric_levels
from explorer.core.loop import ManualLoop
from explorer.core.session import Session
from explorer.data.axes import roles
from explorer.data.kernels import TABLE_N, gamma_table, reduce_u8, reduce_u8_serial, reduce_u8_table_serial


def frame(seed=0, shape=(301, 277), sign=False):
    rng = np.random.default_rng(seed)
    a = rng.gamma(2.0, 300.0, shape).astype(np.float32)
    if sign:
        a = (a - a.mean()).astype(np.float32)
    a[:5, :9] = np.nan                                  # padding
    return a


# ---------------------------------------------------------------- the kernel
@pytest.mark.parametrize("f", [1, 2, 3])
def test_gamma_1_is_today_s_kernel_byte_for_byte_serial_and_in_strips(f):
    img = frame()
    lo, hi = np.nanpercentile(img, (1, 99))
    h, w = img.shape[0] // f, img.shape[1] // f
    want = np.empty((h, w), np.uint8)
    reduce_u8_serial(img, 0, 0, f, float(lo), float(hi), want)
    with ThreadPoolExecutor(4) as pool:
        for p, n in ((None, 1), (pool, 4)):
            got = np.empty_like(want)
            reduce_u8(img, 0, 0, f, float(lo), float(hi), got, p, n, table=None)
            assert np.array_equal(got, want)
            if p is not None:                           # the strips really ran: a frame over STRIP_MIN
                big = np.tile(img, (4, 4))
                a, b = np.empty((big.shape[0] // f, big.shape[1] // f), np.uint8), None
                reduce_u8_serial(big, 0, 0, f, float(lo), float(hi), a)
                b = np.empty_like(a)
                reduce_u8(big, 0, 0, f, float(lo), float(hi), b, p, n)
                assert np.array_equal(a, b)


def test_a_table_in_strips_is_the_table_serial():
    img = np.tile(frame(), (4, 4))
    lo, hi = np.nanpercentile(img, (1, 99))
    t = gamma_table(0.5, False)
    a = np.empty(img.shape, np.uint8)
    reduce_u8_table_serial(img, 0, 0, 1, float(lo), float(hi), t, a)
    b = np.empty_like(a)
    with ThreadPoolExecutor(4) as pool:
        reduce_u8(img, 0, 0, 1, float(lo), float(hi), b, pool, 4, table=t)
    assert np.array_equal(a, b)


def test_the_table_keeps_no_data_ends_and_order():
    img = frame()
    lo, hi = map(float, np.nanpercentile(img, (1, 99)))
    for g in (0.3, 0.5, 2.0):
        out = np.empty(img.shape, np.uint8)
        reduce_u8_table_serial(img, 0, 0, 1, lo, hi, gamma_table(g, False), out)
        nan = np.isnan(img)
        assert (out[nan] == 0).all() and (out[~nan] >= 1).all()
        assert (out[img <= lo] == 1).all() and (out[img >= hi] == 255).all()
        o = np.argsort(img[~nan], kind="stable")
        assert (np.diff(out[~nan][o].astype(int)) >= 0).all()          # monotone in the value
    lin, half = np.empty(img.shape, np.uint8), np.empty(img.shape, np.uint8)
    reduce_u8_serial(img, 0, 0, 1, lo, hi, lin)
    reduce_u8_table_serial(img, 0, 0, 1, lo, hi, gamma_table(0.5, False), half)
    ok = ~np.isnan(img)
    assert (half[ok].astype(int) >= lin[ok].astype(int) - 1).all() and half[ok].mean() > lin[ok].mean() + 20


def test_the_table_at_gamma_1_is_the_straight_line_within_one_level():
    """Not used at gamma 1 (the straight kernel runs), but its shape is the same line: never more than one level
    off it (the table's places against the exact value)."""
    img = frame()
    lo, hi = map(float, np.nanpercentile(img, (1, 99)))
    a, b = np.empty(img.shape, np.uint8), np.empty(img.shape, np.uint8)
    reduce_u8_serial(img, 0, 0, 1, lo, hi, a)
    reduce_u8_table_serial(img, 0, 0, 1, lo, hi, gamma_table(1.0, False), b)
    assert np.abs(a.astype(int) - b.astype(int)).max() <= 1


@pytest.mark.parametrize("g", [0.3, 0.5, 1.0, 2.5])
def test_symmetric_limits_keep_the_sign_x_and_minus_x_mirror_about_the_middle_grey(g):
    x = frame(1, sign=True)
    m = float(np.nanpercentile(np.abs(x), 99))
    img = np.concatenate([x, -x, np.zeros_like(x)])
    out = np.empty(img.shape, np.uint8)
    reduce_u8_table_serial(img, 0, 0, 1, -m, m, gamma_table(g, True), out)
    p, n, z = np.split(out.astype(int), 3)
    ok = ~np.isnan(x)
    assert (p[ok] + n[ok] == 256).all()                 # mirror bytes about 128
    assert (z[ok] == 128).all()                         # 0 stays the middle grey
    assert (p[ok & (x > 0)] >= 128).all() and (p[ok & (x < 0)] <= 128).all()
    assert (p[x >= m] == 255).all() and (p[x <= -m] == 1).all()
    t = gamma_table(g, True)
    assert t[TABLE_N // 2] == 128 and (t.astype(int) + t[::-1].astype(int) == 256).all()


def test_gamma_below_1_keeps_the_faint_end_s_gradient_where_a_lut_over_bytes_bands():
    """Faint values a few bytes above the lower limit (AIA off-limb: 4-6 counts, a byte ~5 counts): a 256 table over
    the bytes already scaled gives a few levels; the 65535 table in the kernel keeps tens."""
    rng = np.random.default_rng(3)
    img = rng.uniform(0, 30, (300, 300)).astype(np.float32)      # 0..30 between limits 0..1337
    lo, hi, g = 0.0, 1337.0, 0.3
    lin = np.empty(img.shape, np.uint8)
    reduce_u8_serial(img, 0, 0, 1, lo, hi, lin)
    lut = np.clip(1 + np.floor(254 * ((np.arange(256) - 1).clip(0) / 254) ** g), 1, 255).astype(np.uint8)
    banded = lut[lin]
    out = np.empty(img.shape, np.uint8)
    reduce_u8_table_serial(img, 0, 0, 1, lo, hi, gamma_table(g, False), out)
    assert len(np.unique(banded)) <= 8 and len(np.unique(out)) >= 30


# ---------------------------------------------------------------- the panels and the step
def test_gamma_panel_at_1_is_what_the_core_gave_and_keeps_the_sign_otherwise():
    a = frame(2, (40, 30), sign=True)
    lv = (-50.0, 50.0)
    same, slv = gamma_panel(a, lv, 1.0)
    assert same is a and slv is lv
    b, blv = gamma_panel(np.concatenate([a, -a]), lv, 0.5)
    p, n = np.split(b, 2)
    assert blv == (-1.0, 1.0) and np.allclose(p, -n, equal_nan=True) and np.isnan(p[:5, :9]).all()
    c, clv = gamma_panel(np.abs(a), (0.0, 100.0), 0.5)
    assert clv == (0.0, 1.0) and np.nanmin(c) >= 0 and np.nanmax(c) <= 1
    assert symmetric_levels((-2, 2)) and not symmetric_levels((0, 2)) and not symmetric_levels((-1, 2))


def test_the_step_is_a_tenth_of_a_decade_back_to_1_exactly_within_crispex_s_range():
    g = 1.0
    for _ in range(3):
        g = gamma_step(g, -1)
    assert g == pytest.approx(10 ** -0.3) and round(g, 3) == 0.501
    for _ in range(3):
        g = gamma_step(g, 1)
    assert g == 1.0
    for _ in range(40):
        g = gamma_step(g, -1)
    assert g == pytest.approx(0.1)
    for _ in range(80):
        g = gamma_step(g, 1)
    assert g == pytest.approx(10.0)


# ---------------------------------------------------------------- the state
def cube(shape=(5, 4, 7, 30, 20)):
    names = ("UTC", "STOKES", "WAVE", "HPLT", "HPLN")
    return types.SimpleNamespace(roles=roles(names, shape), shape=shape, ny=shape[-2], nx=shape[-1])


def test_one_gamma_per_cube_and_stokes_1_by_default_and_said_to_listeners():
    loop = ManualLoop()
    s = Session(loop, cube())
    s.add(cube())
    told = []
    s.store.subscribe(lambda st, ch: told.append(ch))
    assert s.gamma(0, 3) == 1.0 and s.state.gamma == ()
    s.set_gamma(0, 1, 0.5)                              # Q of the main cube
    loop.pump()
    assert told and "gamma" in told[-1]
    assert s.gamma(0, 1) == 0.5
    assert s.gamma(0, 3) == 1.0 and s.gamma(0, 0) == 1.0          # V's and I's are their own
    assert s.gamma(1, 1) == 1.0                                    # and so are the other cube's
    s.set_gamma(1, 3, 2.0)
    assert (s.gamma(0, 1), s.gamma(1, 3), s.gamma(1, 1)) == (0.5, 2.0, 1.0)
    s.set_gamma(0, 1, 1.0)                              # back to 1: no entry, the state as it started for it
    assert s.state.gamma == ((1, 3, 2.0),)
    s.set_gamma(0, 2, 99)
    assert s.gamma(0, 2) == 10.0                        # CRISPEX's range
    with pytest.raises(ValueError):
        s.set_gamma(5, 0, 0.5)

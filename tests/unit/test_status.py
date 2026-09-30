"""The status bar's texts (ROADMAP E4.6): the cursor's pixel in physical units when the header gives them, indices
otherwise, the value as the prototype wrote it; F12's diagnostics."""
import time

import numpy as np
import pytest

from explorer.data.axes import Axes
from explorer.testing import synth
from explorer.ui.status import SEP, padding, pixel_text


def physical_axes():
    ax = Axes()
    ax.lam_nm = np.array([617.30, 617.33, 617.36])
    ax.lam0_nm = 617.33
    ax.t_sec = np.array([0.0, 20.0])
    ax.dateref = np.datetime64("2025-07-11T08:16:57")
    ax.bunit = "W m^-2 Hz^-1 sr^-1"
    ax.cont = 2
    return ax


def test_physical_fields_and_the_value_in_its_units():
    ax = physical_axes()
    txt = pixel_text(ax, 4, 5, 6, 1, 0, 0, 3.2e-8, None, 1e-8, False)
    f = txt.split(SEP)
    assert f[0] == "x 6  y 5"                                               # no corners: the pixel
    assert f[1] == "08:17:17 UT"
    assert f[2] == "λ 6173.000 Å" and f[3] == "Δλ −0.300 Å"
    assert f[4].startswith("v −") and f[4].endswith("km s⁻¹")
    assert f[5] == "I 3.200 × 10⁻⁸ W m⁻² Hz⁻¹ sr⁻¹"
    q = pixel_text(ax, 4, 5, 6, 1, 0, 1, -0.64e-8, 3.2e-8, 1e-8, True)      # Q in % of I_c, locked
    assert q.split(SEP)[-2:] == ["Q/Ic −20.00 %", "locked"]


def test_indices_without_a_header_and_padding():
    txt = pixel_text(Axes(), 1, 5, 6, 3, 2, 0, 1.5, None, None, False)
    assert txt.split(SEP) == ["x 6  y 5", "t 3", "λ 2", "I 1.5"]
    assert pixel_text(Axes(), 1, 5, 6, 3, 2, 0, float("nan"), None, None, False).endswith("I  no data (padding)")
    assert padding(0.0, 0) and not padding(0.0, 1) and padding(float("nan"), 2)
    only_l = pixel_text(Axes(), 1, 5, 6, 0, 2, 0, 1.5, None, None, False, present=("l",))
    assert only_l.split(SEP)[1] == "λ 2"                                 # no t on a (lambda, y, x) cube


def spin(qapp, until, timeout=10.0):
    end = time.perf_counter() + timeout
    while not until() and time.perf_counter() < end:
        qapp.processEvents()
        time.sleep(0.002)
    return until()


@pytest.fixture(scope="module")
def cube(tmp_path_factory):
    return synth.write_dataset(tmp_path_factory.mktemp("status"), "c", shape=(3, 4, 21, 48, 40), icube=False)["im"]


def test_the_shell_shows_q_in_percent_of_ic_and_f12_the_diagnostics(qapp, cube):
    from explorer.data.dataset import Dataset
    from explorer.ui.shell import Shell

    ds = Dataset.open(cube)
    w = Shell(ds)
    try:
        w.show()
        s = w.session
        s.hover(20, 15)
        s.set_index("s", 1)
        assert spin(qapp, lambda: "Q/Ic" in w.status.text())                  # I_c came with the spectrum
        assert "″" in w.status.text() and " UT" in w.status.text()
        assert w.sys_status.isHidden()
        w.set_diagnostics(True)
        assert w.sys_status.isVisible() and "image cache" in w.sys_status.text()
    finally:
        w.close()
        ds.close()

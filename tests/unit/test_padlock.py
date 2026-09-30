"""The padlocks (ROADMAP E4.7), offscreen: the image's fixes the contrast across steps and a right click refits it
to this image; the spectra's fixes their ranges to the sample, and F (or its right click) fits them to this pixel and
shows it closed."""
import time

import pytest

from explorer.testing import synth

SHAPE = (6, 4, 21, 48, 40)


def spin(qapp, until, timeout=10.0):
    end = time.perf_counter() + timeout
    while not until() and time.perf_counter() < end:
        qapp.processEvents()
        time.sleep(0.002)
    return until()


@pytest.fixture(scope="module")
def cube(tmp_path_factory):
    return synth.write_dataset(tmp_path_factory.mktemp("padlock"), "c", shape=SHAPE, icube=False)["im"]


@pytest.fixture
def shell(qapp, cube):
    from explorer.data.dataset import Dataset
    from explorer.ui.shell import Shell

    ds = Dataset.open(cube)
    w = Shell(ds)
    w.resize(1400, 900)
    w.show()
    assert spin(qapp, lambda: w.first_image_s is not None and "spectra" in w.last)
    yield w
    w.close()
    ds.close()


def levels(shell):
    got = shell.last.get("image")
    return tuple(float(v) for v in got[1]) if got is not None else None   # ~1e-9: never rounded


def test_both_open_at_start_on_their_panels_top_right(qapp, shell):
    assert not shell.image_lock.isChecked() and not shell.spec_lock.isChecked()
    g, v = shell.image_lock.geometry(), shell.view.widget
    assert g.right() == v.width() - shell.image_lock.MARGIN - 1 and g.top() == shell.image_lock.MARGIN


def test_the_image_padlock_keeps_the_contrast_across_steps(qapp, shell):
    s = shell.session
    shell.image_lock.click()                            # closed: fixed to this image
    assert spin(qapp, lambda: levels(shell) is not None)
    fixed = levels(shell)
    s.step("t", 2)
    assert spin(qapp, lambda: shell.scheduler.img_idx is not None and shell.scheduler.img_idx[0] == 2)
    assert levels(shell) == fixed
    shell.image_lock.click()                            # open: each image its own
    s.step("t", 1)
    assert spin(qapp, lambda: shell.scheduler.img_idx[0] == 3 and levels(shell) != fixed)
    shell.image_lock.refit.emit()                       # right click: fixed to this image, shown closed
    assert shell.image_lock.isChecked()


def test_the_spectra_padlock_and_f(qapp, shell):
    yr = shell.scheduler.yrange
    shell.spec_lock.click()                             # closed: the sample's ranges, fixed
    assert yr.fixed
    shell.spec_lock.click()
    assert not yr.fixed
    shell.fit_spectra()                                 # F: fitted to this pixel and kept
    assert yr.fixed and shell.spec_lock.isChecked()

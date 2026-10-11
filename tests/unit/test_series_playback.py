"""Playback of a compressed series: the rate is capped by what a frame's decompression costs, as it is by the X11
link; a rate the user chose stays; plain files and cubes are not capped."""
import time

import numpy as np
import pytest
from astropy.io import fits

T0 = np.datetime64("2026-06-07T06:52:00.000", "ms")


def spin(qapp, until, timeout=10.0):
    end = time.perf_counter() + timeout
    while not until() and time.perf_counter() < end:
        qapp.processEvents()
        time.sleep(0.002)
    return until()


def files(d, compressed):
    rng = np.random.default_rng(0)
    out = []
    for k in range(4):
        h = fits.Header()
        h["T_OBS"] = str(T0 + np.timedelta64(12000 * k, "ms"))
        img = rng.integers(0, 3000, (24, 32)).astype(np.int16)
        p = str(d / f"f{k}.fits")
        hdus = [fits.PrimaryHDU(), fits.CompImageHDU(img, h, compression_type="RICE_1")] if compressed \
            else [fits.PrimaryHDU(img, h)]
        fits.HDUList(hdus).writeto(p)
        out.append(p)
    return out


@pytest.fixture(params=[True, False], ids=["rice", "plain"])
def shell(qapp, tmp_path, request):
    from explorer.data.dataset import Dataset
    from explorer.ui.shell import Shell

    ds = Dataset.open(None, series=files(tmp_path, request.param))
    w = Shell(ds)
    w.resize(640, 480)
    w.show()
    assert spin(qapp, lambda: w.first_image_s is not None)
    yield w, request.param
    w.close()
    ds.close()


def test_the_cap_is_what_a_frame_costs(shell):
    w, compressed = shell
    cap = w.dataset.frames.playback_cap()
    assert (cap is not None and cap > 0) if compressed else cap is None     # read: the first image


def test_the_rate_follows_the_frames_and_the_link_the_lowest(shell, monkeypatch):
    w, compressed = shell
    default = w.nav.fps.value()
    monkeypatch.setattr(w.dataset.frames, "playback_cap", lambda: 7.6)        # a frame in ~130 ms
    w.cap_fps_by_frames()
    assert w.nav.fps.value() == 7 and "7 fps" in w.statusBar().currentMessage()
    assert w.auto_fps("link", 12) == 7 and w.nav.fps.value() == 7            # the link allows more: the frames'
    assert w.auto_fps("link", 4) == 4 and w.nav.fps.value() == 4             # less: the link's
    w.nav.fps.setValue(15)                                                    # the user's own: kept
    assert w.auto_fps("link", 3) is None and w.nav.fps.value() == 15
    monkeypatch.setattr(w.dataset.frames, "playback_cap", lambda: None)       # nothing known: as before
    w._fps_auto.clear()
    w.nav.fps.setValue(default)
    w.cap_fps_by_frames()
    assert w.nav.fps.value() == default == 10                                 # the default (the user, 2026-10-11)
    assert w.auto_fps("link", 30) == 10 and w.nav.fps.value() == 10          # a fast link never raises it


def test_a_cube_is_not_capped(qapp, tmp_path):
    from explorer.data.dataset import Dataset
    from explorer.testing import synth
    from explorer.ui.shell import Shell

    d = synth.write_dataset(tmp_path, "c", shape=(3, 4, 5, 48, 40), icube=False)
    with Dataset.open(d["im"]) as ds:
        w = Shell(ds)
        w.show()
        assert spin(qapp, lambda: w.first_image_s is not None)
        default = w.nav.fps.value()
        w.cap_fps_by_frames()
        w.set_playing(True)
        w.set_playing(False)
        assert ds.frames.playback_cap() is None and w.nav.fps.value() == default
        w.close()

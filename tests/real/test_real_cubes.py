"""Every kind of real cube in tests/real/cubes.toml: it opens with its shape, an image has data, the per-pixel file
equals the image cube at two pixels, an LP cube equals its FITS sibling up to the integer scaling (each Stokes in
its own place), and the viewer starts on it without a screen. Only where the data/lp/ links resolve (bellatrix);
-m real_cubes runs just these."""
import os
import subprocess
import tomllib
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
CASES = tomllib.loads((Path(__file__).with_name("cubes.toml")).read_text())["cube"]


def _params():
    out = []
    for c in CASES:
        marks = [pytest.mark.real_cubes]
        if not (ROOT / c["path"]).exists():
            marks.append(pytest.mark.skip(reason=f"no link here: {c['path']}"))
        elif not c["opens"]:
            marks.append(pytest.mark.xfail(strict=True, reason=f"not opened yet: ROADMAP {c['todo']}"))
        out.append(pytest.param(c, id=c["name"], marks=marks))
    return out


def _open(case):
    from explorer.data.dataset import Dataset

    return Dataset.open(ROOT / case["path"])


def _idx(r, t, s, l):  # noqa: E741
    i = [0] * 3
    for a, v in ((r.t, t), (r.s, s), (r.l, l)):
        if a is not None:
            i[a] = v
    return i


@pytest.mark.parametrize("case", _params())
def test_opens_and_reads(case):
    with _open(case) as ds:
        assert list(ds.shape) == case["shape"]
        r = ds.roles
        img = ds.image(_idx(r, r.nt // 2, 0, r.nl // 2)).result()
        good = img[np.isfinite(img) & (img != 0)]
        assert good.size > 0.25 * img.size and np.ptp(good) > 0, "an image with data"
        if ds.pixel is None:
            return
        cal = ds.calibration or {}
        for y, x in ((ds.ny // 2 + 37, ds.nx // 2 - 53), (ds.ny // 3, 2 * ds.nx // 3)):
            block = ds.pixel_block(y, x).result()                          # (s, t, lambda)
            for s in range(r.ns):
                series = np.asarray(ds.read_series(y, x, _idx(r, 0, s, 0), [r.t, r.l]), np.float64)
                series = series * cal.get("scale", 1.0) + cal.get("zero", 0.0)
                tol = 2.0 * abs(cal.get("scale", 0.0)) + 1e-6 * np.nanmax(np.abs(block[s]))
                assert np.nanmax(np.abs(series - block[s])) <= tol, f"_im and _sp differ at ({y}, {x}) s={s}"


@pytest.mark.parametrize("case", [p for p in _params() if "fits" in p.values[0]])
def test_lp_equals_its_fits_sibling(case):
    from explorer.data.dataset import Dataset

    with _open(case) as lp, Dataset.open(ROOT / case["fits"], no_sp=True) as f:
        r, rf = lp.roles, f.roles
        t, l = r.nt // 2, r.nl // 2  # noqa: E741
        scales = []
        for s in range(r.ns):
            a = f.image(_idx(rf, t, case.get("fits_s", s), l)).result()
            b = lp.image(_idx(r, t, s, l)).result()
            m = np.isfinite(a) & np.isfinite(b) & (a != 0)
            k = np.polyfit(b[m][::61], a[m][::61], 1)[0]
            assert np.corrcoef(a[m], b[m])[0, 1] > 0.9999, f"Stokes {s}: not the FITS one"
            scales.append(k)
        assert np.ptp(scales) <= 0.01 * abs(np.mean(scales)), f"one integer scaling for all Stokes: {scales}"


@pytest.mark.parametrize("case", _params())
def test_the_viewer_starts_on_it(case, tmp_path):
    env = {k: v for k, v in os.environ.items() if k != "DISPLAY"}       # never a window on someone's screen
    env.update(QT_QPA_PLATFORM="offscreen", XDG_CONFIG_HOME=str(tmp_path), XDG_CACHE_HOME=str(tmp_path))
    # --quit-after counts from the first image on screen: exiting 0 within the timeout means one was shown
    p = subprocess.run([str(ROOT / "scripts" / "run.sh"), str(ROOT / case["path"]), "--quit-after", "1"],
                       env=env, capture_output=True, text=True, timeout=180)
    assert p.returncode == 0, p.stderr[-2000:]

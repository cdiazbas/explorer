"""Export the prototype's results for the comparison cases (docs/plan.md §7.1, level 1): the oracle explorer must
match. Runs with the PROTOTYPE's Python and imports its modules as they are (read-only):

    <prototype>/.venv/bin/python tools/golden/export_prototype.py [--case NAME] [--make-inputs] [--prototype DIR]

For each case of tests/golden/cases.toml it writes the case's reference .npz: arrays under dotted keys and a JSON
"meta" entry (what each key is, the md5 of the prototype's code, the sha256 of the inputs, versions, host).
What is exported, and the prototype function that computes it:
- frame.i          Cube.image(t, s, l)                                    viewer/cube.py
- limits.i         viewer.limits(img, symmetric=s > 0)                    app/viewer.py:428
- series.j         Cube.series(y, x, (0,0,0), [t, s, l]) -> (nt, ns, nl)   viewer/cube.py
- sp_fits.j        SpFits.block(y, x) -> (s, t, l)                        app/sources.py
- icube.j          SpLP.block after SpLP.calibrate(cube)                  app/sources.py:90
- reduce.k         viewer._reduce_u8_serial (the one the app patches into pgr, level 0 = padding; viewer.py:62, :98)
- slit_*.m         viewer.slit_path, slit_pixels, read_slit_slab (per-pixel file), read_slit_bands (frames)
- axes.*           physics.from_fits                                      app/physics.py
- meta.quv         viewer.quv_amplitude_ranges(cube, ta, sa, la, cont, t, ns, nl)
- meta.viewer      a real Viewer built offscreen as app/selftest.py does: its y ranges from the random sample
                   (_start_sample -> _sample_ready), Q U V ranges (_want_quv), _iscale, first image's limits
--make-inputs writes a synthetic case's input files (explorer.testing.synth) if they are missing.
"""
import argparse
import glob
import hashlib
import json
import os
import platform
import socket
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))

# Qt without a display, and the prototype's window layout into a temporary config, never the user's
os.environ.pop("DISPLAY", None)
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("XDG_CONFIG_HOME", tempfile.mkdtemp(prefix="golden_cfg_"))

import numpy as np  # noqa: E402

FULL_HASH_MAX = 64 << 20        # larger inputs get a fingerprint: hashing a 176 GB cube reads it all (~20 min)
EDGE = 16 << 20


def fingerprint(path):
    """sha256 of the whole file up to FULL_HASH_MAX; above it, "size:mtime:sha256(first and last EDGE bytes)",
    enough to notice that a shared cube was rewritten without reading it through."""
    size = os.path.getsize(path)
    h = hashlib.sha256()
    with open(path, "rb") as f:
        if size <= FULL_HASH_MAX:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
            return h.hexdigest()
        h.update(f.read(EDGE))
        f.seek(size - EDGE)
        h.update(f.read(EDGE))
    return f"{size}:{int(os.path.getmtime(path))}:{h.hexdigest()}"


def prototype_md5(proto):
    files = sorted(glob.glob(os.path.join(proto, "app", "*.py")) + glob.glob(os.path.join(proto, "viewer", "*.py")))
    code = {os.path.relpath(f, proto): hashlib.md5(open(f, "rb").read()).hexdigest() for f in files}
    return hashlib.md5(json.dumps(code, sort_keys=True).encode()).hexdigest()


def case_inputs(case, make):
    """(im, sp_fits or None, icube or None) for a case."""
    if case["source"] == "synthetic":
        d = os.path.join(ROOT, "tests", "golden", "data", case["name"])
        im = os.path.join(d, f"{case['name']}_im.fits")
        if not os.path.exists(im):
            if not make:
                sys.exit(f"missing inputs of {case['name']} ({d}); run with --make-inputs once")
            sys.path.insert(0, os.path.join(ROOT, "src"))
            from explorer.testing import synth
            synth.write_dataset(d, case["name"], shape=tuple(case["shape"]), seed=case["seed"])
        sp, ic = im.replace("_im.fits", "_sp.fits"), im.replace("_im.fits", "_sp.icube")
    else:
        im = os.path.normpath(os.path.join(ROOT, case["path"]))
        sp, ic = im.replace("_im.fits", "_sp.fits"), im.replace("_im.fits", "_sp.icube")
    return im, (sp if os.path.exists(sp) else None), (ic if os.path.exists(ic) else None)


def export(case, proto, make):
    sys.path[:0] = [os.path.join(proto, "app"), os.path.join(proto, "viewer")]
    import physics
    import viewer as V  # the prototype's app/viewer.py (Qt, pyqtgraph, numba)
    from cube import Cube
    from sources import SpFits, SpLP

    im, spf, icf = case_inputs(case, make)
    # the prototype's place relative to explorer, never its absolute path: the reference is versioned
    arrays, meta = {}, dict(case=case, prototype=os.path.relpath(proto, ROOT),
                            prototype_code_md5=prototype_md5(proto),
                            host=socket.gethostname().split(".")[0], date=time.strftime("%Y-%m-%dT%H:%M:%S"),
                            python=platform.python_version(), numpy=np.__version__,
                            inputs={os.path.basename(p): fingerprint(p) for p in (im, spf, icf) if p})
    t0 = time.perf_counter()
    c = Cube.from_fits(im, cache_bytes=256 << 20)
    ta, sa, la = V.axis_positions(c)
    meta["shape"], meta["axes_names"], meta["axis_positions"] = list(c.shape), c.axes, [ta, sa, la]
    free = sorted(a for a in (ta, sa, la) if a is not None)

    # physical axes
    ax = physics.from_fits(im)
    for k in ("lam_nm", "t_sec", "corners"):
        v = getattr(ax, k)
        if v is not None:
            arrays[f"axes.{k}"] = np.asarray(v)
    for k in ("dlam_A", "vel_kms"):
        v = getattr(ax, k)()
        if v is not None:
            arrays[f"axes.{k}"] = np.asarray(v)
    meta["axes"] = dict(line=ax.line, lam0_nm=ax.lam0_nm, cont=ax.cont, bunit=ax.bunit, corner_px=ax.corner_px,
                        dateref=None if ax.dateref is None else str(ax.dateref), source=ax.source,
                        utc=[ax.utc_str(t) for t in range(c.shape[ta])] if ta is not None else None)

    # frames and their contrast limits
    imgs = []
    for i, (t, s, lam) in enumerate(case["frames"]):
        img = c.image((t, s, lam))
        imgs.append(img)
        arrays[f"frame.{i}"] = img
        arrays[f"limits.{i}"] = np.asarray(V.limits(img, symmetric=s > 0))

    # series at pixels, from the image cube and from the per-pixel files
    tsl = tuple(c.shape[i] if i is not None else 1 for i in (sa, ta, la))
    sp = SpFits(spf, tsl) if spf else None
    lp = SpLP(icf, tsl, c.nx) if icf else None
    if lp is not None:
        meta["icube_calibration"] = lp.calibrate(c)
    for j, (y, x) in enumerate(case["pixels"]):
        arrays[f"series.{j}"] = c.series(y, x, (0,) * (len(c.shape) - 2), free)
        if sp is not None:
            arrays[f"sp_fits.{j}"] = sp.block(y, x)
        if lp is not None:
            arrays[f"icube.{j}"] = lp.block(y, x)

    # pgr's reduction as the app uses it
    for k, r in enumerate(case["reduce"]):
        lo, hi = arrays[f"limits.{r['frame']}"]
        out = np.empty((r["h"], r["w"]), np.uint8)
        V._reduce_u8_serial(imgs[r["frame"]], r["y0"], r["x0"], r["f"], float(lo), float(hi), out)
        arrays[f"reduce.{k}"] = out

    # slits
    frame_idx = [tuple(f) for f in case["frames"]]
    for m, pts in enumerate(case["slits"]):
        path = V.slit_path(pts)
        iy, ix = V.slit_pixels(path, c.ny, c.nx)
        arrays[f"slit_path.{m}"], arrays[f"slit_iy.{m}"], arrays[f"slit_ix.{m}"] = path, iy, ix
        if sp is not None:
            arrays[f"slit_slab.{m}"] = V.read_slit_slab(sp, iy, ix)[0]
        arrays[f"slit_bands.{m}"] = V.read_slit_bands(c, frame_idx, iy, ix)

    # Q U V ranges from whole frames
    if sa is not None and c.shape[sa] > 1:
        meta["quv"] = {}
        for t in case["quv_t"]:
            half, info, _, _ = V.quv_amplitude_ranges(c, ta, sa, la, ax.cont, t, c.shape[sa], c.shape[la])
            meta["quv"][str(t)] = dict(half={str(k): v for k, v in half.items()},
                                       info={str(k): list(v) for k, v in info.items()})
    meta["export_s"] = round(time.perf_counter() - t0, 2)
    if case.get("viewer"):
        meta["viewer"] = viewer_level(im)
    return arrays, meta


def viewer_level(im):
    """What only the running Viewer computes: build it offscreen exactly as app/selftest.py does."""
    import startup
    s = startup.prepare("auto", "pgr")
    app, _ = startup.make_app(s, "auto")
    cube, probe, guard, sp, cal = startup.open_cube(im, None, False)
    v = startup.make_viewer(app, s, cube, sp, probe, guard, kind="golden")
    startup.show(app, s, v, size=(1400, 900))

    def wait(cond, secs=60):
        end = time.perf_counter() + secs
        while not cond() and time.perf_counter() < end:
            app.processEvents()
            time.sleep(0.005)
        return cond()

    got_sample = wait(lambda: v._ysample is not None)
    quv = None
    if v.ns > 1 and v.sa is not None:
        v._want_quv()
        if wait(lambda: not v._quv_pending):
            quv = {str(k): list(r) for k, r in (v._yquv or {}).items()}
    d = dict(idx=list(v.idx), limits=list(v._limits(v._img)), iscale=v._iscale, cont=v.ax.cont,
             sample_n=v.SAMPLE_N, sample_k=v.SAMPLE_K, sp_kind=getattr(sp, "kind", None),
             ysample=[list(r) for r in v._ysample] if got_sample else None, yquv=quv)
    v.close()
    return d


def main():
    import tomllib

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--case", help="only this case (default: every case whose inputs exist here)")
    ap.add_argument("--prototype", default=os.path.join(ROOT, "..", "prototype"))
    ap.add_argument("--make-inputs", action="store_true", help="write missing synthetic inputs first")
    ap.add_argument("--out", help="write here instead of the case's reference path")
    a = ap.parse_args()
    proto = os.path.abspath(a.prototype)
    cases = tomllib.load(open(os.path.join(ROOT, "tests", "golden", "cases.toml"), "rb"))["case"]
    for case in cases:
        if a.case and case["name"] != a.case:
            continue
        if case["source"] == "path" and not os.path.exists(os.path.join(ROOT, case["path"])):
            print(f"skip {case['name']}: {case['path']} is not on this machine")
            continue
        arrays, meta = export(case, proto, a.make_inputs)
        out = a.out or os.path.join(ROOT, case["reference"])
        os.makedirs(os.path.dirname(out), exist_ok=True)
        np.savez_compressed(out, meta=np.array(json.dumps(meta, default=str)), **arrays)
        print(f"{case['name']}: {len(arrays)} arrays, meta {sorted(meta)} -> {os.path.relpath(out, ROOT)} "
              f"({os.path.getsize(out) / 1e3:.0f} kB, {meta['export_s']} s)")


if __name__ == "__main__":
    main()

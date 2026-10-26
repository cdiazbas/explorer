"""Captures for a refactor marked `Behaviour: unchanged` (the simplification passes, ROADMAP X.14): 16 states of the
window, each as PNGs of the window and of every plot panel, and a JSON of what pixels do not show (axes' labels and
tick strings, reticle colours, plot backgrounds, pyqtgraph's buttons and menus).

    QT_QPA_PLATFORM=offscreen PYTHONPATH=src python bench/captures.py OUT [--data DIR]

The states: one cube and three linked (a second spectral cube and a La Palma map), each with a slit drawn and the
cursor locked, in dark and light, classic, modern and glass, and the 2x2 view in modern. DIR holds the synthetic
cubes (written once; default: OUT's sibling captures_data), so two runs read the same files.

Run it twice on the base commit to measure the noise (0 of 104 PNG on the Mac, 2026-10-26), then once per commit,
and compare with bench/captures_compare.py. Leave DISPLAY unset and point XDG_CONFIG_HOME and EXPLORER_LAYOUT at a
scratch folder: the window would otherwise reach a screen and rewrite the user's layout.
"""
import argparse
import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "src"))
sys.dont_write_bytecode = True

SHAPE = (3, 4, 5, 60, 48)


def lp_map(path, n, ny=SHAPE[3], nx=SHAPE[4]):
    """A La Palma map cube (nt frames, no axes in the file), opened with --axes t."""
    from explorer.testing import synth

    if not os.path.exists(path):
        synth.write_lp(path, np.random.default_rng(n).normal(size=(n, ny, nx)))
    return path


def axis_info(pi):
    d = {}
    for side in ("left", "bottom", "top", "right"):
        a = pi.getAxis(side)
        if a is None or not a.isVisible():
            continue
        try:
            lo, hi = a.range
            tv = a.tickValues(lo, hi, a.width() if side in ("top", "bottom") else a.height())
            ts = [a.tickStrings(v, a.autoSIPrefixScale, sp) for sp, v in tv]
        except Exception as e:                          # recorded: a change in it is a finding
            ts = repr(e)
        d[side] = dict(label=a.labelText, ticks=ts, tick_len=a.style.get("tickLength"),
                       cache=int(a.cacheMode().value))
    return d


def plots_of(w):
    ps = {}
    for c in w.cubes:
        tag = f"cube{c.k}"
        if c.spectra is not None:
            for i, p in enumerate(c.spectra.plots):
                ps[f"{tag}_spec{i}"] = p
        if c.lambda_t is not None:
            ps[f"{tag}_lt"] = c.lambda_t.w.getPlotItem()
    for i, p in enumerate(w.slit_panels):
        ps[f"slit{i}_ts"] = p.ts
        ps[f"slit{i}_sl"] = p.sl
    return ps


def state(w):
    d = {"plots": {}, "reticles": [], "bg": {}, "geom": [w.width(), w.height()]}
    for k, p in plots_of(w).items():
        d["plots"][k] = dict(axes=axis_info(p), menu=p.menuEnabled(), mouse=list(p.vb.state["mouseEnabled"]),
                             buttons=getattr(p, "buttonsHidden", None),
                             range=[list(map(float, r)) for r in p.vb.viewRange()])
    views = [c.view for c in w.cubes] + (w.grid.views if w.grid is not None else [])
    for v in views:
        d["reticles"].append(None if v.reticle is None else [v.reticle.colour.getRgb(), v.reticle.isVisible()])
    for c in w.cubes:
        for name in ("spectra", "lambda_t"):
            pw = getattr(getattr(c, name, None), "w", None)
            if pw is not None:
                d["bg"][f"cube{c.k}_{name}"] = pw.backgroundBrush().color().getRgb()
    for i, p in enumerate(w.slit_panels):
        d["bg"][f"slit{i}"] = p.w.backgroundBrush().color().getRgb()
    return d


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("out")
    ap.add_argument("--data", help="the synthetic cubes (default: OUT's sibling captures_data)")
    a = ap.parse_args(argv)
    out = os.path.abspath(a.out)
    data = a.data or os.path.join(os.path.dirname(out), "captures_data")
    os.makedirs(out, exist_ok=True)
    os.makedirs(data, exist_ok=True)

    from PySide6 import QtWidgets

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from explorer.data.dataset import Dataset
    from explorer.look import get_look
    from explorer.testing import synth
    from explorer.ui import style
    from explorer.ui.shell import Shell

    main_p, other_p = os.path.join(data, "main_im.fits"), os.path.join(data, "other_im.fits")
    if not os.path.exists(main_p):
        synth.write_dataset(data, "main", shape=SHAPE, icube=False)
        synth.write_dataset(data, "other", shape=(SHAPE[0], SHAPE[1], 7, SHAPE[3], SHAPE[4]), seed=4, icube=False,
                            sp=False)
    blos_p = lp_map(os.path.join(data, "Blos.map.fcube"), SHAPE[0])

    def spin(s, until=None):
        end = time.time() + s
        while time.time() < end and not (until is not None and until()):
            app.processEvents()
            time.sleep(0.004)

    def grab(w, name):
        w.grab().save(os.path.join(out, name + "_window.png"))
        for c in w.cubes:
            for part in ("spectra", "lambda_t"):
                pw = getattr(getattr(c, part, None), "w", None)
                if pw is not None:
                    pw.grab().save(os.path.join(out, f"{name}_cube{c.k}_{part}.png"))
        for i, p in enumerate(w.slit_panels):
            p.w.grab().save(os.path.join(out, f"{name}_slit{i}.png"))
        with open(os.path.join(out, name + ".json"), "w") as f:
            json.dump(state(w), f, indent=1, sort_keys=True, default=str)

    def scenario(tag, ds, linked):
        w = Shell(ds, title=tag, look=get_look("classic"), linked=linked)
        w.setGeometry(40, 40, 1400, 760)
        w.show()
        spin(20, lambda: w.first_image_s is not None and all(c.scheduler.img is not None for c in w.linked))
        spin(0.8)
        w.reset_sizes()
        spin(0.5)
        w.session.set_index("s", 1)
        w.session.hover(30, 20)
        w.session.lock(True)
        w.set_slit_mode(True)
        for x, y in ((6.5, 8.5), (40.5, 50.5)):
            w.slit_tool.add(x, y)
        w.slit_tool.finish()
        spin(10, lambda: w.slit_panel.pix is not None and w.session.state.path is not None)
        spin(1.5)
        for theme in ("dark", "light"):
            w.set_theme(theme)
            spin(1.0)
            for look in ("classic", "modern", "glass"):
                w.set_look(get_look(look))
                spin(2.0)
                grab(w, f"{tag}_{theme}_{look}")
            w.set_look(get_look("modern"))
            spin(1.0)
            w.set_grid(True)
            spin(2.0)
            grab(w, f"{tag}_{theme}_modern_grid")
            w.set_grid(False)
            spin(0.8)
        w.set_theme("dark")
        w.set_look(get_look("classic"))
        spin(0.5)
        w.close()
        spin(0.3)

    style.apply_theme(app, "dark")
    with Dataset.open(main_p) as ds:
        scenario("one", ds, [])
    with Dataset.open(main_p) as ds:
        linked = [Dataset.open(other_p, executors=ds.executors), Dataset.open(blos_p, axes="t", executors=ds.executors)]
        scenario("linked", ds, linked)
        for d in linked:
            d.close()
    n = sum(f.endswith(".png") for f in os.listdir(out)), sum(f.endswith(".json") for f in os.listdir(out))
    print(f"{out}: {n[0]} PNG and {n[1]} JSON", flush=True)


if __name__ == "__main__":
    main()

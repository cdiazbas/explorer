"""Two runs of bench/captures.py compared: every PNG pixel by pixel, every JSON as parsed, and with --leaves the JSON
leaves that differ, counted by path (digits folded).

    PYTHONPATH=src python bench/captures_compare.py A B [--leaves]

Each PNG's bytes are copied out of the QImage before it goes: a numpy view on its freed memory hid differences.
"""
import argparse
import collections
import json
import os
import re
import sys

import numpy as np

sys.dont_write_bytecode = True


def pixels(path):
    from PySide6 import QtGui

    img = QtGui.QImage(path).convertToFormat(QtGui.QImage.Format.Format_RGB32)
    a = np.frombuffer(img.constBits(), np.uint8).reshape(img.height(), img.bytesPerLine())[:, :img.width() * 4]
    out = a.reshape(img.height(), img.width(), 4)[:, :, :3].copy()
    del img
    return out


def leaves(d, p=""):
    if isinstance(d, dict):
        for k, v in d.items():
            yield from leaves(v, f"{p}/{k}")
    elif isinstance(d, list) and d and isinstance(d[0], (dict, list)):
        for i, v in enumerate(d):
            yield from leaves(v, f"{p}[{i}]")
    else:
        yield p, d


def load(path):
    with open(path) as f:
        return json.load(f)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--leaves", action="store_true", help="list the JSON leaves that differ, by path")
    o = ap.parse_args(argv)
    fa, fb = sorted(os.listdir(o.a)), sorted(os.listdir(o.b))
    if fa != fb:
        print("files differ:", sorted(set(fa) ^ set(fb)))
    npng = njson = dpng = djson = 0
    seen: collections.Counter = collections.Counter()
    vals: dict = {}
    for f in fa:
        if f not in fb:
            continue
        pa, pb = os.path.join(o.a, f), os.path.join(o.b, f)
        if f.endswith(".png"):
            npng += 1
            x, y = pixels(pa), pixels(pb)
            n = int((x != y).any(-1).sum()) if x.shape == y.shape else -1
            if n:
                dpng += 1
                print(f"{f}: {n} px differ (shape {x.shape} vs {y.shape})")
        elif f.endswith(".json"):
            njson += 1
            x, y = load(pa), load(pb)
            if x != y:
                djson += 1
                print(f"{f}: JSON differs")
                lx, ly = dict(leaves(x)), dict(leaves(y))
                for k in sorted(set(lx) | set(ly)):
                    if lx.get(k, "<none>") != ly.get(k, "<none>"):
                        g = re.sub(r"\d+", "#", k)
                        seen[g] += 1
                        vals.setdefault(g, set()).add((repr(lx.get(k, "<none>"))[:60], repr(ly.get(k, "<none>"))[:60]))
    if o.leaves:
        for g, n in seen.most_common():
            print(n, g, sorted(vals[g])[:4])
    print(f"{o.a} vs {o.b}: {dpng}/{npng} PNG and {djson}/{njson} JSON differ")
    return 1 if dpng or djson else 0


if __name__ == "__main__":
    sys.exit(main())

"""Compare two reference files (tools/golden/export_prototype.py) or a reference and explorer's results: per key,
identical or not, and by how much, to tell a bug from a wanted fix or a tolerance set wrong.

    python tools/golden/compare.py REF.npz OTHER.npz [--rtol 0] [--atol 0] [--meta]

Arrays compare exactly unless a tolerance is given (NaN equals NaN at the same place). With --meta the JSON
metadata's numbers are compared as well (values under "case", "date", "host", "prototype", "python", "numpy",
"export_s" and "inputs" are ignored: they describe the run, not the results). Exit code: number of differences.
Importable: compare(ref, got, rtol, atol) -> list of Row.
"""
import argparse
import json
import sys
from dataclasses import dataclass

import numpy as np

RUN_KEYS = {"case", "date", "host", "prototype", "python", "numpy", "export_s", "inputs", "source"}


@dataclass
class Row:
    key: str
    status: str          # "same", "close" (within tolerance), "DIFF", "MISSING", "EXTRA"
    detail: str = ""


def _arrays(ref, got, rtol, atol):
    rows = []
    for k in sorted(set(ref) | set(got)):
        if k == "meta":
            continue
        if k not in got:
            rows.append(Row(k, "MISSING", "not in the second file"))
            continue
        if k not in ref:
            rows.append(Row(k, "EXTRA", "not in the reference"))
            continue
        a, b = np.asarray(ref[k]), np.asarray(got[k])
        if a.shape != b.shape:
            rows.append(Row(k, "DIFF", f"shape {a.shape} vs {b.shape}"))
            continue
        if a.dtype.kind in "fc" or b.dtype.kind in "fc":
            fa, fb = a.astype(np.float64), b.astype(np.float64)
            nan_a, nan_b = np.isnan(fa), np.isnan(fb)
            if (nan_a != nan_b).any():
                rows.append(Row(k, "DIFF", f"NaN at {int((nan_a != nan_b).sum())} different places"))
                continue
            ok = ~nan_a
            d = np.abs(fa[ok] - fb[ok])
            if not d.size or d.max() == 0:
                rows.append(Row(k, "same"))
                continue
            scale = np.abs(fa[ok]).max() or 1.0
            n = int((d > 0).sum())
            detail = f"max |diff| {d.max():.3g} ({d.max() / scale:.2e} of max |ref|), {n} values differ"
            within = np.all(d <= atol + rtol * np.abs(fa[ok]))
            rows.append(Row(k, "close" if (rtol or atol) and within else "DIFF", detail))
        else:
            n = int((a != b).sum())
            rows.append(Row(k, "same" if n == 0 else "DIFF", "" if n == 0 else f"{n} of {a.size} values differ"))
    return rows


def _meta(a, b, path, rtol, atol, rows):
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if path == "" and k in RUN_KEYS:
                continue
            p = f"{path}.{k}" if path else k
            if k not in a or k not in b:
                rows.append(Row(f"meta.{p}", "MISSING" if k not in b else "EXTRA"))
            else:
                _meta(a[k], b[k], p, rtol, atol, rows)
    elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        for i, (x, y) in enumerate(zip(a, b, strict=True)):
            _meta(x, y, f"{path}[{i}]", rtol, atol, rows)
    elif isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        if a == b or (a != a and b != b):
            return
        within = abs(a - b) <= atol + rtol * abs(a)
        rows.append(Row(f"meta.{path}", "close" if (rtol or atol) and within else "DIFF", f"{a!r} vs {b!r}"))
    elif a != b:
        rows.append(Row(f"meta.{path}", "DIFF", f"{str(a)[:40]!r} vs {str(b)[:40]!r}"))


def compare(ref, got, rtol=0.0, atol=0.0, meta=False):
    rows = _arrays(ref, got, rtol, atol)
    if meta:
        _meta(json.loads(str(ref["meta"])), json.loads(str(got["meta"])), "", rtol, atol, rows)
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("ref")
    ap.add_argument("other")
    ap.add_argument("--rtol", type=float, default=0.0)
    ap.add_argument("--atol", type=float, default=0.0)
    ap.add_argument("--meta", action="store_true", help="compare the metadata's numbers too")
    a = ap.parse_args()
    rows = compare(np.load(a.ref), np.load(a.other), a.rtol, a.atol, a.meta)
    bad = [r for r in rows if r.status in ("DIFF", "MISSING", "EXTRA")]
    for r in sorted(rows, key=lambda r: (r.status == "same", r.status == "close", r.key)):
        if r.status != "same":
            print(f"  {r.status:7s} {r.key:28s} {r.detail}")
    print(f"{len(rows)} compared: {sum(r.status == 'same' for r in rows)} same, "
          f"{sum(r.status == 'close' for r in rows)} within tolerance, {len(bad)} different")
    return len(bad)


if __name__ == "__main__":
    sys.exit(main())

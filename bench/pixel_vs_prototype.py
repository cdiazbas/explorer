"""Per-pixel blocks (everything at a pixel, from _sp.fits): explorer's SpFits against the prototype's, same
process, ABBA rounds (ROADMAP E1.4).

    python bench/pixel_vs_prototype.py <cube_im.fits> [--prototype DIR] [--per-round 20] [--rounds 4] [--strip 32]

first touch: a pixel whose strip neither implementation has read (random rows); cached: a neighbour in the same
strip, served from each reader's LRU. Shared caches are not evicted, so the ABBA order is what makes the
comparison fair. Blocks are compared bit for bit.
"""
import argparse
import json
import os
import socket
import statistics
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.dont_write_bytecode = True

import numpy as np  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cube")
    ap.add_argument("--prototype", default=os.path.join(ROOT, "..", "prototype"))
    ap.add_argument("--per-round", type=int, default=20)
    ap.add_argument("--rounds", type=int, default=4)
    ap.add_argument("--strip", type=int, default=32)
    ap.add_argument("--out")
    a = ap.parse_args()
    sys.path.insert(0, os.path.join(os.path.abspath(a.prototype), "app"))
    import sources as proto_sources  # the prototype's app/sources.py

    from explorer.data import formats
    from explorer.data.pixel import SpFits

    sp_path = formats.companions(a.cube)[0]
    ours = SpFits(sp_path, strip=a.strip, max_bytes=1 << 30)
    proto = proto_sources.SpFits(sp_path, (ours.ns, ours.nt, ours.nl), strip=a.strip, max_bytes=1 << 30)
    impls = {"prototype": proto.block, "explorer": ours.block}
    rng = np.random.default_rng(int(time.time()))
    rows_used = set()
    res = dict(host=socket.gethostname().split(".")[0], date=time.strftime("%Y-%m-%dT%H:%M:%S"),
               cube=os.path.basename(sp_path), strip=a.strip, load=os.getloadavg(), rounds=[])
    mismatches = 0
    for r in range(a.rounds):
        order = ["prototype", "explorer"] if r % 2 == 0 else ["explorer", "prototype"]
        row = dict(order=order)
        for name in order:
            first, cached = [], []
            for _ in range(a.per_round // 2):
                while True:
                    y = int(rng.integers(ours.ny // 8, ours.ny - ours.ny // 8))
                    if y not in rows_used:
                        rows_used.add(y)
                        break
                x = int(rng.integers(0, ours.nx // a.strip - 1)) * a.strip + 1
                q = time.perf_counter()
                b = impls[name](y, x)
                first.append(time.perf_counter() - q)
                q = time.perf_counter()
                impls[name](y, x + 1)
                cached.append(time.perf_counter() - q)
                other = impls["explorer" if name == "prototype" else "prototype"](y, x)
                mismatches += not np.array_equal(b, other, equal_nan=True)
            row[name] = dict(first_ms=round(statistics.median(first) * 1e3, 2),
                             cached_ms=round(statistics.median(cached) * 1e3, 4))
        res["rounds"].append(row)
        cells = [f"{n}: first {row[n]['first_ms']:6.2f} ms, cached {row[n]['cached_ms']:7.4f} ms" for n in impls]
        print(f"  round {r + 1} ({order[0]} first): " + "   ".join(cells), flush=True)
    for k in ("first_ms", "cached_ms"):
        res[k] = {n: round(statistics.median(x[n][k] for x in res["rounds"]), 4) for n in impls}
    res["mismatches"] = mismatches
    print(f"median over rounds: first touch {res['first_ms']}, cached {res['cached_ms']}; "
          f"blocks differing: {mismatches}")
    if a.out:
        os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
        json.dump(res, open(a.out, "w"), indent=1)
    ours.close()
    return 1 if mismatches else 0


if __name__ == "__main__":
    sys.exit(main())

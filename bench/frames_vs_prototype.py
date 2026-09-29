"""Frame reads: explorer's FrameReader against the prototype's Cube, same process, ABBA rounds (ROADMAP E1.2).

    python bench/frames_vs_prototype.py <cube_im.fits> [--prototype DIR] [--per-round 10] [--rounds 4] [--out F]

Two cases per implementation and round:
- first touch: frames drawn at random, each read by one implementation only, so neither benefits from the
  other's reads. Whether the operating system already held them (other users, earlier runs) is unknown: shared
  caches are not evicted, so the ABBA order is what makes the comparison fair, not a cold cache;
- warm: the same frames read again, from the page cache.
Every frame is compared bit for bit between the two implementations.
"""
import argparse
import json
import os
import socket
import statistics
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
os.environ.setdefault("NUMBA_CACHE_DIR", tempfile.mkdtemp(prefix="bench_numba_"))   # never inside the prototype
sys.dont_write_bytecode = True                                                        # nor its __pycache__

import numpy as np  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cube")
    ap.add_argument("--prototype", default=os.path.join(ROOT, "..", "prototype"))
    ap.add_argument("--per-round", type=int, default=10)
    ap.add_argument("--rounds", type=int, default=4)
    ap.add_argument("--out")
    a = ap.parse_args()
    sys.path.insert(0, os.path.join(os.path.abspath(a.prototype), "viewer"))
    from cube import Cube  # the prototype's reader

    from explorer.data import formats
    from explorer.data.io import FrameReader

    proto = Cube.from_fits(a.cube, cache_bytes=0)             # no cache: every image() reads
    ours = FrameReader(formats.open_layout(a.cube))
    lead = ours.shape[:-2]
    rng = np.random.default_rng(int(time.time()))
    n_total = a.per_round * a.rounds
    flat = rng.choice(int(np.prod(lead)), size=n_total, replace=False)
    frames = [tuple(int(i) for i in np.unravel_index(f, lead)) for f in flat]
    impls = {"prototype": lambda idx: proto._read_frame(idx), "explorer": lambda idx: ours.read(idx)}
    res = dict(host=socket.gethostname().split(".")[0], date=time.strftime("%Y-%m-%dT%H:%M:%S"),
               cube=os.path.basename(a.cube), shape=list(ours.shape), load=os.getloadavg(), rounds=[])
    mismatches = 0
    for r in range(a.rounds):
        order = ["prototype", "explorer"] if r % 2 == 0 else ["explorer", "prototype"]
        chunk = frames[r * a.per_round:(r + 1) * a.per_round]
        half = len(chunk) // 2
        own = {order[0]: chunk[:half], order[1]: chunk[half:]}
        row = dict(order=order)
        for name in order:
            t_first, t_warm = [], []
            for idx in own[name]:
                q = time.perf_counter()
                img = impls[name](idx)
                t_first.append(time.perf_counter() - q)
                q = time.perf_counter()
                impls[name](idx)
                t_warm.append(time.perf_counter() - q)
                other = impls["explorer" if name == "prototype" else "prototype"](idx)
                mismatches += not np.array_equal(img, other, equal_nan=True)
            row[name] = dict(first_ms=round(statistics.median(t_first) * 1e3, 2),
                             warm_ms=round(statistics.median(t_warm) * 1e3, 2))
        res["rounds"].append(row)
        print(f"  round {r + 1} ({order[0]} first): " + "   ".join(
            f"{n}: first {row[n]['first_ms']:6.2f} ms, warm {row[n]['warm_ms']:6.2f} ms" for n in impls), flush=True)
    for case in ("first_ms", "warm_ms"):
        res[case] = {n: round(statistics.median(r[n][case] for r in res["rounds"]), 2) for n in impls}
    res["mismatches"] = mismatches
    print(f"median over rounds: first touch {res['first_ms']}, warm {res['warm_ms']}; "
          f"frames differing: {mismatches}")
    if a.out:
        os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
        json.dump(res, open(a.out, "w"), indent=1)
    ours.close()
    proto.close()
    return 1 if mismatches else 0


if __name__ == "__main__":
    sys.exit(main())

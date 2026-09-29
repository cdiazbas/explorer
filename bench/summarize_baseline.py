#!/usr/bin/env python3
"""Summarise a baseline directory written by bench/prototype_baseline.sh: one row per configuration (display mode,
per-pixel file or not), each metric as the median of every round ("r1 / r2 / ..."), so the spread between rounds is
the noise to compare against. Writes summary.md and summary.json next to the runs. Standard library only.

    python3 bench/summarize_baseline.py bench/results/baseline_<host>_<date>
"""
import glob
import json
import os
import re
import sys

# (column, action name in the selftest JSON (a regex), field)
METRICS = [
    ("first image s", None, "open_to_first_frame_s"),
    ("cursor ms", r"^cursor: crosshair", "median"),
    ("cursor p95", r"^cursor: crosshair", "p95"),
    ("spectrum+λt ms", r"^cursor: spectrum\+λ–t from reader", "median"),
    ("step t ms", r"^step in t$", "median"),
    ("step λ ms", r"^step in λ$", "median"),
    ("Stokes ms", r"^change Stokes$", "median"),
    ("play fps", r"^playback 2 s", "fps"),
    ("bridge MB/move", r"^cursor: X11 bridge traffic", "MB_per_update"),
    ("bridge shown/s", r"^playback: updates shown via X11 bridge", "per_s"),
]


def value(run, action, field):
    if action is None:
        return run.get(field)
    for name, d in run.get("actions", {}).items():
        if re.search(action, name):
            return d.get(field)
    return None


def main(d):
    meta = json.load(open(os.path.join(d, "meta.json")))
    runs = {}
    for f in sorted(glob.glob(os.path.join(d, "*_r*.json"))):
        m = re.match(r"(.+)_(sp|nosp)_r(\d+)\.json$", os.path.basename(f))
        if m:
            runs.setdefault((m.group(1), m.group(2)), {})[int(m.group(3))] = json.load(open(f))
    missing = [os.path.basename(f) for f in glob.glob(os.path.join(d, "*_r*.log"))
               if not os.path.exists(f[:-4] + ".json")]
    table, rows = {}, []
    for (mode, sp), by_round in sorted(runs.items()):
        looks = {r.get("look") for r in by_round.values()}
        row = {"mode": mode, "sp": sp, "look": ",".join(sorted(str(x) for x in looks))}
        for col, action, field in METRICS:
            vals = [value(by_round[k], action, field) for k in sorted(by_round)]
            row[col] = vals
        table[f"{mode}/{sp}"] = row
        cells = []
        for col, _, _ in METRICS:
            vals = row[col]
            cells.append(" / ".join("–" if v is None else f"{v:g}" for v in vals) if any(v is not None for v in vals)
                         else "–")
        rows.append(f"| {mode} | {sp} | " + " | ".join(cells) + " |")
    head = (f"# Prototype baseline on {meta['host']}, {meta['date']}\n\n"
            f"- cube: `{os.path.basename(meta['cube'])}`; look: {meta['look']}; rounds: {meta['rounds']} (ABBA order)\n"
            f"- load at start: {', '.join(f'{x:.2f}' for x in meta['load_start'])}; Python {meta['python']}\n"
            f"- prototype code md5: {meta['prototype_code_md5']}; explorer commit: {meta.get('explorer_commit')}\n"
            + (f"- **runs without results** (see their .log): {', '.join(missing)}\n" if missing else "")
            + "\nEach cell: the value of round 1 / round 2 / ... (medians of the selftest's repetitions).\n\n")
    md = head + "| mode | per-pixel | " + " | ".join(c for c, _, _ in METRICS) + " |\n"
    md += "|---|---|" + "---:|" * len(METRICS) + "\n" + "\n".join(rows) + "\n"
    open(os.path.join(d, "summary.md"), "w").write(md)
    json.dump(dict(meta={k: v for k, v in meta.items() if k != "prototype_files"}, configs=table, missing=missing),
              open(os.path.join(d, "summary.json"), "w"), indent=1)
    print(md)
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))

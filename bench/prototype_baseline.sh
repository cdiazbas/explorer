#!/usr/bin/env bash
# Baseline of the prototype (ROADMAP E0.8): its selftest, in every display mode and with and without the per-pixel
# file, in alternating rounds (ABBA: configurations in order in odd rounds, reversed in even ones).
#   bench/prototype_baseline.sh <cube_im.fits> [--rounds 2] [--modes offscreen,xcb,bridge] [--look modern]
# Modes: offscreen (no X); xcb and bridge on the private Xvfb (EXPLORER_XVFB_DISPLAY, default :97, cookie in
# EXPLORER_XVFB_AUTH, default /tmp/crispex_xvfb/auth). On a Mac only offscreen makes sense (cocoa would open
# windows on the user's screen). Results: bench/results/baseline_<host>_<date>/ (one JSON per run, meta.json,
# summary.md). The prototype is found at $EXPLORER_PROTOTYPE, default ../prototype; it has no git, so meta.json
# records the md5 of its code to know later exactly what was measured. Nothing is written into the prototype, and
# its selftest saves its window layout into a temporary XDG_CONFIG_HOME, not into the user's (Linux).
set -u
here="$(cd "$(dirname "$0")" && pwd)"
root="$(dirname "$here")"
plat="$(uname -s)-$(uname -m)"
proto="$(cd "${EXPLORER_PROTOTYPE:-$root/../prototype}" && pwd)"
cube="${1:?usage: bench/prototype_baseline.sh <cube_im.fits> [--rounds N] [--modes a,b] [--look name]}"; shift
rounds=2 modes="offscreen,xcb,bridge" look=modern
while [ $# -gt 0 ]; do
  case "$1" in
    --rounds) rounds="$2"; shift ;;
    --modes) modes="$2"; shift ;;
    --look) look="$2"; shift ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done
py=""
for v in "$proto/.venv" "$proto/.venv-$plat"; do
  [ -x "$v/bin/python" ] && "$v/bin/python" -c "" 2>/dev/null && { py="$v/bin/python"; break; }
done
[ -n "$py" ] || { echo "no Python environment in $proto (.venv or .venv-$plat)" >&2; exit 1; }
xdisp="${EXPLORER_XVFB_DISPLAY:-:97}" xauth="${EXPLORER_XVFB_AUTH:-/tmp/crispex_xvfb/auth}"
case ",$modes," in *,xcb,*|*,bridge,*)
  [ -S "/tmp/.X11-unix/X${xdisp#:}" ] || { echo "no X server on $xdisp (start the private Xvfb first)" >&2; exit 1; } ;;
esac
out="$root/bench/results/baseline_$(hostname -s)_$(date +%Y%m%dT%H%M)"
mkdir -p "$out"
cfgdir="$(mktemp -d)"; trap 'rm -rf "$cfgdir"' EXIT
unset LD_LIBRARY_PATH
[ "$(uname -s)" = Linux ] && [ -d "$proto/.qtlibs/only" ] && export LD_LIBRARY_PATH="$proto/.qtlibs/only"
export NUMBA_NUM_THREADS="${NUMBA_NUM_THREADS:-64}" XDG_CONFIG_HOME="$cfgdir"

"$py" - "$out/meta.json" "$proto" "$cube" "$look" "$rounds" "$modes" <<'PY'
import glob, hashlib, json, os, platform, socket, subprocess, sys, time
out, proto, cube, look, rounds, modes = sys.argv[1:]
files = sorted(glob.glob(os.path.join(proto, "app", "*.py")) + glob.glob(os.path.join(proto, "viewer", "*.py")))
code = {os.path.relpath(f, proto): hashlib.md5(open(f, "rb").read()).hexdigest() for f in files}
try:
    commit = subprocess.run(["git", "-C", os.path.dirname(os.path.dirname(out)), "rev-parse", "--short", "HEAD"],
                            capture_output=True, text=True).stdout.strip()
except OSError:
    commit = None
json.dump(dict(host=socket.gethostname().split(".")[0], date=time.strftime("%Y-%m-%dT%H:%M:%S"),
               load_start=os.getloadavg(), cube=os.path.realpath(cube), look=look, rounds=int(rounds),
               modes=modes.split(","), python=platform.python_version(), explorer_commit=commit,
               prototype_code_md5=hashlib.md5(json.dumps(code, sort_keys=True).encode()).hexdigest(),
               prototype_files=code), open(out, "w"), indent=1)
PY

configs=()
for m in ${modes//,/ }; do configs+=("$m:sp" "$m:nosp"); done
for r in $(seq 1 "$rounds"); do
  order=("${configs[@]}")
  if [ $((r % 2)) -eq 0 ]; then order=(); for ((i=${#configs[@]}-1; i>=0; i--)); do order+=("${configs[$i]}"); done; fi
  for c in "${order[@]}"; do
    m="${c%%:*}" sp="${c##*:}"
    spargs=(); [ "$sp" = nosp ] && spargs=(--no-sp)
    case "$m" in
      offscreen) envs=(env -u DISPLAY QT_QPA_PLATFORM=offscreen) ;;
      xcb)       envs=(env DISPLAY="$xdisp" XAUTHORITY="$xauth" CRISPEX_X11=native) ;;
      bridge)    envs=(env DISPLAY="$xdisp" XAUTHORITY="$xauth" CRISPEX_X11=bridge) ;;
      *) echo "unknown mode $m" >&2; exit 2 ;;
    esac
    f="$out/${m}_${sp}_r$r"
    t0=$(date +%s)
    "${envs[@]}" "$py" "$here/prototype_selftest.py" "$proto" --look "$look" "$cube" ${spargs[@]+"${spargs[@]}"} --out "$f.json" \
      > "$f.log" 2>&1
    rc=$?
    echo "  round $r  $m  $sp  exit $rc  $(( $(date +%s) - t0 )) s" | tee -a "$out/runs.txt"
  done
done
python3 "$here/summarize_baseline.py" "$out"

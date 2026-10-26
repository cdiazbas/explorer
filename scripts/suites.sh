#!/usr/bin/env bash
# The full suites of this tree, headless, one after the other, each to its log; the load before and after.
#   scripts/suites.sh LOGDIR [--xvfb BIN] [--display :N] [--size WxH]
# tests/unit and tests/golden offscreen; then tests/xvfb on a private X server of its own (BIN, started on :N and
# stopped after), or skipped without --xvfb. Run it on a copy of the tree (only the files git tracks) so that a long
# run does not see later edits, with the environment named by EXPLORER_VENV when the copy has none of its own; a
# copy needs .qtlibs and ../data linked like the tree's for the Qt and real-data tests. --size: at least 1800 px wide
# for the bridge's tests of whole windows (default 2560x1440). Done: LOGDIR/DONE; exit code = suites that failed.
# Over ssh, the whole command in one detached shell, or ssh waits for the suites to end:
#   ssh host 'nohup bash -c "cd COPY && EXPLORER_VENV=... scripts/suites.sh LOGS --xvfb BIN" > out 2>&1 < /dev/null &'
# and stop it by the PID it prints: a pattern given to pkill -f is in ssh's own command line too, and kills it.
set -u
here="$(cd "$(dirname "$0")" && pwd)"
root="$(dirname "$here")"
. "$here/env.sh"                                    # plat, venv and qt_libs
py="$venv/bin/python"
logs="${1:?usage: scripts/suites.sh LOGDIR [--xvfb BIN] [--display :N] [--size WxH]}"; shift
xvfb="" disp=":131" size="2560x1440"
while [ $# -gt 0 ]; do
  case "$1" in
    --xvfb) xvfb="$2"; shift 2 ;;
    --display) disp="$2"; shift 2 ;;
    --size) size="$2"; shift 2 ;;
    *) echo "unknown option $1" >&2; exit 2 ;;
  esac
done
[ -x "$py" ] || { echo "no environment: $py (set EXPLORER_VENV)" >&2; exit 1; }
mkdir -p "$logs"
rm -f "$logs/DONE"
echo "suites.sh pid $$: $root, $py; logs in $logs"
cd "$root"
unset DISPLAY                                       # no window on anyone's screen
qt_libs                                             # no other environment's Qt
export PYTHONPATH="$root/src"
load() { [ -r /proc/loadavg ] && cat /proc/loadavg || uptime; }
load > "$logs/load.log"
fails=0
QT_QPA_PLATFORM=offscreen "$py" -m pytest -q -p no:cacheprovider tests/unit tests/golden > "$logs/unit.log" 2>&1 \
  || fails=$((fails + 1))
if [ -n "$xvfb" ]; then
  "$xvfb" "$disp" -screen 0 "${size}x24" -nolisten tcp > "$logs/xvfbserver.log" 2>&1 &
  xp=$!
  sleep 3
  EXPLORER_TEST_XVFB="$xvfb" EXPLORER_TEST_XDISPLAY="$disp" "$py" -m pytest -q -p no:cacheprovider tests/xvfb \
    > "$logs/xvfb.log" 2>&1 || fails=$((fails + 1))
  kill "$xp"
else
  echo "tests/xvfb skipped: no --xvfb" > "$logs/xvfb.log"
fi
load >> "$logs/load.log"
for f in unit xvfb; do echo "$f: $(tail -1 "$logs/$f.log")"; done | tee "$logs/summary.log"
touch "$logs/DONE"
exit "$fails"

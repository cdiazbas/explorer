#!/usr/bin/env bash
# Every check CI would run, here: hygiene, lint, layer contracts, types, tests. One summary; exit code = failures.
#   scripts/check.sh           all of them (~10 s)
#   scripts/check.sh --fast    hygiene of the tree, ruff and layer contracts (no types, no tests)
# Tests run headless (no DISPLAY: the X11 bridge would otherwise open windows on the user's screen) and without an
# inherited LD_LIBRARY_PATH (another environment's Qt breaks PySide6), as scripts/run.sh does.
# Outside a git repository (the copy on bellatrix, synced without .git) the hygiene check is skipped.
here="$(cd "$(dirname "$0")" && pwd)"
root="$(dirname "$here")"
plat="$(uname -s)-$(uname -m)"
bin="${EXPLORER_VENV:-$root/.venv-$plat}/bin"
fast=0; [ "${1:-}" = "--fast" ] && fast=1
cd "$root"
[ -x "$bin/python" ] || { echo "no environment in $bin: run scripts/setup_env.sh --dev" >&2; exit 1; }
[ -x "$bin/ruff" ] || { echo "no dev tools in $bin: run scripts/setup_env.sh --dev" >&2; exit 1; }
unset LD_LIBRARY_PATH
[ "$(uname -s)" = Linux ] && [ -d "$root/.qtlibs/only" ] && export LD_LIBRARY_PATH="$root/.qtlibs/only"

fails=0; rows=()
step() {                                   # step <name> <command...>
  local name="$1"; shift
  local t0=$(date +%s)
  local out; out="$("$@" 2>&1)"; local rc=$?
  local s="ok"; [ $rc -ne 0 ] && { s="FAIL"; fails=$((fails + 1)); echo "$out" | tail -30; }
  rows+=("$(printf '  %-5s %-10s %4ss' "$s" "$name" "$(( $(date +%s) - t0 ))")")
}
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  step hygiene python3 scripts/hygiene.py
else
  rows+=("  skip  hygiene    (not a git repository)")
fi
step ruff "$bin/ruff" check src tests scripts bench
step layers "$bin/lint-imports"
if [ $fast = 0 ]; then
  step types "$bin/mypy"
  step tests env -u DISPLAY QT_QPA_PLATFORM=offscreen "$bin/python" -m pytest -q
fi
echo "checks:"; printf '%s\n' "${rows[@]}"
[ $fails -eq 0 ] && echo "all passed" || echo "$fails failed"
exit $fails

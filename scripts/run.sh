#!/usr/bin/env bash
# Run explorer from this directory with the environment built by scripts/setup_env.sh (macOS or Linux):
#   scripts/run.sh <cube_im.fits> [options]      scripts/run.sh doctor      scripts/run.sh --version
# - picks the environment that runs on this machine: $EXPLORER_VENV, else .venv-<OS>-<arch>;
# - rebuilds it (setup_env.sh) when the pinned versions changed since it was built, if it can write it;
# - drops an inherited LD_LIBRARY_PATH (another env's Qt breaks PySide6) and adds .qtlibs/only on Linux
#   (libxcb-cursor for X11, see setup_env.sh);
# - more reader threads than cores: scattered reads wait on the disk, not on the CPU (prototype, Fase 17).
# Relative paths in the arguments are relative to where you call it from.
here="$(cd "$(dirname "$0")" && pwd)"
root="$(dirname "$here")"
plat="$(uname -s)-$(uname -m)"
venv="${EXPLORER_VENV:-$root/.venv-$plat}"
if ! { [ -x "$venv/bin/python" ] && "$venv/bin/python" -c "" 2>/dev/null; }; then
  echo "no environment for $plat in $venv: run $here/setup_env.sh first" >&2
  exit 1
fi
# the pins changed since the environment was built: update it if we may (only its owner can)
if [ "$(cksum < "$root/uv.lock")" != "$(cat "$venv/.lock.cksum" 2>/dev/null)" ]; then
  if [ -w "$venv" ]; then
    echo "[run.sh] pinned versions changed: updating $venv" >&2
    "$here/setup_env.sh" --venv "$venv" $([ -f "$venv/.dev" ] && echo --dev) >&2 || exit 1
  else
    echo "[run.sh] note: pinned versions changed; ask the owner of $venv to run setup_env.sh" >&2
  fi
fi
unset LD_LIBRARY_PATH
[ "$(uname -s)" = Linux ] && [ -d "$root/.qtlibs/only" ] && export LD_LIBRARY_PATH="$root/.qtlibs/only"
export NUMBA_NUM_THREADS="${NUMBA_NUM_THREADS:-64}"
exec "$venv/bin/explorer" "$@"

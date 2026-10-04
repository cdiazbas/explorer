#!/usr/bin/env bash
# Run explorer from this directory with the environment built by scripts/setup_env.sh (macOS or Linux):
#   scripts/run.sh <cube_im.fits> [options]      scripts/run.sh doctor      scripts/run.sh --version
# - picks the environment that runs on this machine: $EXPLORER_VENV, else .venv-<OS>-<arch>;
# - rebuilds it (setup_env.sh) when the pinned versions changed since it was built, if it can write it;
# - drops an inherited LD_LIBRARY_PATH (another env's Qt breaks PySide6) and adds .qtlibs/only on Linux
#   (libxcb-cursor for X11, see setup_env.sh);
# - more reader threads than cores: scattered reads wait on the disk, not on the CPU (docs/measured.md).
# Relative paths in the arguments are relative to where you call it from. It may be called through a link (the
# `explorer` command that setup_env.sh --link puts on the PATH): the link is followed to find the code.
src="$0"
while [ -L "$src" ]; do                             # readlink -f is not on every macOS
  dir="$(cd "$(dirname "$src")" && pwd)"
  src="$(readlink "$src")"
  case "$src" in /*) ;; *) src="$dir/$src" ;; esac
done
here="$(cd "$(dirname "$src")" && pwd)"
root="$(dirname "$here")"
plat="$(uname -s)-$(uname -m)"
venv="${EXPLORER_VENV:-$root/.venv-$plat}"
if ! { [ -x "$venv/bin/python" ] && "$venv/bin/python" -c "" 2>/dev/null; }; then
  echo "no environment for $plat in $venv: run $here/setup_env.sh first" >&2
  exit 1
fi
# the pins changed since the environment was built: update it if this user may (only its owner can)
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
# the code next to this script, whichever tree installed the env; the inherited PYTHONPATH without empty entries: an
# empty one is the current folder, and a file there named as a module (types.py) replaced the standard one. A line
# like PYTHONPATH="${PYTHONPATH}:dir" in a shell's startup file leaves one when PYTHONPATH was empty
inherited="" rest="${PYTHONPATH:-}"
while [ -n "$rest" ]; do                            # no arrays: macOS's bash 3.2 under set -u rejects an empty one
  p="${rest%%:*}"
  case "$rest" in *:*) rest="${rest#*:}" ;; *) rest="" ;; esac
  [ -z "$p" ] || inherited="${inherited:+$inherited:}$p"
done
export PYTHONPATH="$root/src${inherited:+:$inherited}"
# NUMBA_NUM_THREADS is left to the user: unset, explorer sizes numba's pool for its scattered reads
# (src/explorer/data/_numba.py, at least 128 threads)
# macOS: Python started through explorer.app (made by setup_env.sh; here, once, if missing), so that the Dock shows
# explorer's icon from launch: a bare executable's is a blank document until the window sets its own.
# __PYVENV_LAUNCHER__ tells that Python its environment; Python unsets it, so nothing started from explorer sees it
if [ "$(uname -s)" = Darwin ]; then
  app="$venv/explorer.app"
  if [ ! -x "$app/Contents/MacOS/explorer" ] && [ -w "$venv" ]; then
    "$venv/bin/python" "$root/tools/icons/export.py" --app "$app" --exe "$venv/bin/python" >/dev/null 2>&1 || true
  fi
  if [ -x "$app/Contents/MacOS/explorer" ]; then
    __PYVENV_LAUNCHER__="$venv/bin/python" exec "$app/Contents/MacOS/explorer" "$venv/bin/explorer" "$@"
  fi
fi
exec "$venv/bin/explorer" "$@"

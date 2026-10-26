#!/usr/bin/env bash
# Run explorer from this directory with the environment built by scripts/setup_env.sh (macOS or Linux):
#   scripts/run.sh <cube_im.fits> [options]      scripts/run.sh doctor      scripts/run.sh --version
# - picks the environment that runs on this machine: $EXPLORER_VENV, else .venv-<OS>-<arch>;
# - rebuilds it (setup_env.sh) when the pinned versions changed since it was built, only if it is this tree's own
#   .venv-<OS>-<arch> and this user may write it: another tree's, shared on StorNext, is never changed;
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
. "$here/env.sh"                                    # plat, venv and qt_libs
if ! { [ -x "$venv/bin/python" ] && "$venv/bin/python" -c "" 2>/dev/null; }; then
  echo "no environment for $plat in $venv: run $here/setup_env.sh first" >&2
  exit 1
fi
# this tree's own environment: .venv-<OS>-<arch> in this folder, compared on disk, so that a link there to another
# tree's environment is that tree's. Only this one is rebuilt or added to: another tree's, named by $EXPLORER_VENV
# or linked, may be shared by everyone, and an old or experimental copy would install its pins under them
own=0 venv_on_disk="$(cd -P "$venv" && pwd)"
[ "$venv_on_disk" = "$(cd -P "$root" && pwd)/.venv-$plat" ] && own=1
# the pins changed since the environment was built: update it if it is this tree's and this user may write it.
# Another tree's is left as it is, and this code runs on the versions of that tree's uv.lock
if [ "$(cksum < "$root/uv.lock")" != "$(cat "$venv/.lock.cksum" 2>/dev/null)" ]; then
  if [ "$own" = 0 ]; then
    first=""                                        # setup_env.sh would build through the link, into that tree's
    [ -L "$root/.venv-$plat" ] && first="remove the link $root/.venv-$plat, then "
    [ -n "${EXPLORER_VENV:-}" ] && first="unset EXPLORER_VENV, then "
    echo "[run.sh] note: $venv_on_disk is not this tree's environment and was built from another uv.lock:" \
         "left as it is; this code runs on its versions. For this tree's own: $first$here/setup_env.sh" >&2
  elif [ -w "$venv" ]; then
    echo "[run.sh] pinned versions changed: updating $venv" >&2
    "$here/setup_env.sh" --venv "$venv" $([ -f "$venv/.dev" ] && echo --dev) >&2 || exit 1
  else
    echo "[run.sh] note: pinned versions changed; ask the owner of $venv to run setup_env.sh" >&2
  fi
fi
qt_libs
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
# explorer's icon from launch: a bare executable's is a blank document until the window sets its own; in this tree's
# environment only (above).
# __PYVENV_LAUNCHER__ tells that Python its environment; Python unsets it, so nothing started from explorer sees it
if [ "$(uname -s)" = Darwin ]; then
  app="$venv/explorer.app"
  if [ ! -x "$app/Contents/MacOS/explorer" ] && [ "$own" = 1 ] && [ -w "$venv" ]; then
    "$venv/bin/python" "$root/tools/icons/export.py" --app "$app" --exe "$venv/bin/python" >/dev/null 2>&1 || true
  fi
  if [ -x "$app/Contents/MacOS/explorer" ]; then
    __PYVENV_LAUNCHER__="$venv/bin/python" exec "$app/Contents/MacOS/explorer" "$venv/bin/explorer" "$@"
  fi
fi
exec "$venv/bin/explorer" "$@"

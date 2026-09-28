#!/usr/bin/env bash
# Build (or refresh) explorer's environment for this machine. macOS or Linux, no root, safe to re-run.
#
#   scripts/setup_env.sh              # .venv-<OS>-<arch> next to the code, explorer installed editable
#   scripts/setup_env.sh --dev        # also pytest, ruff, pyright, import-linter
#   scripts/setup_env.sh --venv DIR   # build it in DIR instead
#   scripts/setup_env.sh --force      # delete the environment first
#
# One directory on shared storage serves Linux and Macs: each builds its own .venv-<OS>-<arch>.
# Tools, as in the prototype's setup_env.sh: uv (on PATH, or its per-platform copy in
# ~/.cache/explorer/uv-<OS>-<arch>) with the exact versions of uv.lock; else mamba/conda for Python 3.12 and pip
# with requirements/lock*.txt (uv.lock exported with hashes by scripts/sync.py). Only tools that run on this
# machine count: a shared home shows Linux tools to Macs. With uv, Python lives next to the environment
# (.python-<OS>-<arch>), never in the home of whoever builds it. The package is installed editable, so code
# pushed by scripts/sync.py takes effect without reinstalling.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
root="$(dirname "$here")"
plat="$(uname -s)-$(uname -m)"
qtlibs="$root/.qtlibs"
cd "$root"
unset LD_LIBRARY_PATH                               # another env's Qt on this path breaks PySide6

venv="$root/.venv-$plat" dev=0 force=0
while [ $# -gt 0 ]; do
  case "$1" in
    --dev) dev=1 ;;
    --force) force=1 ;;
    --venv) venv="$2"; shift ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done
pyhome="$(dirname "$venv")/.python-$plat"
[ "$force" = 1 ] && rm -rf "$venv"

works() { [ -n "$1" ] && [ -x "$1" ] && "$1" --version >/dev/null 2>&1; }
conda_cmd() {  # a real mamba/conda executable: in scripts they are not the shell functions of .bashrc
  local c
  for c in "${MAMBA_EXE:-}" "${CONDA_EXE:-}" "$(type -P mamba || true)" "$(type -P conda || true)"; do
    works "$c" && { echo "$c"; return 0; }
  done
  return 1
}
UV=""
for c in "$(type -P uv || true)" "${XDG_CACHE_HOME:-$HOME/.cache}/explorer/uv-$plat/uv" \
         "${XDG_CACHE_HOME:-$HOME/.cache}/crispex/uv-$plat/uv"; do
  works "$c" && { UV="$c"; break; }
done

if [ -n "$UV" ]; then
  echo "== uv: $venv from uv.lock (Python in $pyhome)"
  export UV_PYTHON_INSTALL_DIR="$pyhome" UV_PROJECT_ENVIRONMENT="$venv" UV_PYTHON_PREFERENCE=only-managed
  "$UV" python install -q --no-bin 3.12
  if [ "$dev" = 1 ]; then "$UV" sync -q --frozen; else "$UV" sync -q --frozen --no-dev; fi
elif c="$(conda_cmd)"; then
  req="requirements/lock.txt"; [ "$dev" = 1 ] && req="requirements/lock-dev.txt"
  [ -f "$req" ] || { echo "missing $req (scripts/sync.py exports it from uv.lock)" >&2; exit 1; }
  if [ ! -x "$venv/bin/python" ]; then
    echo "== $(basename "$c"): $venv (conda-forge Python 3.12)"
    "$c" create -q -y -p "$venv" -c conda-forge --override-channels python=3.12 pip >/dev/null
  fi
  echo "== pip: $req (exact versions, hash-checked)"
  "$venv/bin/python" -m pip install -q --upgrade pip
  "$venv/bin/python" -m pip install -q -r "$req"
  "$venv/bin/python" -m pip install -q --no-deps -e "$root"
else
  echo "need uv, mamba or conda to get Python 3.12 (uv: https://docs.astral.sh/uv/, no admin needed)" >&2
  exit 1
fi
# what run.sh compares to rebuild when the pins change (uv.lock is synced too, uv or not), and the mode
cksum < uv.lock > "$venv/.lock.cksum"
if [ "$dev" = 1 ]; then touch "$venv/.dev"; else rm -f "$venv/.dev"; fi
chmod -R a+rX "$venv" 2>/dev/null || true
[ -d "$pyhome" ] && chmod -R a+rX "$pyhome" 2>/dev/null || true

# Linux only: Qt >= 6.5 needs libxcb-cursor for X11 (ssh -Y). RHEL 9 lacks it and there is no root: take it
# from conda-forge into a prefix of its own and expose only that library (scripts/run.sh adds .qtlibs/only).
if [ "$(uname -s)" = Linux ] && ! /sbin/ldconfig -p 2>/dev/null | grep -q "libxcb-cursor.so.0" \
   && [ ! -e "$qtlibs/only/libxcb-cursor.so.0" ]; then
  if c="$(conda_cmd)"; then
    echo "== libxcb-cursor missing on this system: installing it into $qtlibs"
    "$c" create -q -y -p "$qtlibs" -c conda-forge --override-channels xcb-util-cursor >/dev/null
    mkdir -p "$qtlibs/only"
    for f in "$qtlibs"/lib/libxcb-cursor.so.0*; do ln -sf "../lib/$(basename "$f")" "$qtlibs/only/"; done
  else
    echo "note: no libxcb-cursor and no mamba/conda to install it: Qt will not show over X11 (ssh -Y)" >&2
  fi
fi

echo "== checking (explorer doctor, headless)"
[ -d "$qtlibs/only" ] && [ "$(uname -s)" = Linux ] && export LD_LIBRARY_PATH="$qtlibs/only"
env -u DISPLAY QT_QPA_PLATFORM=offscreen "$venv/bin/explorer" doctor
echo "== done: $venv. Run with  scripts/run.sh <cube_im.fits>"

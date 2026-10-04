#!/usr/bin/env bash
# Build (or refresh) explorer's environment for this machine. macOS or Linux, no root, safe to re-run.
#
#   scripts/setup_env.sh              # .venv-<OS>-<arch> next to the code, explorer installed editable
#   scripts/setup_env.sh --dev        # also pytest, ruff, pyright, import-linter
#   scripts/setup_env.sh --venv DIR   # build it in DIR instead
#   scripts/setup_env.sh --force      # delete the environment first
#   scripts/setup_env.sh --link       # also the `explorer` command on the PATH, from any folder: a link
#                                     # to scripts/run.sh, which picks this machine's environment, so a home
#                                     # shared by macOS and Linux serves both. In the first of $XDG_BIN_HOME,
#                                     # ~/.local/bin, ~/bin that a new terminal has on its PATH; else in
#                                     # ~/.local/bin, put on the PATH by the shell's startup file (a marked
#                                     # block, added once). Then a new terminal is asked to find it and run it
#   scripts/setup_env.sh --link --no-update-shell   # never write a startup file (says what to add)
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

venv="$root/.venv-$plat" dev=0 force=0 link=0 update_shell=1
while [ $# -gt 0 ]; do
  case "$1" in
    --dev) dev=1 ;;
    --force) force=1 ;;
    --link) link=1 ;;
    --update-shell) update_shell=1 ;;               # the default; kept for the commands written with it
    --no-update-shell) update_shell=0 ;;
    --venv) venv="$2"; shift ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done
pyhome="$(dirname "$venv")/.python-$plat"
[ "$force" = 1 ] && rm -rf "$venv"

# What a new terminal of the user's shell sees: run through ssh or from a script, this process's PATH is not the one
# the user will have. A clean environment, the shell interactive (its rc file) or interactive and login (ssh, macOS's
# Terminal: bash then reads ~/.bash_profile, which need not read ~/.bashrc). $1: -ic or -lic; $2: the command
in_new_shell() {
  env -i HOME="$HOME" USER="${USER:-}" LOGNAME="${LOGNAME:-}" SHELL="$sh" TERM=dumb PATH=/usr/bin:/bin \
    "$sh" "$1" "printf '\\n@@explorer@@%s\\n' \"\$($2)\"" </dev/null 2>/dev/null | sed -n 's/^@@explorer@@//p' | tail -n 1
}
on_path() { case ":$2:" in *":$1:"*) return 0 ;; esac; return 1; }

add_block() {                                       # $1: a startup file; the block once, between its marks
  shown="$bin"                                      # under the home as $HOME/...: the same line serves a home
  case "$bin" in "$HOME"/*) shown="\$HOME/${bin#"$HOME"/}" ;; esac     # mounted elsewhere on another machine
  mark="# >>> explorer: $shown on the PATH >>>"
  [ -f "$1" ] && grep -qF "$mark" "$1" && return 0
  {
    printf '\n%s\n' "$mark"
    printf 'case ":$PATH:" in *":%s:"*) ;; *) export PATH="%s:$PATH" ;; esac\n' "$shown" "$shown"
    printf '%s\n' "# <<< explorer <<<"
  } >> "$1"
  echo "[setup_env] $1: $shown added to the PATH (the block between the explorer marks)"
}

link_command() {                                    # the command on the PATH: a link to run.sh, never a copy
  sh="${SHELL:-/bin/bash}"
  [ -x "$sh" ] || sh=/bin/bash
  kind="$(basename "$sh")"
  case "$kind" in bash|zsh|sh|dash|ksh) ;; *) kind=other ;; esac
  bin=""
  if [ "$kind" != other ]; then
    lpath="$(in_new_shell -lic 'printf %s "$PATH"')"
    ipath="$(in_new_shell -ic 'printf %s "$PATH"')"
    for d in ${XDG_BIN_HOME:+"$XDG_BIN_HOME"} "$HOME/.local/bin" "$HOME/bin"; do
      if on_path "$d" "$lpath" && on_path "$d" "$ipath"; then bin="$d"; break; fi
    done
  fi
  reachable=1
  [ -n "$bin" ] || { bin="${XDG_BIN_HOME:-$HOME/.local/bin}"; reachable=0; }
  cmd="$bin/explorer"
  if [ -e "$cmd" ] && [ ! -L "$cmd" ]; then
    echo "[setup_env] $cmd exists and is not a link: left alone" >&2
    return 1
  fi
  mkdir -p "$bin"
  ln -sfn "$here/run.sh" "$cmd"
  echo "[setup_env] $cmd -> $here/run.sh"
  if [ "$reachable" = 0 ]; then
    if [ "$kind" = other ] || [ "$update_shell" = 0 ]; then
      echo "[setup_env] $bin is not on the PATH of a new terminal: add it in your shell's startup file" >&2
      return 1
    fi
    case "$kind" in
      zsh) add_block "$HOME/.zshrc" ;;
      bash)
        add_block "$HOME/.bashrc"
        # a login shell reads the first of these, and not always ~/.bashrc
        if ! on_path "$bin" "$(in_new_shell -lic 'printf %s "$PATH"')"; then
          login="$HOME/.profile"
          for f in "$HOME/.bash_profile" "$HOME/.bash_login" "$HOME/.profile"; do
            [ -f "$f" ] && { login="$f"; break; }
          done
          add_block "$login"
        fi
        ;;
      *) add_block "$HOME/.profile" ;;
    esac
  fi
  # the check: a new terminal, login or not, finds this link first, and it runs
  for how in -lic -ic; do
    found="$(in_new_shell "$how" 'command -v explorer')"
    if [ "$found" != "$cmd" ]; then
      if [ -z "$found" ]; then
        echo "[setup_env] a new terminal ($kind $how) does not find explorer" >&2
      else
        echo "[setup_env] a new terminal ($kind $how) finds another explorer first: $found" >&2
      fi
      return 1
    fi
  done
  if ! version="$(EXPLORER_VENV="$venv" "$cmd" --version 2>&1)"; then
    echo "[setup_env] $cmd --version failed: $version" >&2
    return 1
  fi
  echo "[setup_env] a new terminal finds and runs it: explorer --version -> $version"
}

# --link on an environment already up to date (uv.lock unchanged since it was built, as run.sh checks, and of the
# mode asked: a --dev one serves without --dev too): nothing to install or check again, only the link
if [ "$link" = 1 ] && [ "$force" = 0 ] && [ -x "$venv/bin/python" ] && "$venv/bin/python" -c "" 2>/dev/null \
   && [ "$(cksum < uv.lock)" = "$(cat "$venv/.lock.cksum" 2>/dev/null)" ] && { [ "$dev" = 0 ] || [ -f "$venv/.dev" ]; }; then
  echo "== $venv is up to date (uv.lock unchanged since it was built): only the link"
  link_command
  exit
fi

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

# macOS: explorer.app in the environment, a link to its Python with explorer's icon, which run.sh starts explorer
# through: the Dock then shows the icon from launch, where a bare executable has a blank document
if [ "$(uname -s)" = Darwin ]; then
  if "$venv/bin/python" tools/icons/export.py --app "$venv/explorer.app" --exe "$venv/bin/python" >/dev/null; then
    echo "== $venv/explorer.app: the Dock's icon from launch"
  else
    echo "note: no explorer.app: the Dock shows a blank icon until the window sets explorer's" >&2
  fi
fi

echo "== checking (explorer doctor, headless)"
[ -d "$qtlibs/only" ] && [ "$(uname -s)" = Linux ] && export LD_LIBRARY_PATH="$qtlibs/only"
env -u DISPLAY QT_QPA_PLATFORM=offscreen "$venv/bin/explorer" doctor
echo "== done: $venv. Run with  scripts/run.sh <cube_im.fits>"

if [ "$link" = 1 ]; then link_command; fi

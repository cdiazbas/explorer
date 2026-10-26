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
caller_path="$PATH"                                 # the terminal that runs this: can it use the link at once?

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
# the user will have. A clean environment, the shell interactive (its startup file) or interactive and login (ssh,
# macOS's Terminal: bash then reads ~/.bash_profile, which need not read ~/.bashrc). Each family in its own syntax:
# sh-like (bash, zsh, sh, dash, ksh), csh-like (tcsh, csh: no login with -c, so ~/.login is read after the rc file,
# as a login does). $1: -ic or -lic. Prints that terminal's PATH
new_path() {
  case "$family" in
    posix) probe='printf "\n@@explorer@@%s\n" "$PATH"' ; flags="$1" ;;
    csh)
      probe='echo ""; echo "@@explorer@@$PATH"'
      [ "$1" = -lic ] && probe='if ( -r ~/.login ) source ~/.login; '"$probe"
      flags=-ic ;;
  esac
  env -i HOME="$HOME" USER="${USER:-}" LOGNAME="${LOGNAME:-}" SHELL="$sh" TERM=dumb PATH=/usr/bin:/bin \
    "$sh" "$flags" "$probe" </dev/null 2>/dev/null | sed -n 's/^@@explorer@@//p' | tail -n 1
}
on_path() { case ":$2:" in *":$1:"*) return 0 ;; esac; return 1; }
first_on() {                                        # $1: a PATH; the explorer it finds first, as a shell would
  rest="$1:"
  while [ -n "$rest" ]; do
    d="${rest%%:*}"; rest="${rest#*:}"
    [ -n "$d" ] && [ -x "$d/explorer" ] && { echo "$d/explorer"; return; }
  done
}

add_block() {                                       # $1: a startup file; the block once, between its marks
  shown="$bin"                                      # under the home as $HOME/...: the same line serves a home
  case "$bin" in "$HOME"/*) shown="\$HOME/${bin#"$HOME"/}" ;; esac     # mounted elsewhere on another machine
  mark="# >>> explorer: $shown on the PATH >>>"
  [ -f "$1" ] && grep -qF "$mark" "$1" && return 0
  mkdir -p "$(dirname "$1")"
  {
    printf '\n%s\n' "$mark"
    case "$family" in
      posix) printf 'case ":$PATH:" in *":%s:"*) ;; *) export PATH="%s:$PATH" ;; esac\n' "$shown" "$shown" ;;
      csh) printf 'echo ":${PATH}:" | grep -q ":%s:" || setenv PATH "%s:${PATH}"\n' "$shown" "$shown" ;;
    esac
    printf '%s\n' "# <<< explorer <<<"
  } >> "$1"
  written="$1"
  echo "[setup_env] $1: $shown added to the PATH (the block between the explorer marks)"
}

link_command() {                                    # the command on the PATH: a link to run.sh, never a copy
  sh="${SHELL:-/bin/bash}"
  [ -x "$sh" ] || sh=/bin/bash
  kind="$(basename "$sh")"
  case "$kind" in
    bash|zsh|sh|dash|ksh) family=posix ;;
    tcsh|csh) family=csh ;;
    *) family=other ;;                              # fish and the rest: said what to add, nothing written (untested)
  esac
  bin="" written=""
  if [ "$family" != other ]; then
    lpath="$(new_path -lic)"
    ipath="$(new_path -ic)"
    # a folder a new terminal has; one this terminal has too first, so that the command works here at once
    for here_too in 1 0; do
      for d in ${XDG_BIN_HOME:+"$XDG_BIN_HOME"} "$HOME/.local/bin" "$HOME/bin"; do
        if on_path "$d" "$lpath" && on_path "$d" "$ipath" && { [ "$here_too" = 0 ] || on_path "$d" "$caller_path"; }
        then bin="$d"; break 2; fi
      done
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
    if [ "$family" = other ] || [ "$update_shell" = 0 ]; then
      echo "[setup_env] $bin is not on the PATH of a new terminal; add it in your shell's startup file:" >&2
      case "$kind" in
        fish) echo "  fish_add_path $bin      (in ~/.config/fish/config.fish)" >&2 ;;
        tcsh|csh) echo "  setenv PATH \"$bin:\${PATH}\"      (in ~/.tcshrc or ~/.cshrc)" >&2 ;;
        *) echo "  export PATH=\"$bin:\$PATH\"      (in your shell's startup file)" >&2 ;;
      esac
      return 1
    fi
    case "$kind" in
      zsh) add_block "$HOME/.zshrc" ;;
      bash)
        add_block "$HOME/.bashrc"
        # a login shell reads the first of these, and not always ~/.bashrc
        if ! on_path "$bin" "$(new_path -lic)"; then
          login="$HOME/.profile"
          for f in "$HOME/.bash_profile" "$HOME/.bash_login" "$HOME/.profile"; do
            [ -f "$f" ] && { login="$f"; break; }
          done
          add_block "$login"
          written="$HOME/.bashrc"                   # the one an open terminal reads again
        fi
        ;;
      tcsh|csh)                                     # tcsh reads ~/.tcshrc, else ~/.cshrc; csh ~/.cshrc
        rc="$HOME/.cshrc"
        [ "$kind" = tcsh ] && [ -f "$HOME/.tcshrc" ] && rc="$HOME/.tcshrc"
        add_block "$rc"
        ;;
      *) add_block "$HOME/.profile" ;;
    esac
  fi
  # the check: a new terminal, login or not, finds this link first, and it runs
  for how in -lic -ic; do
    found="$(first_on "$(new_path "$how")")"
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
  # this terminal: a program cannot change the PATH of the shell that started it, so say what it needs, if anything
  if on_path "$bin" "$caller_path"; then
    if [ "$family" = csh ]; then                    # csh keeps a table of the commands it found at start
      echo "[setup_env] in this terminal, run once:  rehash   (or open a new terminal)"
    else
      echo "[setup_env] ready in this terminal too: explorer"
    fi
  else
    case "$family" in
      posix) again=". ${written:-$HOME/.profile}"
             case "$kind" in bash) again="source ${written:-$HOME/.bashrc}" ;; zsh) again="source ${written:-$HOME/.zshrc}" ;; esac ;;
      csh) again="source ${written:-$HOME/.cshrc}" ;;
    esac
    case "$again" in "source $HOME"/*|". $HOME"/*) again="${again%% *} ~/${again#* "$HOME"/}" ;; esac
    echo "[setup_env] in this terminal, run once:  $again   (or open a new terminal)"
  fi
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

# a copy without .git (bellatrix's, synced by scripts/sync.py): the editable build of explorer writes vcs-versioning's
# fallback, 0.0.0, over the version sync.py wrote, and explorer --version and its update notice then said 0.0.0.
# Kept here and put back once installed, or on the way out if the install fails
version_file="$root/src/explorer/_version.py" kept_version=""
if [ ! -e "$root/.git" ] && [ -f "$version_file" ]; then
  kept_version="$(mktemp)"
  cp "$version_file" "$kept_version"
  trap 'cp "$kept_version" "$version_file"; rm -f "$kept_version"' EXIT
fi

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
if [ -n "${kept_version:-}" ]; then                 # before the checks below, which report the version
  cp "$kept_version" "$version_file"
  rm -f "$kept_version"
  trap - EXIT
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

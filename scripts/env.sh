# The environment the scripts run this tree's code with, sourced once $root is set (`. "$here/env.sh"`):
#   plat     this machine's OS and architecture, as the environments are named: .venv-<OS>-<arch>
#   venv     the environment: $EXPLORER_VENV, else this tree's .venv-$plat
#   qt_libs  drops an inherited LD_LIBRARY_PATH (another environment's Qt breaks PySide6) and, on Linux, puts this
#            tree's .qtlibs/only on it (libxcb-cursor for Qt's X11, see setup_env.sh); called where each script needs it
plat="$(uname -s)-$(uname -m)"
venv="${EXPLORER_VENV:-$root/.venv-$plat}"
qt_libs() {
  unset LD_LIBRARY_PATH
  if [ "$(uname -s)" = Linux ] && [ -d "$root/.qtlibs/only" ]; then export LD_LIBRARY_PATH="$root/.qtlibs/only"; fi
}

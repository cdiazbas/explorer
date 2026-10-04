#!/usr/bin/env bash
# Try explorer as it is right now, on a test cube, nothing to type; as the prototype's demo.sh. Any directory,
# macOS or Linux, locally or over ssh -Y:
#   scripts/demo.sh                    the test cube if this machine has it, else a small synthetic one
#   scripts/demo.sh <cube_im.fits>     that cube
#   scripts/demo.sh --synthetic        the synthetic cube even where the test cube exists
#   scripts/demo.sh ... --no-window    no window (headless)
# Over ssh -Y, a first word chooses how the window reaches the screen, to compare them on the same cube:
#   scripts/demo.sh native ...         Qt's own X11 (--x11 native; over ssh the default is the X11 bridge)
#   scripts/demo.sh prototype ...      the prototype's demo.sh (its test cube; --nosp becomes its --no-sp)
# The test cube is chosen by storage, not by OS: CRISP 6173 Stokes when the project's data/ link
# resolves (bellatrix, a Mac on StorNext); otherwise the synthetic cube, written once to ~/.cache/explorer/demo/
# (a Mac on its local disk: no big cubes there).
# The demo keeps a geometry trace (every move and resize of the window and its panels, the monitors seen, who asked:
# ui/geomtrace.py), named when the window closes; EXPLORER_GEOMETRY_TRACE=0 scripts/demo.sh ... goes without it.
export EXPLORER_GEOMETRY_TRACE="${EXPLORER_GEOMETRY_TRACE:-1}"
here="$(cd "$(dirname "$0")" && pwd)"
root="$(dirname "$here")"
cube="$root/../data/stokes_6173_im.fits"
if [ ! -e "$cube" ] && [ -L "$cube" ] && [ -e "/System/Volumes/Data$(readlink "$cube")" ]; then
  cube="/System/Volumes/Data$(readlink "$cube")"       # macOS: StorNext mounted under the data volume
fi
x11=()
case "${1:-}" in
  native) shift; x11=(--x11 native) ;;
  prototype) shift
    args=(); for a in "$@"; do [ "$a" = --nosp ] && a=--no-sp; args+=("$a"); done
    exec "$root/../prototype/demo.sh" ${args[@]+"${args[@]}"} ;;
esac
case "${1:-}" in
  --synthetic) shift; exec "$here/run.sh" demo ${x11[@]+"${x11[@]}"} "$@" ;;
  *.fits|*.icube|*.fcube) c="$1"; shift; exec "$here/run.sh" demo "$c" ${x11[@]+"${x11[@]}"} "$@" ;;
esac
if [ -e "$cube" ]; then
  exec "$here/run.sh" demo "$cube" ${x11[@]+"${x11[@]}"} "$@"
fi
echo "[demo] no shared test cube on this machine: using the synthetic one" >&2
exec "$here/run.sh" demo ${x11[@]+"${x11[@]}"} "$@"

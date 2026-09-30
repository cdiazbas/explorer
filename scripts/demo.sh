#!/usr/bin/env bash
# Try explorer as it is right now, on a test cube, nothing to type; as the prototype's demo.sh. Any directory,
# macOS or Linux, locally or over ssh -Y:
#   scripts/demo.sh                    the test cube if this machine has it, else a small synthetic one
#   scripts/demo.sh <cube_im.fits>     that cube
#   scripts/demo.sh --synthetic        the synthetic cube even where the test cube exists
#   scripts/demo.sh ... --no-window    no window (headless)
# Over ssh -Y, a first word chooses how the window reaches the screen, to compare them on the same cube:
#   scripts/demo.sh A ...              X11 bridge A (the prototype's, brought over as it is; --x11 bridge)
#   scripts/demo.sh B ...              X11 bridge B (the rewritten one; --x11 bridge2)
#   scripts/demo.sh native ...         Qt's own X11 (--x11 native)
#   scripts/demo.sh prototype ...      the prototype's demo.sh (its test cube; --nosp becomes its --no-sp)
# The test cube is chosen by storage, not by OS: CRISP 6173 Stokes (2025-07-11) when the project's data/ link
# resolves (bellatrix, a Mac on StorNext); otherwise the synthetic cube, written once to ~/.cache/explorer/demo/
# (a Mac on its local disk: no big cubes there).
here="$(cd "$(dirname "$0")" && pwd)"
root="$(dirname "$here")"
cube="$root/../data/stokes_6173_im.fits"
if [ ! -e "$cube" ] && [ -L "$cube" ] && [ -e "/System/Volumes/Data$(readlink "$cube")" ]; then
  cube="/System/Volumes/Data$(readlink "$cube")"       # macOS: StorNext mounted under the data volume
fi
x11=()
case "${1:-}" in
  A) shift; x11=(--x11 bridge) ;;
  B) shift; x11=(--x11 bridge2) ;;
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

#!/usr/bin/env bash
# Try explorer as it is right now, on a test cube, nothing to type; as the prototype's demo.sh. Any directory,
# macOS or Linux, locally or over ssh -Y:
#   scripts/demo.sh                    the test cube if this machine has it, else a small synthetic one
#   scripts/demo.sh <cube_im.fits>     that cube
#   scripts/demo.sh --synthetic        the synthetic cube even where the test cube exists
#   scripts/demo.sh ... --no-window    no window (headless)
# The test cube is chosen by storage, not by OS: CRISP 6173 Stokes (2025-07-11) when the project's data/ link
# resolves (bellatrix, a Mac on StorNext); otherwise the synthetic cube, written once to ~/.cache/explorer/demo/
# (a Mac on its local disk: no big cubes there).
here="$(cd "$(dirname "$0")" && pwd)"
root="$(dirname "$here")"
cube="$root/../data/stokes_6173_im.fits"
if [ ! -e "$cube" ] && [ -L "$cube" ] && [ -e "/System/Volumes/Data$(readlink "$cube")" ]; then
  cube="/System/Volumes/Data$(readlink "$cube")"       # macOS: StorNext mounted under the data volume
fi
case "${1:-}" in
  --synthetic) shift; exec "$here/run.sh" demo "$@" ;;
  *.fits|*.icube|*.fcube) c="$1"; shift; exec "$here/run.sh" demo "$c" "$@" ;;
esac
if [ -e "$cube" ]; then
  exec "$here/run.sh" demo "$cube" "$@"
fi
echo "[demo] no shared test cube on this machine: using the synthetic one" >&2
exec "$here/run.sh" demo "$@"

# explorer

Viewer for solar spectropolarimetric cubes [t, Stokes, λ, y, x], successor of CRISPEX.
Under construction: what is there and what is missing, in [docs/roadmap.md](docs/roadmap.md);
all the documentation, in [docs/](docs/README.md) (in Spanish).

## Install

Runs on macOS (Apple silicon and Intel) and Linux x86_64. No root needed. It needs `git`, and either
[uv](https://docs.astral.sh/uv/) or conda/mamba on the machine; with uv, the right Python (3.12) is fetched for you.

```bash
git clone https://github.com/cdiazbas/explorer.git
cd explorer
scripts/setup_env.sh --link
```

`setup_env.sh` builds this machine's environment next to the code (`.venv-<OS>-<arch>`), with the exact versions
the project pins, and checks it. It is safe to run again. `--link` also puts the `explorer` command on your PATH.
If a new terminal would not find it, the script adds one marked line to your shell's own startup file (bash, zsh,
sh, ksh, tcsh and csh are handled; for any other shell it prints the line to add). It then checks that a new
terminal finds the command and runs it.

A program cannot change the PATH of the terminal that started it, so the script ends by telling you what this
terminal needs: nothing ("ready in this terminal"), or the one command for your shell, which it prints. Or open a
new terminal. Then try it:

```bash
explorer --version
explorer demo                    # a synthetic cube, to see it working
explorer path/to/cube_im.fits    # a cube; its per-pixel file (_sp.fits) is found next to it
explorer doctor                  # if something does not work: the environment, numba, Qt and the display
```

`explorer --help` lists the options (theme, look, layout). Inside the window, `?` shows the keys.

**Reporting a problem:** run it again with `--log` (`explorer --log cube_im.fits`, or `explorer demo --log`). The
session then keeps traces of the window (every move and resize) and, over ssh, of what goes to the X server. When the
window closes, the terminal names the files (in `~/.cache/explorer/logs/`): send them with what you saw. Without
`--log` explorer still writes its general log there (`explorer.log`), which records any key that failed.

### Cubes it opens

- **SOLARNET FITS** (`_im.fits`), with its per-pixel file (`_sp.fits`) when it is next to it.
- **La Palma cubes** (`.icube`, `.fcube`), as SSTRED writes them. Their axes come from the per-pixel file
  (`_sp.icube`, `_sp.fcube`) or from the scans in the name (`stokes_8542=0-54_im.fcube`); the times, from the
  `_times+wvl.idlsave` beside it.
- **Maps** (`Blos.6173_map.fcube`, `Vlos.6173_map.icube`): their frames are named by nothing in the file. Opened on
  their own they read as a profile; `--axes t` says they are times:

  ```bash
  explorer Blos.6173_map.fcube --axes t
  ```

  `--axes` names the leading axes of any cube whose header or name does not, slowest first: `t,s,l`, `s,l`, `t,l`
  or `t` (`l` is λ).

### Linked cubes

More than one cube on the command line: the first leads, the others are linked to it.

```bash
explorer stokes_6173_im.icube Blos.6173_map.fcube Vlos.6173_map.icube
```

Each linked image is shown beside the first, the same size and the same region (zoom and pan are shared). The
spectrum and λ–t panels have a tab per cube. The cursor, its lock and t are everyone's; λ is each cube's own,
picked on its own spectrum or λ–t; Stokes is shared when the cubes have as many. For now a cube is linked only when it is on the same pixels and at the same times
as the first: a map with as many frames as the first cube has times takes them as its times (no `--axes` needed); a
map of one frame is shown at every t. Any other cube is left out, and the terminal says why (other pixels, other
times). `--sp` and `--axes` are the first cube's; `--nosp` applies to all.

### Notes

- **Shared storage:** one checkout can serve Linux and Macs at once (e.g. on a shared disk). Run `setup_env.sh`
  once on each kind of machine; each builds its own environment.
- **Remote, over ssh:** `ssh -Y host`, then `explorer cube_im.fits`. The window is drawn on your screen (on a
  Mac, through XQuartz); explorer picks the best way to draw over the link by itself.
- **Updating:** `git pull`. The next `explorer` updates the environment by itself if the pinned versions changed.
- **Without touching your startup files:** `scripts/setup_env.sh --link --no-update-shell` says what to add.
  Without `--link`, run explorer as `scripts/run.sh cube_im.fits` from the checkout.
- **Uninstalling:** delete the checkout, the `explorer` link that `setup_env.sh` reported (usually
  `~/.local/bin/explorer`), and the block between the `explorer` marks in your shell's startup file, if it added one.

## Development

```bash
scripts/setup_env.sh --dev     # also the test and lint tools; safe to repeat
scripts/install_hooks.sh       # once per clone: git hooks (hygiene and commit format)
scripts/demo.sh                # try what there is, on the test cube or a synthetic one
scripts/run.sh doctor          # check the environment, numba, Qt and the display
scripts/check.sh               # everything CI would run: hygiene, lint, layers, types, tests
python3 scripts/sync.py -n     # what would go to bellatrix (needs the ssh master connection open)
```

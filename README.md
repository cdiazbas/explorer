# explorer

Viewer for solar spectropolarimetric cubes [t, Stokes, λ, y, x], successor of CRISPEX.
Under construction: what is there and what is missing, in [docs/roadmap.md](docs/roadmap.md);
all the documentation, in [docs/](docs/README.md) (in Spanish).

## Install

Runs on macOS (Apple silicon and Intel) and Linux x86_64. No root needed. It needs `git`, and either
[uv](https://docs.astral.sh/uv/) or conda/mamba on the machine; with uv, the right Python is fetched for you. It
runs on Python 3.12 (the version it was measured with) and 3.13.

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
explorer update                  # when told there is something new: this copy brought up to date
```

`explorer --help` lists the options (theme, look, layout). Inside the window, `?` shows the keys.

**Without a clone, as an application** (for using it, not for developing it):

```bash
uv tool install git+https://github.com/cdiazbas/explorer.git
```

This puts the `explorer` command on your PATH in an environment of its own, with a Python it can run on (uv fetches
one if the machine has none). The repository is private for now, so this needs the same GitHub access as a clone.
Update it with `uv tool upgrade explorer`.

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
- **Inversions** (a file name with `inversion`, `meinv` or `inv` in it: `inversion_6173_im.icube`): their planes are
  parameters, never λ. They are picked as Stokes are (the toolbar for the first cube, over its image for a linked
  one), each its own image and colour scale, named "Quantity 1", "Quantity 2", … `--axes` still says otherwise.
- **Bifrost snapshots** (as helita writes them): z, x and y in Mm (the `z-coordinate` extension), `BUNIT = T` read
  as tesla, `lg(x)` shown as log₁₀(x). One snapshot's variables given together open as one cube, a variable each,
  picked as Stokes are (`explorer BIFROST_*_bx_385.fits BIFROST_*_bz_385.fits BIFROST_*_lgtg_385.fits`); each file
  is read a frame at a time.
- **A per-pixel file given as the cube** (`explorer stokes_6173_sp.fits`) is recognised (a FITS one by its header,
  whatever its name; an LP one by its image cube next to it, or by its name and dims) and its image cube next to it
  is opened with it; the terminal says so. Without its image cube nothing opens, and the terminal says which file
  is needed; among linked cubes, that one is left out. `--sp` naming a FITS image cube is refused (`explorer
  c_sp.fits --sp c_im.fits` is taken the right way round). A cube whose header gives other times or wavelengths
  than its frames hold is refused when opened.
- **A series of FITS images, one per file** (SDO/AIA, HMI: `--series`): the files are one cube whose t is the files,
  read where they are, without building a cube first. Plain and tile-compressed (JSOC's) files are both read. A
  compressed frame is decompressed at each read, one at a time (~0.12 s for AIA's 1986x1986, ~0.4 s for 4096x4096
  on bellatrix), so playback starts at the rate that allows (the terminal says it); a slit's time slice
  decompresses the rows it crosses in every file, and over hundreds of files takes minutes.

  ```bash
  explorer --series aia*.fits                # or "aia*.fits", quoted: the pattern is expanded by explorer
  ```

  t follows the header times (`T_OBS`, else `DATE-AVG`, else `DATE-OBS`: the first every file has), not the names;
  the terminal says when the two orders differ. Without a time in every file, t is the name order and an index.
  Files at the same time, or of another shape, stored type, scaling, `WAVELNTH`, `INSTRUME` or `BUNIT`, are refused,
  with the files of each group. Without `--series`, several files are linked cubes, as below.

### Noise levels in Q, U, V

The Q/I, U/I and V/I spectra show ±1σ of the noise, as CRISPEX does: the standard deviation of each over the whole
image at the continuum tuning, at the t shown, in % of I_c. Classic draws dashed lines, modern and glass a shaded
band. The continuum is the one the header gives; when it gives none (La Palma `.icube`), explorer takes the tuning
with the least signal in Q, U and V among 500 random profiles, and the status line says which.

### Linked cubes

More than one cube on the command line: the first leads, the others are linked to it.

```bash
explorer stokes_6173_im.icube Blos.6173_map.fcube Vlos.6173_map.icube
```

Each linked image is shown beside the first, the same size and the same region (zoom and pan are shared). The
spectrum and λ–t panels have a tab per cube. The cursor, its lock and t are everyone's; λ is each cube's own,
picked on its own spectrum or λ–t; Stokes is shared when the cubes have as many. For now a cube is linked only when it
is on the same pixels as the first. At each t of the first cube, a linked cube shows its scan nearest in time, as
CRISPEX does: another cadence, another start or two series joined (`=0-54_=0-28`) link, and the terminal says how
far the nearest scans are (when the first cube's t is outside the other's series, its first or last scan stays on
screen). A cube without times links only with as many frames as the first cube has times: a map takes them as its
times (no `--axes` needed); a map of one frame is shown at every t. Any other cube is left out, and the terminal says
why (other pixels; other times with nothing to match them by). `--sp` and `--axes` are the first cube's; `--nosp`
applies to all.

A La Palma cube derived from another of the same observation (`..._stokesI_..._im.icube`, Stokes I alone) has no
`_times+wvl.idlsave` of its own: its times and wavelengths are taken from the full-Stokes cube's
(`..._stokes_..._im_times+wvl.idlsave`) when their sizes are the cube's, and the terminal says so. Its values stay as
stored (counts): that file's scale and padding value are the other cube's.

### Updating

When you are told there is something new:

```bash
explorer update --check          # how far behind this copy is, and the changes it would bring; nothing changed
explorer update                  # this copy brought to the latest version, and which version that is
```

- **What it does:** it asks GitHub for the latest `main` (a `git fetch`: it only reads, with the same access you
  cloned with), lists what is new, and moves this copy forward to it. It never writes to GitHub.
- **Only when you ask:** it never runs by itself, at start or otherwise, so nothing changes in the middle of an
  analysis.
- **Told in the window:** a clone on `main` asks GitHub at most once a day, in the background, whether there is a
  newer `main` (`git ls-remote`: nothing fetched, nothing changed, no password asked; silent if it fails). A new
  version is said at once in a note over the image, with the date of the copy you run, and again every 7 days while
  you stay behind; the `?` sheet ends with the version you run and, while a newer one exists, `explorer update`.
  `explorer update --no-notice` stops the notes for you and this clone (`--notice` brings them back; `--check` says
  which); `EXPLORER_UPDATE_CHECK=0` or `=1` overrides that either way.
- **Restart:** an explorer already running keeps the old code; `explorer update` ends by saying so.
- **Your own work is safe:** a copy with changed files, commits of its own or on another branch is left as it is,
  and it says why. Nothing is merged, stashed or thrown away.
- **The environment:** if the update brings new pinned versions, the next `explorer` rebuilds the environment by
  itself, in the same mode (with or without `--dev`).
- **Installed with or without `--dev`:** the same; both run the code of your clone.
- **A copy without git** (synced or copied from another, e.g. a shared one): its keeper brings it up to date;
  `explorer update` says so and does nothing.
- **Installed without a clone:** `explorer update` says the command of the installer you used:
  `uv tool upgrade explorer`, `pipx upgrade explorer`, or `pip install --upgrade git+https://…`. Installed from a
  wheel file, neither uv nor pipx can follow it: install the newer wheel with `uv tool install --force <file>`.
- **Reporting a problem:** `explorer --version` names the exact commit you run.

### Notes

- **Shared storage:** one checkout can serve Linux and Macs at once (e.g. on a shared disk). Run `setup_env.sh`
  once on each kind of machine; each builds its own environment.
- **Remote, over ssh:** `ssh -Y host`, then `explorer cube_im.fits`. The window is drawn on your screen (on a
  Mac, through XQuartz); explorer picks the best way to draw over the link by itself.
- **Linux without libxcb-cursor** (RHEL 9, for one): Qt's own X11 needs that library. On a local X display
  explorer then draws the window through its own X11 bridge, and says so. For Qt's own X11, install
  `xcb-util-cursor` (RHEL 9: from EPEL; Debian, Ubuntu: `libxcb-cursor0`). Over `ssh -Y` the bridge is used anyway.
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

## License and citation

explorer is distributed under the BSD 3-Clause license ([LICENSE](LICENSE)). If you use it in your research, please
cite it ([CITATION.cff](CITATION.cff)) and CRISPEX, whose way of working it follows: Vissers & Rouppe van der Voort
(2012), ApJ 750, 22.

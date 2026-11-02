# explorer

Viewer for solar spectropolarimetric cubes [t, Stokes, λ, y, x], successor of CRISPEX. Under construction.

## Install

macOS (Apple silicon, Intel) or Linux x86_64; no root needed, only `git` and `curl` (or `wget`). It uses uv or conda
if the machine has one, and fetches uv itself otherwise. Python 3.12 or 3.13.

```bash
git clone https://github.com/cdiazbas/explorer.git
cd explorer
scripts/setup_env.sh --link      # the environment next to the code, and the explorer command on your PATH
```

It is safe to run again. It ends by saying whether this terminal is ready or what to run first (or open a new one).

```bash
explorer demo                    # a synthetic cube
explorer path/to/cube_im.fits    # a cube; its per-pixel file (_sp.fits) is found next to it
explorer doctor                  # when something does not work
```

`explorer --help` lists the options; inside the window, `?` shows the keys.

**As an application, without a clone:** `uv tool install git+https://github.com/cdiazbas/explorer.git` (the
repository is private for now: it needs the same access as a clone); update with `uv tool upgrade explorer`.

**Remote:** `ssh -Y host`, then `explorer cube_im.fits`; on a Mac the window comes through XQuartz.

**Shared disk:** one checkout serves Linux and Macs; run `setup_env.sh` once on each kind of machine.

**Linux without libxcb-cursor** (RHEL 9): explorer draws through its own X11 bridge and says so; for Qt's own, install
`xcb-util-cursor` (Debian, Ubuntu: `libxcb-cursor0`).

**Reporting a problem:** run it again with `--log`. When the window closes, the terminal names the trace files (in
`~/.cache/explorer/logs/`); send them with what you saw, and the output of `explorer --version`. The traces include
the keys typed.

**Uninstalling:** delete the checkout, the `explorer` link `setup_env.sh` reported, and the marked block it added to
your shell's startup file.

## Cubes it opens

- **SOLARNET FITS** (`_im.fits`), with its per-pixel file (`_sp.fits`).
- **La Palma cubes** (`.icube`, `.fcube`), as SSTRED writes them, with their `_sp` file or `_times+wvl.idlsave`.
- **Maps** (`Blos.6173_map.fcube`): nothing in the file names their frames; `--axes t` says they are times. `--axes`
  names the leading axes of any cube that does not say them, slowest first (`t,s,l`, `s,l`, `t,l`, `t`).
- **Inversions** (`inv`, `meinv` or `inversion` in the name): their planes are parameters, picked as Stokes are.
- **Bifrost snapshots**: several variables of one snapshot open as one cube, a variable each.
- **A series of FITS images, one per file** (SDO/AIA, HMI): `explorer --series aia*.fits`, ordered by the header
  times.

When a file cannot be opened as given, the terminal says why and what is missing.

**Noise:** the Q/I, U/I and V/I spectra show ±1σ, as CRISPEX does: the standard deviation over the image at the
continuum tuning, in % of I_c (without a continuum in the header, the quietest tuning, named in the status line).

## Linked cubes

```bash
explorer stokes_6173_im.icube Blos.6173_map.fcube Vlos.6173_map.icube
```

The first cube leads; the others are shown beside it, on the same pixels, with zoom, pan, cursor and t shared, and λ
each its own. At each t a linked cube shows its scan nearest in time, as CRISPEX does. A cube that cannot be linked is
left out, and the terminal says why.

## Updating

```bash
explorer update --check          # what is new; nothing changed
explorer update                  # this copy brought up to date (restart a running explorer)
```

It only runs when you ask. A note in the window says when there is a new version (`explorer update --no-notice`
stops it). A copy with changes of your own is left as it is.

## Development

```bash
scripts/setup_env.sh --dev     # also the test and lint tools
scripts/install_hooks.sh       # once per clone: hygiene and commit format
scripts/check.sh               # what CI runs: hygiene, lint, layers, types, tests
```

## License and citation

BSD 3-Clause ([LICENSE](LICENSE)). If you use it in your research, please cite it ([CITATION.cff](CITATION.cff)) and
CRISPEX: Vissers & Rouppe van der Voort (2012), ApJ 750, 22.

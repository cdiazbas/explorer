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

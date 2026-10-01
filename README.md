# explorer

Viewer for solar spectropolarimetric cubes [t, Stokes, λ, y, x], successor of CRISPEX.
Under construction: what is there and what is missing, in [docs/roadmap.md](docs/roadmap.md);
all the documentation, in [docs/](docs/README.md) (in Spanish).

```bash
scripts/setup_env.sh --dev     # this machine's environment (.venv-<OS>-<arch>); safe to repeat
scripts/demo.sh                # try what there is, on the test cube or a synthetic one
scripts/run.sh doctor          # check the environment, numba, Qt and the display
scripts/check.sh               # everything CI would run: hygiene, lint, layers, types, tests
scripts/install_hooks.sh       # once per clone: git hooks (hygiene and commit format)
python3 scripts/sync.py -n     # what would go to bellatrix (needs the ssh master connection open)
```

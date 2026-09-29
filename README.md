# explorer

Visor de cubos solares espectropolarimétricos [t, Stokes, λ, y, x], sucesor de CRISPEX.
En construcción: qué hay y qué falta, en [docs/roadmap.md](docs/roadmap.md); toda la
documentación, en [docs/](docs/README.md).

```bash
scripts/setup_env.sh --dev     # entorno de esta máquina (.venv-<OS>-<arch>); se puede repetir
scripts/demo.sh                # probar lo que haya, en el cubo de prueba o en uno sintético
scripts/run.sh doctor          # comprobar entorno, numba, Qt y pantalla
python3 scripts/sync.py -n     # qué se subiría a bellatrix (necesita la conexión maestra de ssh abierta)
```

# Traspaso

Dónde lo dejamos, para retomar en otra sesión o en otra máquina. Se reescribe al final de
cada sesión; no crece.

## 2026-09-28

- **Hecho:**
  - `explorer/` creado, con su propio git;
  - `PLAN.md` congelado;
  - `ROADMAP.md`, `docs/decisions/` (ADR 0001 y 0002), `docs/measured.md` y
    `docs/architecture.md` (vacío hasta que haya código).
- **Hechas E0.2, E0.3 y E0.9.** `explorer --version` y `explorer doctor` en el Mac y en bellatrix.
  - `scripts/sync.py` sube a `…/CRISPEX/explorer` en bellatrix; la configuración está en
    `scripts/sync.local.json`, que no se versiona.
  - `scripts/setup_env.sh` crea `.venv-<OS>-<arch>`: con uv en el Mac, con conda + pip en bellatrix.
  - 7 pruebas en verde en las dos máquinas.
- **Primeros commits** (`97b965b`, `3580a4a`, `11f9ce1`), con las etiquetas del
  [ADR 0005](docs/decisions/0005-commits.md). Sin remoto ni `push`.
- **`scripts/demo.sh`** (E0.10): prueba lo que haya en cualquier momento. En el Mac usa un cubo
  sintético; en bellatrix, el de Stokes 6173 (`74b50f0`, `651c05d`).
- **Regla nueva:** la aplicación, en inglés; los `.md`, en español ([ADR 0004](docs/decisions/0004-idioma.md)).
- **Siguiente:** E0.4 (`obs/`, midiendo su coste), E0.5 (CI), E0.6 (cubos sintéticos).
- **Del prototipo, fuera de explorer:**
  - `prototype/actualize.py` sigue apuntando a los `.md` de la raíz, que ahora están en
    `docs/`: no los sube, y `sync` termina antes del `pull`;
  - las teclas de Stokes del prototipo quedaron dentro del bloque del eje t
    (`app/viewer.py`, `_key_table`).

  Los dos son del prototipo y los decide el usuario.

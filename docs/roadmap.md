# Hoja de ruta

Índice de trabajo de explorer. Una fila por tarea: si no está aquí, no existe. Primero las
abiertas. El diseño de partida es [plan.md](plan.md) (congelado); cada tarea cita la
sección que la origina.

- **IDs permanentes:** `E<etapa>.<n>`, o `X.<n>` para lo que aún no tiene etapa; no se renumeran ni se reutilizan. El orden de la
  tabla sale del estado, no del ID.
- **Evidencia:** un commit, un fichero de resultados o una entrada del
  [journal.md](journal.md); nunca repetir lo que dice la tarea.
- **Estado "hecho":** verificado contra el código tal como está, no contra el commit que
  dijo hacerlo.

**Estados** (conjunto cerrado):

| | |
|:---:|---|
| ⬜ | pendiente |
| 🔄 | en curso |
| ⏸ | bloqueada (la columna "Bloquea" dice por qué) |
| ✅ | hecha y verificada |
| ⚪ | descartada (con el motivo en la tarea o en un ADR) |

## Tareas

| ID | Estado | Tarea | Bloquea | Fecha | Evidencia |
|---|:---:|---|---|---|---|
| E0.6 | 🔄 | `testing/synth.py`: cubos sintéticos pequeños con relleno NaN, Stokes, `_sp`, `icube` y cabecera SOLARNET (PLAN §7). **Hecho:** cubo `_im` (t, s, λ, y, x) big-endian con relleno NaN alrededor de un campo girado, determinista, escrito instante a instante; 3 pruebas. **Falta:** `_sp` transpuesto, `icube`, cabecera con las tablas WCS-TAB de los cubos reales | E0.2 | 2026-09-28 | `74b50f0` (el cubo `_im`) |
| E0.4 | ⬜ | `obs/`: `log.py`, `spans.py`, `trace.py`; **medir su coste** (el tramo no puede notarse frente al ruido del cursor) (PLAN §3.8) | E0.2 | 2026-09-28 | — |
| E0.5 | ⬜ | CI: higiene (auditoría versionada, rutas personales, menciones de asistentes y coautoría en el historial, con patrones compuestos), `ruff`, `pyright`, contratos de `import-linter` por capa (PLAN §8, §11) | E0.2 | 2026-09-28 | — |
| E0.7 | ⬜ | `tools/golden/export_prototype.py` + `tests/golden/cases.toml` + referencias del prototipo para los cubos sintéticos (PLAN §7.1, nivel 1) | E0.6 | 2026-09-28 | — |
| E0.8 | ⬜ | Línea base del prototipo: `selftest` ABBA en bellatrix (Xvfb y puente) y en el Mac (sintético), `--look modern`, con y sin `_sp` (PLAN §6) | — | 2026-09-28 | — |
| E0.11 | ⬜ | `sync.py -n` avisa de los ficheros que están en el remoto y ya no en la lista (movidos o borrados aquí), sin borrarlos. Visto el 2026-09-29: al mover las notas a `docs/` quedaron cinco copias viejas en bellatrix, borradas a mano tras comprobar que eran versiones del historial | — | 2026-09-29 | — |
| E3.1 | ⬜ | La orden `explorer` lanzada sin `scripts/run.sh` en Linux: relanzarse sin un `LD_LIBRARY_PATH` ajeno antes de cargar Qt (como `test.py` del prototipo). Visto el 2026-09-28: con el entorno conda de `.bashrc` en bellatrix, Qt no arranca (`Qt_6_PRIVATE_API`) | E3 | 2026-09-28 | `doctor` lo detecta y lo explica |
| X.1 | ⬜ | `explorer install-desktop` (orden explícita, no al instalar): en macOS un `explorer.app` pequeño en `~/Applications` que llama al entorno (Info.plist con los tipos FITS, `QFileOpenEvent` para abrir desde Finder o arrastrando al icono; arregla que el menú diga "python" y la falta de icono); en Linux un `.desktop` y el tipo MIME de FITS | E3 | 2026-09-28 | — |
| E1 | ⬜ | `explorer.data` (desglosar al empezar) (PLAN §3.2, §6) | E0 | 2026-09-28 | — |
| E2 | ⬜ | `explorer.core` + `testing.Driver` (PLAN §3.3, §6) | E1 | 2026-09-28 | — |
| E3 | ⬜ | `platform/plan.py`, `Display` (cocoa, xcb, offscreen), `Shell` mínima con la imagen (PLAN §3.5, §6) | E2 | 2026-09-28 | — |
| E4 | ⬜ | Espectros, λ–t, cursor, reproducción; niveles 2 y 3 de la comparación (PLAN §6, §7.1) | E3 | 2026-09-28 | — |
| E5 | ⬜ | Aspecto moderno como `Look`; `ActionRegistry`; disposición con esquema versionado (PLAN §3.6, §6) | E4 | 2026-09-28 | — |
| E6 | ⬜ | `ssh -Y`: xcb nativo, después el puente (PLAN §3.5, §6) | E5, P4 | 2026-09-28 | — |
| E7 | ⬜ | Rendija o camino → losa → paneles (PLAN §6) | E4, P5 | 2026-09-28 | — |
| E8 | ⬜ | Varias vistas enlazadas (PLAN §6; plan de ventanas enlazadas en `docs/` del proyecto) | E4, D1–D6 | 2026-09-28 | — |
| E0.1 | ✅ | Carpeta `explorer/` con su propio git (sin commits), `.gitignore`, ficheros de seguimiento; `PLAN.md` congelado (hoy `docs/plan.md`) | — | 2026-09-28 | `97b965b`; [ADR 0001](decisions/0001-repositorio-propio.md), [ADR 0002](decisions/0002-notas-del-prototipo.md) |
| E0.2 | ✅ | `pyproject.toml` (nombre `explorer`, [ADR 0003](decisions/0003-nombre-provisional.md); `APP_NAME` en `_name.py`) con Python 3.12, las versiones del prototipo (Mac Intel con marcadores), extra `gpu`, `[project.scripts] explorer`; `uv.lock` (PLAN §2, §8.1). **Cambio respecto al plan:** python-xlib va en la base y no en un extra, porque el puente es el camino por defecto en `ssh -Y`. **Hecho:** lock de 48 paquetes, con ruedas para Linux x86_64, Mac arm64 y Mac Intel en todos los compilados; instalación limpia en Mac arm64 con `explorer --version`; `import explorer.cli` en 6.2 ms sin cargar Qt ni numba. Linux (bellatrix, sin uv): pip desde el lock exportado, Python 3.12.14, 27 s; `explorer --version` y Qt `offscreen` funcionan; importación en 12.8 ms | — | 2026-09-28 | `3580a4a`; comprobado en Mac arm64 y en bellatrix, 2026-09-28 |
| E0.3 | ✅ | `cli.py` y `explorer doctor` (de `prototype/test.py`): Python y entorno aislado (venv o conda), versiones frente a las del lock, variables de pantalla y `LD_LIBRARY_PATH` ajeno, caché escribible, numba (serie, paralelo y capa de hilos), Qt **en un proceso hijo** (sobrevive a un Qt que aborta; comprueba `libxcb-cursor` antes), cubo (cabecera y 4 KB). Informe en `~/.cache/explorer/doctor/`. Importar `explorer.cli` no carga Qt ni numba (PLAN §8.1) | — | 2026-09-28 | 7 pruebas en `tests/unit/`, en verde en el Mac y en bellatrix; `11f9ce1`; `doctor` OK en 2.2 s (Mac) y 1.4 s (bellatrix) |
| E0.9 | ✅ | `scripts/sync.py` (como `actualize.py`: lista desde git, cerrojo `.editing_on_server`, `pull` solo de `bench/results/` sin pisar, nunca borra, exporta `uv.lock` a `requirements/lock*.txt` con hashes antes de cada `push`); `scripts/setup_env.sh` (uv, o conda + pip desde el lock; instalación editable; `libxcb-cursor` en `.qtlibs/`; `--dev`); `scripts/run.sh` (elige el entorno, lo reconstruye si cambió el lock, quita `LD_LIBRARY_PATH` ajeno) (PLAN §2, §8) | — | 2026-09-28 | bellatrix: `setup_env.sh --dev` por conda en 2 min 22 s; `3580a4a`; `sync.py push` y `run.sh doctor` OK |
| E0.10 | ✅ | `scripts/demo.sh` y `explorer demo`: probar en cualquier momento, en el Mac o en Linux, lo más completo que haya. Cubo elegido por almacenamiento, no por sistema: el de Stokes 6173 si el enlace `data/` del proyecto resuelve; si no, el sintético (una vez, en `~/.cache/explorer/demo/`). Hoy ejecuta `doctor` sobre el cubo con una ventana de 2 s; desde E3, el visor | — | 2026-09-28 | Mac: sintético, `doctor` OK en 4.5 s con ventana; bellatrix: cubo real (176 GB, con `_sp`), OK en 1.8 s sin pantalla; 12 pruebas en verde en los dos; `651c05d` |

## Decisiones pendientes

Cada una se convierte en un ADR en [docs/decisions/](decisions/) al decidirse, y
desaparece de esta tabla.

| # | Decisión | Opciones | Bloquea |
|---|---|---|---|
| P1-final | Nombre definitivo (provisional: `explorer`, [ADR 0003](decisions/0003-nombre-provisional.md)) | Comprobar en PyPI; renombrar con las reglas del ADR | publicar en PyPI |
| P4 | Puente X11 | Traerlo tal cual, partido en módulos · reescribirlo | E6 |
| P5 | Rendija | Variante A, C o D del prototipo | E7 |
| P6 | Superficies de imagen | Solo `pgr` al principio · también vispy/gfx locales | E3 |
| P7 | Aspecto clásico | En E5 junto al moderno · más adelante | E5 |
| P8 | Remoto (cliente–servidor) | Dentro del alcance como `Dataset` remoto · fuera | — |
| P9 | Licencia | — | primer commit público |
| D1–D6 | Las del plan de ventanas enlazadas | — | E8 |

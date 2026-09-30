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
- **Rendimiento:** ninguna medida de explorer puede ser peor que la línea base del prototipo en
  las mismas condiciones (en ABBA y dentro del ruido entre rondas), y la meta es mejorarla.
  Cada etapa que toque el visor se compara con [journal.md](journal.md), línea base del
  2026-09-29 (el usuario, 2026-09-29).

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
| E0.11 | ⬜ | `sync.py -n` avisa de los ficheros que están en el remoto y ya no en la lista (movidos o borrados aquí), sin borrarlos. Visto el 2026-09-29: al mover las notas a `docs/` quedaron cinco copias viejas en bellatrix, borradas a mano tras comprobar que eran versiones del historial | — | 2026-09-29 | — |
| E3.1 | ⬜ | La orden `explorer` lanzada sin `scripts/run.sh` en Linux: relanzarse sin un `LD_LIBRARY_PATH` ajeno antes de cargar Qt (como `test.py` del prototipo). Visto el 2026-09-28: con el entorno conda de `.bashrc` en bellatrix, Qt no arranca (`Qt_6_PRIVATE_API`) | E3 | 2026-09-28 | `doctor` lo detecta y lo explica |
| X.1 | ⬜ | `explorer install-desktop` (orden explícita, no al instalar): en macOS un `explorer.app` pequeño en `~/Applications` que llama al entorno (Info.plist con los tipos FITS, `QFileOpenEvent` para abrir desde Finder o arrastrando al icono; arregla que el menú diga "python" y la falta de icono); en Linux un `.desktop` y el tipo MIME de FITS | E3 | 2026-09-28 | — |
| E1 | ✅ | `explorer.data`: tareas E1.1–E1.14 (PLAN §3.2, §6). Criterio de salida de §6 cumplido el 2026-09-29 (E1.1–E1.11); mejoras E1.12 y E1.13 hechas. **Anotado:** los núcleos numba con `cache=True` guardan la caché en `~/.cache/explorer/numba` de cada usuario (`NUMBA_CACHE_DIR`), porque en una instalación compartida la carpeta del paquete puede no ser escribible y numba recompilaría en cada arranque (0.35–0.8 s por núcleo de prueba, [journal.md](journal.md) 2026-09-29) | E0 | 2026-09-28 | — |
| E1.6 | ✅ | Ejecutores: un solo hilo dueño de numba en paralelo, pool de E/S, franjas de CPU; `submit_latest` (la última petición gana) | — | 2026-09-29 | journal 09-29 |
| E1.7 | ✅ | Ejes físicos (de `physics.py`) y papeles de los ejes (de `viewer.axis_positions`); unidades de I y de Q, U, V (de `Viewer._set_spectra`). Prueba: `axes.*` y metadatos de ejes idénticos | E1.1 | 2026-09-29 | journal 09-29 |
| E1.8 | ✅ | Estadística y núcleos (de `viewer.py`): `limits`, `nice_range`, `_reduce_u8_serial` y su reparto en franjas, `_absmax_*`, `quv_amplitude_ranges`, muestreo de perfiles y rangos y (de `_start_sample`, `_sample_job`, `_sample_ready`). Prueba: `limits.*`, `reduce.*`, `meta.quv`, `meta.viewer.ysample`/`yquv` idénticos | E1.2–E1.4, E1.7 | 2026-09-29 | journal 09-29 |
| E1.9 | ✅ | Rendijas (de `viewer.py`): `slit_path`, `slit_pixels`, `read_slit_slab`, `read_slit_bands`. Prueba: `slit_*` idénticos (`slit_path` con tolerancia ~1e-12) | E1.2, E1.4 | 2026-09-29 | journal 09-29 |
| E1.10 | ✅ | Fachada `Dataset` (imagen, píxel y losa como `Future`, `close()`), sin Qt (contrato de capas). Rendimiento frente a la línea base en bellatrix, en ABBA: imagen, serie, bloque `_sp` | E1.1–E1.9 | 2026-09-29 | journal 09-29 |
| E1.11 | ✅ | Pruebas de comparación del nivel 1 (`tests/golden/test_data.py`): el caso sintético siempre; el real del 6173 en bellatrix (`-m golden_real`) | E1.1 | 2026-09-29 | journal 09-29 |
| E1.12 | ✅ | Hilos por petición en las lecturas dispersas: pocos para las pequeñas o probablemente en caché (espectro, movimientos de 1 px), muchos para un λ–t en frío. Un 64 fijo ganó 33 % con el almacenamiento cargado, 4 % con el almacenamiento rápido, y fue más lento en el espectro (27 frente a 20 ms) y en un λ–t en caché del sistema (33 frente a 24 ms). Medir a distintas horas | E1.10 | 2026-09-29 | journal 09-30 |
| E1.13 | ✅ | Vecinos gratis sin `_sp`: cada serie se lee con su fila entera (8 KB por imagen) y los píxeles de esa fila salen de memoria (`data/rowbands.py`). Primera lectura igual que el prototipo (1.009), el vecino 0.10 frente a 17.6 ms | E1.10 | 2026-09-29 | journal 09-29 |
| E1.14 | ✅ | Cubos sin cabecera de ejes: 4-D sin nombres = (t, λ, y, x); 3-D = eje desconocido (perfil en índices, sin llamarlo λ ni t); 5-D en orden SOLARNET; `--axes` para decir otra cosa (p. ej. `s,l`, o `t` para una serie temporal). `Roles.how` dice de dónde salió (a petición del usuario) | E1.7 | 2026-09-30 | journal 09-30 |
| E2 | 🔄 | `explorer.core` + `testing.Driver` (PLAN §3.3, §6; sin Qt, [ADR 0007](decisions/0007-core-sin-qt.md)): tareas E2.1–E2.7 | E1 | 2026-09-28 | — |
| E2.1 | ✅ | `ViewState` inmutable y `Store`: `set(**campos)`, un aviso por ráfaga con los campos que cambiaron; el momento de avisar se inyecta (de `Viewer._on_hover`, `_hover_timer`) | E1 | 2026-09-30 | journal 09-30 |
| E2.2 | ✅ | `Session` con un cubo: tiempo maestro; por cubo, su λ, su Stokes y si van enlazados (trivial con uno, preparado para E8) | E2.1 | 2026-09-30 | journal 09-30 |
| E2.3 | ✅ | `scheduler`: una cola por `Dataset` donde solo vale la última petición; espectro antes que λ–t; qué dispara cada cambio (t → espectros, Stokes → λ–t, λ → marcas; de `set_index`, `_update_cursor`); nada sobre el relleno ni para paneles ocultos; el paso al hilo principal se inyecta | E2.1 | 2026-09-30 | journal 09-30 |
| E2.4 | ⬜ | `levels`: límites de contraste por (Dataset, Stokes, idx), en caché, con modo fijo (de `Viewer._limits`, `_toggle_fix`) | E2.1 | 2026-09-30 | — |
| E2.5 | ⬜ | `yrange`: crece al mover, ajuste tras 0.4 s quieto; rangos fijos desde la muestra; Q U V bajo pedido (de `_set_spectra`, `_yfit`, `_sample_ready`, `_quv_ready`) | E2.3 | 2026-09-30 | — |
| E2.6 | ⬜ | `testing.Driver` sin pantalla: `hover`, `step`, `set_stokes`, `lock`, `state()`, `pump()`, `wait_idle()`; pruebas de generación, ráfagas y relleno | E2.3 | 2026-09-30 | — |
| E2.7 | ⬜ | Coste de las capas frente a la línea base (PLAN §10): cursor y paso en t, ABBA frente al prototipo | E2.6 | 2026-09-30 | — |
| E3 | ⬜ | `platform/plan.py`, `Display` (cocoa, xcb, offscreen), `Shell` mínima con la imagen (PLAN §3.5, §6) | E2 | 2026-09-28 | — |
| E4 | ⬜ | Espectros, λ–t, cursor, reproducción; niveles 2 y 3 de la comparación (PLAN §6, §7.1) | E3 | 2026-09-28 | — |
| E5 | ⬜ | Aspecto moderno como `Look`; `ActionRegistry`; disposición con esquema versionado (PLAN §3.6, §6) | E4 | 2026-09-28 | — |
| E6 | ⬜ | `ssh -Y`: xcb nativo, después el puente (PLAN §3.5, §6) | E5, P4 | 2026-09-28 | — |
| E6.1 | ⬜ | Foco automático de las ventanas que llegan por `ssh -Y`: la ventana de explorer abierta en el remoto toma el foco y el teclado en la máquina local al aparecer, sin que el usuario tenga que hacer clic (XQuartz en el Mac, X en Linux), con xcb nativo y con el puente; también al volver de otra aplicación; paridad xcb frente a puente. Pruebas con ventanas etiquetadas (configuración y hora) y comprobación a la vista del usuario, no solo por píxeles (PLAN §10, riesgo del puente) | E6 | 2026-09-30 | — |
| E7 | ⬜ | Rendija o camino → losa → paneles (PLAN §6) | E4, P5 | 2026-09-28 | — |
| E8 | ⬜ | Varias vistas enlazadas (PLAN §6; plan de ventanas enlazadas en `docs/` del proyecto) | E4, D1–D6 | 2026-09-28 | — |
| E0.1 | ✅ | Carpeta `explorer/` con su propio git (sin commits), `.gitignore`, ficheros de seguimiento; `PLAN.md` congelado (hoy `docs/plan.md`) | — | 2026-09-28 | `97b965b`; [ADR 0001](decisions/0001-repositorio-propio.md), [ADR 0002](decisions/0002-notas-del-prototipo.md) |
| E0.2 | ✅ | `pyproject.toml` (nombre `explorer`, [ADR 0003](decisions/0003-nombre-provisional.md); `APP_NAME` en `_name.py`) con Python 3.12, las versiones del prototipo (Mac Intel con marcadores), extra `gpu`, `[project.scripts] explorer`; `uv.lock` (PLAN §2, §8.1). **Cambio respecto al plan:** python-xlib va en la base y no en un extra, porque el puente es el camino por defecto en `ssh -Y`. **Hecho:** lock de 48 paquetes, con ruedas para Linux x86_64, Mac arm64 y Mac Intel en todos los compilados; instalación limpia en Mac arm64 con `explorer --version`; `import explorer.cli` en 6.2 ms sin cargar Qt ni numba. Linux (bellatrix, sin uv): pip desde el lock exportado, Python 3.12.14, 27 s; `explorer --version` y Qt `offscreen` funcionan; importación en 12.8 ms | — | 2026-09-28 | `3580a4a`; comprobado en Mac arm64 y en bellatrix, 2026-09-28 |
| E0.3 | ✅ | `cli.py` y `explorer doctor` (de `prototype/test.py`): Python y entorno aislado (venv o conda), versiones frente a las del lock, variables de pantalla y `LD_LIBRARY_PATH` ajeno, caché escribible, numba (serie, paralelo y capa de hilos), Qt **en un proceso hijo** (sobrevive a un Qt que aborta; comprueba `libxcb-cursor` antes), cubo (cabecera y 4 KB). Informe en `~/.cache/explorer/doctor/`. Importar `explorer.cli` no carga Qt ni numba (PLAN §8.1) | — | 2026-09-28 | 7 pruebas en `tests/unit/`, en verde en el Mac y en bellatrix; `11f9ce1`; `doctor` OK en 2.2 s (Mac) y 1.4 s (bellatrix) |
| E0.9 | ✅ | `scripts/sync.py` (como `actualize.py`: lista desde git, cerrojo `.editing_on_server`, `pull` solo de `bench/results/` sin pisar, nunca borra, exporta `uv.lock` a `requirements/lock*.txt` con hashes antes de cada `push`); `scripts/setup_env.sh` (uv, o conda + pip desde el lock; instalación editable; `libxcb-cursor` en `.qtlibs/`; `--dev`); `scripts/run.sh` (elige el entorno, lo reconstruye si cambió el lock, quita `LD_LIBRARY_PATH` ajeno) (PLAN §2, §8) | — | 2026-09-28 | bellatrix: `setup_env.sh --dev` por conda en 2 min 22 s; `3580a4a`; `sync.py push` y `run.sh doctor` OK |
| E0.10 | ✅ | `scripts/demo.sh` y `explorer demo`: probar en cualquier momento, en el Mac o en Linux, lo más completo que haya. Cubo elegido por almacenamiento, no por sistema: el de Stokes 6173 si el enlace `data/` del proyecto resuelve; si no, el sintético (una vez, en `~/.cache/explorer/demo/`). Hoy ejecuta `doctor` sobre el cubo con una ventana de 2 s; desde E3, el visor | — | 2026-09-28 | Mac: sintético, `doctor` OK en 4.5 s con ventana; bellatrix: cubo real (176 GB, con `_sp`), OK en 1.8 s sin pantalla; 12 pruebas en verde en los dos; `651c05d` |
| E0.4 | ✅ | `obs/`: `log.py` (un logger por capa, fichero rotado, `EXPLORER_LOG` por capa, con filtro por salida), `spans.py` (tramos, contadores, presupuestos con desglose de hijos, `summary()`), `trace.py` (`EXPLORER_TRACE`, Chrome/Perfetto); `doctor` abre un tramo por comprobación. **Coste:** 0.74 µs por tramo en el Mac y 1.38 µs en bellatrix; 20 tramos en el peor caso = 25 y 50 µs, dentro del presupuesto de 100 µs (PLAN §3.8) | — | 2026-09-29 | [journal.md](journal.md) 2026-09-29; 20 pruebas en verde en el Mac y en bellatrix; `9062dcc` |
| E0.5 | ✅ | Comprobaciones en local ([ADR 0006](decisions/0006-comprobaciones-locales.md)): `scripts/check.sh` (higiene del árbol y del historial, `ruff` con reglas explícitas, contratos de `import-linter`, `mypy`, pruebas sin pantalla) y ganchos `pre-commit`/`commit-msg` (`scripts/install_hooks.sh`). `mypy` en lugar de `pyright` (sin Node.js). Pruebas del propio guardián (`tests/unit/test_hygiene.py`) | — | 2026-09-29 | `check.sh` en verde en el Mac (~3 s) y en bellatrix (sin higiene: no hay `.git`); los ganchos rechazan una ruta personal y un asunto mal formado; `2444f50` |
| E0.8 | ✅ | Línea base del prototipo con el aspecto moderno: `bench/prototype_baseline.sh` (su `selftest` sin modificarlo; `offscreen`, `xcb` y puente sobre Xvfb; con y sin `_sp`; 2 rondas ABBA; md5 del código medido) y `bench/summarize_baseline.py` (PLAN §6) | — | 2026-09-29 | [journal.md](journal.md) 2026-09-29: bellatrix (cubo de Stokes 6173) y Mac (sintético); `a528015` |
| E0.6 | ✅ | `testing/synth.py` v2: `_im.fits` con cabecera SOLARNET como la del cubo 6173 (WCS-TAB `HPLN+HPLT+WAVE+TIME` (nt, nλ, 2, 2, 4), índices, `WAVEBAND`, `DATEREF`, continuo en `PRPARA`; apuntado que deriva con t), `_sp.fits` transpuesto (y, x, s, t, λ) y `_sp.icube` LP (int16 = round(1e11 × valor), como el `_sp.icube` real de Hα según la calibración del prototipo); `write_dataset()`. El demo usa el juego con su `_sp.fits` (PLAN §7) | — | 2026-09-29 | El prototipo lo abre con su propio código (ejes, `find_sp`, `SpFits` idéntico a `Cube.series`, `SpLP` calibra a 1e-11); [journal.md](journal.md) 2026-09-29; 5 pruebas; `eb532b3` |
| E0.7 | ✅ | Comparación frente al prototipo, nivel 1: `tests/golden/cases.toml` (caso sintético con entradas versionadas y caso real del 6173 en bellatrix), `tools/golden/export_prototype.py` (sus propias funciones, y una ventana real sin pantalla para los rangos y), `tools/golden/compare.py` (idéntico, dentro de tolerancia o distinto, por clave). Las comparaciones de explorer contra estas referencias llegan con cada capa (E1 en adelante) (PLAN §7.1) | — | 2026-09-29 | [journal.md](journal.md) 2026-09-29: mismas entradas → mismo resultado en el Mac y en bellatrix salvo 5 float64 en el último dígito; 11 pruebas nuevas; `acea67c` |
| E1.1 | ✅ | Formatos (`data/formats/`): cabecera FITS (desplazamiento de los datos con la API pública de astropy, `BITPIX`, `BSCALE`/`BZERO`/`BLANK`, nombres de ejes); cabecera LP de `icube`/`fcube` (de `bench_icube.lp_header` y `sources.SpLP`); detección por contenido; ficheros por píxel junto al cubo (de `sources.find_sp`). Prueba: forma, ejes y desplazamiento iguales a los del prototipo | — | 2026-09-29 | `data/formats/`; 6 pruebas unitarias; forma y ejes iguales al prototipo en el sintético (Mac y bellatrix) y en el cubo real del 6173 (bellatrix); `6532166` |
| E1.2 | ✅ | `FrameReader` (de `viewer/cube.py`): `preadv` en 4 trozos repartidos entre el hilo que llama y un pool, a float32 nativo; `_im.icube` con el orden de CRISPEX (λ, luego Stokes, luego t). Prueba: imágenes idénticas bit a bit a `frame.*` | E1.1 | 2026-09-29 | `data/io.py`; comprueba las lecturas cortas (el prototipo no); imágenes idénticas bit a bit en el sintético y en el cubo real; mismo tiempo que el prototipo dentro del ruido (37.3 frente a 37.6 ms sin leer; 6.22 frente a 6.31 ms en caché; [journal.md](journal.md)); `3cf03d6` |
| E1.3 | ✅ | `gather` y series por píxel (de `native_gather.py` y `Cube.series`): `pread` por símbolo para que numba lo guarde en caché; caché de numba en `~/.cache/explorer/numba`. Prueba: series idénticas a `series.*` | E1.1 | 2026-09-29 | `data/gather.py`, `data/_numba.py`, `FrameReader.series`; series idénticas bit a bit (sintético y real); mismo tiempo que el prototipo dentro del ruido (λ–t 615 frente a 648 ms sin leer; bloque 2 225 frente a 2 282 ms; [journal.md](journal.md)); `a47bc97` |
| E1.4 | ✅ | Ficheros por píxel (de `sources.py`): `_sp.fits`, `_sp.icube` con su calibración (ajuste lineal contra el FITS, ceros ignorados), lectura en tiras, caché de bloques. Prueba: `sp_fits.*` y `icube.*` idénticos; calibración con tolerancia relativa ~1e-12 (`np.polyfit` difiere entre máquinas). **Pendiente:** el orden de Stokes dentro de un `_sp.icube` con ns > 1 no está verificado con datos reales (`SpLP`: (s, t, λ); `bench_icube.py`: (t, s, λ)) | E1.1 | 2026-09-29 | `data/pixel.py`; bloques idénticos (sintético y real), calibración del `icube` dentro de 1e-12; la calibración salta el relleno y da error sin datos (el prototipo dejaba la escala en 1); no más lento que el prototipo (tira nueva 23.1 frente a 29.8 ms, mejora no establecida; [journal.md](journal.md)); `62611de` |
| E1.5 | ✅ | Política (de `policy.py` y `bench/membench/sysmem.py`): `StorageProbe` (tira, lectura anticipada, hilos por tipo de almacenamiento), `MemoryGuard` (fracciones y topes por sistema, recorte por swap en macOS, cgroup en Linux), instantáneas con ctypes en macOS. Cachés que declaran su memoria. Prueba: decisiones con instantáneas simuladas | — | 2026-09-29 | `data/sysmem.py`, `data/policy.py` (sonda, guardián, `plan_budgets`), `data/cache.py` (LRU de imágenes con lectura anticipada); 10 pruebas con instantáneas simuladas; mismas decisiones y presupuesto que el prototipo con el cubo real en bellatrix ([journal.md](journal.md)); `b55f8f0` |

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

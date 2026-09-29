# explorer: plan del repositorio y de la aplicación

> **Congelado el 2026-09-28.** Es el diseño inicial y no se vuelve a editar. Lo vigente
> está en [roadmap.md](roadmap.md) (trabajo), [docs/decisions/](decisions/)
> (decisiones), [docs/architecture.md](architecture.md) (el código tal como es) y
> [docs/measured.md](measured.md) (decisiones medidas).

`explorer` es la versión sólida del prototipo (`../prototype/`): un visor de cubos solares
N-D [t, Stokes, λ, y, x] de 2k–4k px y 20–180 GB, sucesor de CRISPEX. Parte del prototipo
con el aspecto `--modern`; el clásico se decidirá después y entraría como un aspecto más
(§3.6).

Este fichero es el plan: esqueleto del repositorio, arquitectura, qué se trae del
prototipo y en qué orden se construye. No hay código todavía. Lo que aquí se afirma del
prototipo sale de leer su código y sus notas el 2026-09-28. Las cifras son las del diario
de medidas (`OVERVIEW.md`, citado por fase o fecha) y no se han vuelto a medir para este
plan. Lo que es diseño sin probar va marcado **[propuesta]**.

## 0. Qué cambia respecto al prototipo, y por qué

El prototipo sirvió para medir. Tiene casi todas las respuestas, pero su forma ya frena:

- **`app/viewer.py` tiene 2663 líneas**, y una sola clase (`Viewer`, un `QMainWindow`)
  hace de todo:
  - navegación, E/S y planificación en hilos (4 ejecutores);
  - estadística (muestreo de perfiles, rangos de Q, U y V, núcleos numba);
  - memoria, docks, barra de herramientas, teclado, gestos y tres variantes de rendija;
  - persistencia, monitores y tema.
- **El aspecto moderno se aplica parcheando la instancia:** `look.py` sustituye 5 métodos
  de `Viewer` (`show_frame`, `_set_lt`, `_paint_slice`, `set_locked`, `set_index`), uno del
  backend (`set_crosshair`) y una función de `startup`. Funciona porque las señales se
  conectan con lambdas; una llamada que deje de pasar por esos métodos quita el color sin
  dar error.
- **Las pruebas dependen de nombres internos:** `smoke.py` usa 79 atributos distintos de
  `Viewer`, `conformance.py` 48 y `selftest.py` 22, además de interioridades del puente
  X11. Cambiar un nombre rompe las pruebas.
- **El estado está duplicado:** índices, deslizadores, combo y control segmentado de
  Stokes, y la casilla invisible `fix`, se sincronizan con `blockSignals`.
- **Parte de la E/S corre en el hilo de la interfaz:** `Cube.image` y `sp.block`. Un fallo
  de caché en StorNext cuesta 13–15 ms (Fase 13) y bloquea la interfaz ese tiempo.
- **Defectos vistos al leer, sin reproducir:**
  - `Cube.from_fits` no aplica `BSCALE`/`BZERO`/`BLANK`;
  - `closeEvent` no cierra los pools ni el `Cube`;
  - el presupuesto de memoria no cubre las cachés de la rendija ni los lotes de Q, U y V;
  - el atajo de Stokes (teclas 1–n) quedó dentro del bloque del eje t y sin su condición.

**explorer conserva cada decisión medida y cambia la forma:**
- datos sin Qt;
- un solo estado;
- vistas que declaran de qué dependen;
- aspecto como datos, no como parches;
- plataforma detrás de una interfaz;
- pruebas contra una API pública.

## 1. Principios

1. **Las decisiones medidas son contratos.** Cada una lleva en el código su cifra y dónde
   se midió, como hoy (lista en §4). Cambiarla exige medir otra vez con el mismo método.
2. **Linux primero, también por `ssh -Y`.** El Mac es un extra; tras un cambio pensado para
   el Mac se vuelve a verificar Linux.
3. **`explorer.data` no importa Qt.** Es la prueba de aceptación de esa capa: se importa y se
   prueba sin PySide6.
4. **Un solo estado.** Solo el almacén de estado (`Store`) lo cambia. Las vistas no se
   escriben entre sí: declaran de qué dependen (cursor, t, λ, s…) y el almacén les dice qué
   cambió. La matriz de repintado que hoy vive en `_update_cursor` pasa a ser declarativa.
5. **Todo trabajo en segundo plano lleva número de generación.**
   - Lo obsoleto se descarta antes de leerlo, y un resultado solo se tira si ya hay uno más
     nuevo en pantalla (medido: de 1–11 a 108–131 espectros mostrados).
   - Es la clase de fallo que más se repitió en el prototipo: ecos atrasados y resultados
     viejos aplicados como actuales.
6. **Numba en paralelo, en un solo sitio.** Un ejecutor dueño de todo `parallel=True`,
   porque la capa `workqueue` aborta con dos regiones a la vez (macOS y Linux). Lo demás,
   núcleos en serie `nogil` repartidos en franjas.
7. **Una función por decisión.** La elección de pantalla, de backend, de hilos y de
   presupuesto de memoria sale de funciones puras con tabla de casos, probadas sin pantalla.
   Nada de `if darwin` ni `if bridge` en las vistas.
8. **El aspecto cambia la apariencia, no el comportamiento.** Tema, mapas de color,
   políticas de niveles y superposiciones se inyectan; nunca se parchea.
9. **Fallar pronto y con mensaje propio**, antes de crear Qt si hace falta.
   - El entorno explícito manda: un `QT_QPA_PLATFORM` pedido no se pisa.
   - Al arrancar se imprime la configuración efectiva: pantalla, backend, hilos, memoria y
     sonda.
10. **La persistencia guarda sitio y tamaño, nunca la ausencia.**
    - El esquema lleva versión; uno desconocido se descarta.
    - El reset fija tamaños explícitos.
11. **Las pruebas usan una API pública** (`explorer.testing.Driver`), no atributos
    privados.
12. **Se mide lo que ve el usuario.**
    - Las ventanas de prueba llevan configuración y hora en el título.
    - Lo que cambia cómo llegan los píxeles a la pantalla se da por bueno solo con los ojos
      del usuario en XQuartz o en el Mac.

## 2. Esqueleto del repositorio [propuesta]

```
explorer/
├── PLAN.md                  este fichero (se retira cuando el README y docs/ lo cubran)
├── README.md                qué es, instalar, arrancar
├── pyproject.toml           Python 3.12; dependencias; extras; entradas de consola
├── uv.lock                  versiones exactas con hashes (Mac Intel incluido, con marcadores)
├── scripts/
│   ├── setup_env.sh         uv o, si no hay, mamba/conda (como el prototipo); .venv-<OS>-<arch>
│   ├── run.sh               elige el entorno que corre aquí; quita LD_LIBRARY_PATH ajeno
│   ├── demo.sh              cubo de prueba sin escribir nada
│   └── sync.py              sustituto de actualize.py: lista de subida desde git ls-files
├── src/explorer/
│   ├── __main__.py          python -m explorer (llama a cli.main)
│   ├── cli.py               la orden `explorer`: `explorer cubo.fits`, `explorer doctor`… (§8.1)
│   ├── app.py               arranque: DisplayPlan → Qt → Session → Shell (§3.1)
│   ├── config.py            opciones de línea de órdenes y entorno, en un solo objeto tipado
│   ├── obs/                 observabilidad, SIN Qt; la usan todas las capas (§3.8)
│   │   ├── log.py           logging de la biblioteca estándar: un logger por capa, fichero rotado
│   │   ├── spans.py         span("image.read"): tiempos en anillo, contadores, avisos por presupuesto
│   │   ├── trace.py         --trace salida.json en formato Chrome/Perfetto (hilos en una línea de tiempo)
│   │   └── watchdog.py      bucle de eventos parado; volcado de pilas (lo que hoy hace flightrec)
│   ├── data/                SIN Qt (§3.2)
│   │   ├── formats/         fits.py, lp.py (icube/fcube), raw.py, detect.py
│   │   ├── io.py            FrameReader, PixelReader: los únicos que ven fd y offsets
│   │   ├── gather.py        núcleo numba de lecturas dispersas (native_gather)
│   │   ├── cache.py         FrameCache, BlockCache, SliceCache; interfaz Budgeted
│   │   ├── policy.py        StorageProbe, MemoryGuard
│   │   ├── sysmem.py        memoria del sistema (ctypes en macOS; /proc, cgroup, PSI en Linux)
│   │   ├── executors.py     dueño de numba paralelo, pool de E/S, franjas de CPU; submit_latest
│   │   ├── axes.py          ejes físicos SOLARNET (WCS-TAB, WAVEBAND, PRPARA, DATEREF)
│   │   ├── stats.py         límites, muestreo de perfiles, rangos Q U V
│   │   ├── kernels.py       reduce_u8, absmax (serie, nogil)
│   │   └── dataset.py       fachada: Dataset.open(...) → image(), pixel(), slab(), axes
│   ├── core/                estado y servicios, con Qt solo en señales (QObject)
│   │   ├── state.py         ViewState (inmutable) y Store (set, changed)
│   │   ├── session.py       varios Dataset, tiempo maestro, enlaces λ/Stokes
│   │   ├── coords.py        píxel ↔ ″ ↔ píxel de otro cubo; hora → índice
│   │   ├── scheduler.py     peticiones por Dataset, la última gana, prioridad al principal
│   │   ├── levels.py        LevelsPolicy (por Dataset y Stokes; simétrica en Q U V)
│   │   ├── yrange.py        YRangePolicy (crece al mover; se ajusta en reposo; muestra; fijo)
│   │   └── paths.py         rendijas y caminos (vértices en píxel y ″, muestreo, JSON)
│   ├── ui/
│   │   ├── shell.py         QMainWindow, docks por registro, barra, estado, "?"
│   │   ├── panels.py        PanelRegistry: qué paneles existen y cómo se crean
│   │   ├── views/           image.py, spectrum.py, lambda_t.py, slit.py; protocolo View
│   │   ├── surfaces/        pgr.py (por defecto), vispy.py, gfx.py; protocolo ImageSurface
│   │   ├── overlays/        reticle.py, colour_key.py, lock.py, slit_hint.py
│   │   ├── input.py         ActionRegistry (teclas, hoja "?", menú, paleta), GestureMap
│   │   ├── widgets/         JumpSlider, StokesSegments, axes (Signed, Velocity, Tuning, Index)
│   │   └── layout.py        LayoutStore (QSettings, esquema con versión, por tipo de pantalla)
│   ├── look/
│   │   ├── theme.py         Theme: tokens (acento, bloqueado, tarjeta, tinta, relleno, rejilla)
│   │   ├── colormaps.py     ColormapRegistry (LUT con entrada de relleno; ciclo por clase de Stokes)
│   │   ├── modern.py        el aspecto de partida
│   │   └── style.py, icons.py
│   ├── platform/            lo único que sabe de cocoa, xcb, Wayland o del puente (§3.5)
│   │   ├── plan.py          choose_display(env, platform, args) -> DisplayPlan (pura)
│   │   ├── display.py       protocolo Display y WindowOps
│   │   ├── cocoa.py, xcb.py, offscreen.py
│   │   ├── x11bridge/       transport.py, wm.py, qtinput.py, clipboard.py, render.py
│   │   ├── titlebar.py      barra propia y bordes
│   │   ├── linkprobe.py
│   │   └── flightrec.py     últimos eventos de entrada; usa obs/watchdog.py
│   └── testing/
│       ├── driver.py        Driver: hover, step, set_stokes, play, lock, state(), wait_idle()
│       └── synth.py         cubos sintéticos pequeños con relleno NaN y cabecera SOLARNET
├── tests/
│   ├── unit/                data, core, obs, platform/plan: sin pantalla, en segundos
│   ├── golden/              explorer frente al prototipo: mismos resultados (§7.1)
│   │   ├── cases.toml       entradas fijas: cubo, índices, píxeles, caminos, semillas
│   │   └── data/            referencias pequeñas (cubos sintéticos) versionadas; las grandes, fuera
│   ├── gui/                 offscreen, xcb y bridge (marcadores de pytest)
│   ├── parity/              xcb frente al puente (lista de diferencias aceptadas, versionada)
│   └── conftest.py          fixture de Xvfb con XTEST; cubos sintéticos
├── tools/
│   └── golden/              export_prototype.py: ejecuta el prototipo (solo lectura) y guarda sus
│                            resultados para las mismas entradas; compare.py: informe de diferencias
├── bench/                   medidas, fuera de la puerta de CI: selftest, E/S, puente; ABBA
├── docs/                    arquitectura, decisiones medidas (§4), guía de desarrollo
└── ci/                      trabajos de higiene (§8)
```

**Nombre del paquete.** No he comprobado si `explorer` está libre en PyPI; conviene que el
nombre de distribución sea más específico (decisión P1 en §9), aunque se importe como
`explorer`.

**Orden de consola:** una sola, `explorer`, con subórdenes (§8.1).

**Extras:**
- `x11bridge`: python-xlib.
- `gpu`: vispy, pygfx y wgpu.

## 3. Arquitectura de la aplicación

### 3.1 Capas y sentido de las dependencias

```
platform  ──►  (nadie importa platform salvo app.py y ui/shell.py a través de Display/WindowOps)
data  ◄──  core  ◄──  ui  ◄──  app.py  ◄──  cli.py
                      ▲
                     look  (datos y fábricas que ui recibe; no importa ui)
obs   ◄──  todas      (registro y tiempos; no importa nada del proyecto)
```

- `obs` está debajo de todo: no importa nada del proyecto ni Qt, y todas las capas lo usan.
- `data` no conoce Qt.
- `core` usa Qt solo para señales.
- `ui` no abre ficheros ni lanza hilos: pide a `core`.
- `look` no parchea: `ui` le pregunta.
- Una prueba de importación en CI lo comprueba: se importa cada paquete sin los de más
  arriba.

### 3.2 Datos (`explorer.data`)

Interfaz [propuesta]:

```python
# formats: detección por contenido ("SIMPLE", cabecera LP), no por extensión
open_image_cube(path) -> Layout        # FITS HDU primaria, _im.icube/.fcube, raw; aplica BSCALE/BZERO/BLANK
open_pixel_cube(path, like) -> Layout  # _sp.fits, _sp.icube, _sp.fcube
find_companions(path) -> Companions    # _sp junto al _im, wb_*, tiempos

class FrameReader:                     # preadv en paralelo en 4 trozos (Fase 2: 24.4 → 4.7 ms en frío)
    def read(self, idx, out=None) -> np.ndarray          # float32 nativo; nunca memmap
    def read_rows(self, idx, y0, y1) -> np.ndarray
class PixelReader:
    def series(self, y, x, idx, free_axes) -> np.ndarray # gather numba nogil (Fase 5)
    def strip(self, y, x0, k) -> np.ndarray              # _sp: tira de k px = 1 petición (Fase 13)
    def runs(self, pixels) -> dict                       # rendija: una lectura por tramo de fila

class Dataset:                         # lo único que ve el resto de la app
    @classmethod
    def open(cls, path, sp=None, *, policy=None) -> "Dataset"
    axes: Axes; roles: Roles           # t, s, λ; nt, ns, nl; ny, nx
    def image(self, idx) -> Future[np.ndarray]
    def pixel(self, y, x) -> Future[Block]               # (s, t, λ) de un píxel, una lectura con _sp
    def slab(self, path: Path2D) -> Future[Slab]         # [npath, s, t, λ]
    def close(self) -> None                              # cierra fd y pools (hoy no se hace)
```

- **`executors.py`** concentra los hilos:
  - el dueño de numba en paralelo: un hilo, por el que pasan `series`, el muestreo y la
    rendija;
  - el pool de E/S (`preadv`), dimensionado por la sonda y no por el sistema operativo
    (λ–t en StorNext con 4 frente a 64 hilos: 1255 → 146 ms);
  - las franjas de CPU para `reduce_u8` y `absmax`.

  `submit_latest(key, fn)` implementa "la última gana".
- **Cachés que dan cuenta de su memoria** (`Budgeted.nbytes/trim`):
  - `MemoryGuard` las registra con su parte del presupuesto, incluidas las que hoy se le
    escapan (bloque de rendija, lotes de Q, U y V).
  - Mac: 15 % de lo libre, hasta 2 GB; se reduce con cada +256 MB de swap. Linux: 25 %,
    hasta 8 GB, dentro del cgroup.
- **Ejes (`axes.py`)**, a partir de `physics.py`:
  - WCS-TAB, `WAVEBAND` → λc de laboratorio, continuo por `PRPARA`, tiempos por `DATEREF`
    más la tabla, y HPLN/HPLT por t.
  - Hueco para `WCSDVARR` (hasta 12.2 pm en 6173, ~6 km/s), sin aplicar todavía.
  - Las unidades de I (potencia de diez) y de Q, U y V (% de I_c), que hoy se calculan en
    la interfaz, pasan aquí.
- **Remoto** [propuesta, más adelante]: un `Dataset` que habla con el servidor del
  prototipo (una línea JSON por petición). La app no ve la diferencia.

### 3.3 Estado y servicios (`explorer.core`)

```python
@dataclass(frozen=True)
class ViewState:
    t: int; s: int; l: int                 # del Dataset principal
    cursor: tuple[int, int]; locked: bool
    path: Path2D | None; playing: bool
class Store(QObject):
    changed = Signal(object, frozenset)    # (estado, campos que cambiaron)
    def set(self, **fields) -> None        # agrupa ráfagas: un aviso por pasada del bucle (QTimer 0)
```

- **`Session`** contiene uno o más `Dataset` y el tiempo maestro. Para cada cubo guarda su
  λ, su Stokes y si van enlazados. Con un solo cubo es trivial; está desde el principio
  para que las vistas enlazadas (del plan de ventanas enlazadas, en el `docs/` del
  proyecto) no obliguen a reorganizar.
- **`coords.py`**:
  - identidad si la rejilla es la misma; si no, píxel → ″ con el apuntado de cada t, y de
    ahí al píxel del otro cubo, redondeando (CRISPEX trunca);
  - hora UTC → índice más cercano, con su Δt;
  - bajo demanda (hipótesis: < 0.1 ms por punto).
- **`scheduler.py`**:
  - una cola por `Dataset` en la que solo vale la última petición; primero el principal;
  - el espectro antes que el λ–t (medido: Mac 18–23 → 3–5 ms, StorNext ~165 → ~40 ms);
  - nada se lee sobre el relleno ni para paneles ocultos.
- **`levels.py`**: límites p1/p99 sobre la submuestra `[::8, ::8]` (Fase 3: 55 → 1 ms),
  simétricos para Q, U y V, guardados por (Dataset, Stokes, idx) y con modo fijo. Una sola
  implementación: hoy hay 6 copias.
- **`yrange.py`**:
  - al mover el cursor el rango solo crece, a valores 1-2-5, y se ajusta tras 0.4 s quieto
    (57 → 26 ms por movimiento);
  - rango fijo desde 100 perfiles al azar con semilla fija (con `_sp`, 0.04–0.05 s);
  - Q, U y V desde imágenes enteras, solo cuando se piden (al arrancar subía el cursor de
    14.8 a 18.5–19.3 ms).
- **`paths.py`**: la rendija es un camino de dos puntos; losa [npath, s, t, λ]; JSON.

### 3.4 Interfaz (`explorer.ui`)

```python
class View(Protocol):
    id: str
    depends: frozenset[str]                # {"cursor", "t", "s", "l", "path", "levels"}
    widget: QWidget
    def update(self, st: ViewState, changed: frozenset) -> None
    def apply_look(self, look: "Look") -> None

class ImageSurface(Protocol):              # backend de la imagen
    widget: QWidget
    def set_image(self, img, levels, lut) -> None
    def map_to_data(self, pos) -> tuple[float, float]
    def add_overlay(self, item: "Overlay") -> None
    viewbox: "ViewBox | None"              # None: sin zoom guiado ni superposiciones (vispy/gfx hoy)

class Overlay(Protocol):
    def attach(self, view: View) -> None
    def update(self, st: ViewState, changed: frozenset) -> None

@dataclass
class Action:
    id: str; text: str; keys: tuple[str, ...]; run: Callable; when: Callable[[], bool] = always
class ActionRegistry:                      # teclas, hoja "?", menú, tooltips y, más adelante, Ctrl+K
    def register(self, a: Action) -> None

class PanelSpec(Protocol):                 # registro interno, no plugins públicos
    id: str; title: str; area: Qt.DockWidgetArea
    def create(self, ctx: "Context") -> View
```

- **`pgr` es la superficie por defecto.** Es la más rápida en el visor completo y la única
  que llega por `ssh -Y`: reduce a los píxeles físicos de la vista y a u8 en una pasada
  (Fase 12: paso en t 23.9 → 15.5 ms; por `ssh -Y`, pintado 42 → 4.4–4.9 ms). El nivel 0 se
  reserva para NaN.
- **vispy y gfx** quedan como superficies locales opcionales; sobre X11 se fuerza `pgr`.
- **Paneles de partida:** imagen, espectros (2×2 con I Q U V), λ–t y rendija.
- **Llegan por el registro:** referencia, Doppler, curva de luz y camino → diagrama
  espacio–tiempo.
- **Rendimiento heredado que se mantiene:**
  - ejes en caché de pixmap (7.4–8.5 → 3.3–3.5 ms por movimiento);
  - `useNumba=False` en pyqtgraph para el λ–t (22.4 → 0.17 ms);
  - `ResizeFreezer`;
  - docks sin animación (27–31 → 4.8 MB por el puente al arrastrar un panel).

### 3.5 Plataforma (`explorer.platform`)

- **`choose_display(env, sys.platform, args) -> DisplayPlan`**: función pura con la tabla de
  casos del prototipo.
  - Linux sin pantalla: sale con mensaje.
  - `QT_QPA_PLATFORM` explícito: se respeta.
  - `--x11` explícito: gana.
  - Linux local: xcb.
  - Linux por `ssh -Y`: puente.
  - Mac local: cocoa.
  - Mac por `ssh -Y`: puente.
  - Mac por ssh sin pantalla: sale con mensaje.

  Se prueba sin Qt.
- **`Display`**: `prepare_env()` antes de Qt, `attach(app, window)`,
  `window_ops(w) -> WindowOps` (mover, redimensionar, minimizar, zoom, activar, forma,
  cursor), `link() -> LinkInfo` (bytes por píxel y tope de fps medidos, no constantes),
  `stats()` y `close()`.
  - La interfaz solo ve `WindowOps`.
  - Desaparecen los atributos `_crispex_*` colgados de los widgets y las ramas por sistema
    en las vistas.
- **El puente X11 se trae partido en módulos, detrás de `Display`:**
  - `transport` (teselas, gris 1 B/px con RENDER, doble búfer, codificador numba);
  - `wm` (ICCCM/EWMH, paneles, transitorios, formas);
  - `qtinput` (ctypes a la puerta de plataforma de Qt, con comprobación de símbolos al
    arrancar);
  - `clipboard`.

  Sus cifras (Fase F2, 2026-09-25, bellatrix → XQuartz del usuario): ~12 imágenes/s frente
  a ~8.5 del X11 nativo, con menos de la mitad de bytes.
- **Límites del puente que hay que conocer:**
  - usa símbolos privados de Qt, así que ata PySide6 a una versión exacta;
  - dpr = 1;
  - sin arrastrar y soltar ni IME;
  - portapapeles sin INCR.

  Si merece reescribirse o traerse tal cual es la decisión P4.

### 3.6 Aspecto (`explorer.look`)

```python
@dataclass
class Theme:
    accent; locked; card; ink; padding_colour; grid_alpha; cursor_pen; corner_px; gutter_px
class ColormapRegistry:
    def lut(self, name) -> np.ndarray
    def image_lut(self, name, padding) -> np.ndarray   # entrada 0 = relleno
    def for_stokes(self, s) -> str
    def cycle(self, s, step) -> str                   # C / ⇧C
class Look(Protocol):
    name: str; theme: Theme; colormaps: ColormapRegistry
    overlays: list[type[Overlay]]; stokes_control: type[QWidget]
    def levels_policy(self, stokes) -> LevelsPolicy
```

Las partes del `--modern` actual, cada una como dato o fábrica:
- **colour:** gris para I, divergente para Q, U y V, y la escala en la esquina;
- **cmap:** C/⇧C, y ahora también en la hoja `?`, que hoy no los lista;
- **reticle:** cruz corta con halo; amarilla con anillo cuando está fijada;
- **marks:** acento, curvas, rejilla y línea de cero en Q, U y V;
- **cards:** tarjetas con esquinas de 6 px;
- **stokes:** control segmentado.

**El coste del color depende del transporte.** Por el puente, el color multiplica ×2.4 los
bytes; los "dos tintes con 1 bit de signo" quedarían en 1.09 B/px, sin probar en la app.
Por eso `Look` puede elegir el mapa según `Display.link()`. El aspecto clásico sería otro
`Look`, sin tocar las vistas.

### 3.7 Flujos principales

- **Arranque:**
  1. `config`;
  2. `choose_display` (fallar pronto si no hay pantalla);
  3. crear Qt;
  4. `Dataset.open`, más la sonda de almacenamiento y el guardián de memoria;
  5. `Session`;
  6. `Shell` con los paneles del registro y el `Look`;
  7. restaurar la disposición;
  8. primera imagen;
  9. muestreo de rangos (a los 300 ms) y sonda del enlace (a los 1.5 s), en segundo plano.

  Objetivo del proyecto: 1–4 s hasta la primera imagen. Medido en el prototipo: Mac 2.8 s,
  bellatrix 1.9–3.1 s.
- **Mover el cursor:**
  1. `Store.set(cursor=…)`, agrupado por pasada del bucle;
  2. se actualizan las vistas que dependen de `cursor`;
  3. `scheduler` pide el bloque del píxel (una lectura con `_sp`);
  4. llega por señal con su generación;
  5. se muestran espectros y luego λ–t.
- **Paso en t:**
  1. `Store.set(t=…)`;
  2. imagen desde la caché o el pool de E/S, **fuera del hilo de la interfaz**, con lectura
     anticipada en el sentido del paso;
  3. `levels`;
  4. `surface.set_image`;
  5. los espectros cambian de fila sin leer (el bloque trae todos los t).
- **Reproducción:** un temporizador a los fps elegidos; por X11, el tope sale de
  `Display.link()`. Si una imagen llega tarde, se salta en vez de acumular.

### 3.8 Observabilidad: registro, tiempos y trazas (`explorer.obs`) [propuesta]

El prototipo mide con piezas sueltas: `stats` y `_ms` dentro de `Viewer`, prints a stderr,
F12, `--quit-after`, `flightrec.py`, y los tiempos de `selftest.py`. explorer lo junta en
un paquete que usan todas las capas, sin Qt.

**1. Registro (`obs/log.py`).**
- `logging` de la biblioteca estándar, con un logger por capa (`explorer.data.io`,
  `explorer.core.scheduler`, `explorer.platform.x11bridge`…), para poder subir el detalle de
  una capa sin inundar el resto.
- **Al arrancar**, una línea `INFO` con la configuración efectiva: versión, commit, host,
  pantalla (`DisplayPlan`), superficie, sonda de almacenamiento, hilos, presupuesto de
  memoria, `_sp` sí o no.
- **Salidas:**
  - consola a `WARNING` por defecto;
  - fichero rotado a `INFO` en `~/.cache/explorer/logs/` (`XDG_CACHE_HOME`), porque por
    `ssh -Y` la terminal puede no estar a la vista;
  - `--log-level` y `EXPLORER_LOG=data.io=DEBUG,…` para subir el detalle por capa.
- **Nunca `INFO` por imagen ni por movimiento del cursor.** Por `ssh` la terminal también
  cuesta. Lo repetitivo va a los tiempos (punto 2), no al registro.

**2. Tiempos por operación (`obs/spans.py`).**
- **Uso:**
  ```python
  with span("image.read", ds=ds.id, idx=idx):       # o @timed("levels.compute")
      ...
  ```
- **Dónde se guardan:** en un anillo en memoria por hilo, con `time.perf_counter_ns`.
  También lleva contadores (lecturas evitadas en el relleno, peticiones descartadas por
  viejas, aciertos de caché), que hoy son el `stats` de `Viewer`.
- **Coste:** hipótesis, unos pocos µs por tramo, sin medir. Se mide en E0. **Se apaga si**
  con los tramos puestos el cursor o el paso en t empeoran más que su ruido entre rondas
  ABBA.
- **Presupuestos por operación, con las cifras del §4:** por ejemplo cursor < 33 ms,
  imagen < 33 ms, λ–t < 50 ms.
  - Al pasar de su presupuesto, una línea `WARNING` con el desglose de sus tramos hijos
    (lectura, niveles, reducción, pintado); una por segundo como mucho.
  - Así un cuello de botella aparece en el registro sin tener que buscarlo.
- **Las acciones completas son tramos raíz:** cursor → espectro visible, paso en t → imagen
  pintada. Miden lo que siente el usuario, no solo la función.
- **Dentro de los núcleos numba no hay tramos:** se mide alrededor.

**3. Trazas (`obs/trace.py`).**
- `explorer cubo.fits --trace salida.json` guarda los tramos en formato de eventos de
  Chrome. Se abre en Perfetto o en `chrome://tracing`, con una fila por hilo: GUI, dueño de
  numba, pool de E/S, emisor del puente.
- Es lo que hace falta para ver colas y esperas entre hilos, que `cProfile` mezcla en
  Python 3.12 (ya engañó una vez en el prototipo).

**4. Vigilancia (`obs/watchdog.py`).**
- Detecta si el bucle de eventos no vuelve en N s, o si el puente no hace su tic.
- Vuelca las pilas de todos los hilos (`faulthandler`) al fichero de registro.
- Es el `flightrec.py` de hoy, sin parchear el puente: el puente expone su latido.

**5. Dónde se ve.**
- F12 muestra la mediana y el p95 de los últimos tramos de cada tipo.
- `explorer bench …` escribe todos los tramos en su JSON.
- Las pruebas pueden afirmar sobre contadores; por ejemplo, "0 lecturas sobre el relleno",
  como hoy hace `selftest`.

## 4. Decisiones medidas que explorer conserva

| Decisión | Cifra (condiciones) | Dónde |
|---|---|---|
| `pread`/`preadv`, nunca `memmap` | Imagen 2k en frío 24.4 → 4.7 ms (Mac); StorNext 85 → 23 ms | Fases 2 y 7 |
| Series con numba `nogil` + `pread` de libc | Perfil 0.7 ms, λ–t 11.6 ms en frío (Mac); con hilos de Python, 15 ms por el GIL | Fase 5 |
| Cuentan las peticiones, no los bytes | StorNext 13–15 ms por petición hasta ~180 KB; tira de 64 px = 1.05× un píxel | Fase 13 |
| Fichero por píxel `_sp` | λ–t en 1 lectura: 12.9 frente a 160 ms (bel); Stokes 14.0 frente a 1838 ms (eagle7) | Fases 8 y 17 |
| Hilos según el almacenamiento, no según el SO | λ–t con 4 frente a 64 hilos: 1255 → 146 ms (Hα, StorNext) | Fase 17, diario 09-24 |
| `fadvise`/`madvise WILLNEED`: no | ~10× peores; síncronos en `cvfs` | Fase 13 |
| No fiarse de la caché del SO para releer | Parón de ~10 ms en el tercer acceso | Fases 13 y 17 |
| Reducir a u8 a los píxeles de la vista (pgr) | Paso en t 23.9 → 15.5 ms (Mac); por `ssh -Y` pintado 42 → 4.4–4.9 ms | Fase 12 |
| Reducción en franjas `nogil` | bel 9.0 → 1.45 ms; Mac 3.6 → 0.81 ms; omp 25 ms | Diario 09-24 |
| Contraste en la submuestra `[::8, ::8]` | 55 → 1 ms | Fase 3 |
| Un solo hilo para numba en paralelo | `workqueue` aborta con dos regiones a la vez | Diario 09-24 |
| Espectro antes que λ–t; la última petición gana | Mac 18–23 → 3–5 ms; StorNext ~165 → ~40 ms | Código del prototipo, 09-24 |
| Rango y: crece al mover, ajuste en reposo | 57 → 26 ms por movimiento | F64 (código) |
| Caché de imágenes: el bucle entero o poco | Solo el bucle entero gana (16.5 frente a 18.4–19.8 ms) | Fase 17 |
| `MemoryGuard` vigila el swap en macOS | "Disponible" no avisa: abortó con el swap +0.57 GB y 5.6 GB "libres" | Fase 17 |
| Por `ssh -Y` solo llega `pgr` | vispy/gfx: ventana vacía (OpenGL en el servidor); napari igual (2026-09-26) | Fase 11 |
| Puente X11 por defecto en pantalla remota | ~12 frente a ~8.5 imágenes/s; 1.3 frente a 4.8 B/px | F2, 2026-09-25 |
| Lo que escala por X11 es lo repintado | Mismos bytes con 1 o 4 ventanas; 49 ms repintando todo frente a 20 ms solo cruz + 2 paneles | Fase 17 |
| Color por el puente | ×2.4 bytes; dos tintes 1.09 B/px [sin probar en la app] | ESTUDIO_INTERFAZ §5 |
| Nunca forzar repintados | Cruz 118 → 30 ms | Fase 9 |

**Resultados negativos que no se vuelven a proponer:**
- `memmap`;
- `fadvise`;
- OpenGL por `ssh -Y` (tampoco con IGLX ni VirtualGL);
- napari como anfitrión;
- matplotlib;
- Dash;
- VNC;
- XQuartz a 16 bits;
- reproducción fija a 20 fps;
- rejilla como objeto propio (peor);
- divergente con centro gris (no ahorra bytes).

## 5. Del prototipo a explorer

| Prototipo | explorer | Qué se hace |
|---|---|---|
| `viewer/cube.py` | `data/io.py` (FrameReader), `data/cache.py`, `data/formats/fits.py` | Separar lectura, caché y formato; aplicar BSCALE/BZERO/BLANK; `close()` |
| `viewer/native_gather.py` | `data/gather.py` | Igual |
| `app/sources.py` | `data/io.py` (PixelReader), `data/formats/lp.py`, `data/dataset.py` | Detectar por contenido; `_sp.fcube`; calibración del icube sin suponer (t, s, λ) = (0, 1, 2) |
| `app/physics.py` + `axis_positions` + unidades de `_set_spectra` | `data/axes.py` | Juntar; hueco para `WCSDVARR` |
| `app/policy.py` + `bench/membench/sysmem.py` | `data/policy.py`, `data/sysmem.py` | Sin rutas de `sys.path`; `probe.readers` en uso |
| Núcleos de `viewer.py` (`_reduce_u8*`, `_absmax*`, `quv_amplitude_ranges`, `read_slit_*`, `limits`) | `data/kernels.py`, `data/stats.py` | Una implementación de cada |
| Hilos de `Viewer` (`_bg`, `_quv_bg`, `_slit_bg`, `_strip_pool`) | `data/executors.py`, `core/scheduler.py` | Un dueño de numba en paralelo; ninguna E/S en la interfaz |
| `Viewer` (estado, índices, `hover`, `locked`) | `core/state.py`, `core/session.py` | Un solo estado; sin `blockSignals` en espejo |
| `Viewer` (docks, barra, paneles) | `ui/shell.py`, `ui/views/*`, `ui/panels.py` | Paneles por registro; `depends` declarativo |
| `_key_table`, `_Gestures`, atajos de `look.py` | `ui/input.py` | Una sola tabla: teclas, hoja `?`, menú |
| `ViewGuard`, `PanelLock`, `KeySheet`, `ResizeFreezer`, ejes | `ui/views/image.py`, `ui/overlays/`, `ui/widgets/` | Tal cual, sin estado propio |
| `app/look.py` (`--modern`) | `look/modern.py`, `look/theme.py`, `look/colormaps.py`, `ui/overlays/reticle.py` | De parches a datos y fábricas |
| `app/style.py`, `app/icons.py`, `app/titlebar.py` | `look/style.py`, `look/icons.py`, `platform/titlebar.py` | Sin estado global mutado desde la ventana |
| `app/startup.py` | `app.py`, `platform/plan.py` | La decisión, como función pura |
| `app/xbridge.py`, `xconn.py`, `xrender.py` | `platform/x11bridge/` | Partido en módulos (decisión P4) |
| `app/flightrec.py`, `app/linkprobe.py` | `platform/flightrec.py`, `platform/linkprobe.py` | Sin parchear `_tick_run`: gancho del puente |
| Backends `pg`, `pgr`, `vispy`, `gfx` | `ui/surfaces/` | `pgr` por defecto; los demás, opcionales; `PgSide` sin paneles fantasma |
| `app/selftest.py`, `smoke.py`, `conformance.py`, `test.py` | `explorer bench`, `tests/gui/`, `tests/parity/`, `explorer doctor` | Contra `testing.Driver` |
| `stats`, `_ms`, prints, F12 de `Viewer` | `obs/` (§3.8) | Tramos y contadores en todas las capas |
| `setup_env.sh`, `run.sh`, `check_wheels.py` | `scripts/`, `pyproject.toml` + `uv.lock` | Lock con hashes en vez de `cksum` |
| `actualize.py` | `scripts/sync.py` | Lista de subida desde `git ls-files` (hoy apunta a los `.md` de la raíz, que ya no están ahí) |

**No se trae:**
- `viewer/shell.py`, los backends `fpl` y `mpl`, y los paneles fantasma de `PgSide`;
- los formatos del servidor que perdieron en la Fase 10 (`i16`, `f16`, `lz4`);
- `robust_limits`, que no se usa;
- la rama muerta `PRESENT=bitmap` sobre X11;
- el `sys.path` hacia `bench/`;
- de las tres variantes de rendija (A, C, D), solo la que se elija (decisión P5);
- los números mágicos sueltos, que pasan a constantes con nombre y con su cifra de origen.

## 6. Etapas

Cada etapa se cierra con sus pruebas en verde y, donde toque, con la medida frente a la
línea base del prototipo en rondas alternas (ABBA). Sin alternar apareció un falso +2 ms.

| # | Etapa | Se da por buena cuando |
|---|---|---|
| E0 | Repositorio: `pyproject`, `uv.lock`, scripts, CI de higiene (§8). `cli.py` con `explorer --version` y `explorer doctor`. `obs/` (registro, tramos, traza) y la **medida de su coste**. `testing/synth.py`. `tools/golden/export_prototype.py` y las referencias del prototipo. **Línea base** del prototipo: `selftest` en bellatrix (Xvfb y puente) y en el Mac (sintético), `--look modern`, con y sin `_sp` | CI en verde; `pip install` en un entorno limpio da la orden `explorer` en Linux y en el Mac; referencias y línea base guardadas con host, fecha, carga y versiones; el coste de los tramos es menor que el ruido |
| E1 | `explorer.data`: formatos, lectores, caché, ejecutores, ejes, estadística. Sin Qt | Nivel 1 de §7.1 en verde (datos): idéntico byte a byte donde toca; misma latencia de E/S (ABBA); se importa sin PySide6 |
| E2 | `explorer.core`: `Store`, `Session` (un cubo), `scheduler`, `levels`, `yrange`; `testing.Driver` sin pantalla | Pruebas de generación (lo viejo nunca llega a pantalla), agrupado de ráfagas, sin lecturas sobre el relleno |
| E3 | `platform/plan.py` y `Display` para cocoa, xcb y offscreen; `Shell` mínima con la imagen (`pgr`) | Tabla de decisión probada; primera imagen en 1–4 s; paso en t ≤ el del prototipo |
| E4 | Espectros y λ–t; cursor completo; reproducción | Niveles 2 y 3 de §7.1: mismo estado tras cada acción del guion; cursor, pasos y reproducción dentro del ruido del prototipo |
| E5 | Aspecto moderno como `Look`; `ActionRegistry` con la hoja `?`; persistencia con esquema versionado | Capturas lado a lado con el prototipo; **el usuario lo mira**; nada parcheado |
| E6 | Por `ssh -Y`: primero xcb nativo; después el puente dentro de `platform/x11bridge` | Paridad xcb/puente (lista de diferencias aceptadas); fps y bytes por el puente como en F2; comprobado en XQuartz por el usuario |
| E7 | Rendija o camino → losa → paneles | E/S en 23–96 ms para 600 px, como en la Fase 13 |
| E8 | Varias vistas enlazadas (etapas 4–8 del plan de ventanas enlazadas) | Con un cubo nada cambia; con dos, los criterios de ese plan |
| Después | Aspecto clásico; Ctrl+K; Q/I y ±σ; vista 2×2; Doppler; curva de luz; exportar PNG y película; remoto por `Dataset`; clave de color de dos tintes para el puente | Cada una con su medida |

## 7. Pruebas y medida

### 7.1 Mismos resultados que el prototipo (`tests/golden/`) [propuesta]

explorer debe hacer lo mismo que la parte del prototipo que funciona. El prototipo es el
**oráculo**: se ejecuta tal cual, sin tocar su código, y sus resultados son la referencia.
Tres niveles, de más estricto a menos:

**1. Resultados numéricos, para las mismas entradas.**
- `tools/golden/export_prototype.py` importa los módulos del prototipo desde su carpeta,
  solo para leer, y para cada caso de `tests/golden/cases.toml` guarda un `.npz`:
  - imágenes para una lista de índices;
  - series (espectro, λ–t) y bloques `_sp` para una lista de píxeles;
  - límites de contraste;
  - la imagen reducida a u8 de `pgr` para una vista y un zoom dados;
  - rangos y de la muestra (semilla fija) y de Q, U y V;
  - ejes físicos (Δλ, km/s, UTC, ″) y unidades;
  - losas de rendija para caminos dados.
- **Cómo se compara:**
  - **idéntico byte a byte** lo que es E/S o conversión determinista: imágenes, series,
    bloques, u8, losas;
  - **con tolerancia escrita en el caso** lo que es estadística o coma flotante: límites y
    rangos, por ejemplo `rtol=1e-6`. Una tolerancia nueva exige una línea que diga por qué.
- **Casos:**
  - cubos sintéticos pequeños (con relleno NaN, Stokes, `_sp` e `icube`), cuyas referencias
    se versionan en `tests/golden/data/` y corren en CI;
  - los cubos reales de bellatrix, cuyas referencias se quedan allí, fuera del repositorio
    (`pytest -m golden_real`).
- **Diferencias buscadas.** Donde explorer corrige al prototipo (BSCALE/BZERO, el atajo de
  Stokes), el caso lo dice explícitamente: `expect = "differs"` y el motivo. Así no se
  confunde un arreglo con una regresión.

**2. Mismo comportamiento ante la misma secuencia de acciones.**
- Un guion de acciones (mover el cursor a estos píxeles, fijarlo, t+1, λ−1, Stokes V,
  reproducir 2 s) se ejecuta en los dos.
- En explorer con `testing.Driver`; en el prototipo con un adaptador que llama a lo mismo
  que usa hoy `selftest.py` (`_on_hover`, `_step`…), sin modificarlo.
- Tras cada acción se compara el estado: t, λ, s, cursor, bloqueado, límites mostrados,
  rango y, y qué paneles se actualizaron.
- Los contadores también cuentan: por ejemplo, el mismo número de lecturas evitadas sobre
  el relleno.

**3. Mismo rendimiento o mejor.**
- `bench/` ejecuta el mismo guion en los dos, en orden ABBA, en la misma máquina y sesión,
  y guarda las medianas, los p95 y el desglose de tramos (§3.8).
- **Criterio por etapa:** no peor que el prototipo más su ruido entre rondas. Lo que salga
  peor se explica con la traza antes de seguir.
- Se ejecuta en bellatrix y a mano, no en CI: el tiempo en CI no es fiable.

`tools/golden/compare.py` resume las diferencias en una tabla (caso, magnitud, máximo error,
dónde) para decidir rápido si es un fallo, un arreglo buscado o una tolerancia mal puesta.

### 7.2 El resto de pruebas

- **Unitarias (sin pantalla, en segundos):**
  - formatos, detección, BSCALE;
  - lectores frente a lecturas independientes;
  - ejes con cabeceras reales guardadas como texto;
  - coordenadas y tabla de pantalla;
  - generación de peticiones;
  - codificador del puente frente a python-xlib, byte a byte.
- **GUI** (pytest con marcadores `offscreen`, `xcb` y `bridge`), con un fixture de Xvfb con
  XTEST en lugar de `:97` fijo.
  - Las entradas de ratón y teclado pasan por el servidor X (XTEST), no por `QTest`: por
    `QTest` no se detectó en su día un cuelgue del puente.
- **Paridad xcb/puente**, con la lista de diferencias aceptadas versionada.
- **Cubos sintéticos con relleno NaN y cabecera SOLARNET:** un cubo sin relleno escondió un
  fallo de color en el prototipo.
- **Medida** (`bench/`, fuera de la puerta de CI):
  - `selftest` en ABBA con ≥ 2 rondas;
  - JSON con host, fecha, commit, carga, versiones de Qt y numba, y si el puente estaba
    activo.
- **Sin pantalla de verdad:** `env -u DISPLAY` y `QT_QPA_PLATFORM=offscreen`. Si no, el
  puente abre ventanas en el Mac del usuario.
- **En el Mac, solo cubos sintéticos pequeños,** con `sysctl vm.swapusage` antes y después.

## 8. Proceso del repositorio

- **Commits:**
  - `[DEV]`, `[STYLE]`, `[DOC]`; en `[DEV]`, las líneas `Behaviour:` y `Tests:`;
  - sin menciones de asistentes de IA ni líneas de coautoría;
  - sin `git push` sin permiso para ese push.
- **CI de higiene**, que falla el build si hay:
  - ficheros de auditoría versionados;
  - rutas absolutas del home del Mac o personales de StorNext en ficheros versionados;
  - menciones de asistentes de IA o líneas de coautoría en el historial (`fetch-depth: 0`,
    mensajes y diffs).

  El script de CI compone esos patrones a partir de trozos, sin escribirlos literalmente;
  si no, se encontraría a sí mismo en el historial. Por la misma razón, ningún documento
  versionado los cita literalmente.

  Hoy lo harían fallar varios ficheros del prototipo: rutas personales en notas y en
  `results/`, y dos logs. Por eso explorer empieza limpio y no se copian.
- **Sincronización con bellatrix:** `scripts/sync.py`.
  - El Mac es la fuente de verdad del código; la lista de subida sale de `git ls-files`.
  - Se niega si existe `.editing_on_server`.
  - `pull` solo trae `bench/results/` y nunca pisa lo más nuevo.
- **No se versionan:** entornos, `data/`, código de terceros (`crispex_idl/`), cachés,
  resultados en bruto, la auditoría.
- **Documentos:** las medidas siguen en el diario del proyecto (lo falso se tacha con fecha;
  nunca se borra). `explorer/docs/` recoge la arquitectura y la tabla del §4 con sus cifras,
  para que el repositorio se entienda solo si se clona aparte.

### 8.1 Instalación y la orden `explorer` [propuesta]

**Un paquete de Python normal**, con `pyproject.toml` y el código en `src/explorer/`. En
`[project.scripts]`, `explorer = "explorer.cli:main"` crea la orden al instalar:

```bash
pip install explorer-sst                 # o, sin tocar el Python del sistema:
uv tool install explorer-sst             # (pipx install explorer-sst funciona igual)
pip install "explorer-sst[x11bridge]"    # extras: x11bridge (python-xlib), gpu (vispy, pygfx)
uv pip install -e ".[dev]"               # para desarrollar: editable, con pytest, ruff, pyright

explorer cubo_im.fits                    # abre el cubo; busca el _sp al lado
explorer cubo_im.fits --sp otro_sp.fits --look modern --trace t.json
explorer doctor                          # entorno, Qt, pantalla, libxcb-cursor, lectura de un cubo
explorer bench selftest cubo_im.fits     # la medida de §7.1, JSON con los tramos
explorer --version
python -m explorer cubo_im.fits          # lo mismo sin la orden en el PATH
```

(`explorer-sst` es un nombre de ejemplo; el nombre de distribución es la decisión P1.)

- **Una sola orden con subórdenes.** Si el primer argumento es un fichero, se abre; si no,
  es una subórden (`doctor`, `bench`, `smoke`). Lo que hoy son `run.sh`, `test.py`,
  `selftest.py` y `smoke_all.sh` queda bajo `explorer`.
- **Arranque rápido.** `cli.py` solo importa `argparse` y `config` antes de decidir. Qt,
  numba y astropy se importan después, y solo si hacen falta: `explorer --version` y
  `explorer doctor` sin cubo no pagan los 1–2 s de importar Qt. El objetivo es la primera
  imagen en 1–4 s.
- **Lo que pip no instala, y cómo se resuelve:**
  - Qt ≥ 6.5 necesita `libxcb-cursor` en Linux para X11; RHEL 9 no la trae y no hay root.
    `explorer doctor` lo detecta y dice qué hacer. `scripts/setup_env.sh` mantiene la vía
    de conda-forge del prototipo (`.qtlibs/`).
  - Mac Intel: numba 0.62.1 es la última con ruedas para x86_64. Van versiones distintas
    por plataforma en `pyproject.toml`, con marcadores, y el lock las fija.
  - PySide6 6.11.2 exige macOS ≥ 13 y glibc ≥ 2.34.
- **Entorno compartido en StorNext** (bellatrix y los Mac que lo montan):
  `scripts/setup_env.sh` crea `.venv-<OS>-<arch>` con `uv sync`, y `scripts/run.sh` elige
  el que corre en esa máquina, como hoy. En una máquina propia basta `uv tool install`.
- **Versión** con `setuptools-scm` o similar, desde las etiquetas de git. Aparece en
  `--version`, en la primera línea del registro y en cada JSON de medida.

## 9. Decisiones para el usuario

| # | Decisión | Opciones | Nota |
|---|---|---|---|
| P1 | Nombre del paquete y de la orden | `explorer` · algo más específico para PyPI (sin comprobar si `explorer` está libre) | La importación puede seguir siendo `explorer` |
| P2 | Repositorio propio o dentro del proyecto | `explorer/` con su propio git · un solo repositorio con `prototype/` | Afecta a CI, a `sync.py` y a dónde viven `docs/` |
| P3 | Dónde viven las notas (`OVERVIEW`, `RESEARCH`…) | En `docs/` del proyecto · copiadas o movidas a `explorer/docs/` | Un repositorio clonado aparte no ve `../docs` |
| P4 | Puente X11 | Traerlo tal cual, partido en módulos · reescribirlo | Ata PySide6 a una versión por símbolos privados; es la pieza con más hallazgos abiertos |
| P5 | Rendija | Variante A, C o D del prototipo | Solo una entra en explorer |
| P6 | Superficies de imagen | Solo `pgr` al principio · también vispy/gfx locales | Menos código frente a 6 ms por imagen en local |
| P7 | Aspecto clásico | En E5 junto al moderno · más adelante | Con `Look` cuesta poco, pero duplica las capturas de prueba |
| P8 | Remoto (cliente–servidor) | Dentro del alcance (como `Dataset` remoto) · fuera | Medido: ~30 imágenes/s a ~1000², λ–t en 32 ms |
| P9 | Licencia | — | Antes del primer commit público |
| D1–D6 | Las del plan de ventanas enlazadas | — | Se deciden antes de E8 |

## 10. Riesgos

- **Perder rendimiento al separar capas.** Cada salto entre capas (señal, cola, Future)
  cuesta algo. Mitigación: medir en E1, E2 y E4 contra la línea base; el cursor del
  prototipo está en 6–15 ms.
- **El puente X11**: depende de símbolos privados de Qt; su foco y activación difieren de
  xcb; tiene hallazgos abiertos en XQuartz. Mitigación: aislado en `platform/`, xcb nativo
  primero (E6), paridad como prueba.
- **Reescribir lo que ya funciona.** Mitigación: E1 compara byte a byte con el prototipo, y
  el prototipo sigue vivo como laboratorio de medida hasta que explorer lo iguale.
- **El Mac del usuario tiene el swap casi lleno.** Las medidas grandes se hacen en
  bellatrix; en el Mac, sintéticos pequeños.

## 11. Consejos de desarrollo

Lo que más ahorra en una aplicación como esta, ordenado por lo que el prototipo ya enseñó.

1. **Portar por capas, con el prototipo como oráculo.** Una capa se da por buena cuando
   iguala al prototipo (§7.1); solo entonces se construye encima. El prototipo no se borra
   ni se toca hasta que explorer lo iguale: es la referencia y el laboratorio de medida.
2. **Casi toda la lógica, sin Qt.** Lo que no dibuja (lectura, ejes, niveles, rangos,
   coordenadas, planificación, decisión de pantalla) se prueba en milisegundos y sin
   pantalla. La capa Qt queda fina: recibe estado y pinta.
3. **Hacer cumplir las fronteras.**
   - `import-linter` en CI, con contratos por capa (`data` no importa `PySide6` ni `ui`;
     nadie salvo `app` y `ui.shell` importa `platform`).
   - Sin eso, las capas se vuelven a mezclar en unas semanas.
4. **Tipos y estilo automáticos.**
   - `ruff`: formato y lint.
   - `pyright` o `mypy`: estrictos en `data`, `core` y `obs`; laxos en `ui`.
   - `pre-commit`, para que lleguen al commit ya revisados.
   - Los cambios de solo formato van en commits `[STYLE]` aparte.
5. **Hilos con reglas simples, escritas una vez.**
   - Los objetos Qt solo se tocan en el hilo de la interfaz.
   - Entre hilos solo viajan datos inmutables o copias, por señales en cola.
   - Numba en paralelo, solo en su ejecutor.
   - Cada trabajo lleva su generación.

   Casi todos los fallos difíciles del prototipo fueron de esta clase.
6. **Una sola fuente de configuración.**
   - El prototipo acumula unas 20 variables `CRISPEX_*` repartidas por el código.
   - En explorer, un objeto `Config` tipado: línea de órdenes > entorno > fichero > valor
     por defecto, documentado en un solo sitio e impreso al arrancar.
   - Los experimentos van como banderas de `Config`, no como ramas `if SLIT_UI == …`
     dispersas; se quitan cuando se decide.
7. **Errores que se ven.**
   - Mensaje propio al usuario y detalle en el registro.
   - Nunca volver a otra cosa en silencio (el prototipo lo hizo con QSettings, con el
     puente sobre `offscreen` y con libxcb-cursor).
   - Si algo cae a un modo peor, el registro lo dice en `WARNING`.
8. **Recursos con dueño y cierre.**
   - `Dataset`, lectores y ejecutores son gestores de contexto con `close()`.
   - Al cerrar la ventana se cierran todos, en orden.
   - Una prueba abre y cierra 100 veces y mira que no crezcan los descriptores ni los hilos.
9. **Registro de decisiones (ADR).**
   - `docs/decisions/NNNN-titulo.md`, un fichero corto por decisión: contexto, opciones,
     medida que la decidió (cifra y condiciones), consecuencias.
   - Es el formato de `OVERVIEW.md`, pero de una decisión por fichero y enlazable desde el
     código.
   - Una decisión revocada no se borra: se marca como sustituida por la nueva.
10. **Commits pequeños, cada uno con su prueba.**
    - `Behaviour: unchanged` en todo lo que sea mover código, que es la mayor parte del
      port.
    - Etiquetas de versión en cada etapa cerrada (`v0.1` = E1…), para poder medir cualquier
      etapa otra vez.
    - `CHANGELOG.md` escrito para usuarios.
11. **No optimizar sin traza.** Antes de cambiar algo por velocidad: la traza (§3.8) dice
    dónde se va el tiempo y en qué hilo. Después: ABBA frente a la versión anterior. Es el
    método del prototipo; aquí queda en las herramientas y no depende de acordarse.
12. **Aleatoriedad reproducible.** Semillas fijas (como la del muestreo de perfiles, que sale
    del nombre del fichero) y entornos con lock, para que un resultado se pueda repetir
    meses después.


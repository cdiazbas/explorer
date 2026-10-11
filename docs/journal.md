# Diario de medidas

Diario de medidas de explorer, con el formato de `OVERVIEW.md` del prototipo.

- **Una entrada por medida:** fecha, máquina (`hostname`), carga, frío o caliente,
  versiones (commit, Qt, numba), método y cifras. Los resultados negativos se anotan igual.
- **Lo que resulta falso** se tacha y se marca como retirado, con la fecha; nunca se borra.
- **Comparaciones:** frente al prototipo o a otra versión, en orden ABBA y con al menos 2
  rondas.

## Entradas

### 2026-09-29: arranque del demo frente al del prototipo

**Pregunta del usuario:** el demo le parece lento; ¿es la velocidad que ya tenía el prototipo?

**Método.**
- Tres rondas alternadas (prototipo, explorer), tiempo de reloj desde fuera del proceso, sin
  ventana.
- Prototipo: `demo.sh` (bellatrix) o `app/run.sh <sintético>` (Mac), con
  `QT_QPA_PLATFORM=offscreen --quit-after 0.3`. Su línea "first image on screen" cuenta desde que
  se empieza a importar su módulo, no desde que arranca el intérprete.
- explorer: `scripts/demo.sh --no-window` (commit `0d05ebe`), que hoy ejecuta `doctor` sobre el
  cubo.

**Condiciones.**
- bellatrix: cubo de Stokes 6173 (176 GB, StorNext), carga 0.2.
- Mac (M1 Pro): cubo sintético de 84 MB, carga 4, swap 9.0/10 GB sin cambios durante la medida.

| | Prototipo, primera imagen | Prototipo, reloj (incl. 0.3 s) | explorer, reloj |
|---|---:|---:|---:|
| bellatrix, rondas 2–3 | 2.51–2.53 s | 3.27–3.29 s | 2.13–2.14 s |
| bellatrix, ronda 1 (frío) | 6.02 s | 6.83 s | 3.75 s |
| Mac, rondas 2–3 | 1.29–1.30 s | 1.92–1.95 s | 1.14–1.19 s |
| Mac, ronda 1 | 2.56 s | 3.30 s | 1.66 s |

**Desglose de explorer** (bellatrix / Mac, en caliente):
- `doctor`, prueba de numba: 1.15 / 0.46 s, de los que 0.80 / 0.35 s son compilar sus núcleos de
  prueba, que no están en caché;
- cabecera con astropy: 0.34 / 0.14 s;
- Qt en el proceso hijo: 0.22 / 0.23 s.

**Conclusión.**
- Sin ventana, explorer no es más lento que el prototipo. Pero no hace lo mismo: no pinta
  ninguna imagen, así que no es una comparación de visores; esa llega en E3–E4 frente a la línea
  base E0.8.
- Con ventana, `doctor --show` añade 2 s fijos a propósito: es lo que se percibe como lento.

### 2026-09-29: coste de un tramo de `obs` (ROADMAP E0.4)

**Pregunta:** ¿pueden quedarse siempre activados los tramos (`obs.span`) en el visor?

**Criterio.** Una acción del usuario abrirá unos 20 tramos, y el cursor del prototipo tarda
6–15 ms. Cada tramo debe costar ≤ 5 µs, para que el total sea ≤ 0.1 ms (≤ 1 %).

**Método.** `bench/obs_overhead.py`: 200 000 tramos en un bucle, menos el mismo bucle sin tramos,
7 repeticiones, mediana. Resultados en `bench/results/obs_overhead_*_20260929.json`.

**Condiciones.**
- Mac: M1 Pro, carga 5.4.
- bellatrix: carga 0.4.
- Los dos: Python 3.12, sin commit (el código de `obs` es el de este día).

| µs por tramo | Mac | bellatrix |
|---|---:|---:|
| Desactivado | 0.19 | 0.33 |
| Activado | 0.74 | 1.38 |
| Activado, anidado | 0.80 | 1.45 |
| Activado, con presupuesto (sin pasarse) | 0.74 | 1.38 |
| Grabando traza | 1.27 | 2.49 |
| 4 hilos a la vez | 0.76 | 1.39 |
| **20 tramos, peor caso** | **25 µs** | **50 µs** |

**Conclusión.**
- Pasa en las dos máquinas: los tramos pueden quedarse activados.
- En bellatrix el peor caso usa la mitad del presupuesto: si una acción llega a abrir muchos más
  de 20 tramos, hay que volver a mirarlo.
- La traza casi duplica el coste: se graba solo cuando se pide (`EXPLORER_TRACE`).

### 2026-09-29: línea base del prototipo (ROADMAP E0.8)

**Para qué.** Es la referencia de todo lo que haga explorer. Ninguna medida de explorer puede
ser peor que esta en las mismas condiciones, y la meta es mejorarla (el usuario, 2026-09-29).

**Método.**
- `bench/prototype_baseline.sh`: el `selftest.py` del prototipo, sin modificarlo, con el aspecto
  `--modern` aplicado por `bench/prototype_selftest.py`, que lo confirma en cada ejecución.
- 2 rondas en orden ABBA; cada celda es "ronda 1 / ronda 2".
- Identidad del código medido: md5 del prototipo `a5f3bfce65144fd9b2dd7e536ba30866`, el mismo en
  las dos máquinas. El prototipo no tiene git.
- Resultados en `bench/results/baseline_bellatrix_20260929T0959/` y `bench/results/baseline_069194691202856_20260929T0958/`.

**bellatrix.**
- Cubo de Stokes 6173 (176 GB, StorNext), con y sin `_sp`, carga 0.12 al empezar.
- Modos: `offscreen`; `xcb` y puente sobre el Xvfb `:97`, que no tiene gestor de ventanas ni
  enlace de red. Por eso el puente mide su coste de CPU, no lo que se ve por `ssh -Y`.

| Modo | `_sp` | Primera imagen s | Cursor ms | Espectro+λt ms | Paso t ms | Paso λ ms | Stokes ms | fps | Puente MB/mov. |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| offscreen | sí | 1.92 / 1.58 | 32.1 / 13.5 | — | 16.9 / 14.6 | 20.1 / 17.5 | 11.2 / 11.0 | 51 / 55 | — |
| offscreen | no | 1.64 / 1.73 | 6.7 / 7.9 | 483 / 223 | 16.2 / 15.2 | 19.2 / 18.4 | 11.0 / 9.4 | 59 / 57 | — |
| xcb | sí | 1.67 / 1.60 | 15.4 / 14.0 | — | 17.3 / 16.5 | 19.8 / 17.5 | 9.6 / 9.5 | 55 / 52 | — |
| xcb | no | 1.81 / 1.84 | 8.0 / 8.5 | 288 / 236 | 15.8 / 17.1 | 20.4 / 17.6 | 9.4 / 9.1 | 54 / 52 | — |
| puente | sí | 1.72 / 1.73 | 17.6 / 17.8 | — | 23.4 / 23.0 | 25.0 / 24.7 | 14.8 / 14.6 | 43 / 40 | 0.50 |
| puente | no | 1.89 / 1.78 | 13.0 / 12.3 | 242 / 227 | 20.4 / 20.8 | 24.2 / 23.0 | 14.3 / 12.7 | 38 / 41 | 0.20 |

**Mac** (M1 Pro): ~~cubo sintético (8, 4, 10, 256, 256), solo `offscreen` (cocoa abriría ventanas
en la pantalla del usuario), carga 3.3.~~ **Sustituida el mismo día** por la tabla "Mac, sintético v2"
de abajo. Esta se midió con el sintético v1, sin `_sp`, y ya no sirve de referencia. Se conserva
tal cual:

| `_sp` | Primera imagen s | Cursor ms | Espectro+λt ms | Paso t ms | Paso λ ms | Stokes ms | fps |
|---|---:|---:|---:|---:|---:|---:|---:|
| (no hay) | 0.80 / 0.83 | 1.28 / 1.31 | 5.06 / 5.11 | 4.91 / 5.14 | 4.09 / 5.11 | 3.50 / 3.79 | 62.5 / 62.4 |

**Cómo leerlo.**
- **"Cursor" con `_sp`:** cruz, espectro y λ–t, leídos de una sola vez del fichero por píxel.
- **"Cursor" sin `_sp`:** solo la cruz; los datos llegan después ("Espectro+λt").
- **Caché fría:** las dos diferencias grandes entre rondas (offscreen/sí, cursor 32 → 13 ms;
  offscreen/no, 483 → 223 ms) son de las primeras configuraciones que tocaron el `_sp` y el cubo.
  Cuando explorer se compare con esta tabla, tiene que ser en el mismo orden ABBA, o separando la
  primera pasada.
- **Por el puente:** ~5 ms más por paso y ~40 fps frente a ~55 fps en la reproducción.

**Limitaciones.**
- No mide `ssh -Y` hasta XQuartz, que depende del enlace y de lo que se repinta.
- No mide cocoa en el Mac.
- Tampoco el aspecto clásico.

### 2026-09-29: línea base del Mac con el sintético v2 (sustituye a la del v1)

**Qué cambia.** El sintético v2 trae cabecera SOLARNET con WCS-TAB y su `_sp.fits`, así que el
prototipo lo abre como un cubo real. Con el v1 no había fichero por píxel y las dos filas medían
lo mismo.

**Condiciones.** Mismo método (`bench/prototype_baseline.sh`, `offscreen`, 2 rondas ABBA, aspecto
moderno) y mismo código del prototipo (md5 `a5f3bfce…`). Mac M1 Pro, carga ~3, swap sin cambios.
Resultados en `bench/results/baseline_069194691202856_20260929T1012/`.

| `_sp` | Primera imagen s | Cursor ms | Cursor p95 | Espectro+λt ms | Paso t ms | Paso λ ms | Stokes ms | fps |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| sí | 1.08 / 0.83 | 3.59 / 3.64 | 8.70 / 8.23 | — | 5.17 / 5.51 | 4.57 / 4.56 | 2.95 / 3.01 | 62.5 / 62.5 |
| no | 0.84 / 0.81 | 1.48 / 1.42 | 3.19 / 4.42 | 5.41 / 5.21 | 5.44 / 5.34 | 4.81 / 4.95 | 3.77 / 3.88 | 62.5 / 62.5 |

**Comprobación de compatibilidad.** Antes de medir, el prototipo abrió el sintético v2 con su
propio código (`physics.from_fits`, `Cube`, `find_sp`, `SpFits`, `SpLP.calibrate`):
- línea Fe I 617.3, λ0 617.3341 nm, continuo en la sintonía 5 (de `PRPARA`), Δλ −0.35…+0.70 Å;
- UTC por barrido y segundos de arco que derivan con t;
- `SpFits` idéntico a `Cube.series`;
- calibración del `icube`: escala 1.0e-11, residuo máximo 0.58 unidades. Con el `_sp.icube` real
  de Hα el prototipo midió 0.5 unidades (OVERVIEW, diario 2026-09-24).

### 2026-09-29: referencias del prototipo para la comparación numérica (ROADMAP E0.7)

**Qué se exporta.** `tools/golden/export_prototype.py` corre con el Python del prototipo y llama a
sus propias funciones, sin modificarlas. Para cada caso de `tests/golden/cases.toml` guarda:
- imágenes, límites de contraste, series por píxel y bloques de `_sp.fits` e `icube`;
- la reducción de `pgr` que usa la aplicación (`_reduce_u8_serial`, nivel 0 = relleno);
- rendijas: camino, píxeles, losa y bandas;
- ejes físicos y rangos de Q, U y V;
- de una ventana real del prototipo construida sin pantalla: los rangos y del muestreo y de Q, U y V,
  `iscale` y los límites de la primera imagen.

**1. El sintético no es idéntico entre máquinas.**
- El mismo `write_dataset(seed=7)` da un `_im.fits` y un `_sp.fits` distintos en el Mac (arm64) y en
  bellatrix (x86_64): son distintos los sha256, porque los float32 difieren en los últimos bits.
- El `icube` sí coincide: el redondeo a enteros absorbe la diferencia.
- **Consecuencia:** las entradas del caso sintético se versionan (`tests/golden/data/synth_small/`,
  1.2 MB), y cada máquina lee los mismos bytes.

**2. Con las mismas entradas, el prototipo da lo mismo en las dos máquinas.**
- Exportado en el Mac y en bellatrix y comparado con `tools/golden/compare.py --meta`: 38 de 43
  claves idénticas.
- Las 5 diferencias son del último dígito de un float64:
  - la calibración del `icube` (`np.polyfit`: escala, cero y residuo) difiere en ~1e-15 relativo, y
    aun así los bloques calibrados en float32 salen idénticos;
  - un valor de cada `slit_path`, 3.6e-15 (1e-16 relativo).
- **Para la E1:** lectura y conversiones, idénticas; cuentas en float64 (calibración, caminos), con
  tolerancia relativa del orden de 1e-12, escrita en la prueba con su motivo.

**3. Determinismo.** Dos exportaciones seguidas en el Mac, con las mismas entradas, salen idénticas
en las 40 claves, pese a las lecturas en paralelo.

**4. Coste de la referencia real** (cubo de Stokes 6173, bellatrix, carga ~1).
- 20 s de reloj; 8.4 s de exportación. El resto es arrancar, la ventana sin pantalla y comprimir
  los 118 MB del `.npz`, que se queda en bellatrix y no se versiona.
- El primer intento tardó ~20 minutos: calculaba el sha256 de las entradas completas (dos cubos
  de 176 GB, ~350 GB leídos de StorNext a ~0.3 GB/s).
- Ahora, los ficheros de más de 64 MB se identifican con una huella: tamaño, fecha de modificación
  y sha256 de los primeros y últimos 16 MB. Un cambio en medio del fichero con el mismo tamaño y la
  misma fecha pasaría desapercibido; se acepta, porque los cubos compartidos no se reescriben así.
- En el cubo real, los rangos de Q, U y V recorren la rama del percentil (Q y U: 10.7 %, V:
  15.7 % de I_c). En el sintético pequeño solo se recorre la del suelo de ruido.

### 2026-09-29: lectura de imágenes, explorer frente al prototipo (ROADMAP E1.2)

**Método.**
- `bench/frames_vs_prototype.py`: el `Cube._read_frame` del prototipo y el `FrameReader` de
  explorer en el mismo proceso, en 4 rondas ABBA de 10 imágenes sorteadas.
- En las lecturas nuevas, cada imagen la lee una sola de las dos implementaciones. Las cachés
  compartidas no se vacían, así que el estado previo de la caché es desconocido: lo que hace justa
  la comparación es el orden ABBA.
- Cada imagen se compara bit a bit entre las dos.
- bellatrix, cubo de Stokes 6173 (imagen de 16.6 MB), carga 0.6. Resultado en
  `bench/results/frames_vs_prototype_bellatrix_20260929T1141.json`.

| Mediana de las rondas | Prototipo | explorer |
|---|---:|---:|
| Imagen aún no leída | 37.3 ms | 37.6 ms |
| Imagen ya en caché | 6.22 ms | 6.31 ms |

**Conclusión.**
- Igual dentro del ruido: la dispersión entre rondas de las lecturas nuevas es de 34.8–52.8 ms.
- 0 de 40 imágenes distintas.
- En `tests/golden`, las 5 imágenes del cubo real son idénticas bit a bit a las de la referencia.
- La estrategia de lectura es la misma (`preadv` en 4 trozos). explorer añade la comprobación de
  lecturas cortas y `BSCALE`/`BZERO`/`BLANK` sin coste visible.

### 2026-09-29: series por píxel, explorer frente al prototipo (ROADMAP E1.3)

**Método.**
- `bench/series_vs_prototype.py`: el `Cube.series` del prototipo y el `FrameReader.series` de
  explorer en el mismo proceso, los dos con `gather` de numba y 64 hilos, en 4 rondas ABBA con
  píxeles sorteados. Una llamada en paralelo cada vez.
- Resultados comparados bit a bit.
- bellatrix, cubo de Stokes 6173, sin `_sp`, carga 0.2. Resultado en `bench/results/series_vs_prototype_bellatrix_20260929T1201.json`.

| Mediana de las rondas | Prototipo | explorer |
|---|---:|---:|
| λ–t de un Stokes (2 604 lecturas), sin leer | 648 ms | 615 ms |
| λ–t, en caché | 34.8 ms | 35.1 ms |
| Bloque completo (10 416 lecturas), sin leer | 2 282 ms | 2 225 ms |
| Bloque completo, en caché | 947 ms | 959 ms |

**Conclusión.**
- Igual dentro del ruido; 0 series distintas.
- En `tests/golden`, las series del cubo real son idénticas bit a bit a las de la referencia.
- En el Mac, con el sintético pequeño, también iguales (λ–t 0.2 ms, bloque completo 0.4 ms).
- La primera lectura de la primera ronda sale lenta en las dos implementaciones (hasta 3.7 ms en
  el Mac): es un efecto de arranque, no de la implementación.

**Anotado para después.** Sin fichero por píxel, el bloque completo tarda ~1 s incluso en caché:
~90 µs por lectura, frente a ~13 µs en el λ–t. No escala con el número de lecturas, y está sin
explicar. Coincide con lo que midió el prototipo sin `_sp` (Fase 17: 0.5–1.8 s). El `_sp` lo evita
con una sola lectura por píxel.

### 2026-09-29: ficheros por píxel, explorer frente al prototipo (ROADMAP E1.4)

**Método.**
- `bench/pixel_vs_prototype.py`: el `SpFits` del prototipo (`app/sources.py`) y el de explorer
  en el mismo proceso, tira de 32 px (la que elige la política en StorNext), 4 rondas ABBA de 10
  píxeles sorteados, cada uno en una fila que ninguna de las dos había leído.
- "En caché" es el píxel vecino, servido por la caché LRU de bloques de cada lector.
- bellatrix, `_sp.fits` del cubo de Stokes 6173, carga 0.4. Resultado en `bench/results/pixel_vs_prototype_bellatrix_20260929T1209.json`.

| Ronda | Prototipo, tira nueva | explorer, tira nueva |
|---|---:|---:|
| 1 (prototipo primero) | 33.9 ms | 21.5 ms |
| 2 (explorer primero) | 37.8 ms | 29.6 ms |
| 3 | 25.7 ms | 24.6 ms |
| 4 | 22.1 ms | 21.4 ms |
| Mediana | 29.8 ms | 23.1 ms |

En caché: 0.003 ms en las dos.

**Conclusión.**
- No es más lento en ninguna ronda. El 20 % a favor de explorer **no se da por bueno**: las dos
  leen la tira con un solo `pread` del mismo tamaño, sin diferencia de código que lo explique, y
  la dispersión de StorNext (22–38 ms) es mayor que la diferencia.
- 0 bloques distintos.
- En `tests/golden`, los bloques `_sp.fits` del cubo real son idénticos a los de la referencia.

**`icube`.**
- Solo el caso sintético tiene `_sp.icube`.
- La calibración coincide con la del prototipo dentro de 1e-12 relativo, y los bloques calibrados
  son idénticos.
- Diferencia buscada: cuando el píxel central es relleno, el prototipo deja la escala en 1 sin
  avisar; explorer prueba otros píxeles, y si ninguno tiene datos, da error.

### 2026-09-29: política de almacenamiento y memoria (ROADMAP E1.5)

**Comprobación en bellatrix, con el cubo de Stokes 6173 en StorNext.** La sonda y el guardián de
explorer, frente a los del prototipo (`app/policy.py`), en el mismo proceso:
- las dos sondas deciden lo mismo: `cvfs`, almacenamiento en red, tira de 32 px, 4 imágenes de
  lectura anticipada, 4 lectores y 64 hilos para `gather`;
- los dos guardianes dan 8 GB, el tope en Linux.

La lectura pequeña de explorer midió 0.01 ms porque la sonda del prototipo, con la misma semilla,
acababa de leer esos puntos. La decisión no depende de ella, porque `cvfs` está en la lista de
sistemas en red.

**Diferencia buscada.** En el reparto del presupuesto, la vuelta entera suma las imágenes de lectura
anticipada que decide la política (2 en disco local, 4 en red). El prototipo sumaba siempre 4.

### 2026-09-29: ejecutores (ROADMAP E1.6)

Traídos de `viewer.py` del prototipo (`_bg`, `_quv_bg`, `_slit_bg`, `_strip_pool`, `_series_job`,
`_lt_ready`), en `explorer.data.executors`:
- un hilo `numba` que ejecuta todo numba en paralelo; el número de hilos de numba se fija en ese
  hilo (es por hilo) con el valor de la sonda, como hacía el prototipo en `_bg`;
- un pool de E/S, un pool de franjas (`min(8, núcleos)`, como `_STRIPS`) y un hilo `background`
  para trabajos largos (rangos Q U V, franjas de rendija);
- `submit_latest`: un contador por clave; el trabajo no empieza si ya llegó una petición más nueva,
  y puede pararse entre pasos (espectro, luego λ–t), como `_series_job`;
- `ShownGate`: muestra un resultado salvo que ya haya uno más nuevo en pantalla, como `_lt_ready`.
  Se usará en `core` (E2). La medida que lo justifica está ahora en `measured.md`.

**Comprobación.** 200 peticiones desde 8 hilos a la vez: todas las lecturas `gather` se ejecutan en
el hilo `numba`, nunca dos a la vez, y dan los mismos valores que el FITS. Pasa en el Mac y en
bellatrix.

No hay prueba de velocidad propia. El coste de repartir el trabajo entre hilos se medirá junto con la
fachada `Dataset` (E1.10), frente al prototipo.

### 2026-09-29: ejes físicos, papeles y unidades (ROADMAP E1.7)

En `explorer.data.axes`, desde el código del prototipo:
- `from_fits` y `Axes` (`app/physics.py`);
- `roles` (`viewer.axis_positions`), que ahora devuelve también nt, ns y nl;
- `power_of_ten` y `plot_units` (`Viewer._set_spectra` y `_sample_ready`);
- `unit_text` y `fmt_signed`.

**Comprobación frente a las referencias del prototipo.**
- Sintético y cubo 6173 real (bellatrix): `axes.lam_nm`, `t_sec`, `corners`, `dlam_A` y `vel_kms`
  idénticos, sin tolerancia.
- Metadatos idénticos: línea, λ₀, continuo, BUNIT, esquinas, DATEREF, fuentes y UTC.
- Papeles de los ejes idénticos a `axis_positions`.
- La potencia de diez de I, calculada en el espectro del centro en el índice de arranque del visor,
  es la del visor: 1e-09 en el sintético.

**Diferencias buscadas.**
- `Axes.distortion` dice si la cabecera trae distorsión de λ. En 6173: `WCSDVARR CWDIS3 = Lookup`.
  Sigue sin aplicarse, como en el prototipo, y `source` no cambia.
- Una cabecera que no se puede leer deja además un aviso en el registro, no solo en `source`.

**Se conserva, anotado.** Si el continuo de un píxel no es finito o vale cero (relleno), Q, U y V
se quedan en las unidades leídas, aunque el título diga %. En relleno todo es NaN, así que no se ve.

**Unitarias:**
- cabecera sintética de SSTRED;
- continuo por sintonía aislada: con 5 sintonías no salta (2× la mediana del paso), con 12 sí;
- línea desconocida;
- distorsión;
- fichero sin WCS-TAB, y fichero que no es FITS;
- papeles por nombre y por orden SOLARNET;
- unidades de los espectros.

### 2026-09-29: estadística y núcleos (ROADMAP E1.8)

Desde `app/viewer.py` del prototipo:
- `explorer.data.kernels`: `reduce_u8_serial` y su reparto en franjas, y `absmax_*`;
- `explorer.data.stats`:
  - `limits` y `nice_range`;
  - la muestra de perfiles, de `_start_sample`, `_sample_job` y `_sample_ready`, partida en
    `sample_pixels`, `sample_profiles` y `sample_ranges`;
  - `quv_amplitude_ranges`, `quv_threads` (de `_quv_job`) y `quv_plot_ranges` (de `_quv_ready`).

**Comprobación frente a las referencias del prototipo**, en el sintético y en el cubo 6173 real
(bellatrix), todo idéntico sin tolerancia:
- `limits.*` y `reduce.*`;
- `meta.quv`: semianchos, ruido, píxeles con señal y percentil, en t = 0 y 2 en el sintético y en
  t = 93 en 6173;
- lo que calculaba el visor en marcha: los límites de la primera imagen, los rangos y de la muestra
  con Q, U y V sustituidos por los de las imágenes enteras, y `yquv`.

**Diferencias buscadas.**
- Sin fichero `_sp`, la muestra lee sus valores con una sola llamada a `gather` en el hilo de numba.
  El prototipo usaba un pool de Python con un `pread` por valor. Da los mismos valores (prueba
  unitaria frente al FITS y frente al `_sp`).
- Un cubo de enteros con BSCALE, BZERO o BLANK se convierte a valores físicos antes de calcular los
  rangos de Q, U y V. El prototipo leía los bytes como si fueran float (su `Cube` no admite
  BSCALE). Una prueba unitaria da lo mismo que el cubo float con esos valores.
- `quv_amplitude_ranges` exige un eje de Stokes y avisa si falta.

**Velocidad frente al prototipo** (bellatrix, 6173, 2026-09-29 13:16, carga 2.8–4.8, 64 hilos
de numba, 8 franjas, 4 rondas ABBA). Mediana de las medianas por ronda:

| Caso | Prototipo | explorer | Dispersión entre rondas |
|---|---|---|---|
| Reducción de una imagen entera, f = 1 | 5.58 ms | 5.52 ms | 5.5–5.6 |
| Reducción, f = 2 | 2.45 ms | 2.40 ms | 2.4–2.5 |
| Q U V, t sin leer | 846 ms | 752 ms | 726–926 frente a 704–767 |
| Q U V, releído | 571 ms | 559 ms | 536–603 frente a 550–574 |
| Muestra con `_sp` | 48 ms | 44 ms | 39–62 frente a 40–51 |
| Muestra sin `_sp` | 1555 ms | 1578 ms | 1474–1665 frente a 1540–1810 |

Todo está dentro de la dispersión, así que no se afirma ninguna mejora. En 32 comparaciones, 0
resultados distintos.

**Números que no se reproducen hoy.**
- La muestra sin `_sp` tardó 1.5–1.8 s con las dos implementaciones. En la fase anterior el
  prototipo medía 0.89–0.92 s en las mismas condiciones. Es igual para las dos, así que no es una
  regresión de explorer. Queda pendiente averiguar por qué: carga de StorNext o de la máquina.
- La reducción de 2044×2030 da 5.5 ms a f = 1 y 2.4 ms a f = 2. `measured.md` dice 1.45 ms con
  8 franjas, pero con una salida del tamaño de la pantalla, no de la imagen entera. Las condiciones
  no son las mismas, así que no se comparan.

Script: `bench/stats_vs_prototype.py`. Resultado: `bench/results/stats_vs_prototype_*.json`.

### 2026-09-29: rendijas (ROADMAP E1.9)

En `explorer.data.slits`, desde `app/viewer.py` del prototipo: `slit_path`, `slit_pixels`,
`read_slit_blocks` (con `pixel_runs` aparte), `read_slit_slab`, `read_slit_bands` y `frame_index`
(de `Viewer._frame_index`).

Ahora toda lectura pasa por `io.py`:
- `FrameReader.read_rows_raw`;
- `FrameReader.points`, que la muestra de perfiles usa en vez de calcular los offsets en `stats.py`;
- las imágenes para los rangos de Q, U y V se leen con `read_raw`, no con `os.pread` directo.

**Comprobación frente al prototipo**, en el sintético y en 6173 real (bellatrix):
- `slit_path` dentro de 1e-12 relativo;
- `slit_iy`, `slit_ix`, `slit_slab` y `slit_bands` idénticos;
- las pruebas de oro de E1.8 siguen idénticas tras el cambio de lecturas.

**Medidas** (bellatrix, 6173, rendija de ~600 px, ABBA). El banco `bench/slits_vs_prototype.py`
tuvo que corregirse dos veces:

1. **Rendijas distintas para cada lado.** Cada implementación tenía su propia rendija aleatoria, y lo
   que cuesta una rendija depende de su forma (filas que abarca, tramos seguidos). Salía losa 109
   frente a 72 ms y bandas t 398 frente a 191 ms, y no era una comparación válida. Ahora cada ronda
   usa una misma forma para los dos lados, cada uno en su mitad del campo, alternando mitades.
2. **Control A/A (`--aa`).** El prototipo contra sí mismo da 0.986 en frío, sin efecto de orden. Es
   el suelo de ruido de este diseño.

**Losa `_sp`.**
- Con el código portado tal cual: +2 % templado (41.07 frente a 40.13 ms).
- Causa medida: 0.83 µs más por llamada a `strip_read`, que se nota con cientos de llamadas en 64
  hilos bajo el GIL.
- Arreglo: `SpFits.strip_read` en un solo nivel, con la conversión decidida al abrir, y
  `read_slit_blocks` y `read_slit_slab` aceptan un pool ya abierto. Crear 64 hilos en cada rendija
  costaba 10–16 % de la losa templada.
- Resultado en 16 rondas: frío 0.914 (explorer más rápido en 11/16), templado 0.835 (15/16).

**Probado y descartado.** Losa leída en numba (tramos de longitud variable, `prange`, una sola
conversión):
- templado, 27 frente a 43 ms con muchos tramos, pero más lenta con pocos (26 frente a 21 ms);
- en frío, 1.51× más lenta con 32 hilos y 1.17× con 64 (más rápida en 0/12 y 2/12 rondas).

**Bandas λ:** iguales (7.1 frente a 6.9 ms).

**Bandas t en frío: resuelto.** El 3.5 % tenía dos causas. Se aislaron una a una, con el mismo
fichero y la misma rendija:

| Variante | Ratio en frío | Más rápido | Orden (explorer primero / segundo) |
|---|---|---|---|
| `preadv`, dos pasadas de 16 rondas | 1.072 y 1.075 | 6/16 y 7/16 | 1.17 / 0.95 |
| `os.pread`, como el prototipo | 1.058 | 6/16 | 1.17 / 0.96 |
| Con el mismo descriptor que el prototipo | 1.035 | 3/16 | 1.03 / 1.08 |

1. **NUMA.** bellatrix tiene 2 zócalos y 2 nodos NUMA.
   - Sin fijar el proceso, el coste por imagen es bimodal: ~960 frente a ~1270 µs (+30 %). El caso
     lento cambia entre dos ejecuciones idénticas: una vez los búferes numpy, otra vez los bytes.
   - Depende del nodo al que va a parar la memoria de cada búfer. No hay fallos de página.
   - Fijado al nodo 0 con `taskset`, desaparece. Todas las medidas finas se hacen así desde ahora.
   - El efecto de orden venía de otra cosa: el estado que el núcleo guarda por fichero abierto. En
     el banco hay dos ficheros abiertos sobre el mismo cubo; la app tiene uno solo.
2. **El GIL con 16 hilos.** Fijado al nodo 0, con un hilo explorer era igual (0.993–1.001). Con
   16 hilos era un 8–10 % más lento: por cada imagen hacía más trabajo en Python (comprobaciones,
   `np.empty` y `memoryview`, índice 2-D).
   - Resultado a contrapelo: un obrero más ligero, con los offsets calculados antes, fue un 8–15 %
     **más lento** (1.08–1.15).
   - El más rápido fue el obrero con la forma exacta del prototipo: offset y conversión dentro de
     cada obrero. Así queda `FrameReader.band_values`, que usa `read_slit_bands`. La comprobación de
     posiciones se hace una sola vez, fuera del obrero.

**Controles.**
- Una copia literal de la función del prototipo, dentro del mismo proceso, da 0.999–1.001.
- Con cinco variantes intercaladas la misma copia dio 0.915–0.967. Por debajo del ~5 %, con 16
  hilos, solo valen las comparaciones dentro de una misma ejecución y frente a esa copia.

**Final**, bellatrix, 6173, fijado al nodo 0:
- templado con 16 hilos, cuatro ejecuciones: 0.991–1.003, igual que la copia (0.993–1.005);
- en frío, 16 rondas ABBA:
  - bandas t: 1.008 (6/16), sin efecto de orden (1.01 / 0.99); templado 1.000;
  - losa: frío 0.930 (10/16), templado 0.729 (16/16);
- 0 resultados distintos.

**Retirado.** «Un búfer nuevo de numpy cuesta fallos de página»: medido, 0 fallos por imagen en el
caso real. La diferencia era NUMA.

**Hallazgo para E1.10.** En bellatrix, `NUMBA_NUM_THREADS` vale 32 (los núcleos), así que los 64
hilos de `gather` que decide la sonda se quedan en 32, en el prototipo y en explorer.

### 2026-09-29: fachada `Dataset` y estudio sin `_sp` (ROADMAP E1.10)

**`explorer.data.dataset.Dataset`.** Arma las piezas como `startup.open_cube` y `Viewer` del
prototipo:
- sonda de almacenamiento, guardián de memoria, reparto del presupuesto y ejecutores;
- un fichero por píxel que no se puede usar se ignora con un aviso;
- la calibración de un `_sp.icube` queda en el lector.

Las lecturas devuelven `Future`:
- una imagen o un bloque que ya está en caché vuelve como futuro terminado, sin salto de hilo
  (`FrameCache.peek`, `PixelReader.peek`);
- las imágenes que faltan se leen en un pool propio, con los trozos en el pool de E/S (16 hilos,
  como el `Cube` del prototipo);
- las series van al hilo de numba;
- las losas, a un pool que queda abierto.

`update_memory()` es el `_memory` del prototipo. `close()` cierra los pools y luego los ficheros.

**`explorer demo --sp | --nosp`.** Un paseo del cursor por el campo, con el origen desplazado al
azar en cada ejecución: imprime en cada movimiento el tiempo hasta el espectro y hasta el λ–t.

**Rendimiento frente al prototipo** (bellatrix, 6173, fijado al nodo 0, 8 rondas ABBA, 0
resultados distintos; el prototipo con su tope real de 32 hilos):

| Caso | Prototipo | explorer | Ratio (explorer más rápido) |
|---|---|---|---|
| Imagen en frío | 33.6 ms | 34.2 ms | 1.011 (4/8) |
| λ–t en frío | 406 ms | 370 ms | 0.91 (7/8) |
| Bloque `_sp` en frío | 20.8 ms | 20.2 ms | 0.992 (5/8) |

Estas cifras son con 64 hilos, que al final no se adoptaron (véase abajo). Sin ese cambio,
explorer y el prototipo usan los mismos hilos.

**El bloque `_sp` en frío.** Una primera pasada daba +2 ms (1.088), pero con carga ~5. Repetido con
carga 0.2, las cinco variantes quedaron entre 18.8 y 19.9 ms:
- prototipo directo, dos veces (A/A);
- nuestro lector, directo y a través del futuro;
- el del prototipo a través de nuestro pool.

El A/A ya difiere 0.9 ms, así que la diferencia de la primera pasada queda dentro del ruido.

**Aciertos de caché.** Una imagen en caché a través de la fachada cuesta 5.6 µs. De ellos, ~3 µs son
crear el `Future` (un objeto mínimo ya terminado costaría 0.27 µs). Se deja el `Future` estándar.
Frente a los ~13 ms de un movimiento del cursor es un 0.02 %.

**Estudio sin `_sp`** (bellatrix, fijado al nodo 0, lecturas que el proceso no había hecho, con los
contadores FC para confirmar que eran en frío):
- **Coste por petición.** Un fallo de 4 B va al SAN como una petición de ~4 KB, a ~12.5 ms.
- **Caché del sistema.**
  - Solo guarda esa página, y poco tiempo: el mismo píxel falla otra vez tras ~10 k lecturas, con
    38 GB libres.
  - A 30 filas ya es un fallo.
  - Un λ–t en caché aún cuesta ~24–33 ms, y no se midió por qué.
- **Hilos de numba**, límite del almacenamiento. λ–t / todo el píxel en frío:

  | Hilos | λ–t | Todo el píxel |
  |---|---|---|
  | 32 | 670 ms | 2730 ms |
  | 64 | 462 ms | 1783 ms |
  | 128 | 377 ms | 1468 ms |
  | 256 | 367 ms | 1359 ms |
  | 32 (A/A) | 675 ms | 2831 ms |

  El almacenamiento se satura hacia ~7000–7700 peticiones/s, y el mínimo ronda los 330 ms en todos.
- **io_uring:** bloqueado en bellatrix (`io_uring_disabled=2`, `EPERM` sin root).
- **λ–t progresivo** (cada 4.º t, luego cada 2.º, luego el resto), 64 hilos:
  - primera pasada en 136 ms, frente a 434 ms del λ–t completo;
  - el total tarda un 10 % más (477 ms);
  - la primera pasada interpolada no es fiel: error RMS del 12 % en I y del 34 % en V. A 20 s por
    barrido la estructura temporal no es suave en 80 s.
  - Solo serviría como vista previa mientras el ratón se mueve.
- **Resolución de pantalla:** no ayuda con 186 t. Solo con cubos de más t que píxeles tiene el
  panel.

**Descartado: 64 hilos fijos.** El tamaño del pool de numba se decide al importarlo, y en bellatrix
es 32. Probado, y no adoptado:
- **Con el almacenamiento cargado (tarde):** −33 % en el λ–t en frío.
- **Con el almacenamiento rápido (noche):** paseo del demo, 12 movimientos:
  - λ–t 276 frente a 287 ms, apenas un 4 %; recorta la cola lenta;
  - espectro 27 frente a 20 ms, más lento;
  - un λ–t en caché del sistema, 33 frente a 24 ms, más lento (0/8).
- **Por qué:** con poca espera por hilo, tantos hilos cuestan más de lo que ganan. Se queda el tamaño
  por defecto.
- **Abierto:** hilos por petición (E1.12) y vecinos desde la misma lectura (E1.13).

**Demo en bellatrix** (20:52, sin fijar, 12 movimientos):

| Modo | Espectro | λ–t |
|---|---|---|
| `--sp` | 19.4 ms | 19.4 ms |
| `--nosp` | 20–27 ms | 276–287 ms |

### 2026-09-29: pruebas de comparación del nivel 1 (ROADMAP E1.11)

`tests/golden/` compara con el prototipo todo lo que exportan sus referencias:
- imágenes, series y ficheros por píxel (`_sp.fits` y `_sp.icube` calibrado);
- ejes físicos y sus metadatos, papeles de los ejes y potencia de diez de I;
- límites de contraste y reducción a u8;
- rangos de Q, U y V, rangos y de la muestra y límites de la primera imagen del visor;
- rendijas: camino, píxeles, losa y bandas.

Dos pruebas nuevas en `test_references.py` hacen que siga siendo verdad:
- **Cobertura.** Cada tipo de resultado exportado tiene que estar en la lista de los que se
  comparan. Uno nuevo falla hasta que se escribe su comparación.
- **Referencia caducada.** Donde el prototipo está al lado, la huella de su código tiene que ser la
  que se guardó al exportar. Si cambió, hay que exportar otra vez y mirar con
  `tools/golden/compare.py` qué cambió.

**Resultado:**
- Mac: 14 pasan y 12 se saltan, porque la referencia real no está aquí.
- bellatrix: 26 pasan, con el caso real del 6173 y la misma huella del prototipo.

**Fase E1.** El criterio de salida de PLAN §6 se cumple:
- idéntico byte a byte donde toca;
- la misma latencia de E/S que el prototipo, o mejor, en ABBA;
- `explorer.data` se importa sin PySide6.

Quedan abiertas dos mejoras: E1.12 (hilos por petición) y E1.13 (vecinos desde la misma lectura).

### 2026-09-29: vecinos desde la misma lectura, sin `_sp` (ROADMAP E1.13)

**Idea.** Cada lectura de un λ–t sin `_sp` es una petición por imagen (2604 en 6173). Si pedir más
bytes por petición cuesta lo mismo, esa misma lectura puede traer los píxeles de alrededor.

**Tamaño de petición.** λ–t en frío, bellatrix, fijado al nodo 0, filas nuevas por Stokes, orden
rotado:

| Tamaño | Coste |
|---|---|
| 4 B | 1368 ms (base) |
| 16 KB | 1362 ms |
| 64 KB | 1005 ms |
| 176 KB | +22 % |
| 512 KB | +63 % |

- Con el almacenamiento así de lento, hasta 64 KB no cuesta más que 4 bytes.
- El λ–t de un vecino, sacado de lo guardado, cuesta 0.17–0.23 ms.
- En el mismo estado, las bandas de 1, 2, 4 y 8 filas salen a 0.89–0.98× de la lectura de 4 bytes.

**Frente al prototipo, con la fachada** (`bench/dataset_vs_prototype.py --rows`, 8 rondas ABBA):

| Bloque | Primer λ–t | Vecino (x + 1) |
|---|---|---|
| 8 filas (64 KB) | **1.339** (1/8) | 0.14 frente a 17.7 ms |
| 1 fila (8 KB) | **1.009** (4/8) | **0.10 frente a 17.6 ms** (8/8) |

- Con el almacenamiento rápido (~0.3 s por λ–t), 8 filas hacen la primera lectura un 34 % más lenta.
  Parte de ese 34 % puede venir de que las bandas de explorer calientan la caché del sistema en esas
  8 filas, y lecturas posteriores del prototipo caen en ellas.
- 1 fila no cuesta nada en la primera lectura y cubre todos los movimientos horizontales. Es el valor
  por defecto (`rowbands.ROWS`).

**Implementado:**
- `FrameReader.row_band` y `series_frames`;
- `data/rowbands.py`: un LRU por serie (índice fijo y ejes libres) dentro del presupuesto por píxel,
  con los mismos valores que `FrameReader.series`, y que lee solo el píxel si el bloque no cabe;
- `Dataset` lo usa solo en almacenamiento en red y sin `_sp`, y devuelve los aciertos como futuros
  terminados;
- demo: un segundo paseo de arrastre, en pasos de 1 píxel.

**Demo en bellatrix** (`--nosp`, 12 movimientos):
- saltos: λ–t ~258 ms, igual que antes;
- arrastre: el primer paso 261 ms; los pasos en la misma fila, 0.0–0.3 ms; bajar una fila es una
  lectura nueva, 251 ms, o 50 ms si parte ya está en la caché del sistema.

**Memoria.** Un λ–t de una fila ocupa 21 MB. El presupuesto de bellatrix guarda ~110 filas.

**Pendiente:**
- los movimientos verticales siguen siendo una lectura nueva;
- leer por adelantado la fila siguiente según la dirección del movimiento, con el cursor de E2.

### 2026-09-30: hilos por lectura dispersa (ROADMAP E1.12)

**Medida** (bellatrix, 2026-09-29 22:37, sin fijar, pool de 128). Lecturas en frío de una fila por
imagen, filas nuevas por Stokes, orden rotado, 18 lecturas por caso. Ratio frente a 32 hilos:

| Lectura | 8 | 16 | 32 (A/A) | 64 | 128 |
|---|---|---|---|---|---|
| Espectro (56 peticiones) | 2.02 | 1.15 | 0.92 | 0.86 | — |
| λ–t (2604 peticiones) | — | 1.63 | 0.81 | 0.56 | 0.42 |
| λ–t releído desde la caché del sistema | 0.95 | 0.94 | 1.00 | 1.35 | — |

- 128 hilos dan 261 ms, con p90 de 380 ms frente a 900 ms.
- El ruido entre ejecuciones de 32 hilos (A/A) es ~±20 %.

Solo la lectura desde la caché del sistema empeora con más hilos. Desde E1.13 ese caso casi no
ocurre: una fila leída otra vez sale de la memoria de explorer (~110 filas), y el sistema guarda solo
~50 MB.

**Implementado:**
- `_numba.py`: el pool de numba tiene al menos 128 hilos, salvo que se fije `NUMBA_NUM_THREADS`.
- `gather.gather_limited`: cada lectura usa un hilo por petición, hasta el límite de la sonda y del
  pool.
- La sonda pasa a 128 en red (el 64 del prototipo venía de lecturas de 4 bytes) y sigue en 16 en
  local.
- La losa de rendija se queda en 64 hilos de Python, lo medido en E1.9.

**Frente al prototipo** (bellatrix, 2026-09-30 09:35, sin fijar, 8 rondas ABBA; el prototipo con su
tope real, min(64, CPU) = 32; 0 resultados distintos):

| Caso | Ratio (explorer más rápido) |
|---|---|
| Imagen | 0.991 (4/8) |
| λ–t en frío | **0.94 (8/8)**, 240 frente a 256 ms |
| λ–t del vecino | 0.13 frente a 28.2 ms |
| Bloque `_sp` | 1.025 (3/8) |

Esa mañana el almacenamiento iba rápido; con él cargado, la ganancia esperada es mayor (0.42).

**Incidente, 2026-09-30 ~09:30.**
- Una cadena de órdenes siguió tras fallar `ssh -O check`: un `;` en lugar de abortar. Abrió una
  conexión nueva por login2 (con `BatchMode`), que pasó a ser el maestro.
- La sincronización se había saltado, así que esa ejecución midió el código viejo. Se descartó y se
  repitió.
- Desde entonces cada paso remoto aborta si falla la comprobación.

### 2026-09-30: estado del visor y un aviso por ráfaga (ROADMAP E2.1)

**Decisión previa.** [ADR 0007](decisions/0007-core-sin-qt.md): `explorer.core` sin Qt. Un contrato
de `lint-imports` lo comprueba.

**Implementado:**
- **`core/loop.py`:** `Loop`, con `call_soon` (la próxima pasada del bucle) y `post` (llevar algo al
  hilo principal desde cualquier hilo). `ManualLoop` no ejecuta nada hasta `pump()`, así que la
  prueba decide el orden. La versión de Qt llega en E3.
- **`core/state.py`:**
  - `ViewState` inmutable: t, s, λ, cursor, bloqueo, camino, reproducción y paneles visibles (el
    planificador los necesita para no leer para un panel oculto; el plan no los listaba).
  - `Store.set(**campos)` da un aviso por ráfaga, con los campos que difieren del último aviso,
    como el temporizador de 0 ms del prototipo (`Viewer._hover_timer`). Un campo cambiado y
    devuelto dentro de la ráfaga no se avisa.
  - Un oyente que falla no silencia a los demás; va al registro.

**Pruebas (7):**
- una ráfaga da un aviso;
- sin cambio no hay aviso;
- las ráfagas se miden contra el último aviso;
- el estado es inmutable y se rechazan campos desconocidos;
- los oyentes están aislados;
- desuscribirse y los cambios hechos durante un aviso;
- `post` desde 8 hilos se ejecuta en el hilo que bombea.

**Coste** (Mac M1, 20 000 movimientos × 5): 4.3 µs por movimiento con su aviso, 2.7 µs por `set`
dentro de una ráfaga. Es ~0.05 % de los 6–15 ms que cuesta un movimiento del cursor en el
prototipo.

### 2026-09-30: la sesión con un cubo (ROADMAP E2.2)

**Implementado:** `core/session.py`, desde `Viewer` del prototipo (`__init__`, `set_index`, `_step`,
`_on_hover`, `set_locked`) y el §3.2 del plan de ventanas enlazadas.
- **Estado inicial:** λ en `nl // 2` y el cursor en el centro de la imagen, como el prototipo.
- **`hover`:**
  - no hace nada con el cursor bloqueado;
  - recorta el píxel a la imagen;
  - con el mismo píxel no hace nada y suma el contador `core.hover.same_pixel`, que en el prototipo
    era `stats["skipped_same_pixel"]`.
- **`set_index` y `step`:** recortan al eje. `step` da la vuelta solo con `wrap`, que es lo que usa
  la reproducción. Un eje que el cubo no tiene se ignora.
- **`lock` y `show`:** los paneles visibles están en el estado.
- **`index(member)`:** el índice de los ejes delanteros que necesitan las lecturas de ese cubo.
- **Preparado para varios cubos:**
  - miembros y maestro del tiempo;
  - λ y Stokes de cada cubo, enlazados o no (decisión D3);
  - `add()` rechaza un segundo cubo hasta E8, donde está la correspondencia de píxeles y tiempos.

**Pruebas (7):**
- el estado inicial del prototipo;
- `hover`: recorte, bloqueo y mismo píxel;
- recorte y vuelta en los índices;
- una ráfaga de pasos da un aviso;
- un cubo sin Stokes;
- paneles, y el rechazo del segundo cubo;
- con un `Dataset` real (sintético): la imagen de `index()` es la de los datos.

Pasa en el Mac y en bellatrix.

### 2026-09-30: qué se lee y qué se muestra tras cada cambio (ROADMAP E2.3)

**Implementado:** `core/scheduler.py`, desde `set_index`, `show_frame`, `_update_cursor`,
`_series_job` y `_lt_ready` del prototipo. Los resultados van a un `Sink` (imagen, espectros, λ–t,
paneles vaciados), que en E3 será la interfaz y en las pruebas un registro.

**Qué dispara cada cambio:**
- **t, Stokes o λ:** la imagen del nuevo índice y la lectura anticipada a lo largo del eje que se
  movió. Los paneles del cursor se evalúan al llegar esa imagen, porque es la que dice si el cursor
  está sobre relleno. En el prototipo la imagen se leía antes, en el hilo de la ventana; aquí llega
  como futuro ([ADR 0007](decisions/0007-core-sin-qt.md)).
- **El cursor:** espectros y λ–t. **t:** solo los espectros. **Stokes:** solo el λ–t. **λ:** nada,
  porque las marcas son de la interfaz. **Mostrar un panel:** ese panel.
- **Nada** para un panel oculto, ni sobre relleno (NaN, o 0 exacto en Stokes I). Con relleno los
  paneles se vacían una sola vez.

**Lecturas:**
- **Con `_sp`:** el bloque del píxel. Si está en caché, sin salto de hilo.
- **Sin `_sp`:**
  - desde las filas en memoria si las tienen (`Dataset.peek_series`, nuevo), al momento;
  - si no, en el hilo de numba: el espectro primero y el λ–t después (`Dataset.read_series`,
    nuevo);
  - el trabajo se salta si llegó una posición más nueva antes de empezar, o entre las dos lecturas.
- **Regla de pantalla:** se muestra un resultado salvo que ya haya uno más nuevo
  (`executors.ShownGate`).

**Arreglo frente al prototipo.** Sin `_sp`, un paso en t o en Stokes que saca el cursor del relleno
rellenaba solo el panel de ese eje y dejaba el otro vacío: `_cleared` solo se usaba con `_sp`.
Aquí, tras el relleno, el siguiente píxel válido rellena los dos paneles haya cambiado lo que haya
cambiado. Hay una prueba de ello.

**Pruebas (12).** Con el cubo sintético, con y sin `_sp`:
- el arranque;
- qué lee cada cambio;
- paneles ocultos;
- relleno.

Con un cubo de prueba cuyas lecturas suelta la prueba:
- el trabajo viejo se salta antes de leer: de 4 posiciones seguidas solo se leen la primera y la
  última;
- una imagen vieja nunca sustituye a una más nueva;
- una ráfaga de pasos pide una sola imagen;
- la vuelta desde el relleno sin `_sp`.

10 de 10 ejecuciones en el Mac y 3 de 3 en bellatrix, sin fallos intermitentes.

### 2026-09-30: cubos sin cabecera de ejes (ROADMAP E1.14)

**Problema** (medido con FITS sin cabecera). Sin CTYPE, un cubo de 3 o de 4 dimensiones se quedaba
sin papeles: solo la imagen, sin espectro, sin λ–t y sin pasos. El `axis_positions` del prototipo
solo supone el orden con exactamente tres ejes delanteros, y explorer lo había traído tal cual.

**Regla, decidida por el usuario:**
- **4-D sin nombres:** (t, λ, y, x) por defecto.
- **3-D:** puede ser (t, y, x) o (λ, y, x), así que se trata como caso general. El eje se recorre y
  se dibuja como un perfil en índices, y la interfaz no lo llama λ ni t (`Roles.how == "unknown"`).
- **5-D:** en orden SOLARNET, como antes.
- **`--axes`** dice otra cosa: una letra por eje delantero, del más lento al más rápido (`t`, `s`,
  `l`), p. ej. `s,l` o `t`. Un valor mal formado se rechaza.
- **`Roles.how`** dice de dónde salieron los papeles: `header`, `SOLARNET order`,
  `default (t, lambda)`, `unknown` o `--axes`.

**Arreglo en el planificador.** Pide espectro solo si hay λ, y λ–t solo si hay t y λ. Una serie
temporal (`--axes t`) queda con la imagen y sus pasos. Su panel natural sería una curva de luz, que
el plan deja para después.

**Pruebas:**
- `roles` por nombre y por número de ejes, `--axes` y sus errores;
- de punta a punta (`Dataset`, `Session`, `Scheduler`) con FITS sin cabecera: 4-D por defecto,
  4-D `s,l`, 3-D desconocido, 3-D `t` y 5-D. Pasos, espectros y λ–t en índices.

El demo acepta `--axes`.

### 2026-09-30: niveles de contraste (ROADMAP E2.4)

**Lo que había en el prototipo.** No eran seis copias iguales, sino dos reglas:

| Dónde | Regla |
|---|---|
| Imagen (`limits`, en caché en `_limits`) | submuestra `[::8, ::8]`, valores finitos y distintos de 0; I entre los percentiles 1 y 99; Q, U y V simétricos al p99 de \|v\|; caché por (índice, Q U V o no), LRU de 4096 |
| λ–t y cortes de rendija (`_set_lt`, `_paint_slice`) | todos los valores finitos, ceros incluidos; p1–p99, o mín–máx con 10 valores o menos; (0, 1) si nada es finito |

Además, `look.py` pone el λ–t y los cortes simétricos en Q, U y V (p99 de |v|, si es mayor que 0),
y `_toggle_fix` / `_image_refit` fijan los niveles de la imagen.

**Implementado:** `core/levels.py`, con las dos reglas en un solo sitio (`image_levels`, que es
`stats.limits`, ya idéntico al prototipo en las pruebas de oro, y `panel_levels`), la caché y el
modo fijo.
- El planificador calcula los niveles y los pasa con cada imagen y cada λ–t.
- `Scheduler.fix_levels(on, refit)` es el candado de la imagen.

**Diferencia buscada.** El prototipo guardaba un solo par de niveles fijos: fijados en I, Q se
seguía pintando con el rango de I. Aquí se guardan aparte para I y para Q U V.

**Pruebas (5):**
- la regla de la imagen es la del prototipo;
- la regla del λ–t, con sus casos límite (todo NaN, pocos valores, plano, |v| = 0);
- caché por índice, con desalojo, y niveles fijos separados para I y para Q U V;
- con el planificador sobre el cubo sintético:
  - la imagen llega con sus niveles, y fijados se mantienen al cambiar t;
  - V tiene los suyos, simétricos;
  - el λ–t de V es simétrico.

### 2026-09-30: rangos y de los espectros (ROADMAP E2.5)

**Implementado:** `core/yrange.py`, desde `_set_spectra`, `_yfit`, `_set_yfixed`, `_lock_spectra`,
`_ysample_fixed`, `_sample_ready` y `_quv_ready` del prototipo. Tiene la lógica y nada más: qué
rango lleva cada panel y cuándo cambia. Usa las funciones ya verificadas en E1.7 y E1.8
(`power_of_ten`, `plot_units`, `sample_ranges`, `quv_plot_ranges`).

**Unidades.** La potencia de diez de I sale del primer espectro con datos o de la muestra, lo que
llegue antes. Q, U y V van en % de I_c si se conoce la sintonía del continuo.

**Candado abierto** (el arranque, como en el prototipo):
- mientras el cursor se mueve, el rango solo crece, a valores 1-2-5;
- en reposo (0.4 s sin espectro nuevo), cada panel pasa al rango de su propio perfil.

**Candado cerrado:**
- los rangos de la muestra de 100 perfiles, fijos;
- Q, U y V desde imágenes enteras, pedidos la primera vez que se cierra, y mientras llegan Q, U y V
  conservan el suyo.

**Acciones:**
- `fit()` (tecla F, clic derecho en el candado): cada panel al perfil que se ve, y fijo ahí;
- `to_sample()` (Shift+F): los rangos de la muestra;
- `reset()`: la muestra si está fijo, el perfil si no.

**Planificador:**
- lanza la muestra 300 ms después de la primera imagen, en el hilo de numba;
- lanza Q, U y V en el hilo de fondo, para no retrasar el cursor;
- pasa los espectros al `Sink` ya en las unidades de los paneles, con `y_range(k, rango)` y
  `units(iscale)`.

**Bucle.** `call_later(segundos, fn)`. En `ManualLoop` hay un reloj virtual (`advance`), así que las
pruebas no esperan de verdad. Un temporizador que se reinicia marca la llamada anterior como vieja.

**Pruebas (5):**
- crecer al mover, y ajustar en reposo con el reinicio del temporizador;
- Q, U y V en %;
- el candado toma la muestra, y luego Q, U y V de imágenes enteras, pedidos una sola vez;
- `fit` y `reset`;
- con el planificador sobre el cubo sintético: los rangos de la muestra y los de Q, U y V son
  exactamente los de las funciones ya comparadas con el prototipo.

Planificador, niveles y rangos: 5 de 5 ejecuciones seguidas pasan. También pasa en bellatrix.

### 2026-09-30: rango y a mano, y `testing.Driver` (ROADMAP E4.1 en el núcleo, E2.6)

**Rango y a mano.** A petición del usuario, arrastrar el eje y de un espectro ajusta su rango.
- **En el núcleo:**
  - `YRange.manual(k, rango)` fija ese panel, y las reglas automáticas (crecer, ajustar en reposo)
    lo dejan en paz;
  - `auto(k)` (doble clic en el eje) lo devuelve;
  - F, reset, Shift+F y el candado también lo devuelven.
- **El gesto** (arrastrar para mover, rueda o botón derecho para estirar) es de la interfaz: nueva
  fila E4.1. Sobre la curva, arrastrar sigue eligiendo λ, como en el prototipo.

**`testing.Driver`** (`testing/driver.py`). La API pública con la que las pruebas manejan el núcleo
sin pantalla (plan §2, regla 11):
- tiene un `Dataset`, una `Session` sobre `ManualLoop` y un `Scheduler`;
- su `Sink` guarda en `Shown` lo que se dibujaría: imagen, espectros en las unidades de los paneles,
  λ–t, niveles, rangos y, cuántas veces llegó cada cosa;
- acciones: `hover`, `step`, `set_index`, `set_stokes`, `lock`, `show`, `fix_levels`, `set_y_fixed`,
  `fit_y`, `reset_y`;
- tiempo: `pump`, `advance`, `wait_idle`.

**Pruebas (10)**, con y sin `_sp`, sobre el cubo sintético:
- lo dibujado es el dato (imagen, λ–t, espectro en sus unidades);
- una ráfaga de 10 movimientos lee una vez;
- relleno, bloqueo y paneles ocultos no leen;
- un paso en t redibuja solo los espectros;
- muestra y candado de los rangos y.

5 de 5 ejecuciones en el Mac y 3 de 3 en bellatrix.

**Criterios de salida de E2** (plan §6), ya cubiertos:
- lo viejo nunca llega a pantalla (E2.3);
- una ráfaga da un aviso y una lectura (E2.1, E2.6);
- nada se lee sobre el relleno (E2.3, E2.6).

Falta E2.7: el coste de las capas frente al prototipo.

### 2026-09-30: coste de las capas del núcleo (ROADMAP E2.7) y cierre de E2

**Método** (`bench/core_overhead.py`). Cada operación se hace de dos maneras, sobre datos nuevos y
en ABBA:
- a través del núcleo (`testing.Driver`: estado, aviso, planificador, niveles, rangos y, entrega al
  `Sink`);
- directamente, con las mismas lecturas sobre el `Dataset`.

La diferencia es lo que cuestan las capas. explorer aún no dibuja, así que el cursor completo frente
al prototipo llega con E3–E4.

**Condiciones.** bellatrix, cubo 6173, 2026-09-30 10:53, fijado al nodo 0, 8 rondas de 10.

| Caso | Con `_sp`: núcleo / directo | Sin `_sp`: núcleo / directo |
|---|---|---|
| Cursor a una fila sin leer | 20.7 / 21.1 ms | 364 / 368 ms |
| Cursor al vecino (en caché) | 0.36 / 0.01 ms | 0.54 / 0.17 ms |
| Paso en t (imagen y espectros en el nuevo t) | 2.8 / 4.3 ms | 26.1 / 26.8 ms |

**Conclusión:**
- En frío y en los pasos, las capas no cuestan nada medible: las diferencias están dentro del ruido.
- En un movimiento a un píxel ya en caché añaden ~0.35 ms: pasar el dato a lo que se dibuja
  (unidades, rangos y, niveles del λ–t, avisos), trabajo que el prototipo también hacía en su
  ventana.
- Es ~3 % del cursor del prototipo (13.5 ms, dibujo incluido), y muy por debajo de un fotograma
  (16 ms).

**Sin medir:** el bucle de eventos de Qt y el dibujo. Llegan con E3–E4, cuyos criterios ya comparan
el cursor y los pasos con el prototipo.

**E2 cerrada.** Hecho:
- estado y avisos por ráfaga;
- sesión;
- planificador (la última gana, espectro antes que λ–t, nada sobre el relleno ni para paneles
  ocultos);
- niveles de contraste;
- rangos y, con rango a mano;
- `testing.Driver`;
- coste de las capas.

Diferencias buscadas frente al prototipo, cada una anotada en su entrada:
- el relleno sin `_sp`;
- los niveles fijos, por separado para I y para Q U V;
- los espectros solo si hay λ.

### 2026-09-30: cómo llegan las ventanas a la pantalla (ROADMAP E3.2)

**Implementado:** `platform/plan.py`, con `choose_display(env, sys.platform, --x11,
bridge_available) -> DisplayPlan`. Es una función pura, desde la tabla del prototipo
(`startup.prepare`, `remote_x11`, `xbridge.wanted`):
- **Linux sin pantalla** (`DISPLAY`, `WAYLAND_DISPLAY` y `QT_QPA_PLATFORM` sin fijar): se para con
  un mensaje, porque Qt aborta con un volcado de memoria.
- **`QT_QPA_PLATFORM` fijado por quien lanza:** se respeta, y nunca se cambia por el puente. En el
  prototipo, las pruebas `offscreen` lanzadas por ssh abrieron ventanas en el Mac del usuario.
- **`--x11 native|bridge`**, o `EXPLORER_X11`, gana sobre lo automático.
- **Pantalla remota** (ssh y `DISPLAY` que no es `:N`; en un Mac, cualquier `DISPLAY`
  bajo ssh): el puente. Hasta E6 se usa el xcb de Qt, con una nota.
- **Linux local:** xcb (o el Wayland de Qt si solo hay Wayland). **Mac local:** cocoa.
- **Mac por ssh sin X:** se para con un mensaje. El prototipo lo descubría después de arrancar Qt,
  por la lista de pantallas vacía.
- `DisplayPlan.kind` da una clave por modo de mostrar, para guardar la disposición de las ventanas.

Un contrato de capas impide que `platform.plan` importe Qt.

**Pruebas (18):** la tabla, caso por caso, en Linux y en Mac, con y sin puente, más los mensajes y
las claves. Pasa en el Mac y en bellatrix.

### 2026-09-30: el bucle de Qt para el núcleo (ROADMAP E3.3)

**Implementado:** `ui/loop.py`, `QtLoop`, el adaptador que pedía el
[ADR 0007](decisions/0007-core-sin-qt.md). Es la primera pieza de `explorer.ui`.
- **`call_soon`:** un `QTimer` de 0 ms, como el temporizador con el que el prototipo agrupaba los
  movimientos del ratón.
- **`call_later`:** un `QTimer` con retardo.
- **`post`:** una señal en cola. Se emite desde cualquier hilo y la función corre en el principal.
- **Una llamada que falla** va al registro, y las demás siguen.

**Capas:**
- nuevo contrato: `ui` no importa la orden, `doctor` ni `demo`;
- las pruebas con Qt usan un `QApplication` compartido (fixture `qapp`), siempre `offscreen`.

**Pruebas (3):**
- `post` desde 8 hilos, `call_soon` y `call_later` corren en el hilo principal, en su orden, y
  `call_later` tras su retardo;
- una llamada que falla va al registro y el bucle sigue;
- un `Scheduler` real sobre el cubo sintético, sin `_sp`: lecturas en el hilo de numba, una ráfaga
  de 10 movimientos y un paso en t. Todo lo que llega al `Sink` llega en el hilo principal.

5 de 5 ejecuciones en el Mac y 3 de 3 en bellatrix.

### 2026-09-30: `Display` para cocoa, xcb y offscreen (ROADMAP E3.4)

**Implementado:** `platform/display.py`, desde `startup.py` del prototipo (`prepare`, `make_app`,
`show`, `_mac_zoom_not_fullscreen`, `start_link_probe`):
- **`prepare_env()`:** pone lo que pide el plan (`QT_QPA_PLATFORM`) antes de arrancar Qt, o se para
  con su mensaje (`NoDisplay`).
- **`make_app()`:** crea el `QApplication`, o usa el que ya hay. Se para con un mensaje si Qt no ve
  ninguna pantalla, que es lo que pasa en un Mac por ssh sin X11. Fusion fuera de cocoa; el aspecto
  llega en E5.
- **`attach(app, ventana) -> WindowOps`:** muestra la ventana, la sube y le da el teclado, como el
  `show` del prototipo (si no, la primera tecla iba a la terminal). En un Mac local, el botón verde
  maximiza en vez de abrir pantalla completa.
- **`link()`:** para X11 remoto, los 4.8 B/px y el tope de 30 fps que midió el prototipo. La medida
  en vivo del enlace llega con el puente (E6).
- **`WindowOps`:** `resize`, `activate`, `zoom` y `minimize`. Las vistas solo ven esto.

**Para E6.1** (foco sin clic), anotado en su fila: el prototipo ya pide el foco al mostrar la
ventana, y aun así por `ssh -Y` hace falta un clic.

**Pruebas (3, offscreen):**
- el entorno que prepara, y la parada con mensaje;
- la aplicación (nombre, estilo) y una ventana adjuntada, con su tamaño;
- el enlace y el informe, según el plan.

Pasa en el Mac y en bellatrix.

### 2026-09-30: el panel de imagen (ROADMAP E3.5)

**Implementado:** `ui/imageview.py`, desde `backend_pgr.py` y `backend_pg.py` del prototipo, con la
reducción parcheada de `viewer.py` y su `ViewGuard`.
- **Superficie:** una `ViewBox` de aspecto bloqueado, un `ImageItem` y la cruz del cursor.
- **Solo la región visible:** reducida a los píxeles físicos de la vista, a u8, en una pasada
  (`kernels.reduce_u8`, en franjas). Nivel 0 para el relleno, datos en 1..255.
- **Un zum o un desplazamiento** vuelven a pintar. Una ráfaga pinta una vez, con un temporizador de
  0 ms.
- **`ViewGuard`,** traído tal cual con comentarios neutros:
  - no más fuera que la imagen entera;
  - como mucho 3×3 píxeles de dato dentro;
  - al alejar, se recentra poco a poco;
  - el centro nunca sale de la imagen.
- **El ratón** da (y, x) en píxeles de dato. `show_all()` es el doble clic del prototipo.
- **La conversión numba de pyqtgraph, apagada.** Costaba ~22 ms fijos por imagen, y aquí la imagen
  ya llega en u8.

Los gestos (doble clic, la mano al arrastrar) y la conexión con la sesión y el planificador van en
la ventana (E3.6).

**Pruebas (3, offscreen):**
- lo que se entrega a pyqtgraph es la reducción de la región visible, con el relleno en 0;
- el zum se queda entre la imagen entera y 3×3 píxeles, y dentro pinta a resolución completa;
- el ratón da píxeles de dato y la cruz va al cursor.

Pasa en el Mac, 3 de 3 ejecuciones, y en bellatrix.

### 2026-09-30: la ventana mínima y `explorer cubo.fits` (ROADMAP E3.6)

**Implementado:**
- **`ui/shell.py`, la ventana.** El panel de imagen, una línea de estado (x, y, t, λ, Stokes, valor
  o relleno, bloqueado) y las teclas.
  - Une vista, sesión y planificador: el ratón mueve el cursor; un clic lo mueve ahí y lo bloquea;
    el derecho lo suelta; el doble clic enseña la imagen entera.
  - La cruz sigue al cursor.
  - Cada segundo, el presupuesto de memoria se ajusta (`Dataset.update_memory`, el `_memory` del
    prototipo).
- **Teclas,** en una sola tabla desde `_key_table`: ← → para λ, ↓ ↑ para t, 1–4 para Stokes, L,
  Esc, Ctrl+W, Ctrl+M y Ctrl+Q (en el Mac, ⌘Q es el del menú).
- **`ui/app.py`:** plan de pantalla, `Display`, aplicación, `Dataset` y ventana. Imprime el tiempo
  hasta la primera imagen en pantalla.
- **`explorer cubo.fits`** abre la ventana, con `--sp`, `--nosp`, `--axes`, `--x11` y
  `--quit-after S`, este último para medir, como el del prototipo.
- **El demo** abre el visor tras `doctor`, y ya no la ventana en blanco de 2 s. Con `--no-window`
  hace los paseos del cursor.
- **Ruido de `offscreen` filtrado:** solo los mensajes que filtraba el prototipo.
- **`Executors.n_strips`,** público, en vez de leer un atributo privado del pool.

**Arreglo frente al prototipo.** En `_key_table`, la fila de las teclas de Stokes estaba sangrada
dentro de `if self.ta is not None:`, así que un cubo sin t no tenía teclas de Stokes. Aquí dependen
solo de que haya Stokes. Hay una prueba con un cubo `--axes s,l`.

**Pruebas (4, offscreen):**
- primera imagen, teclas y estado;
- el ratón mueve el cursor y la cruz;
- teclas de Stokes sin t;
- `explorer cubo.fits --quit-after` de punta a punta.

3 de 3 ejecuciones en el Mac. Pasa en bellatrix.

**Primera medida, sin ABBA** (bellatrix, cubo 6173, offscreen): primera imagen en 1.83–2.43 s desde
el principio de la apertura. La línea base del prototipo en offscreen era 1.58–1.92 s. La
comparación de verdad es E3.7.

### 2026-09-30: el puente X11 traído tal cual (ROADMAP E6, opción A de P4)

**Implementado** (commit `0411db0`): el puente del prototipo (`app/xbridge.py`, `xconn.py`,
`xrender.py`) en `platform/xbridge/`, partido por temas y con sus decisiones medidas y sus mandos:
- `bridge.py`: la conexión del hilo de la interfaz, el tic de 4 ms y el filtro de eventos de Qt;
- `wm.py`: ventanas X, ICCCM y EWMH, paneles transitorios, formas, cursores, iconos, activación;
- `qtinput.py`: la entrada X a Qt por la puerta de plataforma (ctypes), con la vía antigua de
  reserva;
- `transport.py`: teselas de 32×32, gris a 1 B/px por RENDER, doble búfer y el codificador numba,
  en su propio hilo y conexión;
- `render.py`, `clipboard.py`, `xconn.py`, y `state.py` (el estado compartido, para `mypy`);
- `display.py`: `BridgeDisplay`, que el plan elige cuando python-xlib se importa, y
  `BridgeWindowOps`, que sustituye al `BridgeMover` del prototipo.

`platform/linkprobe.py` también, sin arrancarlo: lo usa la reproducción (E4). El plan decía
`x11bridge/`; el directorio es `xbridge/`.

**Diferencias con el prototipo:**
- Las piezas de la barra de título (forma, bordes, ventana activa, marco propio) son llamadas de
  `WindowOps` (`set_shape`, `set_resizer`, `active`) en vez de atributos `_crispex_*` en los
  widgets. La barra propia llega en E5; hasta entonces el gestor de ventanas pone el marco.
- No se traen el modo de repintado `window` (medido sin ganancia) ni el mando del intervalo del
  GIL.
- Mandos `EXPLORER_XB_*` en vez de `CRISPEX_XB_*`, leídos una vez.
- `close()`: para el temporizador, espera al hilo emisor y cierra las conexiones. El prototipo
  nunca cerraba.
- La caché de numba del puente va a la del usuario, como los demás núcleos.
- No se fuerza el tema oscuro con el puente: el aspecto llega en E5.

**Pruebas:**
- Sin X (13): el codificador numba da los mismos bytes que python-xlib; teselas numba frente a
  numpy; tramos; teclas; cookies; formatos de RENDER; los símbolos privados de Qt 6.11.2 están
  todos; el plan elige `BridgeDisplay`.
- Sobre un Xvfb privado (7, en un proceso aparte): los píxeles de la ventana X son los de Qt (0
  distintos); una tecla X mueve t; un movimiento X mueve el cursor al píxel de dato que toca; la
  vía antigua de entrada; panel flotante transitorio y de tipo utilidad; menú emergente
  `override-redirect`; forma (24 rectángulos) y su retirada; portapapeles en los dos sentidos;
  estadísticas de tráfico; salida con 1 cuando X desaparece. 3 de 3 en bellatrix. Se saltan sin
  `EXPLORER_XVFB_DISPLAY=:N`.
- `scripts/check.sh` pasa en el Mac (las pruebas X se saltan) y en bellatrix.

**Medida** (commit `eb77c6f`):
- bellatrix, 2026-09-30 13:00–13:08; Xvfb privado `:98` (3840×1080, sin gestor de ventanas);
  cubo de Stokes 6173 (StorNext).
- Fijado al nodo NUMA 0 (16 CPU), con el cerrojo de medidas. Carga 3.3 al empezar la primera tanda
  y 38 al acabar; 18 durante la segunda.
- Una ejecución de calentamiento por programa y configuración.
- Resultados en `bench/results/` de la carpeta de la medida: `bridgeA_20260930T1300.json` y
  `bridgeA_ab8_20260930T1306.json`.

**Solo el puente** (`--modes bridge-ab`): la ventana de explorer con el puente del prototipo (P) y
con el de explorer (E). Cada paso espera a estar en X. 8 rondas ABBA; mediana P / E, razón
pareada E/P y rondas en que E fue más rápido.

| | con `_sp` | sin `_sp` |
|---|---|---|
| Primera imagen enviada a X, s | 1.005 / 1.000; 1.005 (4/8) | 0.927 / 0.917; 0.986 (4/8) |
| Primera imagen vista en X desde la orden, s | 2.27 / 2.22; 1.03 (4/8) | 2.15 / 2.20; 1.06 (4/8) |
| Paso en t hasta X, ms | 21.2 / 20.5; 0.92 (6/8) | 67.7 / 64.4; 0.90 (6/8) |
| Paso en λ hasta X, ms | 17.9 / 18.2; 1.02 (3/8) | 17.6 / 17.5; 1.00 (5/8) |
| Stokes hasta X, ms | 14.4 / 13.5; 0.91 (6/8) | 54.5 / 53.9; 0.92 (6/8) |
| Bytes por paso (t, λ, Stokes) | 612 300, 612 230, 612 396 en los dos | iguales en los dos |

- Los bytes por paso y por envío son idénticos: mismas teselas, mismo gris, mismas peticiones.
- Tiempos dentro del ruido: la primera tanda de 4 rondas dio razones de 1.01–1.11 con `_sp`
  (0–1 de 4 a favor de E) y 0.94–0.97 sin `_sp`. Con 8 rondas, 0.90–1.06.
- **Efecto del orden:** en cada par, el primero en ejecutarse tarda ~2.5 s en verse y el segundo
  ~1.9 s. Sin ABBA saldría una diferencia falsa de ~25 %.

**Programa contra programa** (`--modes bridge`): cada uno con su puente, 4 rondas ABBA; P / E,
razón y rondas a favor de E. Los pasos se miden hasta que Qt pinta, como en el `selftest` del
prototipo, y no hasta X.

| | con `_sp` | sin `_sp` |
|---|---|---|
| Primera imagen (tras crear la aplicación), s | 1.55 / 1.02; 0.66 (4/4) | 1.74 / 0.87; 0.50 (4/4) |
| Primera imagen vista en X desde la orden, s | 3.18 / 2.57; 0.81 (4/4) | 3.38 / 2.15; 0.63 (4/4) |
| Paso en t, ms | 19.4 / 17.2; 0.88 (4/4) | 19.1 / 46.5; **2.49 (0/4)** |
| Paso en λ, ms | 20.8 / 16.0; 0.77 (4/4) | 22.0 / 15.4; 0.71 (4/4) |
| Stokes, ms | 12.4 / 9.7; 0.79 (4/4) | 12.5 / 41.4; **3.35 (0/4)** |
| kB por paso en t / λ / Stokes | 556 / 520, 613 / 582, 558 / 765 | 517 / 551, 614 / 613, 558 / 689 |

Las ventanas no son iguales. El prototipo repinta espectros y λ–t en cada paso; explorer, la imagen
y la línea de estado. El panel de imagen mide 772×803 en los dos.

**Resultados negativos y avisos:**
- **Sin `_sp`, explorer tarda 2.5× en t y 3.3× en Stokes.** Pasa igual con los dos puentes
  (41–45 ms en t, 33–35 ms en Stokes), así que no es el puente: es algo del programa sin `_sp`.
  Queda para E3.7/E4.
- **Un núcleo compilado durante la medida para al emisor del puente ~0.6 s** (cubo sintético, sin
  `_sp`, primera ejecución con la caché de numba vacía). Por eso se calienta cada configuración.
- **Sin medir:** `ssh -Y` hasta XQuartz, es decir, las ~12 frente a ~8.5 imágenes/s y los bytes
  frente a xcb de la Fase F2. Necesita al usuario. El foco sin clic (E6.1) tampoco se ha medido: en
  Xvfb no hay gestor de ventanas.

### 2026-09-30: el puente X11 reescrito, opción B de P4 (ROADMAP E6, borrador)

**Qué.** Un puente nuevo, `platform/xbridge2/`, escrito sin copiar el del prototipo: `--x11 bridge2`
o `EXPLORER_X11=bridge2`. `auto` no lo elige. Diseño y decisión propuesta en
[ADR 0009](decisions/0009-puente-x11-reescrito.md). En paralelo, otro trabajo trae el del
prototipo tal cual (opción A), para que el usuario compare.

**Cómo está hecho:**
- **Cliente X11 propio** (`xproto.py`) en lugar de python-xlib: peticiones en búfer, respuestas en
  un hilo lector.
  - Al empezar, átomos, extensiones, teclado, monitores y puntero salen juntos: tres idas y
    vueltas antes de Qt.
  - La conexión de imágenes se abre en su hilo mientras Qt arranca.
- **Transporte** (`transport.py`, `kernels.py`): las ideas medidas del prototipo, reescritas.
  - Teselas 32×32 y gris a 1 B/px por RENDER.
  - Pixmap en el servidor y una CopyArea: nunca media actualización en pantalla.
  - Peticiones escritas por numba.
  - Como mucho dos actualizaciones sin confirmar por el servidor; la siguiente se captura cuando
    el emisor queda libre.
  - Un `Expose` se repinta desde el pixmap del servidor, sin volver a enviar píxeles.
- **Ventanas** (`windows.py`): ICCCM/EWMH, transitorios, formas, cursores, iconificar,
  maximizar, y ecos de `ConfigureNotify` por número de petición.
  - El foco: `_NET_ACTIVE_WINDOW` con una hora del servidor al mapear la ventana,
    `_NET_WM_USER_TIME`, `WM_TAKE_FOCUS`.
  - Sin gestor de ventanas, el foco X directo.
- **Entrada** (`qtinput.py`) **solo con API pública de Qt:** eventos enviados al `QWindow`,
  `QCursor.setPos`, `requestActivate`. Qt hace casi todo con ellos. El puente añade el doble clic,
  la propagación de la rueda y la activación que sigue al foco X.
- **Portapapeles** (`clipboard.py`) con INCR en los dos sentidos.
- **Sin sondeo cada 4 ms:** los eventos X despiertan a la interfaz de uno en uno, también dentro
  del bucle de un menú (el cuelgue F45 del prototipo).

**Encontrado por las pruebas mientras se escribía:**
- **Doble clic.** Qt entrega a los widgets pulsar, soltar, doble clic, soltar, y la segunda
  pulsación deja al widget como receptor del soltar. Mandar el doble clic tras una segunda
  pulsación hacía que pyqtgraph viera un clic simple. Mandarlo sin ella hacía que Qt tirara el
  soltar. Queda con `grabMouse` en ese widget hasta soltar.
- **Salir.** La ventana auxiliar que deja a Qt sin ventana activa, cuando el foco X está en otra
  aplicación, impedía salir al cerrar la última ventana. Medido: el proceso seguía vivo hasta el
  tiempo límite (código 2) y ahora sale con 0. Ahora es secundaria de la última activa y solo se
  enseña mientras hace falta.
- **Modificadores.** El `keyboardModifiers()` de Qt sigue a las pulsaciones y al ratón, pero no
  al soltar una tecla modificadora sola. Es el único desfase de la entrada pública que queda.
  Medido y probado.
- **Minimizar, con metacity.** Leer "minimizado" de Map/Unmap, como el prototipo, escondía la
  ventana al maximizarla: metacity la desmapea para cambiarle el marco. Ahora se lee de
  `WM_STATE`. Qt manda además Hide y Show espontáneos al minimizar y restaurar, y el puente
  destruía la ventana X; ahora los ignora.
- **No es del puente:** un clic derecho sobre la imagen abre el menú de pyqtgraph, en cualquier
  plataforma. El prototipo lo apagaba (app/viewer.py:1023–1028).

**Pruebas:**
- 30 unitarias, sin X y en `offscreen`: bytes de las peticiones frente a python-xlib; las
  teselas y peticiones se reproducen sobre arrays y dan la imagen exacta; teclado; la entrada
  pública sobre la ventana de explorer y sobre widgets corrientes.
- 7 contra un Xvfb privado (`tests/xvfb/`, con `EXPLORER_TEST_XDISPLAY`), con python-xlib como
  otro cliente: la ventana mapeada con la imagen idéntica al píxel a la de Qt; teclas sin clic;
  el puntero mueve el cursor y un clic lo bloquea; panel transitorio y con forma; popup; el
  portapapeles con INCR en los dos sentidos; tráfico contado; un `Expose` sin bytes.
- 2 con metacity en ese Xvfb (`EXPLORER_TEST_XWM`), 3 de 3 ejecuciones:
  - la ventana toma el foco X y es la activa aunque una "terminal" acabe de recibir un clic y una
    tecla, y la primera tecla llega al visor;
  - el marco del gestor, y mover, maximizar y restaurar desde el gestor;
  - Ctrl+M minimiza por el gestor y la barra de tareas la restaura;
  - el panel queda encima de su ventana;
  - el botón de cerrar, con la aplicación inactiva, termina el proceso con 0.

  Las 7 de Xvfb pasan también con metacity en marcha.
- `scripts/check.sh` en verde en el Mac (sin pantalla) y en bellatrix: 248 pruebas, 22
  saltadas (entre ellas las 9 de X, que piden su Xvfb).

**Medidas** (bellatrix, cubo 6173, ventana 1400×900, nodo NUMA 0, cerrojo compartido, 4 rondas
ABBA; `bench/bridge_vs_prototype.py`, los dos puentes sobre la misma ventana de explorer, y
píxeles releídos del servidor hasta que son los de Qt):

| | Xvfb directo, 1.ª serie (pareado) | 2.ª serie (pareado) | Enlace emulado 16 ms / 25 MB/s: prototipo → B (pareado) |
|---|---|---|---|
| Primera imagen en el servidor | 2.005 → 1.935 s (0.967, 4/4) | 2.123 → 2.010 s (0.947, 4/4) | 2.933 → 2.051 s (0.698, 4/4) |
| Paso en t | 30.2 → 29.9 ms (0.988, 3/4) | 29.9 → 29.8 ms (1.022, 1/4) | 76.4 → 63.9 ms (0.843, 4/4) |
| Paso en λ | 26.8 → 27.3 ms (1.056, 1/4) | 28.8 → 24.5 ms (0.883, 4/4) | 75.1 → 62.2 ms (0.828, 4/4) |
| Cambio de Stokes | 22.4 → 23.0 ms (1.038, 2/4) | 23.2 → 20.7 ms (0.898, 2/4) | 71.3 → 58.0 ms (0.820, 4/4) |
| Bytes por paso (enlace) | — | — | 758.5 → 758.6 kB (1.000) |

- **Sin latencia empatan:** las dos series dan el signo cambiado, y la carga de la máquina subió a
  20–26 al final de ambas, por trabajos de otros. Resultados en `bench/results/` de
  `explorer-bridgeB` en bellatrix (`bridges_link_r1.json`, `bridges_direct_r2.json`,
  `selftest_bridge_r1.json`, `es_r2_*.json`). La 1.ª serie directa quedó solo en el registro:
  el guion se paró al resumir bytes sin enlace, ya corregido.
- **Con latencia, B gana en todo con los mismos bytes.** Un paso de B está en el mínimo físico
  del enlace emulado.
- **Coste del puente en la interfaz,** `bench/explorer_selftest.py` offscreen frente a
  `bridge2`, 4 rondas ABBA, con `_sp`: pasos 1.19 (t), 1.22 (λ) y 1.17 (Stokes) veces más
  largos, 2–4 ms. El del prototipo es el mismo: tiempos de Qt parejos en la comparación de
  arriba.
- **Negativo:** ese coste no baja con la reescritura.
- **Las autopruebas de cada visor con su puente** (`bench/selftest_vs_prototype.py --modes
  bridge`) comparan visores distintos (el prototipo dibuja espectros y λ–t; explorer todavía no),
  así que no sirven para comparar puentes. Primera imagen de explorer 0.70 y 0.56 veces la del
  prototipo. Pasos de explorer 1.17–1.57 veces más largos, y 4.1 en Stokes sin `_sp` (51 frente a
  12 ms). Casi todo es la capa de datos de explorer: el mismo cubo en `offscreen`, sin puente, da
  40–45 ms en ese caso. El puente añade el resto (2–4 ms, arriba).

**Sin probar aquí:** XQuartz y quartz-wm, y qué aplicación pone macOS delante. Es la comprobación
del usuario por `ssh -Y`.


### 2026-09-30: medidas de E3.7, los dos puentes comparados y P4 decidido (ROADMAP E3.7, E6, E6.1)

**E3.7, la autoprueba frente a la del prototipo** (`bench/selftest_vs_prototype.py`, commit
`7ac47e8`). bellatrix, 2026-09-30 12:39–12:44, cubo de Stokes 6173, 4 rondas ABBA; offscreen y xcb
sobre el Xvfb privado `:97`; el panel de imagen de explorer al tamaño del del prototipo (772×803:
antes tenía el doble de píxeles que dibujar). Razón pareada explorer / prototipo (rondas en que
explorer es más rápido):

| | Primera imagen | Paso en t | Paso en λ | Cambio de Stokes |
|---|---|---|---|---|
| offscreen, con `_sp` | 0.742 (4/4) | 0.990 (2/4) | 0.874 (3/4) | 0.937 (4/4) |
| xcb, con `_sp` | 0.715 (4/4) | 0.912 (3/4) | 0.952 (2/4) | 0.868 (4/4) |
| offscreen, sin `_sp` | 0.593 (4/4) | 1.166 (0/4) | 1.427 (1/4) | 3.288 (0/4) |
| xcb, sin `_sp` | 0.554 (4/4) | 1.310 (0/4) | 1.481 (0/4) | 3.755 (0/4) |

Con `_sp`, igual o mejor en todo. Sin `_sp`, los pasos más lentos: sigue en E3.8, con lo medido y
lo descartado.

**El demo por `ssh -Y`.** Abre el visor primero y deja las comprobaciones de `doctor` para
después (`8372c99`): 4 s menos, según el usuario. La línea de la primera imagen cuenta desde que
arranca la orden y reparte el tiempo (importaciones, Qt, cubo, ventana, imagen).

**Los dos puentes (P4).** A, el del prototipo traído tal cual, y B, el reescrito, se escribieron
en paralelo, cada uno en su rama, y se juntaron en una rama de comparación. Ahí, `scripts/demo.sh`
elige A, B, xcb nativo o el prototipo con la primera palabra. Medidas y conformidad en
[ADR 0009](decisions/0009-puente-x11-reescrito.md). En corto:
- velocidad por el enlace emulado: B 0.68× A en la primera imagen y 0.84–0.85× por paso, con los
  mismos bytes; xcb nativo, 4.1× los bytes y ~3× el tiempo por paso;
- la suite de conformidad del prototipo, corrida sobre su visor sin cambiarlo: A difiere de xcb en
  2 pasos de 147; B, en 51 al empezar y en 2 tras seis correcciones, cada una con su causa trazada
  y una prueba que falla antes y pasa después.

El usuario eligió B. A queda en el historial (merge `a81c4ce`, quitado en `2f4bb2c`).

**Cómo se buscó cada causa** (herramientas fuera del repositorio, en la carpeta de trabajo):
- `show_step.py`: un paso de la suite en xcb, A y B, campo por campo y evento a evento;
- trazas de la cadena de ventanas X bajo el puntero en cada pulsación (`query_pointer`), de los
  movimientos que llegan a cada `QWindow` con su origen, y de las decisiones del redimensionador;
- bisección de los pasos previos para un fallo que solo salía en la secuencia completa
  (`panel_two`: lo rompía un doble clic de `panel_cycle`).

**Resultados negativos:**
- **La primera lectura de la comparación era falsa en 7 de las 8 diferencias.** Las esquinas no
  eran un fallo al redimensionar: en xcb y A la pulsación caía fuera de la ventana redondeada, y
  B, sin la forma, redimensionaba. La cruz desplazada venía de movimientos sintéticos, no de la
  compresión. Por eso ninguna diferencia se da por explicada sin traza.
- **Una regla "misma posición" para el píxel del separador rompió 10 pasos que pasaban.** Venía
  de leer en el código de Qt que la vía de plataforma descarta un movimiento sin cambio de
  posición. La traza directa de xcb la desmintió: xcb entrega ese movimiento al `QWindow` las 7
  veces, como B. Revertida. El píxel del separador sigue sin explicar.
- **`QCursor.setPos` al punto donde ya está no hace nada** (sonda en offscreen): forzarlo no daba
  el Leave de una ventana que se va de debajo del puntero. Se resuelve llevando el cursor fuera de
  toda pantalla y volviendo.
- **Una traza mía rompió una ejecución:** reutilicé el nombre `b` en el envoltorio de `press` y
  XTEST recibió algo que no era un número. Descartada.
- **Xcb nativo por el enlace emulado se colgaba** en la primera imagen: con el Xvfb en la misma
  máquina, Qt usa memoria compartida y se salta el enlace. Con `QT_XCB_NO_MITSHM=1`, como por
  `ssh`.

**El foco sin clic (E6.1).** En macOS, ni A, ni B, ni xcb toman el teclado al aparecer la
ventana. Las teclas van a la aplicación del frente (la terminal), y el foco X no la cambia.
- Apple-WM `SetFrontProcess`, pedido desde bellatrix: XQuartz contesta con error. El servidor
  trata como remoto a todo cliente cuyo proceso se llama `ssh` (xserver `os/access.c`,
  `ComputeLocalClient`), a propósito.
- Un ayudante local en el Mac (cliente X local que ve aparecer la ventana del visor):
  `SetFrontProcess` contesta "Success", pero macOS lo ignoró en 4 de 5; `open -a XQuartz` trajo
  XQuartz al frente en 9 de 9, con el foco X en la ventana del visor. Medido con `lsappinfo`; sin
  capturas (VS Code no tiene permiso de grabación de pantalla) y sin teclas de verdad.
- El usuario lo descarta: la solución tiene que valer en cualquier máquina y sistema sin
  instalar nada.
- La alternativa, probada con una copia de explorer: leer las teclas también de la terminal que
  lo lanzó (modo cbreak, `QSocketNotifier`). El usuario, por `ssh -Y`: "funciona genial". Queda
  como E6.2.

**Las pruebas X de B en Linux.** Al pasar `tests/xvfb` en bellatrix salieron dos fallos:
- `bridge_app.py` guardaba sus capturas en una carpeta de `/tmp` con nombre de usuario, borrada
  al limpiar (`f8f68b4`);
- con un popup abierto, Qt en Linux deja la ventana padre activa sin ventana con foco
  (`be8564b`).

Tras los dos arreglos: 247 pasan y 3 se saltan (necesitan gestor de ventanas).


### 2026-09-30: las teclas desde la terminal (ROADMAP E6.2)

**Implementado** (`ui/termkeys.py`, enganchado en `ui/app.run` tras mostrar la ventana): lo que el
usuario probó con una copia fuera del repositorio, con dos cambios:
- **Las teclas se comparan como combinaciones de Qt** (`QKeyCombination`: tecla y modificadores),
  no como texto. El texto de un `QKeySequence` cambia de orden y de forma entre sistemas; la
  combinación es lo que compara un `QShortcut`.
- **El corte en teclas es una clase aparte** (`KeyStream`), probada sin Qt: secuencias partidas
  entre lecturas, Escape solo (espera 50 ms), UTF-8 entero, Escape seguido de otra tecla (Alt).

Una mayúscula llega como Mayúsculas + letra, como en la ventana: `L` no bloquea el cursor, `l` sí.

**Pruebas:**
- `tests/unit/test_termkeys.py`: la tabla de secuencias (flechas CSI y SS3, modificadores, `~`,
  control, Alt, UTF-8); el corte; un pseudoterminal unido a una `Shell` real: ↑ mueve t, dos →
  en una lectura mueven λ dos pasos, `2` pone Q, `l` bloquea y Escape desbloquea tras 50 ms. La
  terminal vuelve como estaba, salvo `PENDIN`, que macOS pone solo al volver al modo canónico.
- macOS y Linux (bellatrix): pasan.
- La orden real (`scripts/run.sh`) bajo un pseudoterminal, en el Xvfb privado por el puente: la
  línea que lo anuncia, 9 actualizaciones tras ↑ → `2`, y Ctrl+W cierra con 0.

**Sin probar:** Ctrl+Z y `fg` (al volver, la terminal quizá no esté en modo cbreak), y la
comprobación del usuario por `ssh -Y` con esta versión.


### 2026-09-30: los pasos sin `_sp` no eran más lentos (ROADMAP E3.8)

**Hipótesis:** la regresión de E3.7 sin `_sp` (Stokes 2.9–3.8×) viene del orden de la
autoprueba, no de explorer. La del prototipo (`app/selftest.py:58-103`) pasa tras 30 posiciones
del cursor (cada una esperando a su λ–t), 30 sobre el relleno y una ráfaga de 50. La de explorer
pasaba nada más abrir, con la muestra del rango y aún leyendo.

**Medida:** bellatrix, 2026-09-30 21:12–21:20, offscreen, 4 rondas ABBA, fijado al nodo NUMA 0.
Carga 0.2 al empezar y 20 al acabar (trabajos de otros, que pesan igual en cada par). Dos series
seguidas, la autoprueba de explorer tal como estaba y con la fase del cursor del prototipo
delante. Razón pareada explorer / prototipo, sin `_sp` (rondas en que explorer es más rápido):

| | Primera imagen | Paso en t | Paso en λ | Cambio de Stokes |
|---|---|---|---|---|
| Como estaba | 0.603 (4/4) | 1.023 (1/4) | 1.360 (1/4) | 2.893 (0/4) |
| Con el procedimiento del prototipo | 0.570 (4/4) | 0.986 (2/4) | 0.639 (4/4) | 0.682 (4/4) |

Con `_sp`, las dos series: t 0.99–1.01, λ 0.69, Stokes 0.72–0.76.

**Resultado:** la hipótesis se confirma. Con el mismo procedimiento, explorer iguala al prototipo
en t y es más rápido en λ y Stokes. La conclusión de E3.7 ("sin `_sp`, los pasos más lentos") era
un artefacto de la prueba. `bench/explorer_selftest.py` ya sigue el procedimiento del prototipo.
El margen de 50 px del prototipo solo se reduce en un cubo más pequeño (el sintético de 48×40),
así que en el 6173 las posiciones son las del prototipo.

**Sin medir:** pasar en los primeros segundos tras abrir, con la muestra en marcha, en los dos
programas. La autoprueba del prototipo nunca mide ese momento. Queda para E4, cuando los paneles
dibujen.


### 2026-09-30: los paneles (ROADMAP E4.1–E4.9) y sus medidas

**Implementado:** docks (`7578992`); espectros, λ–t, barra de herramientas y de estado
(`1efabad`, con `21ba16b` para el orden de los paneles); candados y F / Mayús+F (`a51db83`);
clics en los paneles (`2da71d7`); reproducción y la sonda del enlace sobre el cliente X del
puente (`d3e0b2a`); el rango y de un espectro a mano, en la franja de su eje (`fec692f`).

**Velocidad frente al prototipo** (`bench/selftest_vs_prototype.py`: la autoprueba de cada
programa, 10 pasos por acción tras su fase del cursor). bellatrix, offscreen, fijado al nodo
NUMA 0, 4 rondas ABBA salvo donde se dice. Razón pareada explorer / prototipo (rondas en que
explorer es más rápido):

| Tras | `_sp` | Primera imagen | Paso en t | Paso en λ | Cambio de Stokes |
|---|---|---|---|---|---|
| E4.3 | sí | 0.945 (4/4) | 0.986 (3/4) | 0.822 (4/4) | 0.732 (4/4) |
| E4.3 | no | 0.713 (4/4) | 0.962 (3/4) | 0.820 (3/4) | 0.724 (4/4) |
| E4.4 | sí | 0.915 (4/4) | 0.930 (4/4) | 0.815 (4/4) | 0.889 (4/4) |
| E4.4 | no | 0.695 (4/4) | 0.971 (3/4) | 0.892 (4/4) | 0.696 (4/4) |
| E4.8 | sí | 0.910 (4/4) | **1.107 (0/4)** | 0.850 (4/4) | 0.812 (4/4) |
| E4.8 | no | 0.690 (4/4) | **1.037 (1/4)** | 0.875 (4/4) | 0.816 (4/4) |
| E4.8, 8 rondas | sí | 0.929 (7/8) | **1.026 (1/8)** | 0.910 (7/8) | 0.797 (8/8) |
| E4.8, 8 rondas | no | 0.676 (8/8) | **1.044 (3/8)** | 0.882 (6/8) | 0.767 (7/8) |

Carga de otros usuarios: hasta 29 al acabar la serie de E4.4 y 37 al empezar la de 8 rondas
(pesa igual en cada par, no en cada ronda).

### 2026-09-30: el paso en t tras E4.8 (ROADMAP E4.13)

Tras E4.8 la autoprueba da el paso en t de explorer un 3–11 % más lento que el del prototipo,
lo que la regla de la hoja de ruta no permite. Lo medido, en orden:

1. **Qué parte de la ventana cuesta** (en un mismo proceso, 48 bloques de 10 pasos, variantes
   alternadas por bloque; bellatrix, offscreen, fijado). Mediana del paso en t, ms:

   | | con `_sp` | sin `_sp` |
   |---|---|---|
   | completa | 15.46 | 15.48 |
   | sin barra de estado | 14.42 | 14.44 |
   | sin candados | 14.75 | 15.04 |
   | sin sincronizar la barra de herramientas | 14.06 | 14.51 |

   Cada widget que cambia en un paso cuesta 0.5–1.4 ms. Pero el prototipo tiene los mismos.
2. **Hipótesis: explorer repinta la ventana más veces por paso. Rechazada.** Contados los
   repintados por widget y los volcados de la ventana en los dos programas (Mac, offscreen, cubo
   sintético 12×4×21×200×180), el prototipo también vuelca 4 veces por paso con `_sp` y pinta dos
   veces su barra de estado. Diferencias: explorer repinta además los separadores de los docks
   tras cada reajuste de la ventana principal, y su línea de estado, estirada, ocupa 1374 px
   frente a 717. Ni fijar la altura de la etiqueta de t ni ignorar el tamaño de la de estado
   quitan ese repintado; lo que lo dispara es el reajuste de la ventana, que el prototipo también
   hace. `setAnimated(False)` ya estaba.
3. **Hipótesis: la lectura en otro hilo. Rechazada.** Con la imagen en caché, `sink.image`
   llega dentro de la propia llamada del paso.
4. **Las fases de un paso, en 200 pasos seguidos** (bellatrix, 2 rondas alternadas): explorer
   es **más rápido**, 21.1 frente a 26.6–27.0 ms con `_sp` (0.79×) y 25.6–27.5 frente a 31.1 ms
   sin él (0.85×).
5. **El procedimiento de la autoprueba repetido 6 veces en un proceso** (fase del cursor y 10
   pasos, 60 pasos por ejecución; 4 ejecuciones por programa y modo): explorer más rápido en
   las 8 parejas. Con `_sp`, 20.3–21.3 frente a 21.2–22.9 ms; sin él, 20.1–23.4 frente a
   24.2–29.8 ms. Los rangos y cambian igual de poco en los dos (0–0.17 por paso), y el primer paso
   tras la fase del cursor cuesta ~29 ms en ambos.

6. **Los 10 primeros pasos tras abrir, aparte** (el mismo guion; la primera repetición es lo que
   mide la autoprueba; carga 0.3–3). Mediana del paso en t con `_sp`, ms:

   | ronda | prototipo | explorer |
   |---|---|---|
   | 1 | 17.36 | 16.66 |
   | 2 | 15.95 | 17.30 |
   | 3 | 17.98 | 17.13 |
   | 4 | 15.82 | 16.34 |

   Empate: explorer más rápido en 2 de 4. Las repeticiones 2–6, 20.6–21.8 frente a 21.3–23.3 ms.
   En los dos programas la primera repetición es más rápida que las siguientes.

**Resultado provisional:** con `_sp`, en los 10 primeros pasos, empate dentro del ruido; después,
explorer algo más rápido. La serie de 8 rondas (1.026, 1/8) corrió con carga 19–37 de otro
usuario. Pendiente, en bellatrix: la parte sin `_sp` de la medida 6 y la serie de 8 rondas con
carga baja (`scratch_focus/e38/st2.log`, `e48c.log`; la conexión se cortó antes de leerlas).


### 2026-09-30: las pruebas del prototipo sobre explorer (ROADMAP E4.11, E4.12)

**Por qué:** repetir los casos del prototipo con su mismo software, primero las funciones y
después la velocidad, en vez de pruebas nuevas escritas para explorer.

**Cómo** (`63d0739`, `e509680`): `bench/protoface.py` pone los nombres del prototipo
(`v.spec_dock`, `v.idx`, `v._yr`, `v.stats`...) sobre la `Shell`, mezclados en su clase, así que
la ventana que manejan las pruebas es la de explorer, también para las comparaciones de
identidad. `bench/proto_smoke.py` sustituye `app/startup.py` y `app/viewer.py` y deja fuera
cualquier otro módulo del prototipo: ninguna comprobación puede pasar probando el prototipo.
Lo que explorer aún no tiene (rendija, disposición guardada, barra de título y bordes propios,
temas) cuenta como NO AÚN, nunca como pasada ni fallo, también cuando se salta: un salto
silencioso escondería el hueco.

**La prueba de humo** (`app/smoke.py`), bellatrix, cubo 6173:

| modo | prototipo | explorer |
|---|---|---|
| offscreen | 108 pasan, 23 se saltan | 82 pasan, 1 falla, 25 NO AÚN, 22 se saltan |
| xcb (Xvfb) | 125 pasan, 6 se saltan | 99 pasan, 1 falla, 24 NO AÚN, 6 se saltan |

Igual con y sin `_sp`. En xcb, los saltos de explorer son los del prototipo.

**Fallos encontrados y su causa:**
- **Menús contextuales** (corregido, `f48efa3`): el clic derecho abría el menú de pyqtgraph sobre
  la imagen y el de `QMainWindow` sobre la barra, los títulos de los paneles y los deslizadores.
  El prototipo los quita (`app/viewer.py:1018-1028`). Con un menú abierto, además, las teclas
  siguientes no llegaban: con los dos quitados, las 5 comprobaciones de teclas pasan. Mi primera
  hipótesis, que un deslizador se quedaba el foco, era falsa: el foco siguió en ninguno. La
  prueba nueva falla sin el arreglo (`QMenu`, `QMenu`, `ViewBoxMenu`).
- **El título de Stokes I** (E4.14, abierto): sin su 10ⁿ hasta que llega el primer espectro,
  0.39 s tras abrir en el Mac. El prototipo lee el primer espectro al construir la ventana. Sin
  `_sp`, el prototipo falla la misma comprobación: allí también llega por su hilo lector.
- **El aviso de fuentes de Qt** en el Mac, offscreen: el prototipo da el mismo. Es del Mac.

**La suite de conformidad** (`app/conformance.py`, xcb): corren los 147 pasos sobre explorer. En
la primera comparación todos los pasos difieren por una sola causa de partida: con un tamaño
dado, el `show` del prototipo no llama a `restore()` y sus paneles quedan con el tamaño de Qt
(650 px), mientras explorer los dimensionaba al mostrarse (520 px). Corregido en el adaptador
(`_sized`). Su barra de título propia (32 px, E5) desplaza las posiciones en la ventana: en el
clic sobre la imagen, los 14 eventos son los mismos y en el mismo orden, a 32 px en y. Pendiente:
leer la segunda comparación, ya hecha en bellatrix (`scratch_focus/pconf/run_xcb2.log`).


### 2026-10-01: el aspecto, la barra de título, la disposición y la hoja `?` (ROADMAP E5.1–E5.5)

**Implementado, probado en el Mac (offscreen); falta Linux** (la conexión a bellatrix se cortó):
- **Temas** (`72d8620`): el estilo del prototipo (`app/style.py`) sobre Fusion, oscuro y claro;
  `--theme auto|dark|light|native`. La prueba de humo del prototipo comprueba ya el estilo de
  explorer, no el suyo.
- **Barra de título propia, esquinas y bordes** (`e9f6cd9`): `app/titlebar.py` entero. `WindowOps`
  es ahora el `Mover` del prototipo: el zoom llena el monitor por geometría (sin gestor de ventanas
  también), y existen antes de mostrar la ventana. `platform/screens.py` porta `monitor_rect`
  (cabezas Xinerama por el cliente X propio; el Dock del Mac fuera por XQuartz).
- **La disposición entre sesiones** (`b53bd64`): geometría y paneles por tipo de pantalla, esquema
  con versión en el nombre del grupo (`app/v1.<tipo>/`), `--reset-layout`.
- **La hoja `?`** (`ae389ce`): una sola tabla de teclas y ratón para los atajos, la terminal y la
  hoja.
- **Los aspectos `classic` y `modern`** (`3584774`), como datos que toman la ventana y sus vistas;
  nada se sustituye sobre ellas, al contrario que en `app/look.py`. Por defecto `classic`.

**Encontrado al portar, del prototipo:** dos cosas de su ventana de todos los días que explorer no
tenía. Los deslizadores de t y λ van rellenos del rojo de los marcadores que mueven
(`app/viewer.py:1044-1049`). La cruz cambia de color con el cursor bloqueado
(`app/viewer.py:1245-1249`): en explorer un cursor bloqueado se veía igual que uno libre.

**Encontrado en las pruebas:**
- Las pruebas dejaban vivas todas sus ventanas: 8425 widgets al llegar a las del estilo, y cada
  `setStyle` por el estilo en Python costaba 0.82 s. Al borrarlas, la suite pasó de 40 a 18 s.
- Borrarlas sacó un fallo real: lo pendiente en el bucle (`call_soon`, `call_later`) se ejecutaba
  después de borrada su ventana. El reajuste del rango y en reposo fallaba con un error en el
  registro. Corregido con el bucle como contexto de los temporizadores (`903b0a2`), con una prueba
  que fallaba antes.
- Un segfault al borrar ventanas venía de mi accesorio, no de explorer: borraba antes que su gráfico
  los menús de pyqtgraph, que no tienen padre en Qt. Ahora solo borra ventanas principales.
- La prueba de humo del prototipo en el Mac da lo mismo que su propia ejecución, salvo el título de
  Stokes I (E4.14), la rendija y las comprobaciones `persist:`, que dibujan una rendija antes de
  cerrar.

**Pendiente (E5.6):** en Linux, la prueba de humo y la de conformidad en xcb y por el puente; la
barra de título vista por un servidor X de verdad; el coste del estilo (cada dibujo pasa por
Python) frente al prototipo; y que el usuario mire las dos apariencias y elija la de por defecto.

### 2026-10-01 (2): Linux, la tecla M, la hoja `?`, Stokes desplegable y un panel que volvía mal

**La copia de bellatrix estaba atrasada.** El arranque del demo en Linux había pasado de 2–3 s a
5–7 s: la copia remota era anterior al puente y usaba el X11 nativo. Sincronizada, vuelve a lo de
antes. Decía además `explorer 0.0.0`: la versión sale de git al instalar (hatch-vcs) y la copia
remota no tiene git. `scripts/sync.py` escribe ahora `src/explorer/_version.py` en cada push, aquí y
allí (`f2d24e0`).

**El aspecto** (`e4b4aca`, `329d4c8`, `f117f5b`):
- M cambia entre `classic` y `modern` mientras corre. Vuelve exactamente al clásico, y los mapas
  elegidos con C se conservan. El aspecto de la última sesión es el de la siguiente, salvo que
  `--look` diga otro.
- Un botón `?` abre la hoja de teclas, ahora una tarjeta redondeada y algo translúcida.
- En el clásico, ninguna línea clara bajo los títulos de panel; el fondo sigue negro y el eje de
  velocidad se conserva.
- Los deslizadores de t y λ miden 0.95 de los del prototipo (209 px como máximo), en los dos
  aspectos.
- En el moderno, Stokes es un desplegable ("Stokes V ▾", 71 px) en lugar de los segmentos en la
  barra (165 px). Con la ventana a 1100 px, los deslizadores del moderno miden ahora 204 px; antes
  medían 157 y los del clásico, 192.

**En Linux (bellatrix, Xvfb :97):**
- Pruebas unitarias offscreen: 335 pasan, 1 se salta.
- Pruebas X: 9 pasan y 2 se saltan (necesitan gestor de ventanas). Una prueba esperaba aún el menú
  de pyqtgraph al hacer clic derecho, que `f48efa3` quitó como en el prototipo; corregida
  (`3c49cc0`).
- Una prueba nueva maneja el desplegable de Stokes con clics XTEST a través del puente (`354ca4a`).

**Encontrado con la suite de conformidad del prototipo (xcb):** λ–t reacoplado con su botón de
flotar quedaba en (590, 466) de una ventana de 1200 px. Es decir, donde había flotado, ahora como
hijo, y 40 px más allá en cada flotar y reacoplar. Los clics posteriores en λ–t caían 80 px
desplazados.
- Qt 6.11 hace lo mismo con una `QMainWindow` desnuda, en xcb y offscreen: el sitio del dock en el
  layout no ha cambiado, así que Qt no lo vuelve a colocar. Ni `invalidate()` ni repetir la
  geometría del layout lo mueven.
- El arreglo (`74953e2`): cada dock recuerda dónde estuvo acoplado y vuelve allí cuando Qt lo deja
  donde flotaba.
- Desplazar todo el layout un píxel y volver también funcionaba, pero repintaba la ventana entera:
  1.26 Mpx frente a 0.51 por reacople (offscreen). El arreglo elegido mueve solo el dock: 0.51.

**El prototipo tiene el mismo fallo, y contamina su referencia.** En su ejecución, el espectro
acaba acoplado a 520×420 o 580×470, su tamaño de flotante, sobre un hueco de 650×353. De ahí que:
- sus pasos `separator_grab_*` midieran separadores de 858 y −134 px;
- en `panel_cycle`, su último doble clic no hiciera flotar el panel.

Explorer, arreglado, difiere ahora de él en esos pasos: 61 pasos distintos frente a 45, 83
idénticos. Las diferencias nuevas son de dos clases:
- los paneles, donde explorer hace lo que el paso pide;
- los deslizadores al 0.95, porque los clics a una fracción de su largo caen en otro valor.

**Pendiente:**
- `separator_central_docks`: el rango y del espectro difiere ([2, 4] frente a [0, 4]).
- `dock_float_dblclick_redock`: el espectro mide 353 frente a 347.
- `enter_leave_window`: el puntero cruza el botón `Panels` en el prototipo y un widget sin nombre en
  explorer. Sin rastrear.
- E4.13, E4.14 y E5.6.

### 2026-10-01 (3): el título de Stokes I desde el principio (ROADMAP E4.14) y el hover del adaptador

**E4.14, corregido (`918c797`).** Con fichero por píxel, el prototipo lee el primer espectro al
construir la ventana (`app/viewer.py` `_set_spectra`, 1927). Explorer lo leía en su pool de E/S,
así que el título de I salía sin su 10ⁿ y el eje se ensanchaba al llegar el espectro.
- Ahora el scheduler lee el bloque del cursor al construirse. El bloque queda en la caché, así que
  la primera lectura del cursor lo encuentra allí.
- Coste en bellatrix, cubo real: 2–24 ms en un proceso nuevo (24 en frío). En el Mac, con el cubo
  sintético, 0.1 ms.

**Encontrado al medirlo: la prueba de humo comparaba mal el cursor.** `hover()` del prototipo bombea
10 ms y solo espera al lector cuando no hay fichero por píxel, porque con él la lectura era
síncrona.
- En explorer, "spectrum follows" comparaba lo que hubiera en pantalla. Con un bloque en frío
  (20–50 ms en StorNext) comparaba el espectro del primer píxel consigo mismo y fallaba. O
  comparaba el primer espectro con un gráfico vacío y pasaba por suerte.
- ABBA 4+4 en offscreen, cubo real, con la espera aún sin corregir:
  - con el arreglo: "spectrum follows" falla 3/4;
  - sin él: el título falla 4/4.
- Una primera espera en el adaptador no hizo nada: la lectura del cursor se pide en la siguiente
  vuelta del bucle, no dentro de `hover()`.
- Corregida (`b078c60`): con el arreglo, 0 FAIL en 4/4; sin él, el título falla 4/4.
- La comprobación de tiempo del cursor cuenta ahora la lectura, como en el prototipo: mediana de
  12–15 ms (límite 60).

**El hook de los mensajes** (`08736c5`): ahora exige la línea en blanco tras el asunto y, en
`[ADD]`, `[DEV]`, `[FIX]` y `[PERF]`, las líneas `Behaviour:` y `Tests:` de la ADR 0005. Los últimos
40 mensajes lo pasan.

### 2026-10-01 (4): la ventana por X11 hacia un Mac (ROADMAP E5.7–E5.9), y el paso en t (E4.13)

**E4.13, la causa del paso en t lento** (`c608e38`). El paso en t de explorer era bimodal: la mitad
de los pasos en ~15 ms, como el prototipo, y la otra mitad en 18–20 ms.
- Descartadas: la muestra del rango y en segundo plano (16.5 frente a 17.1 ms) y el recolector de
  basura (igual de bimodal con `gc.disable()`).
- Causa: la lectura anticipada se pedía dentro del paso, y sus lecturas frenaban el pintado. Ahora se
  pide en la siguiente vuelta del bucle.
- Mediana de los 10 pasos por ejecución: de 17.9–19.3 a 13.8–15.0 ms. El prototipo, 15.8.
- Serie canónica (8 rondas ABBA; la carga subió a 19.6 durante la serie):
  - sin `_sp`: 1.100 → 0.933, explorer más rápido 8/8;
  - con `_sp`: 1.109 → 1.022, 3/8. Pendiente de repetir con carga baja.

**El techo** (`6e794a8`, E5.7): arrastrada por su barra, la ventana subía por encima de la pantalla.
Solo por X11: con quartz-wm la barra mueve la ventana por sí misma, sin límite (heredado del
prototipo). Ahora no sube del borde superior de su monitor. El usuario lo confirma en XQuartz.

**La barra de estado** (`5ad42b6`): el texto empezaba a 2 px del borde, dentro de la esquina
redondeada de 16 px. Ahora hay 8 px a cada lado. El usuario lo confirma.

**El redimensionado por los bordes** (`1ad53a3`, `fb3f6c1`, E5.8):
- En vivo, cada paso redimensionaba la ventana entera. Por un enlace emulado (8 ms, 20 MB/s,
  puente), un arrastre de 200 px en 1 s mandaba 17.7 MB, con el enlace lleno.
- Con un contorno de cuatro tiras dibujadas por Qt: 0.7–0.9 MB. Pero en XQuartz el contorno salía
  blanco, se volvía azul y llegaba al puntero segundos tarde.
- Medido en XQuartz con `bench/x_ops.py` (por `ssh -Y`):
  - ida y vuelta: 1 ms;
  - una tira: 10 ms;
  - las cuatro tiras de un paso: 57 ms (p90 536);
  - una ventana con forma: 33 ms;
  - una ventana grande redimensionada: 406 ms.

  Lo caro es el servidor, no el enlace: a un paso cada 25 ms, las tiras se encolaban.
- Ahora el contorno lo dibuja el propio servidor X: una ventana con forma de anillo, sin píxeles por
  el enlace, en una conexión propia. Un hilo aplica el último tamaño pedido y espera a que el
  servidor lo haya hecho antes del siguiente; lo que no da tiempo a dibujar se salta.
- Abrir la conexión en cada arrastre añadía 0.32–1.42 s a la primera respuesta. Ahora se abre una
  vez por ventana.
- Por el enlace emulado, con el puente y con xcb: primera respuesta 0.04–0.11 s; el contorno llega
  al puntero 0–0.09 s después del último movimiento. En vivo con xcb, en cambio, se quedaba 1.34 s
  atrás.
- El usuario lo ve "mucho más fluido". Quedan líneas y artefactos, pendientes de sus capturas.

**Retirado:** dije que en vivo la ventana "solo siguió 223 de los 800 px del puntero" y que al
soltar "se quedó 577 px por detrás". Era falso: el Xvfb de 3840 px se parte en dos monitores de 1920,
y la ventana topaba con el borde. El arreglo de tomar el tamaño en el punto de soltar se mantiene,
correcto en lógica, pero sin evidencia de que fallara en el enlace.

**E5.9, no es un defecto:** Qt en xcb no arrancaba por el enlace emulado porque, con el Xvfb en la
misma máquina, intenta memoria compartida (MIT-SHM), que se queda esperando a través del proxy TCP.
Con `QT_XCB_NO_MITSHM=1` funciona; por un `ssh -Y` real nunca la usa.

### 2026-10-01 (5): el Dock de macOS por X11 (ROADMAP E5.10) y Panels por el puente

**Panels colgaba el visor por el puente** (`90ea38c`), como F45 en el prototipo:
- gdb en el proceso del usuario: el hilo principal dentro del bucle anidado del menú
  (`QMenu::exec` desde `QToolButton::mousePressEvent`), en `poll`.
- Causa: la liberación del botón llegó cuando ya corría el bucle del menú, y la cola de eventos
  del puente seguía contando al hilo principal como despierto.
- Ahora se libera esa marca antes de cada evento. El test X suelta 0.3 s después de pulsar, como
  una mano: sin el arreglo falla 2/2, con él pasa 3/3.
- XTEST manda pulsar y soltar a la vez, y por eso las pruebas no lo veían. El usuario lo confirma
  resuelto.

**El Dock, medido en el XQuartz del usuario** (consultas de solo lectura, y una ventana de prueba con
título, ~1 s por monitor):
- No hay `_NET_WORKAREA` ni propiedad de la raíz que describa el Dock. Apple-WM está presente, pero
  trata de marcos de ventana.
- Xinerama da dos monitores: el principal en 1920,30 1920x1050 (ya sin la barra de menús) y otro en
  0,0 1920x1080. `_NATIVE_SCREEN_ORIGIN` es (−1920, 0).
- quartz-wm anuncia `_NET_WM_STATE_MAXIMIZED_*`. Maximizada, la ventana de prueba tomó:
  - en el monitor principal, 1920,30 1920x985: el Dock abajo, 65 px;
  - en el otro, 0,0 1920x1080: sin Dock.
- La suposición de explorer (70 pt abajo, en todo monitor) sobra 5 px en el principal y quita 70 que
  no hacen falta en el otro.

### 2026-10-01 (6): el coste del estilo, `resize_top` y las esquinas (ROADMAP E5.6, E4.12)

**El coste de nuestro estilo** (ABBA 6+6, autoprueba en offscreen, fijada al nodo 0, carga estable
1.6–1.9; `EXPLORER_STYLE=0` deja Fusion con la misma paleta). Mediana de las medianas:

| | con estilo | sin él | diferencia |
|---|---|---|---|
| paso en t | 14.14 ms | 13.67 ms | +0.47 (+3 %) |
| paso en λ | 16.22 ms | 15.30 ms | +0.92 (+6 %) |
| cambio de Stokes | 8.69 ms | 8.13 ms | +0.56 (+7 %) |

- Medido dentro del estilo, durante los pasos: 0.82 ms por paso.
- Por elemento:
  - el fondo de la barra de estado: 48 veces, 196 µs cada una, 0.34 ms por paso;
  - el slider: 280 µs por paso de t o λ;
  - el combo de Stokes: 270 µs.
- **Hipótesis descartada:** que el fondo de la barra costara por estar estirada la etiqueta de estado
  (en explorer ocupa todo el ancho; en el prototipo no se estira, `app/viewer.py:1001`). Sin
  estirarla cuesta lo mismo, 195–201 µs, y los pasos quedan dentro del ruido.
- El prototipo usa el mismo estilo portado: esto no es una diferencia con él. No lo toco por ahora.

**`resize_top`, no reproducible:** la diferencia de 1 px en el reparto entre paneles (374/371 frente
a 373/372) salió en una sola ejecución. En cuatro más (tres en vivo y una con el contorno) da
373/372, como el prototipo.

**Los pasos de redimensionado con el contorno:** durante el arrastre, la ventana conserva su tamaño
(a propósito); al final, el tamaño es idéntico al de en vivo en los ocho pasos.

**Las esquinas:** los cuatro pasos de esquina no redimensionan, en el prototipo ni en explorer. Sus
puntos están a 3 px de la esquina, y la forma redondeada (radio 16) ya ha cortado la ventana ahí; una
ventana X no recibe eventos fuera de su forma. Para agarrar una esquina hay que entrar unos 7 px en
diagonal; en macOS se puede agarrar incluso un poco por fuera.

**Capturas lado a lado** (E5.6; Xvfb, xcb, aspecto clásico, mismo cubo y tamaño, 1476x923;
`bench/results/e56_screens_2026-10-01/`, sin versionar):
- Iguales salvo:
  - el botón `?`;
  - la línea de estado, que en el prototipo aún decía "start-up";
  - las etiquetas del eje Δλ de λ-t: el prototipo pisa +0.3 y +0.4;
  - el marcador de λ en λ-t, 5 px más a la derecha. Es del mismo orden que el desplazamiento del área
    del gráfico, pero no lo he medido con precisión.
- El marcador es del mismo rojo en los dos, (255, 80, 80), leído en los píxeles: en la imagen
  reducida parecía blanco en el prototipo.
- La primera captura de explorer salió negra: cogí la ventana de una ejecución anterior del
  prototipo, aún abierta con el mismo título. La captura toma ahora la más reciente.

### 2026-10-01 (7): la vista 2×2 (ROADMAP E5.11)

**Pedido por el usuario:** I Q U V en cuatro paneles enlazados, cada uno pintando solo lo visible a
resolución de pantalla, con sus límites y su mapa de color; tecla 5 o «All»; un clic cambia λ-t a
ese Stokes.
- **Origen:** el prototipo la tenía en su aspecto "glass" (tecla G; `app/look_glass.py`,
  StokesGrid 221-315).
- **Implementación** (`7360cdc`): explorer la monta sobre su `ImageView`, cuatro veces, con los
  ViewBox enlazados. El scheduler lee el cuadro de cada Stokes en cada cambio de t o λ y los lee
  por adelantado.

**Encontrado al probarla: el factor de reducción** de `ImageView` salía de la región recortada a la
imagen, no del rango de la vista.
- Allí donde la vista es más ancha o más alta que la imagen, la pintaba a resolución completa: una
  imagen de 400x360 en un panel de 80x215 (factor 1), 4.5 veces los píxeles que se ven.
- El prototipo hacía lo mismo (`viewer/backend_pgr.py:52-53`). Corregido. El test de "no más
  píxeles que el panel" falla con el cálculo anterior.

**Coste** (bellatrix, cubo real, offscreen, fijado al nodo 0, ABBA de 4 rondas, carga 0.6–1.0):
- Paso en t: la vista única 21.5–22.1 ms; la 2×2, 64.3–67.6 ms.
- En un paso de la 2×2: render 46.9 ms (5 renders) y límites 10.4 ms; las lecturas aciertan en la
  caché 97 de 100.
- El quinto render era la vista única, tapada. Ahora no pinta mientras la cubre la 2×2: de 70–73 a
  64–68 ms.
- Reproducir a 20 fps no da (50 ms por cuadro).

### 2026-10-01 (8): la conformidad, cerrada (ROADMAP E4.12) y la velocidad (E4.13)

**E4.12, conformidad del prototipo en xcb**, con el código de hoy y `EXPLORER_RESIZE=live`, para que
los pasos de redimensionado se comparen como con como:
- **Primera ejecución, inválida:** la carga de otro usuario era de 10–17 y la entrada X llegó
  errática. El doble clic recibió 56 eventos, el paso siguiente ninguno, otro 120; lo normal son 9–25.
  Salieron 107 pasos distintos.
- **Repetida esperando a carga < 2:** 77 idénticos y 67 distintos. `--compare` los clasifica ya solo
  (`735ee95`):
  - 2 solo en el orden de los eventos;
  - 28 solo en la barra de pestañas que el prototipo acumula;
  - 37 por leer, todos explicados:

| causa | pasos |
|---|---|
| cambios de la barra hechos a propósito: sliders al 0.95, `?`, «All» ensancha el combo (el clic cae 3 px más a la derecha) | 17 |
| margen de 8 px de la línea de estado | 1 |
| reacople del prototipo con su tamaño de flotante, que explorer corrige (`74953e2`) | 15 |
| tiempos: repetición automática, tooltips, 1 px de redondeo en `resize_top` (2 de 6 ejecuciones), orden de activación | 4 |

**E4.13, cerrada.** Cinco series de 8 rondas, y en todas la carga de otro usuario subió durante la
serie, hasta 20–30.
- Sin `_sp`, explorer es más rápido en todo.
- Con `_sp`, los pasos en t y λ empatan: medianas entre 0.98 y 1.02, con cada ronda entre 0.80 y
  1.24.
- No hay evidencia de que explorer sea más lento. Resolver un 2 % pediría muchas más rondas con la
  carga quieta.

### 2026-10-02: el aspecto glass (ROADMAP E5.12)

**Pedido por el usuario:** portar el aspecto "glass" del prototipo. Decidido con él: se entra y se
sale con M, como en un ciclo de tres; solo los paneles flotantes.
- **Origen:** `app/look_glass.py` entero, leído por partes y citado en `ui/glass.py`.
- **Forma:** `GlassChrome` lo aplica sobre las partes del aspecto moderno (menos sus tarjetas) y
  `remove()` devuelve todo lo que tomó: las acciones de la barra en su orden, los anchos de los
  sliders, los títulos de panel, los márgenes, el estado de los paneles, la geometría, el título y
  el acento. Un test entra en glass y vuelve a classic y compara todo eso.
- **Disposición:** glass guarda la suya (`LayoutStore.for_look`), como el `kind + "-glass"` del
  prototipo (`look_glass.py:630`).

**Encontrado al compararlo con el prototipo**, con un test que falla antes:
- la barra quedaba debajo de la vista 2×2 (el prototipo la sube encima, `look_glass.py:887`);
- la 2×2 creada ya en glass tenía la retícula blanca;
- lo seleccionado (segmentos de Stokes, botones activos, filas de menú) seguía en azul. El
  prototipo lo pasa al acento oscurecido hasta que el texto blanco se lee a 4.5:1
  (`look_glass.py:87-96`, `929-940`).

**No portado:** la columna de tarjetas (decisión del usuario) y la rendija, que llega con E7.

**La suite, más lenta mientras se escribía** (109–150 s frente a ~40 s): no se reproduce. Medida
de nuevo: 47.4 s, con carga del Mac de 22–29. Ningún test de glass entre los más lentos.

**Un test golden falla, ajeno a glass:** la huella del código del prototipo ya no es la registrada
en `tests/golden/data/synth_small/reference.npz` (exportada el 2026-09-29). `app/viewer.py`,
`app/look.py` y `app/look_glass.py` del prototipo cambiaron el 2026-10-01 entre las 18:10 y las
19:39. Sin reexportar: pendiente de saber de dónde vienen esos cambios.

**Visto por el usuario, el mismo día:**
- **De glass a classic, los paneles volvían con otro tamaño.** Reproducido fuera de pantalla: el
  espectro pasaba de 520x343 a 414x245 y la imagen de 662 a 768 px de ancho, con la ventana igual.
  `remove()` restauraba el estado de los paneles antes que el tamaño de la ventana, y Qt los
  repartía en la ventana estrecha de glass (480 px). Ahora va primero el tamaño y luego el estado,
  y otra vez cuando el gestor de ventanas haya aplicado el tamaño. El test de ida y vuelta compara
  ya los paneles y la imagen; fallaba antes.
- **El prototipo no cambia de aspecto mientras corre:** se elige al arrancar (`--look`,
  `app/viewer.py:2631`; su Ctrl+M es minimizar). No hace ningún "reset" al cambiar: cada aspecto
  empieza de cero con su disposición guardada. explorer lo cambia en caliente con M, y por eso tiene
  que devolver lo que tomó.
- **El acento es naranja:** el prototipo lo cambió el 2026-10-02 a las 09:32 (Apple orange,
  `look_glass.py:56-61`, con sus medidas frente a amarillo, verde y blanco). Portado. El acento de
  sistema de este Mac también es naranja (`AppleAccentColor` 1). Los controles nativos de un Mac
  local lo toman igualmente.

**Por X11 hacia el Mac (bellatrix → XQuartz), visto por el usuario: título doble en los paneles de
glass y lambda-t bajando sola 2–3 s.** En el Mac local no pasaba. Un registro de cada movimiento
de la ventana y los paneles, con quién lo pide (pila de Qt o aviso de X), lo explicó en minutos:
- **El tipo de ventana.** El puente reescrito declaraba *utility* toda ventana Qt::Tool. quartz-wm
  pone a una *utility* su tira de título de 16 px aunque pida sin decoración: el título doble.
  Cada posición confirmada llegaba 16 px más abajo y el puente se la daba a Qt: lambda-t en 353,
  369, 379, 395, 411, 427. El prototipo lo había medido y resuelto (`xbridge.py:660-690`,
  auditoría F23c), y no se portó; una prueba de X exigía *utility*. Corregido en `5ec4214`.
- **Respuestas viejas.** Sin deriva, los paneles aún saltaban 1.2 s: el puente preguntaba a X
  dónde estaba una ventana enmarcada sin esperar, y aplicaba la respuesta aunque Qt hubiera pedido
  otra posición después. Ahora se descarta (`dcf0353`).
- **Paneles antes que su ventana.** Al arrancar en glass con su disposición guardada, los paneles
  flotan antes de que exista la ventana X principal: nacían sin dueño (`d404c2b`).
- **Títulos pisados.** Al arrancar en glass en Linux, el marco de app.py ponía los títulos de panel
  después del aspecto; el prototipo los pone antes (`startup.py:145`). `e55f9af`.

**Por qué se escapó:** las pruebas de X corren en un Xvfb sin gestor de ventanas, y los tres
fallos del puente solo existen con uno; ninguna prueba arrancaba en glass con disposición
guardada; y un hallazgo medido del prototipo no pasó al puente reescrito. Las tareas E5.15 y
E6.4–E6.7 del roadmap son para eso.

### 2026-10-03: cubos de La Palma reales (ROADMAP E1.15–E1.20)

**Qué se probó.** Solo lectura en bellatrix, sin copiar cubos: los cubos LP (`icube`/`fcube`) de los datos
reducidos compartidos, cabeceras con `formats.open_layout` y datos con `Dataset`, frente a los FITS de las
mismas observaciones. Qué ficheros, con sus rutas y fechas: `docs/data.local.md` (no se versiona).

**Lo que funciona.**
- Los `_im.icube` con su `_sp.icube` al lado abren, con la forma que dice la cabecera (6173, 7699, 8542 y
  6563).
- Imagen a mitad de serie, `icube` frente a FITS: `FITS = 1.0e-11 × icube`, correlación 0.999999–1.000000,
  residuo p99 4.95e-12 (medio paso de la cuantización), en un 6563 y en un 6173 (`stokesI` frente al FITS de
  Stokes).
- Bloque λ–t de un píxel, `_im.icube` frente a `_sp.icube`: diferencia máxima 4.6e-13 (6173, calibración
  escala 1.0) y 0 (6563): el orden de los fotogramas y de los píxeles es correcto con ns = 1.

**Lo que fallaba y se arregló (E1.15).** Un 6563 tiene `_sp.fits` y `_sp.icube` junto a su `_im.icube`; el
`_im.icube` tomaba el FITS y el bloque λ–t salía en unidades físicas (máximo 3.42e-8) frente a una imagen en
cuentas (3.42e3). `companions()` pone ahora el compañero del formato del cubo primero. Prueba nueva que
fallaba antes; en el cubo real, `_sp.icube` con calibración 1.0 y diferencia 0. `check.sh` en bellatrix:
lint, capas y tipos bien; 437 pruebas bien y las 2 de E0.13 (referencias caducadas) fallan como antes.

**Lo que queda (E1.16–E1.20).**
- Sin ejes físicos en los LP: el `…_times+wvl.idlsave` no se lee, y scipy no está en el entorno.
- Los mapas de campo (`.fcube`, (x, y, t)) no abren: se exige un `_sp`.
- Los nombres `aligned6173` y `clipped` no encuentran su compañero.
- El orden de Stokes en un `_sp.icube` con ns > 1, sin datos reales en ese momento (resuelto en E1.19).
- Datos y campo a la vez: segundo cubo, E8.

### 2026-10-03 (2): un cubo real de cada tipo (ROADMAP E1.19, E1.21)

**Barrido.** Solo cabeceras de los cubos LP de los datos reducidos de 2023, 2024 y 2025 (el detalle, en
`docs/data.local.md`). Los `icube` de Stokes con ns > 1 solo aparecen en 2023 (6173 y 5380 con IQUV, en
FITS y en `icube`; un 8542 `aligned6173.fcube` con IQUV); en 2024 y 2025 el 6173 y el 8542 van a `icube`
como `stokesI`. Tipos encontrados: cubos de imágenes FITS e `icube`/`fcube` con su `_sp`; nombres
`aligned6173`, `clipped`, `cmapcorr`; mapas sueltos (`Blos`, `Bhor`, `Bazi`, `Binc`, `Bstr`, `Vlos`, en
`fcube` y en `icube`, con `_` o con `.` tras el nombre, algunas cabeceras sin `stokes=`); productos de
inversión (`meinv` con su `_sp`, tres parámetros en el lugar de λ) y `doppl`/`corew` (`_im.fcube`).

**E1.19, Stokes en `_sp.icube` con ns = 4** (un 6173 de 17 t, IQUV, 27 λ):
- imagen por Stokes frente al FITS: `FITS ≈ 1.0e-11 × icube`, correlación 1.000000 (I) y
  0.99997–0.99999 (Q, U, V: pocas decenas de cuentas, pesa la cuantización);
- `_im.icube` frente a `_sp.icube`, dos píxeles, cada Stokes: ≤ 9e-13;
- `_sp.icube` frente a `_sp.fits`: cada Stokes se parece más al mismo del FITS que a cualquier otro
  (0.9993–1.0). El orden es (s, t, λ), el que usa `SpLP`, no el (t, s, λ) de `bench_icube.py`.

**E1.21, `tests/real/`.** Quince casos, uno por tipo, enlazados con nombres genéricos en `data/lp/` (que
conservan lo que explorer lee del nombre: `_im`/`_sp`, `.aligned6173`, `clipped=`, `Blos_`/`Blos.`). Por
caso: abre con su forma, una imagen con datos, `_im` = `_sp` en dos píxeles y por Stokes, LP = su FITS por
la escala entera, y `scripts/run.sh cubo --quit-after 1` sin pantalla (sale con 0 solo si mostró una
imagen). En bellatrix: 17 pasan y 16 fallos esperados (mapas sueltos y productos sin `_sp`, E1.17;
`aligned` y `clipped`, E1.18), en 45 s. Los esperados fallan por la razón dicha (falta el `_sp`), pero el
visor la da como traza de Python, no como mensaje.

**Datos privados.** Las rutas, nombres de ficheros y fechas de las observaciones de StorNext no van en el
repositorio: `docs/data.local.md` (ignorado por git, y por tanto tampoco lo envía `sync.py`) tiene la tabla
de enlaces y el barrido completo.

### 2026-10-03 (3): cubos LP sin fichero por píxel (ROADMAP E1.17)

**Hipótesis.** Un cubo LP sin `_sp` no dice en su cabecera cómo se reparten sus fotogramas, pero su nombre
sí: SSTRED pone los escaneos (`=a-b`). Si hay tantos fotogramas como escaneos, es un fotograma por escaneo
(t, y, x); si es un múltiplo, (t, s, λ) en el orden de CRISPEX.

**Medida que la confirma.** Un `clipped=0-85` (2236 fotogramas = 86 × 26) frente al cubo `stokesI` completo
de la misma serie: los fotogramas (t, λ) leídos como `t * 26 + λ` son idénticos bit a bit en t = 0, 10, 40,
85; leídos al revés (`λ * 86 + t`) la correlación cae a 0.87. Los mapas (`Blos`, `doppl`) tienen tantos
fotogramas como escaneos en el nombre.

**Cambio.** `formats.lp_single_layout`, usado por `open_layout` cuando no hay `_sp`. Sin escaneos en el
nombre (`Blos.6173_….fcube`), un eje sin nombre que `roles()` llama desconocido, como E1.14; `--axes t` lo
hace tiempo. `ui.app.run` da un mensaje al no poder abrir un fichero, en vez de la traza.

**Verificación.** Tres pruebas nuevas (mapa, reparto por escaneos con dos series unidas, sin escaneos), que
fallan sin el cambio. `tests/real` en bellatrix: los 15 tipos abren y el visor arranca con todos (33
pasan). Los enlaces genéricos de `data/lp/` conservan ahora el rango del nombre, que es lo que lee el
lector. `check.sh`: ruff, capas y tipos bien; 477 pruebas bien, las 2 de E0.13 fallan como antes.

**Queda.** Los `aligned6173` abren sin su `_sp.aligned6173` (E1.18).

### 2026-10-03 (4): cubos alineados con su fichero por píxel (ROADMAP E1.18)

SSTRED nombra un cubo alineado a la malla de otra línea `<stem>_im.aligned6173.icube`, y su fichero por píxel
`<stem>_sp.aligned6173.icube`; `companions()` buscaba `<stem>_sp.icube` y estos cubos abrían sin él
(desde E1.17, repartidos por los escaneos del nombre). Ahora la etiqueta entre `_im` y la extensión se
conserva. En bellatrix: el 6563 alineado (`icube`) se empareja con su `_sp`, calibración escala 1.0 y
residuo 2e-12 (las mismas cuentas); el 8542 de Stokes alineado (`fcube`, 110 GB, dos series unidas) con el
suyo, y `_im` = `_sp` en dos píxeles para los cuatro Stokes: el orden (s, t, λ) se cumple también en un
`fcube` de flotantes. `tests/real` 33 pasan; `check.sh` 478 pasan, las 2 de E0.13 como antes.


### 2026-10-03 (5): unidades, relleno y ejes de los cubos LP desde su idlsave (ROADMAP E1.16)

Un cubo LP no tiene cabecera física: SSTRED guarda lo que significan sus valores en
`<stem>_im_times+wvl.idlsave`, al lado (la etiqueta de un cubo alineado no entra en ese nombre). Se lee
con un lector propio, `data/formats/idlsave.py`, biblioteca estándar y numpy (scipy no entra en el
proyecto por un formato).

**El lector frente a `scipy.io.readsav`** (scipy solo en un entorno de pruebas fuera del proyecto, en
bellatrix): las 120 idlsave de los cubos CRISP de los datos compartidos, todas sin comprimir. Mismos nombres y las
mismas 824 variables, con forma, tipo y valores idénticos bit a bit (textos comparados como texto); ninguna
queda sin leer. Tiempo, las 120 con la caché caliente: scipy 3.33 s, el propio 1.57 s. Lo que no decodifica
(estructuras, punteros, objetos, descriptores de 64 bits) vuelve como `Unread` y el resto del fichero se
lee; los comprimidos se rechazan (ninguno entre los de SSTRED).

**Qué dice el fichero, medido contra los hermanos FITS** de dos cubos reales (Fe I 6173 con cuatro Stokes,
Hα), antes de usarlo:
- `lambda` (nm) es la λ de la WCS-TAB del FITS, idéntica.
- El tiempo por escaneo, media de los segundos de cada tuning, coincide con el del FITS (DATEREF más
  t_sec) en menos de 3e-11 s. Son segundos del día UT y el fichero no trae la fecha: se muestran como
  hora del día (`Axes.time_of_day`). Los segundos en float se llaman `time` en un fichero y `times` en el
  otro (el otro nombre guarda el texto 'HH:MM:SS' por escaneo): se toman por tipo.
- Valor físico = cuenta / `fac` (1e11 en ambos; 1e9 en el 5576 de `cmapcorr`; 1 en el `fcube` de 8542,
  que ya está en unidades físicas).
- `nan_rplcmnt` (−1240 en el 6173, −1 en el Hα) está exactamente donde el FITS tiene NaN: coincidencia en
  el 100 % de los píxeles de 24 fotogramas repartidos por cada cubo, un 25–27 % de relleno, y ningún valor
  por debajo. En los `_sp` es el mínimo. En el `fcube` de 8542 es un float (−1.769e-08), un 25 % de cada
  fotograma en I y en V, nada por debajo, sin NaN: el mismo relleno.

**Qué cambia.** `formats.lp_values` pone `scale = 1/fac` y `blank = nan_rplcmnt` en el `Layout` (el `blank`
float se compara con la precisión del fichero). El fichero por píxel LP hereda los dos de su cubo y su
calibración se ajusta ahora contra valores físicos. `axes.from_lp` da λ, la línea (la única de `LINES`
dentro del rango sintonizado: Fe I 617.3, Hα, Fe I 557.6, Ca II 854.2 en los cinco cubos con idlsave), el
continuo con la regla de `from_fits` y el tiempo por escaneo. Lo que no encaja con el cubo (otro nλ u otro
nt) se descarta con un aviso. Una idlsave ilegible deja el cubo en cuentas, con un aviso, y abre igual.

De paso, E1.20 queda medio resuelta: el icube de Hα con su `_sp.fits` dado a mano coincide ahora, con NaN
en los mismos píxeles y una diferencia ≤ 5e-12, media cuenta de redondeo. Queda abierta para icubes sin
idlsave.

`tests/real`: los cinco cubos con idlsave (tres enlaces nuevos en `data/lp/`) tienen su línea y un tiempo
por escaneo. Los dos con hermano FITS lo igualan en valores (±1 cuenta), NaN, λ y hora UT. La prueba
`_im` = `_sp` multiplicaba la serie por la calibración porque suponía fotogramas en cuentas; ahora compara
directamente. 33 pasan. `check.sh` en bellatrix: 489 pasan, las 2 de E0.13 como antes.

Sin usar todavía: `xcent0`, `ycent0` (el centro del campo en segundos de arco) y `mu`. Sin la escala del
píxel no dan las esquinas del campo.

### 2026-10-03 (6): el último de dos movimientos rápidos se perdía (ROADMAP E6.13)

`test_the_pointer_moves_the_cursor_and_a_click_locks_it` volvió a fallar en la integración continua, esta
vez con lo que la prueba dice desde `8d111ae`. El segundo movimiento: el cursor sigue en [54, 66]. X tiene
el puntero en (430, 320), en la ventana principal (justo el destino), sin bloqueo ni menú. El puente cuenta
`mouse: 2`. Un Enter solo mueve el cursor de Qt con `setPos` y no suma a esa cuenta, así que los dos
movimientos llegaron a la ventana Qt.

**Hipótesis descartada: la disposición.** El segundo punto, 70 px a la derecha del centro, podía caer
fuera de la imagen (80 px de ancho). Medido en bellatrix, offscreen, con la ventana de `bridge_app` (mismo
cubo, 800×600) entre 0.05 s y 4 s tras mostrarla: el primer punto da el píxel (54.8, 66.1), el mismo [54, 66]
del CI, y el segundo (45.2, 79.4), dentro del ViewBox, en la última columna. Estable.

**Causa.** `GraphicsScene.mouseMoveEvent` de pyqtgraph 0.14 descarta todo movimiento que llega a menos de
1/`mouseRateLimit` s del anterior (100/s por defecto: 10 ms) y no lo entrega después. En la prueba, entre
los dos movimientos solo hay dos ida y vuelta de `state` por la tubería: en un runner rápido, menos de
10 ms. Los `setPos` del puente que podrían repetir la posición se filtran a propósito (sus movimientos
sintéticos no son entrada). Así que nada vuelve a llevar la cruz al último píxel. Con un ratón real pasa
lo mismo: el último movimiento antes de pararse puede caer en esos 10 ms. El prototipo engancha la imagen
a la misma señal (`prototype/viewer/backend_pg.py:44`).

**Prueba.** Dos `MouseMove` seguidos al viewport, offscreen, sin X: con el límite por defecto el cursor se
queda en el primer píxel; con `mouseRateLimit=0` pasa. La prueba falla antes del arreglo y pasa con él.

**Arreglo.** La imagen toma sus movimientos de los eventos de su viewport (`imageview._Moves`), no de
`sigMouseMoved`; la escena conserva su límite para lo demás (espectros, λ-t). Coste medido en bellatrix,
offscreen, 2000 movimientos a píxeles distintos: 142 µs por movimiento con hover, 42 µs sin él. Esos
~100 µs del hover antes se pagaban como mucho 100 veces por segundo; a 120 Hz son ~1.2 % de un núcleo.

`tests/xvfb` con un Xvfb privado como el del CI (el binario del proyecto en bellatrix, 1920×1080): 19 pasan
y 2 se saltan (piden gestor de ventanas); la prueba del puntero 10 de 10. En bellatrix ya pasaba antes:
esto solo muestra que nada se rompe. La prueba del defecto es la unitaria. `check.sh`: 490 pasan, las 2 de
E0.13 como antes.

### 2026-10-03 (7): idlsave a través de un enlace, y frames de enteros junto a un `_sp.fits` (ROADMAP E1.22, E1.20)

**E1.22.** La idlsave se buscaba solo junto a la ruta abierta. Un cubo enlazado solo, con otro nombre y en
otra carpeta (como en `data/lp/`, o en otro ordenador), abría en cuentas y sin aviso, aunque la idlsave
estuviera junto al fichero real. Los `_sp` sí se buscaban allí (`companions()`, como el `find_sp` del
prototipo). Ahora la idlsave se busca primero junto al enlace y después junto al fichero real, con el nombre
real. Un cubo de enteros sin idlsave lo dice en el log: valores en cuentas y relleno como dato.

**E1.20.** Un icube sin idlsave con un `_sp.fits` dado a mano mostraba la imagen en cuentas y los espectros
en unidades físicas, y el relleno como dato. Ahora las frames se ajustan al FITS en la λ-t de Stokes I de
un píxel (`pixel.calibrate_frames`, el ajuste de `SpLP.calibrate` al revés). El relleno es el único valor de
cuenta que aparece donde el FITS tiene NaN, buscado en ese píxel y en dos esquinas. Medido en el Hα real
(bellatrix), con la idlsave ocultada por un monkeypatch, sin tocar ficheros:
- escala 1e-11, cero −5.6e-14, relleno −1: lo que dice la idlsave (`fac` 1e11, `nan_rplcmnt` −1);
- residuo 5e-12 (media cuenta de redondeo), en el píxel central;
- tres frames (t, λ) = (0, 0), (24, 7), (48, 14) iguales a las del camino con idlsave en 5.5e-14 (0.006
  cuentas), con NaN en los mismos píxeles; abrir el cubo, 0.79 s en total.

En la prueba sintética el ajuste usa solo 6 muestras (2 t × 3 λ), así que la tolerancia es de 2 cuentas,
como en la de `SpLP`. Un cubo sin escaneos en el nombre y sin `_sp` LP sigue sin repartirse en (t, s, λ),
aunque se le dé un `_sp.fits` (E1.17): eso no cambia.

`tests/real` 33 pasan; `check.sh` en bellatrix 493 pasan, las 2 de E0.13 como antes.

### 2026-10-03 (8): `demo --look`, la cookie del contorno, la rueda por el puente (ROADMAP X.5, E6.9, E6.10)

**X.5.** `explorer demo` abre la misma ventana que `explorer`, pero rechazaba `--look`, `--theme` y
`--reset-layout`. Ahora las tres opciones se definen una sola vez, junto a `run()`
(`ui.app.window_options`), y las dos órdenes las toman de ahí. Construir el parser sigue sin importar nada
pesado (`-X importtime`: ni PySide6, ni numpy, ni astropy).

**E6.9.** python-xlib busca la cookie de un display TCP solo por la dirección del servidor. Solo prueba con
el nombre del host si la dirección es 127.0.0.1 (`Xlib/support/unix_connect.py`, `new_get_auth`). Con
`DISPLAY=host:10` (sshd con `X11UseLocalhost no`, como en macOS), sshd guarda la cookie con el nombre del
host, así que la conexión del contorno de redimensionado no enviaría ninguna. Ahora, cuando python-xlib no
encuentra cookie, se elige como en el puente (`platform/xlibauth.py` → `choose_cookie`), como hacía el
prototipo para todas sus conexiones. Verificado en la causa: con un Xauthority que solo tiene la cookie por
nombre, python-xlib por sí solo devuelve vacío y con el respaldo devuelve la cookie. No lo he probado de
extremo a extremo: haría falta un servidor X escuchando por TCP, y no lo abrí en la máquina compartida.

**E6.10.** Una prueba X nueva reproduce el fallo: la rueda sobre el combo de Stokes, por el puente, no le da
el foco. Qt solo da el foco por rueda (`giveFocusAccordingToFocusPolicy`) a los eventos espontáneos, y el
puente envía los suyos. El puente aplica ahora esa regla antes de entregar la rueda. La hipótesis se
confirmó con la misma prueba, con la ventana activa en los dos casos:
- sin la llamada (copia de `src` en el scratch, delante en `PYTHONPATH`), falla;
- con la llamada, pasa.

Primer intento de la prueba: falló por otra razón. La prueba anterior del módulo abre otra app, que se
queda con el foco X, y en una ventana inactiva `focusWidget()` es `None`. Ahora la prueba activa su
ventana antes. `tests/xvfb`: 20 pasan, 2 saltadas (piden gestor de ventanas).

### 2026-10-03 (9): propiedades X por clase de ventana frente al prototipo (ROADMAP E6.5)

Lo que quedaba de E6.5 (menús, tooltips, ventanas de herramienta y la gravedad de `WM_NORMAL_HINTS`), con
una sonda nueva, `bench/xprops.py`. La suite de conformidad conduce cada programa sin modificarlo, un paso
cada vez, en un Xvfb privado. Mientras tanto, un cliente python-xlib independiente lee lo que vería un
gestor de ventanas en cada ventana que aparece: override-redirect, tipo, Motif, `WM_TRANSIENT_FOR`,
`WM_NORMAL_HINTS`, `WM_HINTS` y `WM_PROTOCOLS`. Pasos usados: `combo_open`, `tooltip`, `panel_float_api` y
`dock_title_drag_float`. Medido en bellatrix (3840×1080, cerrojo de medidas, carga 0.44 al empezar);
resultados en `bench/results/e65_xprops_2026-10-03/`.

**Hallazgo: explorer escribía `WM_NORMAL_HINTS` con el tipo equivocado** (`windows.py`, átomo 40 en vez de
`WM_SIZE_HINTS`, 41). Los gestores piden el tipo `WM_SIZE_HINTS` y, con otro, no leen nada. Así que la
gravedad Static que corrige el desplazamiento de 16 px en XQuartz (F23c del prototipo), la marca de
posición y el tamaño mínimo no tenían efecto. La sonda lo vio como `normal_hints: null`. La prueba X nueva
falla antes del arreglo (tipo `WM_NORMAL_HINTS`) y pasa después; `tests/xvfb` 21 pasan.

Un falso hallazgo, retirado: el `repr` del objeto de python-xlib mostraba solo 8 de los 18 valores. Parecía
una escritura truncada, pero `get_full_property` lee en dos trozos y el `repr` enseña solo el segundo.
`.value` tiene los 18.

**Tras el arreglo:**
- Iguales en los dos programas: menús y tooltips (override-redirect, sin propiedades), el panel flotante
  (normal, sin decoración, transient de la ventana principal) y la gravedad Static con `PPosition` y
  `PSize`.
- Diferencias que se quedan, a propósito:
  - `WM_TAKE_FOCUS`, `_NET_WM_PING` y `WM_HINTS` (input): los necesita el foco por el puente, y es lo
    que pide ICCCM;
  - el tipo NORMAL explícito en la ventana principal: para EWMH es lo mismo que no declarar tipo;
  - el tamaño mínimo (`PMinSize`, como declara xcb). El `PMaxSize` 32767 del panel no limita nada.
- Un tooltip que solo salía en explorer durante `combo_open` era un artefacto de la sonda. Los dos
  programas comparten el display y el segundo empieza con el puntero donde lo dejó el primero (`--first`).
  Con explorer primero, no sale en ninguno.

**Falta:** verlo en XQuartz. Ahora el gestor sí aplica estas hints a las ventanas de explorer, y en
XQuartz eso no lo he podido comprobar desde aquí.

### 2026-10-03 (10): el registro de geometría (ROADMAP E6.7)

**Para qué:** el 2026-10-02 la deriva de los paneles por XQuartz se explicó en minutos con una sonda que
anotaba cada movimiento y quién lo pedía; sin ella, solo se veía el síntoma. Ahora va dentro de explorer
(`ui/geomtrace.py`), para que cualquiera pueda mandar un registro desde su máquina:

    EXPLORER_GEOMETRY_TRACE=1 explorer cubo_im.fits   ->  ~/.cache/explorer/logs/geometry-<pid>.log

- **EVT:** el Move o Resize que sufrió la ventana o un panel, con los botones del ratón y el puntero.
- **CALL:** una llamada de explorer (`setGeometry`, `move`, `resize`, `setFloating`) con los marcos que la
  pidieron, del más interno al más externo. Un EVT sin CALL delante vino de Qt, del gestor o del puente.
- **LOOK, SHOW, HIDE:** el aspecto puesto, y un panel o ventana que aparece o se va.
- Apagado no envuelve nada (una prueba lo comprueba), y `stop()` lo deja todo como estaba.
- Variable propia: `EXPLORER_TRACE` ya era la traza de tiempos (Perfetto) de `obs/trace.py`; con
  `EXPLORER_TRACE=geometry` esa traza se escribía en un fichero llamado `geometry` en la carpeta actual.

**Visto funcionar:** fuera de pantalla en el Mac (un arranque en glass: el `setFloating` de
`glass.py place_panels` y el `setGeometry` de `fit_window`), en Linux, y por el puente en bellatrix con el
gestor tipo quartz-wm de las pruebas: ahí aparecen las llamadas del propio puente
(`bridge.py _apply_geometry <- windows.py configured`).

**Visto de paso, sin investigar:** con `EXPLORER_TITLEBAR=wm` bajo ese gestor, la ventana principal baja de
y=94 a y=110 (16 px). El gestor de las pruebas ignora la gravedad a propósito, y el prototipo dice que con
gravedad estática quartz-wm no desplaza: puede ser solo del gestor de las pruebas.

### 2026-10-03 (11): las size hints en XQuartz (ROADMAP E6.5, E6.14)

Lo que faltaba de E6.5: comprobar en XQuartz el efecto del arreglo del tipo de `WM_NORMAL_HINTS`
(`822e4db`). Medido en el Mac: XQuartz 2.8.6 con quartz-wm, display `:3`, 3067×1513, explorer por el
puente, cubo sintético (3, 4, 5, 96, 80). La ventana principal y el panel flotante se mueven por la API
6 veces cada uno (20, 12 px por paso, 0.5 s entre pasos, como un arrastre). Tras cada paso se anotan la
posición pedida, la de Qt y la de X. Las hints de antes del arreglo se recrearon con un monkeypatch del
tipo (40), sin tocar el código. Hay dos modos de barra: la propia y `EXPLORER_TITLEBAR=wm`. Resultados y
script en `bench/results/e65_xquartz_2026-10-03/` (en el Mac). La swap no creció durante la medida.

| hints | ventana principal, pasos 3–6 | panel, barra propia | panel, marco del gestor |
|---|---|---|---|
| antes (tipo `WM_NORMAL_HINTS`) | +22 px en y en cada paso | +22 px | +16 px |
| ahora (`WM_SIZE_HINTS`) | exacta | exacta | exacta |

Antes del arreglo, quartz-wm no leía la gravedad y colocaba la ventana por debajo de lo pedido. Qt toma esa
posición como la suya, así que en un arrastre, que mueve desde la posición creída, el error se suma en cada
paso: el mecanismo de F23c del prototipo. Con el arreglo, la ventana cae donde se pide.

Aparte (E6.14, abierta y sin investigar): los dos primeros movimientos de la ventana principal justo después
de mostrarla caen lejos de lo pedido (x 1147, y 22; después +618 px en y), igual con las dos hints. Desde
el tercero son exactos.

### 2026-10-03 (12): los primeros movimientos en XQuartz (ROADMAP E6.14)

**Con el arranque real** (`ui.app.run`, puente, XQuartz 2.8.6, registro de geometría activo): seis
`move()` de la ventana principal a partir de 3 s, separados 0.5 s. Los seis caen exactos en X y en Qt,
desde el primero. La ventana estaba donde la puso explorer, (1437, 71), y quartz-wm la respetó.

**Con la sonda de (11)** (ventana construida a mano, pedida en (200, 150) antes de mostrarla), el registro
dice quién movió la ventana:
- a los 679 ms, quartz-wm la recoloca en (1147, 22) y el puente lo aplica (`windows.py:265`, `configured`);
- `move(220, 160)` a los 2681 ms; 11 ms después el puente vuelve a aplicar (1147, 22);
- `move(240, 172)`: el puente aplica (1147, 22) y después (240, 790);
- `move(260, 184)`: aplica (240, 790) y después (260, 184), por la otra rama (`windows.py:261`); desde ahí,
  exactos.

Son avisos sintéticos del gestor que llegan después de nuestra petición, con la posición anterior. No
están entre lo pedido (`rec.asked`) ni son anteriores a la última petición (`cfg_seq`), así que el puente
los toma por nuevos. Mi hipótesis previa, que el tamaño que fija `Shell` con la primera imagen pisaba los
movimientos, era falsa: el registro no muestra ninguna llamada de `Shell`.

Sin explicar: por qué quartz-wm recoloca una ventana pedida en (200, 150), y de dónde sale (240, 790).
E6.14 queda abierta con esto. Scripts y datos en `bench/results/e65_xquartz_2026-10-03/` (Mac).

### 2026-10-03 (13): espectros y λ-t en cocoa (ROADMAP E5.17, E5.20)

E5.17 decía que en una sonda en cocoa los espectros y la λ-t salían vacíos. Lo comprobé con el arranque
real (`ui.app.run`), en ventanas del Mac, cubo sintético (3, 4, 5, 96, 80), en classic y en glass: el
cursor se lleva a (40, 30) a los 4 s y se mira a los 6 s. En los dos looks, `Shell.last` tiene los
espectros (4 × 5, todos finitos, en ese píxel) y la λ-t (3 × 5). Las capturas de los paneles tienen entre
191 y 401 colores, y vistas muestran los cuatro Stokes con sus ejes físicos y la λ-t con su cursor. No es
un fallo: lo vacío venía de la sonda de entonces, que esperaba en un bucle anidado. Capturas en
`bench/results/e517_cocoa_2026-10-03/` (en el Mac).

En la captura de la λ-t, el eje de tiempos rotula 08:17, 08:17, 08:16: en HH:MM, con una cadencia de 20 s,
dos marcas seguidas dicen lo mismo. El prototipo hace igual (`app/viewer.py:1103-1104`). Queda como E5.20,
para decidir.

### 2026-10-03 (14): el pool de numba al arrancar por `run.sh` (ROADMAP E0.16)

`run.sh` exportaba `NUMBA_NUM_THREADS=64`, un valor del primer commit de entorno (09-28). Es anterior a la
medida de las lecturas dispersas con 128 hilos (E1.12, 09-30). `data/_numba.py` sube el pool a 128, pero
solo si la variable no está fijada, así que todo lo que arrancaba por `run.sh` se quedaba en 64.
`gather.py:34` y `executors.py:65` limitan los hilos al pool.

**Medida** (bellatrix, sin fijar a nodo porque la pregunta es de número de hilos, bajo el cerrojo): λ-t
en frío desde las frames del 6173 (sin `_sp`), con `NUMBA_NUM_THREADS=64` o sin fijar, en procesos
separados y rondas alternas. Cuatro lecturas por proceso, en filas a 64 de distancia (las de `rowbands`
no se solapan).

| ronda | 64 hilos | 128 hilos |
|---|---|---|
| 1 | 0.46 s | 0.23 s |
| 2 | 0.56 s | 0.36 s |
| 3 | 0.39 s | 0.40 s |
| total | mediana 0.57 s (16 lecturas) | 0.34 s (12 lecturas) |

La carga subió de 5 a 22 durante la medida (otros usuarios), y en la cuarta ronda el proceso de 128 no
devolvió nada. Concuerda con la medida de E1.12 (0.56 frente a 0.42). Datos en
`bench/results/e016_threads_2026-10-03/`.

Dos errores de mi sonda, corregidos antes de esta tabla:
- importaba numba antes que explorer, así que `_numba.py` no subía el pool y la variante «128» tenía 32;
- leía filas a 7 de distancia y, desde la tercera lectura, venían de la memoria de `rowbands`.

**Arreglo:** `run.sh` deja la variable al usuario. El doctor importaba numba antes de que explorer
dimensionara el pool e informaba los núcleos (32), no el pool del visor; ahora lo importa por la capa de
datos. `run.sh doctor` en bellatrix: `threading layer omp, 128 threads`.

### 2026-10-03 (15): el Mac Intel en la integración continua (ROADMAP X.10)

El tercer entorno de `[tool.uv]` (Mac Intel: numba 0.62.1, con su numpy y su llvmlite) no se instalaba ni
se probaba en ninguna parte. Según el changelog de GitHub (2025-09-19, «macOS 13 runner image is closing
down»), `macos-13` se retiró en diciembre de 2025. Para x86_64 queda `macos-15-intel`: runner estándar,
macOS 15, la última imagen Intel de Actions, que se retira en otoño de 2027. Añadido a la matriz, con la
fecha junto a la etiqueta. Después de esa fecha el Mac Intel no se probará en ninguna parte. La primera
ejecución llegará con la próxima subida.

### 2026-10-03 (16): un solo arranque para el visor y su self-test; `setup_env --link` (ROADMAP E0.15, X.4)

**E0.15.** `bench/explorer_selftest.py` construía su propia ventana: sin barra de título, con la clase base
del display (nunca el puente) y sin bordes en los paneles. Medía una ventana que nadie ve; es el F4 del
prototipo, que desde entonces comparte `app/startup.py`. Ahora `ui.app.start()` hace todo lo que `run()`
hacía antes del bucle de eventos, y lo devuelve (`Started`: aplicación, `Shell`, cubo, display, tema
aplicado, instantes). `run()` es `start()` más el bucle. El self-test usa `start(saved_layout=False)`: la
disposición guardada del usuario no se lee, ni se escribe al cerrar, ni se borra. Su
`open_to_first_frame_s` sigue contando desde que existe la aplicación, como el del prototipo. En el Xvfb
privado de bellatrix, con `--x11 bridge`, el self-test informa `bridge: true` y la sonda del enlace X
corre, como en el arranque real.

**X.4.** `setup_env.sh --link` instalaba y pasaba el doctor antes de enlazar. Ahora, si el entorno está al
día (el criterio de `run.sh`: el `cksum` de `uv.lock` es el guardado al construirlo) y es del modo pedido
(un entorno `--dev` sirve también sin `--dev`), solo enlaza. La prueba usa un entorno falso y un `PATH`
sin uv ni conda: si el atajo no se toma, el script se detiene enseguida en vez de instalar. La ejecución
real en bellatrix recreó `~/.local/bin/explorer` con el mismo destino (`scripts/run.sh`); `.bashrc` no se
tocó.

### 2026-10-03 (17): la barra de herramientas tras restaurar una disposición (ROADMAP E5.18)

Un estado guardado lleva la visibilidad de la barra. Una disposición guardada con la barra oculta dejaba
sin ella a un look que la usa, y una con la barra visible dejaba una barra vacía de 20 px sobre la imagen
de glass. El prototipo fuerza la barra tras restaurar: la muestra en `viewer.py:2413-2415` y glass la
vuelve a ocultar en `look_glass.py:618-622`. Explorer ahora hace lo mismo en `LayoutStore.restore`.

Primer intento, fallido: decidía por el look de la ventana. `test_start_paths` lo pilló enseguida
(`glass-classic`: la barra oculta en classic y modern). Al salir de glass, `_start_afresh` restaura la
disposición de classic cuando la ventana todavía lleva glass. Ahora se decide por la disposición que se
restaura (la de glass es la de `-glass`), y la prueba nueva cubre también ese caso. `check.sh` en
bellatrix: 504 pasan, las 2 de E0.13 como antes.

### 2026-10-04: las pruebas de `setup_env.sh` en los runners de GitHub (ROADMAP X.4)

La CI falló en Ubuntu 22.04 y 24.04 con la prueba de X.4 del caso desfasado. La causa fue una suposición
mía: que con `PATH=/usr/bin:/bin` no habría uv ni conda, y el script se pararía enseguida. Los runners
tienen conda. El script siguió a `== pip: requirements/lock-dev.txt`, y pip fue a instalar en el
intérprete al que enlazaba el entorno de pega, el del propio proyecto. Lo paró PEP 668
(«externally-managed-environment»); sin esa marca habría modificado ese Python.

Ahora la prueba no depende de lo que tenga la máquina:
- un uv de pega va primero en el `PATH`: responde a `--version`, así que el script lo elige antes que
  cualquier conda, y falla en todo lo demás;
- un conda de pega muestra que nunca se llega a él;
- el `python` del entorno de pega es un script que no hace nada.

Con un conda en el `PATH`, las dos pruebas pasan. Con el `setup_env.sh` de antes de X.4, la del entorno al
día falla en el uv de pega, sin tocar nada. En el Mac y en bellatrix ya pasaban, porque allí no había
conda en ese `PATH`.

### 2026-10-04 (2): mypy en el Mac Intel (ROADMAP X.10)

La primera ejecución en `macos-15-intel` falló en mypy: 6 `type: ignore` sin usar, todos sobre numba
(`config`, `prange`). Mi primera explicación, que numba 0.62 declarara esos atributos, era falsa. La
rueda 0.62.1 para Mac Intel no trae `py.typed` (comprobado listando la rueda de PyPI), así que, con
`ignore_missing_imports`, mypy toma numba como `Any` y no hay nada que ignorar. La 0.67.0 sí lo trae, y
en ella esos atributos no existen. Reproducido aquí con una configuración de mypy que no sigue los tipos
de numba: los mismos 6 errores. Con `unused-ignore` añadido a esos `ignore`, ninguno en los dos casos.

### 2026-10-04 (3): los límites de color golden en el Mac Intel (ROADMAP X.10)

Tras el arreglo de mypy, el Mac Intel llegó a las pruebas, y una golden falló. Los límites simétricos de
una frame del caso sintético (`limits.2`) salían a 1 ulp de float32 de la referencia: 5.744442768684799e-11
frente a 5.744443115629494e-11. Para separar versión y arquitectura, guardé la submuestra exacta de esa
frame y calculé `np.percentile(|s|, 99)` en este Mac arm64. Con numpy 2.5.3 (la de la referencia) sale el
valor de la referencia; con 2.3.5 (la que fija el Mac Intel), en un entorno temporal, el del Mac Intel. Es
la versión: la interpolación de `np.percentile` sobre float32 redondea distinto. El prototipo, con la
misma numpy, daría lo mismo.

La prueba sigue exigiendo igualdad bit a bit cuando numpy es la que registra la referencia, y admite 1 ulp
de float32 con otra versión. Comprobé la segunda rama sustituyendo solo el percentil de esa frame por el
de 2.3.5. Dos errores de mi simulación por el camino, ambos corregidos:
- falsear `np.__version__` antes de importar astropy rompió astropy;
- `np.isclose` con su `atol=1e-8` por defecto sustituía todos los percentiles de orden 1e-11.

### 2026-10-04 (4): una prueba de tiempos en un runner cargado

En `macos-latest` falló `test_the_server_never_waits_for_the_pointer`. El log tenía la explicación: los 20
pasos con `sleep(0.025)` tardaron 2.41 s en vez de 0.5 (unos 120 ms por cada sleep de 25 ms), y el último
tamaño llegó 0.246 s después del último movimiento, cuando el límite era 0.2 s. No había nada encolado:
el runner iba lento. La prueba quería comprobar una propiedad («un tamaño por detrás como mucho, nunca el
arrastre entero») y la medía con el reloj. Ahora la cuenta: tras el último movimiento, el servidor aplica
como mucho el tamaño en curso y el último.

Medido con una versión encolada de pega, con movimientos cada 10 ms frente a 30 ms por tamaño: el contorno
deja 1 o 2 tamaños por aplicar, la versión encolada 13 o 14, igual con todos los tiempos 5 veces más
largos. Con movimientos cada 25 ms la separación era pobre (1–2 frente a 3–4), por eso la prueba usa 10
ms. Pasa 5 de 5 veces aquí, con 8 procesos ocupando la CPU, y 3 de 3 en bellatrix.

### 2026-10-04 (5): el panel de espectro fuera de sitio tras un reset en glass, desde bellatrix

El usuario ve el espectro fuera de su sitio, sin alinear con nada, tras un reset en glass, al lanzar
explorer en bellatrix (por `ssh -Y`, el puente y XQuartz en su Mac). No lo he reproducido. Probé cinco
situaciones antes del reset (recién abierto, espectro movido a mano, paneles ocultos con I, ventana
movida, ventana reducida) en tres entornos: cocoa en el Mac, y el puente en bellatrix con Xvfb sin gestor
y con el quartz-wm de pega. En todas, la posición que cree Qt y la real en X dejan el espectro a la
derecha de la ventana por `GAP` y alineado arriba, con la λ-t debajo.

Quedan dos sospechosos que esas pruebas no cubren:
- el quartz-wm real recolocando el panel después de que explorer lo coloque (el mecanismo de E6.14);
- el monitor que cree explorer: por el puente, `monitor_rect` no usa los heads de Xinerama, y una
  pantalla de XQuartz puede ser dos monitores.

Para separarlos, el registro de geometría (E6.7) anota ahora:
- `SCREENS` al arrancar: las pantallas de Qt y los heads de X;
- `RESET` en cada reset;
- `PLACE` con el monitor y el marco de la ventana de los que parte cada colocación.

`scripts/demo.sh` lo guarda por defecto (`EXPLORER_GEOMETRY_TRACE=0` para no hacerlo), y al cerrar dice
dónde está el fichero. Lanzado por el puente en bellatrix escribió `SCREENS` y `PLACE`, con la ventana
ajustada a 891 px y el espectro en su borde derecho más `GAP`. Falta el registro del caso real.

### 2026-10-04 (6): el espectro fuera de sitio en glass, desde bellatrix: la causa

El registro de la sesión del usuario (`demo.sh` por `ssh -Y`, dos monitores que explorer ve bien, sin
reset: M de classic a glass) lo explicó:
1. glass coloca los paneles bien, el espectro en (2757, 55);
2. 230 ms después llegan los avisos de quartz-wm con la geometría con que se creó la ventana X del panel,
   (2703, 87) con 598×423, y el puente los aplica como nuevos (`windows.py:265`);
3. el espectro vuelve allí, 42 px encima de la ventana principal.

El puente descarta los avisos de una geometría que pidió antes de su última petición (`rec.asked`), pero
la geometría de creación no estaba entre ellas. En Xvfb, sin latencia, ese aviso llega antes que la
colocación de glass, y por eso no se reproducía.

Reproducido con el arranque real (`ui.app.start`, puente) y el gestor de pega con `--late 300`: el
espectro acaba en (725, 32) frente a (584, 0); sin retraso queda en su sitio. Una primera versión de la
prueba con `bridge_app` fallaba también sin retraso: ese atajo no pasa por el arranque real. La prueba
usa ahora `glass_switch_app.py`. Con la geometría de creación anotada como pedida, la prueba pasa;
`tests/xvfb` 22 pasan y `check.sh` solo falla en las 2 de E0.13.

Por confirmar en el caso real: si quartz-wm, además, devuelve de verdad la ventana a su tamaño de
creación. En el registro hubo cambios de tamaño posteriores por la rama de «ventana dentro de un marco»
(7.2–7.3 s), que con el lado de Qt solo no se pueden distinguir de un eco.

### 2026-10-04 (7): segunda sesión desde bellatrix: la otra ruta del mismo fallo

Con el arreglo de (6), el usuario repitió la sesión por `ssh -Y`: entró seis veces en glass con M. El
registro (`geometry-819580.log`) muestra que el aviso sintético viejo ya no se aplica. Pero en las
colocaciones 1, 3 y 6, 150–200 ms después, el espectro volvió a (2703, 87) por otra rama del puente: la de
una ventana dentro del marco del gestor, en la que el puente pregunta a X dónde está. X respondió la
geometría de creación porque quartz-wm aún no había aplicado la petición de glass. En la 3 y la 6, un aviso
posterior lo puso bien entre 0.6 y 1.1 s después; en la 1 se quedó mal. Ahora esa respuesta pasa la misma
regla que los avisos sintéticos: una geometría pedida antes de la última es un eco. La prueba unitaria
nueva falla antes del arreglo. `tests/xvfb` 22 pasan; `check.sh` solo falla en las 2 de E0.13.

La sesión acabó con «the X display went away»: las dos conexiones del puente (la ventana y el contorno) se
cerraron a la vez a los 53.8 s, lo que apunta a XQuartz o al túnel X de ssh, no a una petición de explorer
(que cortaría solo una). El doctor de después salió bien. Pendiente de lo que diga el usuario.

### 2026-10-04 (8): «the X display went away»: XQuartz se cayó

La segunda sesión desde bellatrix acabó con las dos conexiones X del puente cerradas a la vez (la ventana y
el contorno de redimensionado), 3 s después de que el usuario redimensionara la λ-t por el borde. El
usuario no cerró nada.

En el Mac hay un informe de fallo de `X11.bin` a las 12:13:20, el final de esa sesión. XQuartz 2.8.6 en
macOS 26.5.2 murió por SIGSEGV (`KERN_INVALID_ADDRESS`) en su hilo de dibujo asíncrono
(`com.apple.Xplugin.asyncRendering`), al aplicar la forma de una ventana: `_xp_configure_window_cb` →
`shape_window_internal` → `CGSWindowSetShape` → `memmove`. Después XQuartz se reinició: ahora es `:4`, y
eso explica que mi conexión de prueba a `:3` fuera rechazada por autorización.

Explorer da forma (X SHAPE) a tres cosas: las esquinas redondeadas de la ventana, las de los paneles y el
anillo del contorno de redimensionado. El contorno es una ventana override-redirect reutilizada a la que se
cambia tamaño y forma en cada paso del arrastre. Es el patrón de la incidencia de XQuartz #499 (macOS 26,
XQuartz 2.8.6): redimensionados repetidos de una ventana override-redirect reutilizada bloquean el servidor
durante segundos (3.4 s tras 40), en el mismo código rootless con SkyLight. La #499 informa de bloqueos,
no de cierres; nuestro fallo, con su forma, no aparece documentado. **Hipótesis sin verificar:** el
contorno lo provoca. Reproducirlo en el XQuartz del usuario puede tirarlo abajo, así que no lo he
intentado sin preguntar.

### 2026-10-04 (9): arrastrar un panel sobre otro, explorer frente al prototipo

El usuario nota más lento en explorer que en el prototipo arrastrar paneles sueltos unos sobre otros. En
el prototipo eso se alivió (F27: una ida y vuelta a X por cada aviso del gestor, 167 de 780 ms en un
arrastre de 40 pasos). Nada lo medía en explorer.

`bench/panel_drag.py` lo mide. Cada programa arranca por su camino real, con el puente y sus títulos de
panel. Con los dos paneles sueltos, se arrastra el título del espectro con XTEST (40 movimientos cada
20 ms, sobre la λ-t y luego sobre la ventana principal), y un observador en el propio servidor X mide el
retraso con que se ve cada movimiento, el final y los bytes.

Dos primeras versiones no valían:
- movía los paneles por la API en `bridge_vs_prototype.py`, con la ventana sin barra de título: los
  paneles los enmarcaba el gestor, y el puente del prototipo ni llevaba a X los movimientos de Qt;
- tenía un error de signo en la posición de X.

Bellatrix, Xvfb 3840×1080, quartz-wm de pega, enlace emulado de 8 ms por sentido, 4 rondas ABBA, carga
0.4–0.7 (`bench/results/panel_drag_2026-10-04/`):

| | explorer | prototipo |
|---|---|---|
| retraso de X por movimiento, mediana | 17.7–18.0 ms | 33.4–35.5 ms |
| p95 | 19.2–19.5 ms | 38.8–40.6 ms |
| movimientos mostrados | 40/40 | 38–40 |
| de soltar a la posición final | 0.1 ms | 0.1–21.8 ms |
| píxeles por arrastre | 4.0–4.1 MB | 5.6–7.1 MB |

En esta emulación, explorer sigue al ratón con una ida y vuelta y el prototipo con dos. Lo que nota el
usuario tendría que venir de lo que la emulación no tiene: el XQuartz real (quartz-wm, el dibujo de macOS,
bloqueos como los de la incidencia #499) o su enlace real. Sin medir en XQuartz: XTEST está apagado allí
salvo que se active. Que el panel arrastrado quede debajo de la λ-t, en los dos programas, no es
concluyente: el gestor de pega no sube la ventana al hacer clic, y quartz-wm sí.

### 2026-10-04 (10): las paradas de los paneles al arrastrar por ssh -Y

El registro de la última prueba del usuario (`geometry-1075661.log`, classic, dos monitores, XQuartz por
`ssh -Y`) no tiene ningún movimiento de los paneles venido de avisos del puente: los arreglos de (6) y (7)
aguantan. Arrastró mucho, sobre todo la λ-t (598×776), también de un monitor al otro. Qt recibe del orden
de 85–150 posiciones por segundo, con huecos típicos de 6–12 ms. Pero casi la mitad de los arrastres
tienen **paradas de 145 a 290 ms**: el panel se queda quieto mientras el ratón sigue. En esos huecos el
registro no muestra nada más.

No se han reproducido:
- bellatrix, Xvfb con el quartz-wm de pega, cubo real del 6173, enlace sin límite y limitado a 48 MB/s (la
  medida del enlace del usuario): explorer, retraso máximo 11–13 ms, quietud máxima 29–30 ms, ningún
  movimiento por encima de 100 ms; el prototipo, máximo 17–51 ms;
- el XQuartz del usuario en el Mac (XTEST activado con
  `defaults write org.xquartz.X11 enable_test_extensions -boolean true` y XQuartz reiniciado, con
  permiso), cubo sintético, paneles 560×420: explorer muestra las 40 posiciones, retraso mediano 6.9 ms,
  máximo 15.8 ms, quietud máxima 31 ms, acaba donde debe y por encima de la λ-t.

En XQuartz el primer clic sobre una ventana inactiva solo la activa (la preferencia «click-through» está
apagada por defecto), así que el banco hace ahora un clic de activación antes de arrastrar. Aun así, el
banco no consigue arrastrar el panel del prototipo en XQuartz, ni el de explorer cuando lo agranda a
598×776: queda por arreglar antes de comparar ahí. Falta también lo que tienen los arrastres del usuario y
ninguna prueba: el enlace ssh real hacia XQuartz y el cubo real a la vez, y los paneles grandes cruzando de
un monitor a otro.

### 2026-10-04 (11): ráfagas cada medio segundo al arrastrar, y lo que se repinta

En el registro `geometry-1124805.log` (classic, XQuartz por `ssh -Y`) el espectro se movió a ráfagas: de
10 a 17 posiciones en unos 0.1 s y luego nada durante **510–514 ms**, una y otra vez (26 huecos de más de
100 ms en 24 s). Un periodo tan regular apunta a un temporizador o a un tope. La cola de eventos del puente
despierta a Qt en el primer evento de cada lote, y no hay en explorer un temporizador de 0.5 s que encaje.
La incidencia #499 de XQuartz describe bloqueos en `xp_lock_window` / `SLSLockWindowRectBits` al mover y
redimensionar ventanas en macOS 26. Sin verificar.

Para separar los dos casos, el registro anota ahora cada evento de ratón que toma el puente (`XIN`) con la
hora del servidor X. Si esas horas vienen ya separadas 0.5 s, el retraso nace en XQuartz o en el Mac; si
vienen juntas y se procesan a golpes, en el enlace o en explorer. En bellatrix, un arrastre por el puente
escribió 45 líneas `XIN`.

Aparte, en el XQuartz del usuario (XTEST activado), un arrastre del espectro por encima de la ventana
principal envía 6.8 MB en 5 envíos. No es el panel arrastrado: es la ventana principal, que se repinta bajo
el aviso de acople de Qt (`QRubberBand`). `Hairline`, el filo de las esquinas, se repinta 9 veces, pero
solo sobre lo que ya se repinta debajo. El prototipo envía lo mismo (5.6–7.1 MB). No explica las ráfagas
del usuario: en esa sesión arrastró por el otro monitor, lejos de la ventana principal.

El arrastre por XTEST en XQuartz solo prende si XQuartz es la aplicación activa de macOS. Si no, el primer
clic activa la aplicación y el segundo la ventana. Las ejecuciones buenas se hicieron con XQuartz al
frente.

Un error mío al hacer los commits: el del registro `XIN` lo rechazó el hook (asunto largo). Una cadena de
`&&` saltó los pasos siguientes, y un commit de documentación posterior se llevó el código preparado, con
el mensaje «[DOC] journal: …» y sin `Behaviour:` ni `Tests:`. Con permiso del usuario, la historia subida
se reescribió para darle su mensaje (`1c523dd`, contenido idéntico) y se subió forzando, con
`--force-with-lease`. Desde entonces, cada commit se comprueba antes del siguiente.

### 2026-10-04 (12): las paradas al arrastrar nacen en XQuartz

Nueva sesión del usuario (`geometry-1182770.log`, classic, XQuartz por `ssh -Y`, después de que XQuartz
se reiniciara para activar XTEST). El usuario la nota «mucho mejor». La mayoría de los arrastres van
fluidos (110–290 posiciones/s, huecos máximos de 15–28 ms); quedan algunas paradas de unos 500 ms.

Las 3191 líneas `XIN` dan la hora del servidor de cada movimiento. Cuando hay un hueco nuestro de más de
100 ms, la hora del servidor tiene casi el mismo hueco: 546 frente a 545 ms, 526/525, 830/828, 507/505,
504/502. XQuartz, es decir el Mac, deja de producir o entregar movimientos del ratón durante medio segundo,
y ni el enlace ni explorer los retienen. Solo en un caso el retraso fue nuestro: 502 ms con 7 ms de
servidor.

Que vaya mejor tras reiniciar XQuartz encaja con un XQuartz que se degrada con el uso. La incidencia #499
describe un bloqueo que crece con el número de redimensionados. **Hipótesis, sin medir.** En el Mac, 30
arrastres del contorno (1200 redimensionados) no mostraron crecimiento de las idas y vueltas.

### 2026-10-04 (13): la vista 2×2, un 40 % más lenta que la del prototipo (ROADMAP E5.19)

`bench/grid_step.py` mide el paso en t con la vista 2×2 (I, Q, U, V a la vez) en los dos programas, cada uno
por su arranque: desde el paso hasta que los cuatro cuadrantes tienen la t nueva, más una vuelta del
bucle. Condiciones: bellatrix, offscreen, cubo 6173, fijado al nodo NUMA 0 (CPU pares), bajo el cerrojo,
4 rondas ABBA de 20 pasos, carga 0.2–2.

| | explorer | prototipo |
|---|---|---|
| antes | 68.3–70.4 ms | 48.0–50.8 ms |
| con todas las reducciones en tiras (experimento, parche en tiempo de ejecución) | 48.6–51.5 ms | — |
| con el cambio | 48.8–49.4 ms | 49.8–51.2 ms |

cProfile: `reduce_u8`, 8.8 ms por cuadrante, los cuatro uno tras otro. Un cuadrante sale de ~350×350 px,
por debajo del umbral de tiras, que iba por píxeles de salida, así que se reducía en un solo hilo aunque
lee la frame entera de 2k (f = 6). El umbral va ahora por lo que se lee (salida × f²). El prototipo diezma
cada cuadrante (1 de cada k píxeles, sin promediar): más barato y con aliasing. Explorer promedia y queda
igual de rápido. La vista única no cambia: 19.3–19.9 ms con el cambio frente a 19.5–21.1 con el
`reduce_u8` antiguo, en ABBA. Una ejecución suelta de 26 ms antes de esa comparación era ruido.

Quedan en el paso unos 11 ms de límites de color (2.7 ms por cuadrante), los mismos que en el prototipo.

### 2026-10-04 (14): el filo de las esquinas y los límites de color en la vista 2×2

Del perfil del paso en t con la vista 2×2 quedaban dos costes que no son de lectura:
- **El filo de las esquinas (`Hairline`):** 762 contornos redondeados en 45 pasos, 2.4 ms por paso. Cubre
  la ventana para dibujar 1–2 px, y Qt lo repintaba con cualquier cambio debajo. Ahora tiene una máscara:
  una banda de 3 px en los bordes y las esquinas. La ventana sale idéntica, con máscara o sin ella (0
  píxeles distintos de 540 000). En ABBA, fijado al nodo 0, las medianas por ronda son 47.6–52.5 ms con
  máscara frente a 49.6–51.8 sin ella: unos 2 ms, con solape. `check.sh` y `tests/xvfb` (22) en bellatrix.
- **Los límites de color:** ~11 ms por paso (2.7 por cuadrante), calculados en el hilo de la interfaz; el
  prototipo hace lo mismo. El techo, con los límites gratis (parche en tiempo de ejecución), es 47 → 40–42
  ms. Pide calcularlos en el hilo que lee, también en la lectura anticipada (que hoy no da futuros), y que
  sigan idénticos a los del prototipo. Queda como E5.21.

### 2026-10-04 (15): oscuro y claro mientras corre, con T (ROADMAP E5.23)

El usuario pidió una forma de cambiar entre el modo oscuro y el claro, y que la rendija (E7) suba en la hoja
de ruta. E7 pasa a ser la primera de las abiertas, marcada como prioridad.

**Medida:** las dos ventanas, la cambiada y una arrancada en ese tema, offscreen en bellatrix, con el cubo
sintético (20, 4, 15, 120, 160) a 1400×900. Por cada parte se cuenta qué fracción de píxeles difiere en más
de 24 niveles. El cambio solo de la aplicación (`style.apply_theme`, oscuro → claro, classic) dejó en el tema
viejo:
- la ventana, 53 %;
- la imagen, 60 %;
- los espectros, 99 %;
- la λ–t, 30 %;
- el candado de la imagen, 87 %;
- el panel de espectros, 91 %.

La paleta llega a todos los widgets, pero cada parte tomó el tema al construirse:
- el fondo y el gris de la imagen;
- la tinta de las curvas y de los ejes de pyqtgraph, que fija la pluma al crearse;
- los candados;
- los rótulos de la vista 2×2;
- los mapas divergentes;
- la hoja de los segmentos de Stokes y la de la hoja `?`;
- el estilo propio de la ventana (separadores).

**Hecho:**
- cada parte tiene `set_light`, y `Shell.set_theme` los llama tras `apply_theme`;
- el aspecto se vuelve a poner (marcas, tarjetas, mapas);
- en glass, en su sitio (`GlassChrome.retheme`). Quitarlo y ponerlo devolvía los paneles junto a la
  ventana y mostraba la imagen entera.

**Resultado:** las 16 combinaciones dan 0 píxeles distintos en todas las partes:
- classic, modern, glass y la vista 2×2;
- en los dos sentidos.

El arranque con el código nuevo es idéntico al de antes en los 8 casos. El cambio cuesta ~205–215 ms
(~300 en glass), sin fijar al nodo 0: es una tecla, no un paso.

**Dos fallos del estilo, que solo se ven al cambiar:**
- **Separación de la barra de herramientas:** `polish` la pone a 6 px, pero el `StyleChange` de Qt llega
  después y la devuelve a 1. Los controles quedaban 5 px más juntos que en un arranque en ese tema; el único
  resto del primer intento (6.9 % de la barra).
- **Hojas de estilo:** los menús, las barras de desplazamiento y las listas de los combos conservaban la hoja
  del tema viejo, porque `polish` solo llenaba una hoja vacía. Ahora reemplaza también la suya del otro
  tema, nunca la de la aplicación.

**Pruebas:** `tests/unit/test_theme.py`, más una en `test_style.py` y otra en `test_look.py`. Contra el
código de HEAD, con `set_theme` como el cambio de la aplicación sola, fallan 11 de 12. Pasa la de glass en
su sitio, que vigila que nadie lo resuelva quitando y poniendo glass. Toda la suite unitaria pasa en
bellatrix con los dos arreglos, (15) y (16): 489 y 1 omitida.

**Queda:**
- **El contorno de redimensionar** conserva el azul de selección con que se creó, de un tono algo distinto
  en el otro tema.
- **Un Mac en tema nativo:** T pasa a Fusion y suelta las costuras (`MacSeams`); no se ha probado en
  ventana real.
- **Guardar el tema para la sesión siguiente** es una decisión del usuario (E5.24).

### 2026-10-04 (16): `python -m explorer` en un árbol con `.qtlibs/only`

Encontrado al pasar la suite en bellatrix: `test_a_start_with_the_variable_writes_the_trace` falla con
`attempted relative import with no known parent package`.

**Causa:** en Linux, `cli.main` se relanza sin el `LD_LIBRARY_PATH` ajeno, como `[python] + sys.argv`. Bajo
`-m`, `sys.argv[0]` es la ruta de `__main__.py`, que el proceso nuevo ejecuta como guion suelto.

**Por qué no se veía:** solo se relanza donde existe `.qtlibs/only` (bellatrix). La integración continua y
el Mac no lo tienen, y la orden `explorer` pasa por su propio guion.

**Arreglo:** relanzar con `sys.orig_argv`, que conserva `-m explorer`. La prueba nueva de `test_cli.py`
falla antes del arreglo con `-m` y pasa con la orden.

### 2026-10-04 (17): el tema elegido con T, también en el arranque siguiente (ROADMAP E5.24)

El usuario decidió que el tema se guarde. Se guarda el que está en uso al cerrar, como el aspecto, pero uno
por forma de mostrar (`ui/v1.<forma>/theme` en `layout.ini`):
- **Por qué no uno para todas:** por el puente auto es oscuro y en un Mac local es nativo. Uno común
  llevaría el oscuro de una sesión por ssh al Mac local, que dejaría el tema nativo por Fusion oscuro.
- **Sin pulsar T** se guarda el mismo que se habría elegido, así que no cambia nada.
- **`--theme` explícito manda.** Sin él, el guardado; si no hay ninguno, auto.
- **`--reset-layout`** no lo borra: el tema no es disposición.

`--theme` y `start(theme=...)` pasan a tener `None` por defecto. La prueba de `explorer demo` esperaba
`auto` y ahora espera `None`, que significa lo mismo que en `explorer`.

**Pruebas:** dos nuevas, en `test_layout.py` y `test_app_start.py`; esta encadena cuatro arranques con T. Las
dos fallan sin el cambio. Toda la suite unitaria pasa en bellatrix: 491 y 1 omitida.

### 2026-10-04 (18): `explorer` en el PATH de una terminal nueva, comprobado (ROADMAP X.3)

En bellatrix, `explorer --version` daba `command not found`. El enlace `~/.local/bin/explorer` existía, pero
esa carpeta no estaba en el PATH y el `~/.bashrc` no tenía el bloque.

**Causa:** `--link` juzgaba el PATH por el del proceso que lo ejecutaba. Por ssh o desde un guion, ese no es el
que tendrá la terminal siguiente del usuario. Además, sin una terminal donde preguntar, no escribía el fichero
de arranque.

**Ahora:**
- **Qué PATH tendrá:** se pregunta a una terminal nueva de la shell del usuario, de login y sin login, desde un
  entorno limpio.
- **Si ya hay una carpeta habitual en ese PATH** (`$XDG_BIN_HOME`, `~/.local/bin`, `~/bin`), el enlace va ahí y
  no se escribe nada.
- **Si no,** `~/.local/bin` entra en el fichero de arranque, en un bloque marcado y una sola vez:
  - bash: `~/.bashrc`, y además el de login si este no lee `~/.bashrc`;
  - zsh: `~/.zshrc`.

  El bloque se escribe como `$HOME/...`, así sirve a un home montado en otra ruta. `--no-update-shell` no
  escribe nada y dice qué añadir.
- **La comprobación:** las terminales nuevas tienen que encontrar este enlace antes que ningún otro `explorer` y
  ejecutarlo. Si no, falla y dice por qué.

**Probado:**
- **`test_setup_env.py`,** siempre en un HOME temporal: 6 pruebas nuevas, que fallan con el script anterior. En
  macOS (bash 3.2 y zsh) y en bellatrix.
- **Con copias de los ficheros de arranque reales:**
  - Mac: escribe en `.bashrc` y `.bash_profile`, porque este no lee el primero. 5.8 s.
  - bellatrix: escribe solo en `.bashrc`. 27 s, por las cinco shells nuevas con ese `.bashrc`.
  - La segunda ejecución no escribe nada en ninguno de los dos.
- **El paso del CI,** que ahora prueba bash y zsh, de login y sin login, desde otra carpeta: pasa en el Mac y
  en bellatrix con un HOME vacío.

**Falta** ejecutarlo en la cuenta real del usuario en bellatrix; toca su `~/.bashrc` y espera su visto bueno.

### 2026-10-04 (19): los límites de color, fuera del hilo de la interfaz (ROADMAP E5.21)

**Hipótesis:** `stats.limits` suelta el GIL, así que calcularlo en el hilo que lee no frena la interfaz.
Condiciones: bellatrix, fijado al nodo 0, sin el cerrojo, carga 2.8, 8 frames de 2044×2030 del cubo 6173, 80
llamadas.

| medida | resultado |
|---|---|
| `limits` en serie | 1.69 ms por frame |
| `limits` en 4 hilos | 0.64 ms por frame |
| bucle de Python en el hilo principal, solo | 11.50 ms |
| el mismo bucle con `limits` en otro hilo | 10.66 ms |

Lo suelta.

**Hecho:**
- **Dónde se calculan:** `Levels.ahead` calcula y guarda los límites en el hilo que leyó la frame, antes de
  pasar el resultado a la interfaz. Vale para la imagen, cada cuadrante de la vista 2×2 y las frames leídas por
  adelantado; `prefetch` da ahora el futuro de su lectura.
- **En la interfaz:** los encuentra en la caché. Uno que se está calculando en otro hilo se espera, no se repite.
- **Cuándo no se calculan:** para una lectura ya vieja, en el hilo principal, y con el candado cerrado (los
  límites fijos siguen ganando).
- **Valores:** los de antes (`image_levels`), luego los del prototipo (golden).
- **Seguimiento de las lecturas:** el planificador sigue una lectura hasta que su resultado está en el bucle.
  Con el futuro de la lectura, una espera sobre `in_flight()` acababa antes de los límites y `settle` daba
  vueltas en vacío.

**Medida:** paso en t con la vista 2×2. `bench/grid_step.py`, offscreen, cubo 6173, bellatrix, nodo 0, bajo el
cerrojo, orden A B C C B A en 4 rondas, 20 pasos por ejecución, carga 2.6–4.8:

| | medianas por ejecución |
|---|---|
| antes | 50.8–55.0 ms (y una primera en frío de 61.0) |
| con el cambio | 45.4–48.6 ms |
| prototipo | 47.9–54.4 ms |

**Contadores, en los 160 pasos con el cambio:**
- 0 límites calculados en la interfaz y 0 esperas;
- 100 de 100 servidos de la caché por ejecución;
- antes del cambio, 80 calculados en la interfaz por ejecución.

El hueco entre guardar una frame leída por adelantado y tener sus límites no se dio nunca, así que no hace falta
tocar la caché de frames.

**Negativo:**
- Se ganan ~5 ms de los ~7 del techo medido con los límites gratis (47 → 40–42 ms, aquel con menos carga).
- La mediana queda por debajo de los 50 ms de 20 fps; el p95 no (53–66 ms).

### 2026-10-04 (20): E7.1, dibujar la rendija (variante D, sin cortes aún)

**Portado del prototipo** a `ui/slit.py`, de `app/viewer.py` 811, 836, 869-875, 1224-1243, 1355, 1419,
1486-1619 y 1721-1739, y de `app/icons.py` 111 y 219:
- S o el botón de la barra activan el modo.
- Clic añade un punto en el centro del píxel; doble clic termina.
- Clic derecho quita el último punto; sin puntos, sale del modo.
- Esc o S cancelan la rendija a medio dibujar y conservan la terminada; ⌫ o Supr la quitan.
- Dos puntos dan una recta; tres o más, una Catmull-Rom por todos.
- La terminada va a `ViewState.path` mediante `Session.set_path`, que exige dos puntos como mínimo y los recorta
  a la imagen.

**El lápiz** se dibuja al dpr de la pantalla de la imagen (F69a), con el punto activo en (1, 23).
`ui/gestures.py` devolvía la cruz tras cada clic o arrastre; ahora devuelve el puntero en reposo, y el lápiz
sobrevive al clic.

**Color y aspectos:**
- El trazo usa el color del cursor en classic y el acento en modern y en glass.
- La pista sigue al tema (T).
- En la vista 2×2 la rendija está en los cuatro paneles y se puede dibujar en cualquiera.
- En glass la pista baja bajo la clave de color.
- A y D quedan libres (F75); la pista no las nombra hasta que existan.

**Pruebas:** en bellatrix, offscreen, nodo 1.
- `test_slit_draw`: 15/15 en 3 de 3 ejecuciones. Las 15 fallan en `3860a0a`. Con solo `gestures.py` revertido
  falla 1, porque vuelve la cruz.
- `tests/unit` en la copia del agente: 509 pasan y fallan 2, las mismas que en `3860a0a`, donde pasan 494:
  - la de `run.sh` del doctor, porque esa copia no tenía entorno;
  - el tool tip del puente, que solo falla en la suite completa.

**Negativo:** en glass el botón de la rendija no se ve, porque glass solo pasa a su barra los botones que
conoce. El arreglo va en `ui/glass.py`: añadir `nav.slit` en `GlassChrome._bar` y en su `_flatten`. Falta
también comprobarlo en una ventana real, y eso lo mira el usuario.

**Nota de método:** los agentes en paralelo compartían el scratchpad, y un `msg.txt` con nombre fijo llevó el
mensaje de un commit a otro. Se corrigió con `--amend` antes de integrar. Cada agente debe usar su propio
subdirectorio.

### 2026-10-04 (21): icono de la aplicación, el cubo con un corte (ROADMAP E5.28)

El usuario eligió el cubo entre cinco propuestas. Hasta ahora explorer no tenía icono.

**Qué es:**
- La fuente es `ui/assets/explorer.svg`: un cubo isométrico con un corte en el acento, sobre una losa oscura.
- Lo dibuja el motor SVG de Qt en todas las ventanas.
- El plugin `qsvgicon` viene en las ruedas de PySide6-Essentials 6.11.2: comprobado en el Mac arm64 y en
  bellatrix. El CI instala las mismas ruedas, pero no se ha ejecutado allí.
- Sin el plugin (rutas de plugins vacías), explorer arranca sin icono y lo avisa en el registro.

**Coste,** medido en procesos nuevos con la aplicación ya creada:

| dónde | coste |
|---|---|
| Mac, sin pantalla (3 ejecuciones) | 2.6–8 ms |
| Mac, cocoa (3 ejecuciones) | unos 4 ms de QIcon más 11 ms de la imagen de 256 px del Dock; 34 ms la primera vez |
| Mac, primera carga del plugin con el Mac en swap | 538 ms |
| bellatrix, sin pantalla, nodo 1 | 4.3 ms (un QIcon vacío, 1.7 ms) |

Generar los PNG con QSvgRenderer costaba 15–30 ms, así que se descartó.

**Por eso se pone después de la primera imagen.** Importar `appicon` cuesta 2.7 ms en StorNext, y también se
importa después.
- Primera imagen en bellatrix (cubo sintético, sin pantalla, 7 ejecuciones alternadas): mediana 2.29 s antes y
  2.37 s después, dentro del ruido (1.9–3.2 s).
- El icono llega 29–37 ms después de la primera imagen, así que no puede estar en ese tiempo.
- En el Mac, el Dock muestra el icono de Python hasta la primera imagen y luego cambia al cubo.

**Qué muestra cada sistema:**
- **xcb** (Xvfb en bellatrix): la ventana principal, creada antes del icono, publica después `_NET_WM_ICON` a
  16, 32, 64 y 128 px.
- **Mac:** `NSApp.applicationIconImage` es el cubo a 256 px.
- **Puente X11:** la ventana no tiene `_NET_WM_ICON`. Es un resultado negativo y queda como E5.29.

**Exportación:** `tools/icons/export.py` genera desde el mismo SVG los PNG de 16 a 1024, el ICO, el ICNS (con
iconutil) y el árbol hicolor. No se versiona nada generado.

**Arnés de pruebas:** el de `test_start_paths` sustituía entera la espera tras la primera imagen. Con el icono,
los 9 arranques fallaban. Ahora solo intercepta la de `run()`.

**Pendiente de diseño, sin probar:** a 16 px el trazo (0.78 px) queda blando. Una variante con trazo más grueso
para 16 px es decisión de diseño.

**El parche del puente (E5.29),** descrito y sin aplicar, porque el puente lo tenía otro trabajo (E5.25):
- **La conversión:** el contrato de capas impide que `platform` importe `ui`. La conversión del QIcon a ARGB
  (`appicon.net_wm_icon`, que solo usa Qt) pasa a `platform/xbridge`, y `ui.appicon` la importa de allí.
- **`windows.py`:**
  - `_NET_WM_ICON` entra en `ATOMS`.
  - En `_properties`, tras `_NET_WM_PID`, se llama a un `set_icon(rec)`, que cambia la propiedad con los datos
    del icono de la ventana o la borra si no hay icono.
- **`bridge.py`:**
  - El filtro de eventos atiende `WindowIconChange`, junto a `WindowTitleChange`, para las ventanas que no son
    emergentes.
  - Hace falta porque el icono llega después de la primera imagen, con la ventana principal ya creada.
  - Que Qt envíe ese evento a las ventanas de nivel superior tras `ApplicationWindowIconChange` sale de leer su
    código; no está probado.
- **Tamaño:** 16 + 32 + 48 + 128 px son 79 904 bytes, bajo los 262 140 de una petición sin BIG-REQUESTS. Basta
  una sola ChangeProperty.

### 2026-10-04 (22): los paneles de glass mal pintados al arrancar por el puente: la máscara gris (ROADMAP E5.25)

**La traza del puente.** La traza de geometría no ve el pintado, así que el puente tiene ahora la suya.
- `EXPLORER_BRIDGE_TRACE=1` escribe `~/.cache/explorer/logs/bridge-<pid>.log`.
- Por ventana: lo que se crea, mapea, forma, mueve, envía y copia; los avisos del servidor; y los errores de las
  dos conexiones del puente, que antes se ignoraban sin decir nada.
- A los `EXPLORER_BRIDGE_PROBE` s (2 y 6 por defecto) lee cada ventana del servidor X (GetImage), la compara con
  lo enviado y con lo que tiene Qt, y guarda las imágenes en PNG en `bridge-<pid>/`.

**Reproducido en Xvfb.** Condiciones: bellatrix, Xvfb a 3840×1080, el gestor tipo quartz-wm con `--late 300`, y
el arranque real en el glass guardado (antes, una sesión en glass cerrada).
- La imagen de la λ–t quedó negra en X, en todos los sondeos, en 4 de 10 arranques con el cubo sintético
  (91 709 px) y en 4 de 10 con el CRISP 6173 (118 854 px).
- Los 8 tenían la λ–t antes que la ventana principal; ninguno de los otros 12 falló.
- Cada fallo dejó 4 errores en la conexión de imagen, todos sobre la máscara gris: BadDrawable en PutImage y
  BadPicture en Composite.

**El mecanismo:**
1. La primera actualización lleva las tres ventanas.
2. Sus trozos grises (1 B/px por RENDER) pasan por una sola máscara de 8 bits, que crece cuando una ventana la
   necesita mayor y libera la vieja.
3. Los trozos de cada ventana se codifican uno tras otro y se envían todos al final. Cuando la máscara creció
   para la principal (743×923), la de la λ–t (560×437) ya estaba liberada al salir sus trozos.
4. El puente los anotó como enviados, y la comprobación periódica no volvió a mandarlos.

El orden de las ventanas es el de `topLevelWidgets()` de Qt, que cambia de un arranque a otro: por eso «no
siempre, muchas veces». El espectro, en oscuro, no tiene trozos grises.

**Arreglo:** una máscara por actualización, del tamaño de la mayor ventana con trozos grises, pedida antes de
codificar. Después, 0 de 10 con el sintético (3 con la λ–t primero) y 0 de 10 con el 6173 (6 con la λ–t
primero).

**Pruebas:**
- `test_bridge_glass_start.py` envía una actualización con un panel de 560×408 y después una ventana de
  825×863, grises, y las lee de X. Antes del arreglo, 228 480 de 228 480 px mal y 2 errores X; ahora, bien.
- Otra prueba recorre el arranque entero tres veces con la traza. En una pantalla de 1920 px pasa también sin el
  arreglo, porque la imagen de la λ–t no siempre va en la primera actualización: 6 arranques antes del arreglo,
  5 con la λ–t primero, ninguno falló.
- `tests/xvfb`: 25 pasan y 2 se omiten. `tests/unit`: 498 pasan.

Las 136–153 px distintas en todos los sondeos eran las esquinas fuera de la forma redondeada; la traza ya no las
cuenta.

**Sin confirmar en XQuartz** que sea lo que ve el usuario.

**Hipótesis sin medir:** la ventana se crea por la conexión de control y su GC por la de imagen, y un servidor
puede atender antes a la segunda. La traza lo diría con un XERR BadDrawable en CreateGC.

### 2026-10-04 (23): el tooltip que fallaba a veces en la suite completa: ventanas que la limpieza no borraba

**El síntoma:** `test_xbridge_input::test_tool_tip_after_a_rest` fallaba en la suite completa y pasaba sola (3 de
3).

**No era un commit:** en bellatrix (nodo 1, cuatro suites en paralelo), falló en `f639e74`, que es anterior a los
cambios de glass del día, y en `b5a5deb`, pero no en `a2abd97` ni en `ddaefc3`.

**Lo que se vio con una sonda (plugin de pytest):**
- En el momento del fallo, la ventana de la prueba estaba activa, no había emergentes ni modales, y el tooltip no
  llegó a mostrarse.
- Seguían visibles dos paneles flotantes, `spectrum` y `lambda_t`. El de espectros ocupaba (239, 48, 560, 380) en
  la pantalla, y el puntero de la prueba caía en (342, 341), dentro de él.
- Los dejó `test_polish.py::test_glass_panels_are_never_too_short`: su `Shell` estaba oculto, pero vivo.

**El mecanismo:** la limpieza (`tests/conftest.py`, `_no_windows_left`) apuntaba las ventanas de antes de la prueba
por el `id()` de sus envoltorios Python, que eran temporales. Liberados, sus direcciones las reutilizaban las
ventanas que creaba la prueba, que se tomaban por ventanas de antes y no se borraban.

**Medido:** con un registro de esos casos, una suite completa saltó 25 ventanas (11 `Shell` y 14 `QMainWindow`),
y el tooltip falló. Con los envoltorios vivos mientras dura la prueba, sus `id()` no se reutilizan: 2 de 2 suites
sin ese fallo.

**Una nota sobre mis sondas:** una primera versión de la sonda miraba las ventanas justo después de la limpieza, y
esa suite acabó en segfault dentro del `gc.collect()` de la limpieza. Mirando al empezar la prueba siguiente no
volvió a pasar. Es probable que la causara la propia sonda, pero no lo he aislado.

### 2026-10-04 (24): el icono en el Dock desde el lanzamiento (ROADMAP E5.28)

El usuario: en el Mac aparecía primero un icono blanco y al rato el cubo.

**De dónde sale el blanco:** no es un retraso de Qt. Es el icono que LaunchServices da a un ejecutable sin bundle,
un documento en blanco.
- Leído desde otro proceso (`NSRunningApplication.icon`), es ese documento antes y después de `setWindowIcon`.
- El proceso entra en el Dock al volver `QApplication()`. Antes no hay NSApp; después tiene política regular y
  tipo Foreground en LaunchServices.

**Primer paso: el icono justo después de la QApplication,** antes de abrir el cubo.

| | Mac (cocoa) | bellatrix (xcb) |
|---|---|---|
| condiciones | cubo sintético del demo, 8 arranques, 0.3–1.5 GB de swap libre | Xvfb, nodo 1, 8 pares alternados |
| icono puesto, desde el inicio del proceso | 0.46–0.53 s (antes 1.5–3.3 s) | 1.20–1.29 s (antes 2.6–2.8 s) |
| tras la QApplication | 12–28 ms | 2.1–2.8 ms |
| coste del icono | 11–27 ms, mediana 17 ms | — |
| primera imagen | ruido de 1.3–3.0 s | mediana 2.651 s frente a 2.649 s |

Aun así el blanco se veía.

**Segundo paso: en macOS, explorer arranca dentro de un bundle.** `run.sh` lo arranca a través de `explorer.app`,
dentro del entorno. Lo construyen `setup_env.sh` y, si falta, `run.sh` la primera vez; en el Mac del usuario
tardó 1.0 s.
- Lleva un `Info.plist` con `CFBundleIconFile` y el `.icns` hecho del SVG.
- El ejecutable es un enlace al Python del entorno; `__PYVENV_LAUNCHER__` hace que encuentre su entorno, y Python
  la borra, así que nada de lo que lance explorer la hereda.
- LaunchServices da entonces el cubo desde el lanzamiento.
- Sin bundle (un entorno que no es del usuario), arranca como antes.

Sin cambio medible en la primera imagen: 1.47–2.16 s frente a 1.46–3.11 s, en 4 pares. `run.sh` tarda 0.20 s
frente a 0.19 s.

**Resultado negativo:** poner el icono de NSApp por ctypes antes de Qt no cambia el que da LaunchServices; sigue el
documento en blanco. Si el Dock lo pinta en su primer fotograma no se sabe sin mirarlo, y no se implementó.

**Solo se comprueba mirando:** que el primer fotograma del Dock sea el cubo (`scripts/demo.sh`). Para comparar con
lo de antes: `.venv-Darwin-arm64/bin/explorer demo`.

### 2026-10-04 (25): referencias golden reexportadas, qué cambió (ROADMAP E0.13)

**Qué copia del prototipo vale:** la del Mac, la más nueva, con `app/pens.py` y los cambios del 10-03 y el 10-04.
En bellatrix no había nada más reciente ni cerrojo de edición, así que se subió con el `actualize.py push` del
prototipo. Las dos copias tienen ya la misma huella, `956a5a1e…`; las referencias tenían `a5f3bfce…`.

**La reexportación:** los dos casos, en bellatrix, con el Python del prototipo (3.12.14, numpy 2.5.3), en el nodo
1 y sin escribir cachés dentro del prototipo. Comparados con `compare.py --meta`:
- **stokes_6173:** las 35 matrices y todos los números de la meta son idénticos; solo cambia la huella. Las dos
  exportaciones son de bellatrix, así que ningún cambio del prototipo desde el 2026-09-29 toca lo que se exporta.
  No hay diff del código, porque el prototipo no está en git; la prueba es la salida idéntica.
- **synth_small:** 38 de 44 idénticas. Además de la huella, difieren 5 float64 en el último dígito. La referencia
  vieja era del Mac, y las 5 diferencias son de la máquina, no del código. Se aisló en las dos máquinas con el
  `slit_path` del prototipo (`viewer.py:811`, mismo texto) y el ajuste de `SpLP.calibrate` (`sources.py:96-100`,
  misma md5), sobre las mismas entradas: cada máquina reproduce su referencia bit a bit y no la otra.
  - `slit_path`, un valor por rendija (3.55e-15): los puntos, `hypot` y la longitud de arco son idénticos; difiere
    `np.interp`. Su `slope*(x - xp) + fp` con un solo redondeo (FMA, calculado exacto) da el valor del Mac, y con
    dos el de bellatrix, en los dos valores.
  - La calibración (escala, cero, residuo): `np.polyfit` sobre entradas idénticas bit a bit, con Accelerate en el
    Mac y OpenBLAS en bellatrix. Sin aislar qué rutina de LAPACK diverge.

  Las tolerancias de `test_data.py` (1e-12 relativo) ya lo cubren.

**Sustituidas:** la de synth_small, versionada, y la de stokes_6173, en la copia de bellatrix (no se versiona).
`tests/golden` en bellatrix: 26 pasan, con el caso real.

**La ruta del prototipo, dentro de la referencia versionada:**
- La exportación guarda en `meta["prototype"]` la ruta absoluta del prototipo. En la referencia nueva ese campo
  pasa a `../prototype`; el resto de la meta y las 41 claves se comprobaron iguales.
- La referencia anterior, versionada desde `328bcc5` (2026-09-29) y ya subida, lleva la ruta personal del Mac.
  Ni `hygiene.py` ni el grep de la historia la ven, porque numpy guarda las cadenas en UTF-32. Se abre X.11.

### 2026-10-04 (26): el icono por el puente X11 (ROADMAP E5.29)

Por el puente, las ventanas X no tenían `_NET_WM_ICON`; en xcb lo publica Qt.

**Qué hace:**
- **Dónde está la conversión:** pasa del QIcon a ARGB en `platform/xbridge/icon.py` (solo usa Qt, y `platform` no
  puede importar `ui`); `ui.appicon` la importa de allí.
- **Cuándo se publica:** cada ventana gestionada lleva `_NET_WM_ICON` desde que se crea, con su icono efectivo (el
  suyo, si no el de su dueña o el de la aplicación), y otra vez con `WindowIconChange`. Sin icono, la propiedad se
  borra.
- **Tamaño:** 16 + 32 + 48 + 128 px son una ChangeProperty de 79 928 B. Sin BIG-REQUESTS una petición tiene como
  mucho 262 140 B, y un servidor puede admitir menos: entonces se quitan los tamaños mayores hasta que quepa.

**Qt sí avisa** a las ventanas ya mostradas tras `QApplication.setWindowIcon`: dos veces a cada una, a la QWindow
y al widget, medido offscreen. Por eso no se vuelve a enviar un icono que X ya tiene, y la traza muestra una línea
ICON por ventana e icono.

**Coste** (bellatrix, nodo 1, 7 ejecuciones): 2.2 ms la primera ventana y 0.02 ms cada una de las demás.
Empaquetar valor a valor con `struct.pack` costaba 3 ms por ventana; ahora se empaqueta una vez.

**Comprobado en Xvfb,** leyendo las propiedades con python-xlib:
- La ventana principal y los dos paneles flotantes, hechos antes del icono, lo tienen después a 16, 32, 48 y
  128 px, igual que `net_wm_icon`.
- Una ventana hecha después lo tiene desde que se crea.
- Con un icono propio cambia solo el de esa ventana.
- Sin icono de la aplicación, la propiedad se borra.

**Pruebas:** las 8 nuevas fallan sin el cambio. `tests/unit`: 542 pasan (falla la conocida de `test_doctor`, en
una copia sin entorno). `tests/xvfb`: 26 pasan y 2 se omiten.

**XQuartz no lo usa:** quartz-wm (3570364) no lee `_NET_WM_ICON` ni lo anuncia en `_NET_SUPPORTED`, y al
minimizar pasa al Dock solo la ventana y su título. El servidor (`hw/xquartz`) tampoco lo menciona. Esto se ha
leído en el código, sin probarlo en el Mac: en el Mac del usuario, el Dock sigue mostrando el icono de XQuartz. Sirve
para los gestores de Linux y para xprop.

### 2026-10-04 (27): la vista 2×2 sin la clave de color de un solo Stokes (ROADMAP E5.30)

**El fallo:** en la vista 2×2 (tecla 5, «All»), cada panel I Q U V lleva su propio mapa y sus propios niveles.
Aun así, la clave de color del último Stokes quedaba encima, porque `set_grid` la subía a propósito, y describía un
solo mapa y un solo rango.

**El prototipo** nunca la mostraba ahí: crea la rejilla después de la clave, sobre el mismo widget, y la sube por
encima (`app/look.py:327`, `app/look_glass.py:928-945`).

**Ahora** `ColourKey.show_with` la oculta mientras la vista 2×2 está activa.
- Da igual por dónde se entre (5, «All») y lo que pase dentro: clic en un panel, C, M, T, la barra de glass.
- Al salir (1–4, un Stokes en el control, 5), vuelve la del Stokes de la imagen, con su mapa y su rango.

**Un segundo fallo, también arreglado:** C en la 2×2 solo cambiaba el mapa de la vista simple oculta. Ahora el
panel del Stokes de la sesión cambia al instante.

**Pruebas:** 15 nuevas (`tests/unit/test_grid_colour_key.py`). Con el código anterior fallaban 14 (la decimoquinta
solo existe en glass); con solo la mitad del arreglo, 2.

**Propuesta pendiente, sin construir:** una clave por cuadrante, con la etiqueta del Stokes dentro.

**Visto una vez y sin explicar:** en la batería del agente, `test_theme::…[light-dark-glass-False]` falló con un
~14 % de píxeles distintos, y pasó sola y al repetirla. Se abre X.12.

### 2026-10-04 (28): E7.2 y E7.3, el panel de la rendija y sus lecturas

El usuario, tras probar E7.1: solo se dibujaba la rendija, y no aparecía ninguna ventana con el resultado.

**Portado** de `app/viewer.py` (1023-1048, 1505-1515, 1664-1719, 1745-1948) a `ui/slitpanel.py` y
`core/slitreads.py`:
- **El panel:**
  - Los cortes temporal y espectral a lo largo de la rendija, con marcas de t, λ y el cursor.
  - Un clic elige t o λ y el punto de la rendija.
  - Sin el menú de pyqtgraph (F20g).
  - Sigue el tema, los aspectos, los mapas de color y la vista 2×2.
- **La pestaña de λ–t:** sale con S y se pone delante al terminar la rendija; se va con ⌫. En glass, el panel
  flota bajo λ–t.
- **Las lecturas:**
  - Con fichero por píxel, bloques en caché (F71, 8000), una lectura a la vez.
  - Sin él, filas por frame, tras 250 ms de reposo al dibujar; el corte espectral no se lee al reproducir.
  - Los cortes y sus niveles se hacen en un hilo propio (`Executors.slit`).
- **`GatedDock`:** la pestaña no se puede mostrar sin rendija. Sin esto, la restauración de la disposición la
  abría vacía (F70a), y en glass dejaba la ventana en 1098 px alrededor de una imagen de 480 px.

**Medida:** bellatrix, cubo 6173, nodo 0, bajo el cerrojo, ABBA en 4 rondas, offscreen. Con fichero por píxel,
carga 2.9-5.0 y 16 rendijas de 601-688 px:

| | explorer | prototipo |
|---|---|---|
| E/S de la rendija entera | 75.9 ms (24.1-103.8) | 76.0 ms (28.0-102.4) |
| de terminar a pintar los dos cortes | 118.6 ms | 109.5 ms |
| actualizaciones al dibujar (60 movimientos a 16 ms) | 45.5 | 76 |

La E/S es igual y queda dentro de los 23-96 ms, salvo la primera rendija de cada proceso. Sin fichero por píxel,
con carga 5.2-19.6, 217 frente a 381 ms; confundido por la caché de páginas y la carga.

**Negativo** (queda como E7.5):
- **Menos actualizaciones al dibujar.** Al principio eran 31, porque el resultado de cada paso llegaba tras el
  siguiente y se descartaba; ahora se muestra mientras se dibuja (`2e99840`). Aún quedan 49 peticiones para 60
  movimientos y 25 llegadas de bloques. La causa no está medida: la hipótesis es que el hilo de la interfaz se
  queda atrás.
- **Al terminar, 9 ms más que el prototipo.** La primera rendija de cada proceso tiene ~75 ms de más tras la
  lectura.

**Pruebas:** 43 nuevas, que pasan en 3 de 3 ejecuciones; las del panel fallan en `ad645ab`. Una de ellas pasa por
`ui.app.start` y dibuja la rendija con el ratón en los tres aspectos. `tests/unit` y `tests/golden` en la copia
del agente: 604 pasan y falla la de `test_doctor`, por la copia sin entorno.

### 2026-10-04 (29): glass con la ventana ampliada: se estrecha a la izquierda de los paneles (ROADMAP E5.27)

**El fallo:** en el Mac, con la ventana ampliada con el botón verde, al pasar a glass la ventana seguía del ancho de
la pantalla y los dos paneles caían encima. La traza lo mostraba: `PLACE … window (0, 30, 1352, 785)`, los
paneles en x = 791 y ningún `setGeometry` de la principal.

**Causa:** `fit_window` no hacía nada con la ventana ampliada (`isMaximized()`), igual que el prototipo
(`look_glass.py:543`).

**Medido en el Mac** (cocoa, una ventana de prueba):
- El botón verde deja a Qt en `WindowMaximized` al instante.
- Tras él, `setGeometry` y `showNormal` actúan al momento sin que la animación los deshaga, y `showMaximized`
  vuelve a ampliarla.
- Con FullScreenNone, `toggleFullScreen:` no hace nada: en un Mac local no se llega a pantalla completa.

**El arreglo,** la opción 1 que eligió el usuario:
- **Al entrar en glass,** la ventana ampliada deja de estarlo. Ocupa la altura del monitor desde su borde
  izquierdo, tan ancha como la imagen, con la columna de los paneles a su derecha. El resto de glass no cambia.
- **Al salir,** primero recupera el tamaño de antes de ampliarla y después se vuelve a ampliar, así que el botón
  verde la devuelve luego a ese tamaño.
- **El zoom de nuestra barra de título** (puente, xcb): la ventana ya se estrechaba, pero el botón la seguía dando
  por ampliada en glass. Ahora ese estado se olvida en glass y se devuelve al salir.
- **Pantalla completa** se trata igual que ampliada, porque no deja sitio para los paneles al lado. Al salir de
  pantalla completa, el marco cambia antes de que el widget lo sepa, así que se leen los márgenes de la plataforma;
  sin eso, la ventana se pasaba 4 px del monitor.

**Pruebas:**
- `test_glass_zoomed`, fuera de pantalla con un monitor de 1352×878: ampliada, pantalla completa y zoom de nuestra
  barra.
- `test_bridge_glass_zoomed`, por el puente con el gestor tipo quartz-wm: ampliada y zoom de la barra.
- Las cinco fallan antes, con una ventana de 1352 px en glass y los paneles en x = 791 o con el zoom de la barra
  aún puesto en glass, y pasan después.
- En bellatrix, `tests/xvfb` pasa entero dos veces y `tests/unit` no tiene fallos nuevos.

**Sin probar:** GNOME y KDE maximizando por xcb, y el Mac de punta a punta, que lo mira el usuario.

### 2026-10-04 (30): la higiene lee los binarios (ROADMAP X.11)

**El hueco:** `scripts/hygiene.py` se saltaba todo fichero binario. numpy guarda las cadenas en UTF-32, así que la
ruta personal de una referencia golden no la veían ni la higiene ni el grep de la historia.

**Ahora** los binarios versionados o preparados para commit se leen como Latin-1, UTF-16 y UTF-32 en todas las
alineaciones, cada miembro de un zip por separado (un `.npz` lo es).

**Comprobado:**
- La referencia vieja, sacada de la historia, da «Mac home path»; la actual sale limpia.
- El árbol: 0 hallazgos.
- Las dos pruebas nuevas (un `.npz` con la ruta, normal y comprimido) fallan con la higiene anterior.

**La exportación** de referencias guarda ya la ruta del prototipo relativa a explorer.

**Queda (X.11, parte 3):** la historia sigue teniendo esa ruta en `328bcc5`. Mirar los binarios de la historia
fallaría hasta que el usuario decida si se reescribe.

### 2026-10-05 (1): la historia limpia de la ruta personal (ROADMAP X.11)

El usuario decidió limpiar la historia y ejecutó él mismo los comandos preparados:
- Copia de seguridad: `git bundle --all`, fuera del repositorio.
- `git filter-branch` solo sobre `main` desde `b93c4a3`. Sustituye la única versión con la ruta (blob `e13dd22`)
  por la misma con `meta.prototype = ../prototype` (blob `5d0fca2`; las 41 claves y el resto de la meta, iguales).
  Un filtro traduce los identificadores citados en los mensajes.
- Subida forzada (`--force-with-lease`).

**Comprobado después:**

| comprobación | resultado |
|---|---|
| commits | los mismos 332 |
| contenido actual | sin diferencias con el de antes |
| los 25 commits anteriores | intactos |
| `b93c4a3` | pasa a ser `328bcc5` |
| la versión con la ruta en la historia de `main` | ninguna |
| los 5 binarios de la historia | limpios |
| las 10 citas de los mensajes | apuntan a commits existentes |
| GitHub | tiene el mismo `main` |

**Citas en los documentos:** las 178 citas de commits reescritos de `docs/` se tradujeron con la correspondencia de
las dos historias, emparejadas commit a commit, con los 332 asuntos iguales.

**La higiene** lee ya los binarios de toda la historia (1.8 s en el repositorio entero): la historia antigua daba
«Mac home path», la nueva nada.

**Queda:** GitHub puede servir un commit antiguo a quien conozca su identificador exacto hasta que limpie su caché.
El repositorio es privado; para borrarlo de inmediato habría que pedírselo a su soporte.

### 2026-10-05 (2): `setup_env.sh --link` con cualquier shell, y lo que necesita esta terminal (ROADMAP X.3)

El usuario: no debería hacer falta `source ~/.bashrc` a mano, y no todo el mundo usa bash.

**Lo que no se puede hacer:** un programa no cambia el PATH de la terminal que lo lanzó. Por eso los instaladores
piden abrir una terminal nueva o leer un fichero.

**Lo que se hace ahora:**
- **Una carpeta que la terminal actual ya tiene:** entre las carpetas habituales que una terminal nueva tendrá en el
  PATH, se prefiere una que ya esté en la actual; entonces `explorer` funciona al momento.
- **El final del script dice lo que necesita esta terminal:**
  - nada («ready in this terminal too»);
  - la orden de su shell (`source ~/.bashrc`, `source ~/.zshrc`, `. ~/.profile`, `source ~/.cshrc`);
  - `rehash` en tcsh y csh, que guardan la tabla de órdenes que encontraron al arrancar.
- **Cada familia de shell, con su sintaxis:**
  - tcsh y csh: su bloque en `~/.tcshrc` o `~/.cshrc`; una terminal de login se imita leyendo `~/.login` tras
    el fichero de arranque.
  - fish y las demás: se dice la línea que hay que añadir y no se escribe nada. fish no está probada: no está
    instalada en el Mac ni en bellatrix.
- **El README** ya no da una orden fija de bash.

**Pruebas:** `test_setup_env.py`, 12; las 4 nuevas fallan antes. Pasan en macOS y en bellatrix.

### 2026-10-05 (3): E7.4, la rendija en glass, en la disposición y con A/D

**Portado del prototipo:**
- **Glass con tres paneles (F84):**
  - El panel de la rendija es el tercer panel flotante, con la piel de glass.
  - Los tres se apilan 40/30/30 junto a la ventana (`look_glass.py:572`). Con S, el panel va debajo de λ–t si el
    monitor tiene sitio (320 px); si no, se apilan de nuevo los tres (`look_glass.py:607-618`).
  - I y ↺ lo conocen; sin rendija nunca se muestra.
  - El botón de la rendija va en la barra de glass, antes de Panels (`look_glass.py:729-731`). Con él, la fila de t
    pedía 454 px de los 448 de una ventana de 480; tras ceder los deslizadores, los huecos pasan de 8 a 4 px.
- **A y D (F75):** llevan el cursor al píxel anterior o siguiente de la rendija, fijado; desde fuera, al punto más
  cercano; mantenidas, la recorren. Sin rendija, la línea de estado dice para qué son.
- **La disposición (F21, F70a, F70b):** probada en cada camino: disposición guardada en classic y en glass, I, ↺, y
  la salida de glass, que devuelve la pestaña de λ–t. ↺ mientras se dibuja ya no quita la pestaña.
- **`MacSeams` (F59)** en el panel de la rendija, con prueba.
- **F71a no aplica:** solo existe la variante D, y las opciones llegan por un único `argparse`.
- **La rendija en el menú Panels** (`viewer.py:1131`), activa solo con rendija.

**Encontrado al traducir los nombres de la rendija para la prueba de humo del prototipo** (`bench/protoface.py`):
- La prueba de humo no arrancaba desde E7.1.
- Una segunda ventana sobre el mismo cubo daba `AttributeError: glass`. Su primera imagen ya estaba en la caché, y
  el planificador la mostraba dentro de su constructor, antes de que la ventana tuviera los atributos que lee.
  Corregido.

**La prueba de humo** (cubo 6173, offscreen, con y sin `_sp`), en las 19 comprobaciones de rendija y persistencia:
13 pasan, 2 fallan solo por la pista (ya corregida en E7.5), 2 por diseño (S pone la pestaña delante; sin rendija
no hay panel), 1 queda NO AÚN (la variante C) y 1 se salta (solo X).

**Pruebas:** `test_slit_glass` (6) y `test_slit_layout` (13), que fallan en el código anterior salvo 6 guardas.
Suites completas en bellatrix: `tests/unit` y `tests/golden` 654, `tests/xvfb` 28, sin fallos.

### 2026-10-05 (4): E7.5, la rendija al dibujar: lo que llega a la pantalla, y la rendija terminada

**Medida:** bellatrix, cubo 6173 con fichero por píxel, nodo 0, bajo el cerrojo, offscreen, ABBA con el código
anterior y el prototipo en las mismas rondas.

**Al dibujar:**
- Cada movimiento llega: 60 de 60, por `_Moves`.
- El hilo de la interfaz pinta una vez por pasada del bucle. Las pasadas duran 35-41 ms (el prototipo, 51-56); el
  banco se queda atrás y los movimientos de una misma pasada se juntan en un solo aviso: 24 avisos para 60
  movimientos.
- **Las 76 «actualizaciones» del prototipo eran llamadas a setImage.** Las hace dentro de cada movimiento, pero
  pinta 19-28 cortes; explorer pinta 35-46. `bench/slit_read.py` cuenta ahora los cortes pintados. La regla: una
  petición por aviso del Store, es decir, por pasada.

**Rendija terminada:**
- La lectura esperaba al aviso de los paneles, una pasada después: 23.5 ms, y 66 ms en la primera rendija. Ahora
  empieza en su propio aviso.
- El planificador volvía a leer y mostrar los espectros al cambiar los paneles (3.5-17 ms del hilo de la interfaz);
  ahora solo llena el panel que aparece.

**Tiempo propio al terminar** (total menos E/S), rendijas tras la primera:

| tanda | antes | después | prototipo |
|---|---|---|---|
| 4 rondas, carga 1.3-4.5 | 31.8 ms | 14.9 ms | 13.7 ms |
| 8 rondas, carga 1.8-8.4 | 32.4 ms | 27.3 ms | 14.0 ms |

Primera rendija: 98 → 45 ms y 74 → 61 ms (prototipo, 23 y 27).

**La primera rendija:** su panel aparecía primero como tercer panel; los espectros pasaban de 373 a 215 px y vuelta,
y su ResizeFreezer hacía un `grab()` de 79 ms. El prototipo crea el panel ya como pestaña de λ–t (`viewer.py:1047`).
Con ese cambio en `shell.py`, la primera rendija bajó de 63.8 a 24.2 ms (prototipo, 30.7), medido por el agente
sobre su rama. El cambio está en `main`, pero no se ha vuelto a medir tras integrarlo.

**La caché de bloques** cuenta ya en `Dataset.nbytes` y en el presupuesto: el 0.2 del presupuesto y como mucho 8000
bloques. 8000 bloques del 6173 son 333.3 MB; el proceso creció 331 MiB.

**La pista** dice «A/D walk the slit · ⌫ remove · S new slit», como el prototipo (`viewer.py:1536`).

**Negativo:**
- Hacer los cortes en el hilo que lee bajó los pintados de 46 a 33: descartado.
- Suscribir el planificador antes que el shell no dio nada; fue una tanda A/A por un `rsync` fallido.
- El tiempo de asentarse no mejoró.
- El tiempo propio al terminar sigue por encima del prototipo en 3 de las 4 tandas finales. El del prototipo varía
  entre ~14 y ~37 ms según la tanda, y dos tandas A/A ponen el ruido en ±4 ms.

**Pruebas:** 4 nuevas o cambiadas, que fallan antes. `tests/unit` y `tests/golden` en la copia del agente: 633
pasan; falla la de `test_doctor`, por la copia sin entorno.

### 2026-10-05 (5): las trazas con `--log`, y una tecla que falla lo dice

**El caso:** la ventana se volvió negra en una máquina a la que no se puede volver: un Mac, ssh a un Linux y de ahí
a un Mac, con XQuartz en una pantalla grande. Sin traza no hay forma de saber si fue el enlace o el servidor. Hasta
ahora solo `scripts/demo.sh` activaba la traza de geometría; `explorer algo.fits` arrancaba sin ella.

**Primer intento, medido y descartado: las dos trazas activas por defecto.** ABBA del autotest en bellatrix (nodo 0,
cerrojo, cubo sintético de 20×4×15×256×256, 4 rondas, carga 0.4-1.4):

| | trazas apagadas | trazas activas |
|---|---|---|
| mover el cursor, offscreen | 15.7-16.2 ms | 16.3-16.6 ms (+3 %, sin solapar) |
| mover el cursor, puente (rondas 2-4) | 19.9-21.1 ms | 22.1-22.4 ms (+7 %, sin solapar) |
| primera imagen, puente (rondas 2-4) | 1600-1620 ms | 1680-1860 ms |
| paso en t | 19.1-20.1 y 23.9-24.5 ms | 20.0-20.7 y 24.8-25.2 ms |

Un coste pequeño pero real en todas las sesiones, para servir a unas pocas. La causa no está medida: la hipótesis es
la línea por cada movimiento del puntero y la instalación de las trazas al arrancar.

**Lo que queda, a propuesta del usuario:**
- **`--log`** (en `explorer` y en `explorer demo`) activa las dos trazas: la de geometría y, por el puente, la del
  puente. Sin `--log`, ninguna, también en el demo, para que los dos caminos sean iguales. Las variables
  (`EXPLORER_GEOMETRY_TRACE=1`, `EXPLORER_BRIDGE_TRACE=1`) siguen sirviendo.
- **Las sondas del puente,** que leen cada ventana de vuelta (la imagen entera por el enlace), solo con
  `EXPLORER_BRIDGE_PROBE`.
- **Se guardan las 30 sesiones más recientes** de cada traza; las más viejas se borran solas.
- **El README** dice cómo informar de un problema.

**Una tecla que falla lo dice.** Qt solo imprime en la terminal lo que lanza la acción de un atajo, así que una
tecla que fallaba parecía no hacer nada. Es el caso de M en el cubo [nt, ny, nx] de ALMA de un compañero, que no se
reproduce aquí: en offscreen y en una ventana real del Mac, con o sin cabecera, M pasa por los tres aspectos. Ahora
todas las teclas (los atajos y las de la terminal, por `ActionRegistry.binds`) pasan por una guarda: el error con su
traza en `explorer.log` y una línea en la barra de estado.

**Pruebas:**
- `test_actions`: una acción que falla, por su atajo y por `binds()`. Falla antes.
- `test_geomtrace` y `test_xbridge_trace`: solo cuando se piden, con `--log` de punta a punta, las sondas aparte y
  la rotación. Fallan antes.
- `test_demo` comprueba que `--log` llega hasta `run`.

### 2026-10-05 (6): la ventana negra de Mats: el tamaño va y viene tras cada cambio por el borde

**El caso:** Mats K. vio la ventana volverse negra al hacerla grande. Mandó la traza de geometría de esa sesión
(`geometry-477441.log`, 1748 líneas, de ellas 1094 de movimientos del puntero), leída con scripts y no entera.

**La sesión** (52 s): explorer en un Linux, por el puente, hasta el XQuartz de un Mac con tres monitores unidos en
una pantalla X de 5568×1084. La ventana estuvo siempre dentro del tercer monitor (desde x = 3648, de 1920×1047).
Mats la agrandó cuatro veces por el borde con la barra de título de explorer: 1336×835 → 1452×873 → 1452×848 →
1748×1013 → 1716×1003. Además la arrastró: 283 movimientos.

**Descartado:** que la ventana cruzara de un monitor a otro o los superara. Su tamaño máximo, 1748×1013, cabe en el
tercero.

**Encontrado:** tras cada uno de los cuatro cambios por el borde, el tamaño de la ventana va y viene de 2 a 4 veces,
en 30-160 ms, entre el nuevo y el viejo:
1. El puente aplica un aviso atrasado del gestor (quartz-wm) con el tamaño anterior (`windows.py:346 configured`).
2. Luego vuelve a imponer el nuevo (`bridge.py:380 _run_call`).

Al final queda el tamaño correcto. Es de la familia de E6.14: avisos atrasados del gestor tomados por nuevos.

**Hipótesis, sin medir:** cada cambio de tamaño crea un pixmap nuevo en el servidor y reenvía la ventana entera
(hasta ~7 MB sin comprimir a 1748×1013), varias veces seguidas, por dos saltos de ssh. Mientras no llega, XQuartz
pinta de negro, y cuanto más grande la ventana, más tiempo. La sesión no tenía la traza del puente, que diría cuánto
duró el negro y si el servidor rechazó algo; ahora se activa con `explorer --log`.

**Siguiente paso:** reproducirlo en Xvfb con el gestor tipo quartz-wm y un enlace lento emulado, medir el tiempo en
negro y los reenvíos, y que un cambio de tamaño dé un solo cambio y un solo reenvío (E6.15).

### 2026-10-05 (7): por qué el tamaño iba y venía, y el arreglo (ROADMAP E6.15)

Mats redimensionó cuatro veces la ventana principal por su borde, por el puente y XQuartz (tres monitores en una
pantalla X de 5568×1084). Las dos trazas de la sesión (geometría y puente, pid 477441) dicen lo mismo en las cuatro:
el tamaño va y viene 2-4 veces en 30-160 ms entre el nuevo y el viejo, y cada tamaño se envía entero (a 1748×1013,
tres `SEND ... new back` en 104 ms, 5.7 MB). Además la ventana se queda en su sitio viejo: pedida en y = 3, 12, 75 y
18, acaba en y = 168, 50, 50 y 8.

**El mecanismo**, leído en el código de quartz-wm (`x-input.m`, `x-window.m`) y visto en la traza del puente:
1. Qt hace `setGeometry` como un `move` y luego un `resize`, y el puente pedía a X cada uno aparte.
2. quartz-wm responde al `move` con su registro del marco, que solo cambia cuando X confirma el marco: un aviso
   sintético con el sitio y el tamaño viejos. El `resize` lo arma con ese mismo registro: el marco nuevo va al sitio
   viejo. Por eso el sitio se perdía.
3. El puente aplicaba ese aviso a Qt con `resize` y luego `move`. Entre los dos, Qt tenía el tamaño viejo en el sitio
   nuevo, distinto de lo que X había dicho, y eso salía como petición nueva: en la traza, `CONF width=1452
   height=848` 0.3 ms después del aviso. X volvía al tamaño viejo y después al nuevo.
4. Lo que el puente creía haber pedido quedaba con el tamaño equivocado, y en los arrastres siguientes los avisos del
   gestor ya no se reconocían como ecos: 69 aplicados en un arrastre, la ventana tirada atrás.

**Reproducido en Xvfb** (bellatrix) con un gestor nuevo, `tests/xvfb/fake_quartzwm_frames.py`, que lleva el
registro del marco como quartz-wm, y `tests/xvfb/resize_app.py`, que redimensiona por la esquina de la barra de
título (pulsar, mover, soltar en el `EdgeResizer`). Dos redimensionados seguidos; se mide el segundo. Antes:
- Qt pasa por 1630×1133 y vuelve a 1480×1033;
- 4 peticiones, y el redimensionado se deshace (sitio y tamaño viejos), en 3 de 3 repeticiones;
- la misma `CONF width=1480 height=1033` justo después del aviso viejo que en la traza de Mats.

En Xvfb el final es el tamaño viejo y en XQuartz el nuevo: el orden en que el gestor atiende las peticiones cambia;
el mecanismo es el mismo.

**Arreglo** (`windows.py`, `bridge.py`):
- una geometría de Qt es una sola petición con lo que difiere de lo que X dijo (o de lo último pedido);
- mientras Qt toma la geometría de X, sus `Move` y `Resize` no piden nada; lo que Qt no acepte (su tamaño mínimo) se
  pide una vez, después.

Después, en 3 de 3: un cambio de tamaño, una petición, una ventana entera enviada (2.24 MB), en el sitio pedido.
Con `glass_switch_app` y `glass_zoom_app` bajo ese gestor, mismo resultado y menos peticiones (2 → 1, 6 → 3).

**El negro.** En Xvfb, con el arreglo, la parte nueva de la ventana se ve negra desde que X cambia de tamaño hasta que
llegan los píxeles: 123-136 ms sin enlace, 246-257 ms con `bench/xlink.py` a 8 ms y 20 MB/s, 590-609 ms a 25 ms y
5 MB/s (3 repeticiones cada uno; el 27 % de la ventana). Es el puente esperando píxeles, no X perdiéndolos. En la
sesión de Mats, en cambio, la traza dice que el puente lo había enviado todo y no hubo XERR; si vio negro después,
puede ser el dibujo de XQuartz (cf. #499). Sin las sondas (`EXPLORER_BRIDGE_PROBE`) no se puede saber.

**Medido y descartado:**
- Una regla de eco por tamaño (un aviso con un tamaño pedido antes del último, antes de que llegue el último), con
  una comprobación a X 1 s después: con el arreglo no se disparó ni una vez en redimensionado, `move` + `resize`
  aparte, arrastre, cambio a glass ni zoom. No entra.
- Basar la geometría pedida en la última de X en vez de en la última pedida: sin diferencia medible (0 retrocesos en
  un arrastre tras un redimensionado del gestor, con y sin el cambio). No entra.
- Conservar el contenido del pixmap viejo en la parte común: solo el 17-20 % de los cuadros de 32×32 de la ventana
  nueva son iguales (la imagen se reescala). No compensa.

**Sin probar en XQuartz real.** Mats: `git pull`, luego `explorer --log cubo.fits` por `ssh -Y`, redimensionar por el
borde, y mandar las dos trazas que se nombran al cerrar (`geometry-<pid>.log` y `bridge-<pid>.log`).

**Pruebas:** `tests/xvfb/test_bridge_resize.py` falla antes (2 cambios de tamaño, 4 peticiones, geometría final
vieja) y pasa después; `tests/unit/test_xbridge_resize.py` (5). En bellatrix, con todo integrado: `tests/unit` y
`tests/golden` 666 pasan, `tests/xvfb` 29 pasan y 2 se omiten.

**Probado también en el Mac del usuario,** sin ssh, contra su XQuartz con tres pantallas (dos 4K a 1920×1080 y la
del portátil, que XQuartz ve como 1147×719 y debajo de las otras). Normal, grande (1748×1050) y vuelta, en la de la
derecha y en la del portátil, con las sondas del puente:
- X tuvo la imagen correcta en los seis casos (0 px distintos donde se ve).
- Un reenvío por cambio de tamaño y ningún error.
- El usuario, mirando la pantalla, no vio negro en ninguno.

Lo que el caso de Mats tiene distinto es el enlace (dos saltos de ssh), el vaivén (ya arreglado) y su Mac y su
XQuartz. Queda pendiente su prueba con sondas (`EXPLORER_BRIDGE_PROBE`).

### 2026-10-05 (8): el puente frente a quartz-wm, petición a petición; las pruebas X con enlace (ROADMAP E6.14, E6.16-E6.20)

Tras E6.15, buscar los siguientes fallos de la misma familia antes que los usuarios: el orden en que el gestor y el
puente ven las peticiones del otro cambia con el enlace, y las pruebas X solo conocían un enlace de cero.

**Las pruebas X a través de un enlace emulado** (`EXPLORER_TEST_XLINK=RETARDO,MBPS`, `tests/xvfb/xlinkenv.py`): la
aplicación bajo prueba va por `bench/xlink.py`; el gestor y las miradas de la prueba al servidor, directas, como
quartz-wm y la pantalla en el Mac. Sin la variable no cambia nada. `tests/xvfb` entero en bellatrix (Xvfb 1920×1080,
nodo 1): sin enlace 29 pasan y 2 se omiten (166 s); a 8 ms/20 MB/s y a 25 ms/5 MB/s falla una, la del portapapeles
(164 y 172 s). Mecanismo: la aplicación contesta «copy» cuando Qt tiene el texto y su `SetSelectionOwner` llega al
servidor un retardo después; la petición de la prueba no encontraba dueño. Es de la prueba (nadie pega 16 ms después
de copiar): ahora espera al dueño. Ningún otro comportamiento cambió con el enlace.

**El puente frente a quartz-wm** (github.com/XQuartz/quartz-wm, `3570364`):

| Petición del puente | Qué hace quartz-wm | Qué espera el puente | Riesgo |
|---|---|---|---|
| ConfigureWindow x/y (`windows.py:315-341`, `configure` 298-313) | Mezcla lo no pedido con su registro `_xattr` (`x-input.m:653-670`); `resize_client` (`x-window.m:733-767`) valida (`validate_frame_rect` 2563-2571: entre 72×16 y la pantalla X; `validate_window_position`, `x-screen.m:655-802`: un marco en ningún monitor va a uno). Sin cambio pendiente, `do_resize` mueve el marco (582-627) y, sin cambio de tamaño, manda **en el acto** un aviso sintético con su registro: sitio y tamaño de antes (763-765). Cuando X confirma el marco, `report_frame_size` manda otro con el sitio nuevo (708-709). Con un cambio pendiente del mismo tamaño, `XMoveWindow` encadenado sin aviso inmediato (646-660); si no, a la cola, la última gana (664-666), con aviso inmediato | Aviso sintético = dónde está (ICCCM 4.1.5): lo último pedido se aplica, lo pedido antes es eco, lo no pedido se aplica (`windows.py:357-367`) | El aviso inmediato es posterior a la petición (no lo filtra `cfg_seq`) pero viejo: si el registro no lo pidió el puente (colocado o validado por el gestor), Qt salta atrás un viaje de ida y vuelta y vuelve con la confirmación. Si el gestor rechaza la última petición y se queda en algo pedido antes, ese aviso es su única respuesta (E6.17) |
| ConfigureWindow w/h | La misma mezcla: x/y del registro, que solo cambia al confirmar X el marco. Con cambio de tamaño, sin aviso inmediato (621-624); al confirmar, `XResizeWindow` del cliente (696-700): aviso **real**, en coordenadas del marco; sin sintético si además se movió (708) | Real y enmarcada → `TranslateCoordinates`, aplicado si no hubo otra petición (`windows.py:368-388`) | Con un `move` aún sin confirmar, el tamaño va al sitio viejo (E6.15 en un `setGeometry`; E6.16 en un `move()` y un `resize()`) |
| ConfigureWindow x/y/w/h | Sin mezcla: un `XMoveResizeWindow` del marco y aviso real al confirmar | Ídem | Ninguno: la forma segura |
| ConfigureWindow stack_mode (`windows.py:461-467`) | Al marco, no al cliente (`x-input.m:643-651, 673-676`); ningún aviso | Nada | — |
| MapWindow (`windows.py:171`) | `init_with_id` (`x-window.m:487-580`): marco (`reparent_in` 166-211); `place_window` (312-420) respeta PPosition/USPosition y si no coloca (transitoria centrada en su dueña, o en cascada desde la esquina del monitor principal) y valida; mapea; aviso con el registro **anterior** a la colocación (556); foco (564) | ReparentNotify → `rec.reparented` (`bridge.py:442`); el aviso de la geometría creada = `asked[-1]`, aplicado | Si coloca o valida, dos avisos: lo pedido y lo colocado (no pedido → aplicado). Correcto: E6.14 |
| WM_NORMAL_HINTS (`windows.py:266-279`, solo al crear) | `property_changed` → `update_frame` (1703-1739, 1570-1650): relee tamaño, Motif, tipo y `_NET_WM_STATE`; si cambia la decoración, vuelve a enmarcar | Gravedad estática; PPosition si Qt la movió | — |
| _MOTIF_WM_HINTS (`windows.py:209`) | Solo en `update_frame`; `property_changed` no la mira | Antes del mapeo: entra | Cambiarla después no haría nada |
| _NET_WM_WINDOW_TYPE | `update_net_wm_type_hints` (1175-1370), después de Motif: UTILITY pone la tira aunque Motif diga ninguna | NORMAL; UTILITY solo con `EXPLORER_TITLEBAR=wm` | Ya conocido (F23c) |
| WM_TRANSIENT_FOR (`windows.py:211, 218`) | `update_parent`, `update_group`, `update_frame` (1652-1691); `XAppleWMAttachTransient` del marco al de la dueña (1688) | Panel encima de su dueña | Sin medir: en Cocoa un hijo adjunto se mueve con su padre |
| _NET_WM_STATE (`windows.py:425-433`) | Por átomo (`x-input.m:455-460`, `x-window.m:1442-1491`): `do_maximize` (2335-2352) al `zoomed_rect` (`x-screen.m:836-873`); quitar → `do_zoom` (2314-2333); reescribe `_NET_WM_STATE` en cada cambio de marco (1411-1440) | Sigue `_NET_WM_STATE` (`bridge.py:502-512`) | Un marco igual al `zoomed_rect` sale como maximizado (`is_maximized`, 2308-2312) |
| _NET_ACTIVE_WINDOW (`windows.py:435-448`) | `focus:` (`x-input.m:451-452`, `x-window.m:1876-1924`): sube, `XSetInputFocus`, `WM_TAKE_FOCUS` | Contesta `WM_TAKE_FOCUS` (`windows.py:450-453`) | — |
| WM_CHANGE_STATE (`windows.py:420-423`) | `do_collapse` (`x-input.m:449-450`) | `WM_STATE` (`bridge.py:587-604`) | — |
| SHAPE (`windows.py:470-497`) | `ShapeNotify` → `update_shape` (`x-input.m:683-695`) | — | — |
| _NET_WM_ICON | quartz-wm no lo lee | Uno por ventana e icono | — |
| El aviso sintético de quartz-wm | `send_configure` (`x-window.m:276-298`): sitio del registro, tamaño de `_xattr`: (a) al adoptar; (b) en el acto ante una petición que no cambia ya el tamaño del marco; (c) al confirmar X un movimiento sin cambio de tamaño. Nunca tras un cambio de tamaño | Fresco si es posterior a la última petición | (b) es el registro de antes de la petición |

**Encontrado y arreglado:**
1. **E6.16, un `move()` y un `resize()`, dos peticiones.** `15221d3` hizo de un `setGeometry` una petición; un
   `move()` y un `resize()` siguen siendo dos. quartz-wm rellena la segunda (solo el tamaño) con el sitio de su
   registro y la encola: la ventana acaba en el sitio viejo con el tamaño nuevo, en X y en Qt. Bajo
   `fake_quartzwm_frames.py`, Xvfb 3840×2160: 3 de 3 a 25 ms/5 MB/s y 3 de 3 sin enlace (0 de 1 en una tanda
   anterior); primero el tamaño, 0 de 3. Arreglo: mientras X no haya dicho la geometría desde la última petición, la
   petición la lleva entera. Después, 3 de 3 bien en los dos órdenes y enlaces; el arrastre igual (40 peticiones, 0
   retrocesos); el negro igual (601-655 ms a 25 ms/5 MB/s).
2. **E6.17, un tamaño que quartz-wm rechaza.** Una ventana tan alta como la pantalla X a la que se pide crecer se
   queda como está (`x-window.m:640-644`) y la única respuesta es el aviso de su registro, algo pedido antes: el puente
   lo tomaba por eco. Con `--validate`, Xvfb 1920×1080: X 1200×1080 y Qt 1200×1150, 1150 filas enviadas a una ventana
   de 1080. Arreglo: si 1 s después de un eco no se ha aplicado ningún aviso ni se ha pedido otra cosa, el puente
   pregunta a X (`GetGeometry`, `TranslateCoordinates`) y Qt lo toma. En unas 40 ejecuciones de arrastres,
   redimensionados y glass no se disparó. Riesgo sin medir: si la última petición tarda en llegar más de 1 s (detrás
   de una imagen grande a 5 MB/s), Qt tomaría la geometría de antes un momento y volvería con el aviso.

**E6.14 explicada, no es del puente.** `validate_window_position` lleva a un monitor un marco que no toca ninguno, al
mapear y en cada petición. Con la disposición deducida de la pantalla X de entonces (3067×1513; el portátil, 1147×719,
abajo a la izquierda; deducida, no leída del Mac) una ventana de 900 px a la izquierda de x = 247 no toca ninguno:
(200, 150), (220, 160) y (240, 172) se recolocaron, (260, 184) y siguientes se quedaron; la sonda ya daba Qt = X en
cada paso. Reproducido con `--validate --heads` y ese agujero, sin enlace y a 25 ms, con el puente de antes de
`15221d3` y el de ahora. Sin explicar: el (240, 790) del segundo paso.

**El arrastre de la traza de Mats.** 156 avisos en 1.37 s para 78 peticiones: dos por petición, el inmediato del
registro (`x-window.m:763-765`) y el de la confirmación (708-709); 69 aplicados porque lo pedido guardaba el tamaño
equivocado (arreglado en `15221d3`). Ahora, 40 movimientos tras un redimensionado, 3 repeticiones: sin enlace 40 ecos y
40 «applied (the last asked)» alternados, sin efecto; a 25 ms/5 MB/s, 78 ecos anteriores a la última petición, 1 eco y
1 aplicado; 0 retrocesos de Qt. Nada que arreglar.

**El gestor con el registro en más escenarios** (sin enlace, 8/20, 25/5; 2 repeticiones, 1 con el puente anterior):
cambio a glass, ampliada a glass y vuelta (las dos formas), arranque en el glass guardado, paneles colocados, la
rendija y un panel arrastrado. Con los dos gestores, antes y después: la misma geometría final en X y Qt, las mismas
peticiones, ningún error de X. Cambian los avisos (el arrastre: 30 reales aplicados con el gestor viejo, ecos con el
del registro), no lo que se hace con ellos. Negro tras la primera imagen, igual en los dos: zoom 640-845 ms a 25/5,
zoom por la barra 237-260 ms a 8/20; panel arrastrado 179-218 ms en dos exposiciones a 25/5, 0 a 8/20.

**Medido, sin arreglar:**
- Gestor viejo, ventana sin marco: con `move()` + `resize()` Qt pasa una vez por el tamaño viejo (el aviso real del
  movimiento se genera con las dos peticiones ya en el servidor). X acaba bien.
- Una exposición se contesta copiando del pixmap del puente: a 25 ms el trozo expuesto se ve negro un viaje de ida y
  vuelta. Idea **sin probar**: el pixmap de cada ventana como su fondo (`CWBackPixmap`).
- Con la caché de numba vacía, la primera imagen llega 3-4 s después del mapeo (el emisor compila sus núcleos). Sin
  medir con la caché caliente.

**Sin probar en XQuartz real.**

**Pruebas:** nuevas `test_bridge_first_moves.py`, `test_bridge_panels.py`, dos en `test_bridge_resize.py`, tres en
`tests/unit/test_xbridge_resize.py`; `test_bridge_glass_zoomed.py` bajo los dos gestores. En bellatrix, con la venv
(unit y golden en el nodo 1, Xvfb 1920×1080): `tests/unit` + `tests/golden` 669 pasan y 2 se omiten (945 s);
`tests/xvfb` 35 pasan y 2 se omiten (227 s). En una copia sin venv, `tests/xvfb` igual a 8/20 (230 s) y a 25/5 (242 s). Las pruebas nuevas suman
unos 62 s a `tests/xvfb` sin enlace (166 → 228 s).

### 2026-10-06 (1): E8.1, cubos enlazados, el caso sencillo

**Qué hace.** `explorer a b c`: el primero manda; cada uno de los demás se planifica contra él (`data/link.py`) y, si
casa, se abre al lado. En la ventana, las imágenes lado a lado con el mismo tamaño y la misma región; en Spectrum y
λ–t, una pestaña por cubo. El cursor, el bloqueo y t son de todos; λ es la de cada cubo, y Stokes se comparte si
tienen los mismos. Los que no casan quedan fuera y la terminal dice por qué.

**Planificado contra `stokes_6173_im.icube`** (los 15 cubos de `data/lp` que no son `_sp`): se enlazan Blos y Vlos de
6173 (17 cuadros sin nombre: los 17 tiempos) y `stokes_6173_im.fits` (tiempos iguales a 2e-11 s). Los otros 12 se
rechazan: 10 por la rejilla (de 2030×2044 a 2052×2044 frente a 2031×2028; `stokesI_6173_im.icube` es 2032×2025), y
el 8542 alineado por la cadencia (84 tiempos frente a 17).

**Cambios fuera de la ventana:**
- **Hilos compartidos.** Con un hilo de numba por cubo, el espectro de un cubo enlazado abortó el proceso: «Numba
  workqueue threading layer is terminating: Concurrent access has been detected» (Mac, la primera prueba del
  planificador con dos cubos). Un cubo enlazado usa los `Executors` del primero (`Dataset(executors=)`) y no los
  cierra.
- **Lecturas pendientes al cerrar.** Al no cerrar los hilos, sus lecturas en cola corrían con los ficheros ya
  cerrados: `ShortRead` en la prueba (y, con el descriptor reutilizado, podría leer otro fichero). Ahora su `close()`
  espera a lo encolado en numba, background y slit.
- **Memoria.** Cada `Dataset` se daba el 15 % de la memoria del Mac (25 % en Linux): dos cubos, el doble.
  `GuardShare` reparte un presupuesto entre los n.
- **El aviso «values in counts»** salía tres veces por fichero (dos al planificar, una al abrir). Ahora una.

**Lo oculto no gasta.** Lecturas contadas por cubo (Mac local, offscreen; cubos sintéticos 5×4×15×120×110 y
5×4×9×120×110; 40 movimientos del cursor):
- **Con las pestañas del enlazado detrás,** el principal hace 40 bloques (con `_sp`) u 80 series (sin `_sp`), y el
  enlazado 0.
- **Con ellas delante,** al revés.
- **Cinco pasos en t:** cada cubo lee 4 imágenes y 8 por adelantado.
- **Excepción, al arrancar:** el enlazado oculto tomaba igual su muestra de rangos y (y, con `_sp`, el primer bloque
  de unidades). Son 100 perfiles en el hilo de numba, ahora compartido con las lecturas del cursor del principal.
  Ahora esperan a que su espectro se muestre, en cualquier cubo. El principal lo muestra al empezar y no cambia.
- **El primer recuento no vio la muestra con `_sp`:** lee con `pixel.strip_read`, que no contaba. La prueba nueva
  la cuenta en `sample_profiles`.

**La disposición, en dos intentos.**
- **Primero, docks propios** tabulados con los del principal. En classic y modern bien, pero en glass flotaban
  cuatro paneles en una columna: el espectro del enlazado quedaba en 120 px. Con dos columnas no caben en una
  pantalla de portátil: 3 × 480 px de imagen mínima más 2 × 572 de paneles pasan de 1728 px.
- **Ahora, `PanelTabs`:** pestañas dentro de cada panel, iguales en los tres looks. Solo se lee la pestaña delante.
- **Glass ajusta la ventana a n imágenes,** con 480 px mínimos entre todas.
- **Las disposiciones guardadas,** aparte para ventanas con cubos enlazados (`+linked`). El tema y el look se
  comparten.

**Dos defectos encontrados al mirar los cubos reales** (offscreen 1920×1080 en bellatrix; el cursor fijado en (1100,
900), tras classic → modern → glass → classic):
- **El cursor de Blos quedaba 18 filas más abajo**, con la región x 57–1974 frente a 0–2031. Causa: `setXLink` y
  `setYLink` de pyqtgraph con el aspecto fijo dejan a la deriva vistas de tamaños distintos. Pasaba ya en el 2×2
  (`stokesgrid._follow`, que no usa esos enlaces). Las imágenes enlazadas siguen ahora la región igual (`ViewSync`).
  Reproducido en una copia con el código anterior (cursor en y 233.6 frente a 215.7) y arreglado.
- **De antes de E8, con un solo cubo:** al salir de glass, la imagen volvía 18 px mayor (530×616 → 548×634). Glass
  guardaba los márgenes del elemento (`ci.getContentsMargins()`, 0) en vez de los del layout (9), y devolvía 0.
  Corregido; glass trata igual los márgenes de las imágenes enlazadas.

**Medido** (bellatrix, offscreen 1920×1080, sin fijar a nodo; 20 pasos en t; cubo 6173 con Blos y Vlos):
- **Mediana por paso:** solo, 27.0–28.9 ms; enlazados, 34.1–34.7 ms (dos ejecuciones).
- **Primer paso:** solo, 47.6–65.7 ms; enlazados, 117.6–221.3 ms, en frío. Los dos mapas son de 17 cuadros y no
  tienen espectro.
- **No medido:** dos cubos con espectro, y el enlace X.

**Pruebas:**
- **Nuevas:** `test_linked_window` (5), en `test_session` (4), en `test_scheduler` (3), y una en cada una de
  `test_policy` y `test_layout`. `test_glass`, ampliada con el tamaño de la imagen tras la vuelta.
- **Una más en `test_scheduler`:** el espectro oculto, con y sin `_sp`.
- **Fallan antes:** la de la región tras glass, la de las lecturas al cerrar, la de los márgenes y la del espectro
  oculto.
- **En bellatrix,** copia en `/tmp` con la venv del árbol compartido:
  - `tests/unit`, `tests/golden` y `tests/real/test_link_real.py`: 684 pasan, 15 se omiten y falla 1 (699 s).
    Falla `test_doctor` por `run.sh`, como en toda copia en `/tmp`: no encuentra la venv junto al código.
  - `tests/xvfb` (Xvfb privado, 1920×1080): 35 pasan y 2 se omiten (228 s).

### 2026-10-07 (1): E8.1 visto por el usuario: imágenes que se separan, títulos, anchos y glass

Probado en bellatrix por el puente con 6173, Blos y Vlos. Los cambios, uno por petición del usuario:

- **Separar una imagen enlazada** (no se podía; el mock con paneles flotantes sí dejaba). Cada imagen enlazada es un
  panel entre la imagen principal y los espectros: se arrastra por el título para separarla, el doble clic la acopla,
  el menú Panels la cierra y la abre. Cerrada no lee nada; al volver, la imagen del momento.
- **Las tres imágenes iguales y sin símbolos raros en las esquinas.** El mismo título en las tres (la principal, como
  cabecera en el mismo sitio); las marcas de separar y cerrar, dibujadas en el color del texto, solo con el puntero
  encima.
- **La rendija en todas las imágenes,** y se puede dibujar en cualquiera (como los paneles del 2×2).
- **El título recortaba campo.** Medido con la imagen entera: 0 % de escala perdida en classic y en glass, con 2 y 3
  imágenes. Con zoom: caja de 807 px sin título, 782 con él (3.2 % menos de filas a la vista). De tres mocks con los
  cubos reales, el usuario eligió el título fino: 14 px en total. En glass va sobre negro (el color de su barra de
  título).
- **Nombres largos** (`aligned_stokes_8542=0-54_=0-28_im.aligned6173`). `data/names.py` da la línea y, en un mapa,
  la magnitud: "Ca II 854.2", "Blos · Fe I 617.3". Con ninguna de las dos, el nombre del fichero cortado por el medio
  a 32 caracteres; el fichero entero, en el tooltip. Probado con todos los cubos de `data/lp`.
- **Glass:**
  - las franjas entre imágenes salían grises, y ahora toman el color de la imagen;
  - las pestañas eran botones grises sobre el panel casi negro (luminosidad 67–74 frente a 5–18), y ahora son planas
    (6, y 34 la de delante);
  - sobraba un anillo de foco naranja en una pestaña, que ya no sale.

**Encontrado al mirar los mocks:** la imagen principal salía más estrecha que las enlazadas (223 px frente a 362 en
el arranque real). Las anchuras se repartían antes de que Qt aplicara el ancho nuevo de los espectros. Arreglado;
la prueba falla con el código anterior (116 frente a 201).

**Una hipótesis descartada:** que una barra de pestañas con el foco se quedara con ← →. Con el código anterior, un
clic en una pestaña tampoco le daba el foco (offscreen). La prueba queda como guarda.

**La conexión con bellatrix cayó a mitad de un sync** (2026-10-06): el trabajo local siguió sin abrir conexión
nueva.

**Pruebas:**
- **Nuevas en `test_linked_window`:** el panel de imagen; el ancho; la rendija; los títulos; las franjas y las
  pestañas en glass; las teclas tras un clic en una pestaña. También `test_names` (15).
- **Fallan antes:** todas menos la de las teclas.
- **En bellatrix,** copia en `/tmp` con la venv del árbol compartido:
  - `tests/unit`, `tests/golden` y `tests/real/test_link_real.py`: 706 pasan, 15 se omiten y falla 1, la de
    `run.sh` en `test_doctor`, como en toda copia en `/tmp` (720 s).
  - `tests/xvfb`: 35 pasan y 2 se omiten (228 s).

### 2026-10-07 (2): una clase para las vistas de cada cubo; cada cubo en su ventana (mock 3)

**Auditoría de simplificación** (la primera de la regla «cada 10 commits»). Las vistas del cubo principal vivían en
`Shell` y las de un cubo enlazado en `LinkedCube`: el mismo comportamiento escrito dos veces.
- **Duplicado:** las selecciones en espectro y en λ–t, los candados, el clic y el paso del ratón por la imagen, los
  gestos, la cruz y los marcadores, el look, el tema y el reinicio.
- **Ahora:** una sola clase, `CubeView` (`ui/cube.py`), el miembro k de la sesión. Una selección fija la λ del
  propio cubo con `Session.set_member_index`, que para el principal es su índice de siempre.
- **`Shell`** se queda con lo de la ventana (rendija, vista 2×2, escala de color, línea de estado) y con sus nombres
  de antes para las partes del cubo principal.
- **Líneas:** `shell.py` + `linked.py` + `cube.py`, de 1649 a 1554.
- **Verificación, `Behaviour: unchanged`:** 12 escenarios capturados antes y después (un cubo y enlazados; oscuro y
  claro; classic, modern y glass). Los 36 PNG y JSON salen idénticos píxel a píxel; dos tandas del mismo código ya
  daban 0 diferencias.

**Cada cubo en su ventana.** Panels → «Each cube in a window of its own», el mock 3 que eligió el usuario.
- El panel de imagen de cada cubo enlazado flota con su espectro y su λ–t al lado. Sus pestañas salen de la ventana
  principal (`PanelTabs` las presta y las recupera).
- **Vuelve por cualquier camino:** desmarcando la entrada, con doble clic en el título, con ↺ o al salir de glass.
- Arrastrar el título de una imagen sigue sacando la imagen sola.

**Estudiado en dos pantallas** (2560×1440 y 1512×982, la del Mac del usuario), en classic y en glass, de un look
al otro y con ↺. En cada paso se midieron los solapes, los tamaños y el zoom; las capturas, en
`CRISPEX/summary_detach_2026-10-07/`, fuera del repositorio. Lo que encontró el estudio, en orden:
- **Las ventanas tapaban la ventana principal y se tapaban entre sí** (254 y 410 px), porque la principal no cedía
  sitio. Ahora cede el de las imágenes y lo recupera primero al volver: acopladas en la ventana estrecha, Qt la
  ensanchaba por su cuenta.
- **El sitio liberado se lo quedaba el espectro**, en la misma zona de paneles: imagen principal de 80 px. Ahora el
  espectro guarda su ancho al separar; al volver, las imágenes salían de 647 px en vez de 428.
- **Glass ajustaba la ventana contando imágenes flotantes, y al volver la cortaba** (845 px por 1092): una imagen
  recién acoplada conservaba su tamaño de ventana flotante. Ahora ajusta cuando el layout ya las tiene, también con
  ↺.
- **Dos ventanas se solapaban 22 px:** un marco es más ancho que el tamaño pedido. Se cuentan 24 px por ventana.
- **Tamaño de cada ventana:** lo que la imagen principal muestra con su zoom. La imagen entera ocupa 214×252 px;
  antes se le daba la caja alta y estrecha de la principal, 226×759. La de un cubo, más ancha por sus paneles y de
  al menos 560 px de alto.
- **Colocación:** en fila o en columna junto a la ventana (en glass, junto a su columna de paneles), con paneles del
  ancho de la ventana principal o de 320 px. Se elige lo que menos encoge. La primera opción que cabía dejaba la
  ventana de un cubo en 743×325, con el espectro ilegible, cuando una columna cabía sin encoger.
- **Límite conocido:** separados en classic en la pantalla de 1512 px y después pasando a glass, se apilan en
  cascada. Con el zoom compartido, cada ventana necesita el sitio de la imagen principal, que glass ajusta a la
  altura de la pantalla. Separados ya en glass, caben.

**Fuera del visor:**
- **Las instrucciones de trabajo del proyecto, fuera de git, unas para el Mac y bellatrix:** las que había solo en
  bellatrix, puestas al día (estaban anticuadas: notas de la época del prototipo, `HANDOFF.md` del 25 de
  septiembre) y con la regla de auditar simplificaciones cada 10 commits.
- **Cómo se sincroniza:** con `sync.py`, por una lista `also` de ficheros fuera de git en su configuración local, que
  no está versionada.

### 2026-10-08 (1): las ventanas de cada cubo como docks, frente a ADS; el contorno de redimensionado; el arranque sin blanco (ROADMAP E8.1, E8.3, E5.8, E6.21)

**El problema de fondo.** Cada fallo de las ventanas de cubo de estos días salía de una costura entre cuatro
maneras de poner una vista en pantalla: la imagen principal como widget central con una cabecera que imitaba un
título, cada imagen enlazada como dock, espectro y λ-t como pestañas de un dock compartido, y la ventana de un cubo
como el dock de su imagen flotando con un divisor que tomaba prestadas esas pestañas. Se probaron dos salidas en
paralelo, cada una en su rama desde `038d30b`, con los mismos criterios: parecido medido contra las capturas de
ahora (12 escenarios, 36 ficheros), una lista de comportamientos, velocidad y tamaño.

- **A, Qt Advanced Docking System (PySide6-QtAds 5.1.1):** 8 de 12 escenarios idénticos (en 4 el espectro 1 px más
  bajo), +949 líneas en la capa de acoplado (unas 360 solo para que pareciera `QDockWidget`), una dependencia atada
  a PySide6 6.11.2 y cinco remiendos entre ADS, el puente y el estilo. En Linux, 10 tests nuevos fallaban y una
  comprobación acababa en segfault. A mano, en el Mac, el usuario no consiguió volver a acoplar una imagen: medido
  con el puntero real, la ventana arrastrada (su borde superior en y 471) tapaba la mitad inferior de los brazos de
  la cruz de ADS (453-501), y solo se veían "arriba" y "centro". Descartada; lo medido, en `CRISPEX/ads_prototype/`.
- **B, la capa de `QDockWidget` hecha uniforme (rama `e8-docks`):** la ventana de un cubo es un `QMainWindow` dentro
  del dock de su imagen, y su espectro y su λ-t son docks normales en él (creados la primera vez que el cubo se
  separa: el arranque no cambia). Idéntica píxel a píxel en los 36 ficheros; +91 líneas; de 19 esperas de una
  pasada del bucle a 11. Comprobaciones de comportamiento: 73 bien y 9 mal en `038d30b`, 87 y 1 (el límite de
  `ViewGuard`, E8.3), lo mismo en el Mac y en bellatrix. El usuario, en el Mac y por el puente: "mucho más
  intuitivo"; Qt abre el hueco donde caerá el panel.

**El comparador de capturas tenía un fallo.** Devolvía una vista de numpy sobre la memoria de una `QImage` ya
liberada, y el resultado cambiaba de una ejecución a otra: con las capturas de A contaba 10 ficheros distintos donde
había 14. Con `.copy()`, la línea base contra sí misma sigue en 0 de 36. El refactor de `b571d12` vuelve a dar
iguales los 12 escenarios salvo 1 fichero (824 px) que también difiere entre dos tandas del mismo código: ruido.

**Velocidad de B** (bellatrix, offscreen, los tres cubos de `data/lp`, ABBA con el cerrojo, nodo NUMA 0, carga
0,2-1,5; medianas de 4 procesos, ms): separar los cubos 72 / volver 109 / redimensionar 62 en classic, contra 72 /
103 / 43 antes; en glass 69 / 100 / 79 contra 68 / 133 / 54. Todo el coste de más al redimensionar venía de repartir
el ancho de las imágenes en cada paso (`same_image_widths` en `resizeEvent`: dos pasadas de layout); sin esa línea,
43 y 51. Ahora se reparte 150 ms después del último cambio de tamaño: 43 / 52, y volver más rápido que antes (89
frente a 102, 79 frente a 134). Durante el arrastre la imagen principal se lleva el cambio y al soltar se igualan.

**El contorno de redimensionado (E5.8).** Por el puente, XQuartz mostraba el anillo con forma blanco por dentro
mientras crecía, y al encoger dejaba anillos atrás; lo mismo en `038d30b`, no era de B. Medido en el XQuartz del
usuario, con el coste de cada paso en el registro: el anillo, 34-40 ms; el anillo con la forma puesta antes que el
tamaño, 32-36 ms e igual de sucio; cuatro ventanas sin forma, limpias pero 540-1100 ms (el borde a 1-2 pasos por
segundo); las mismas subidas al frente una sola vez, igual de lentas. Una sola ventana sin forma, rellena del color
del look y con el borde propio del servidor en el acento: 31-34 ms (p90 36-44), limpia. Lleva el tamaño escrito en
el centro con una fuente del servidor.

**El arranque en blanco (E6.21).** El puente creaba sus ventanas X sin fondo, y XQuartz las mostraba blancas hasta
sus primeros píxeles, la ventana entera mientras se leían los cubos. Con el color de la ventana de Qt como fondo, el
usuario la ve aparecer "de forma instantánea". El test se escribió primero con una conexión simulada incompleta:
pasaba solo y fallaba en la suite completa de Linux, donde otro test ya había puesto un icono a la aplicación; ahora
pone el icono él mismo.

### 2026-10-08 (2): un fichero por píxel dado como cubo (ROADMAP E1.23)

**El fallo.** `explorer` con el `_sp.fits` corregido de una serie de Hα (nb_6563, 35 scans) se caía al construir la
ventana: `IndexError: index 2027 is out of bounds for axis 0 with size 35` en `Axes.utc`, desde la barra. El
fichero (bellatrix, solo leído) tiene NAXIS = [11, 35, 1, 2032, 2028] con CTYPE WAVE, UTC, STOKES, HPLN, HPLT: en
orden de numpy (HPLT, HPLN, STOKES, UTC, WAVE). `roles()` encontraba STOKES en la tercera posición, completaba t y λ
por el orden SOLARNET (t = 0, λ = 2, la misma que s) y tomaba las 2028 filas por tiempos; la cabecera daba los 35
tiempos de la WCS-TAB. Reproducido en el Mac con el `_sp.fits` sintético con su WCS-TAB y DATEREF, como lo escribe
SSTRED (`synth.write_sp_fits(..., wcs=True)`): `utc_str(15)` con 3 tiempos, el mismo `IndexError`. Sin DATEREF
(el sintético de antes) `utc` devolvía None antes de indexar: por eso no lo veía ninguna prueba.

**Lo hecho.**
- **Al abrir:** unos ejes espaciales antes de los de la imagen son un fichero por píxel, y `roles()` lo rechaza,
  diga lo que diga `--axes`; una cabecera con tantos tiempos o λ distintos de los pasos del cubo en t o λ se rechaza
  al abrir el `Dataset`, con las dos cifras. Tres ejes delante con solo algunos nombrados ya no ponen dos papeles
  en el mismo eje.
- **Lo que se da:** `formats.per_pixel` reconoce el fichero (un FITS por su cabecera; un LP por las cabeceras del
  `_im` de al lado, del mismo formato primero, o por su nombre `_sp` y más cuadros que píxeles por cuadro, como el
  `_sp.icube` de nb_6563: 21 × 66 y 4068240) y `formats.opening` abre su `_im` con él:
  `[explorer] c_sp.fits is the per-pixel file of c_im.fits (its header puts HPLT, HPLN first): opening that one
  with it`. Sin `_im`: `[explorer] c_sp.fits is a per-pixel file (...), not an image cube, and its image cube
  c_im.fits is not next to it: open that one (...)`, estado de salida 1, sin traza. Entre cubos enlazados, el que
  no tiene `_im` se queda fuera con el motivo, como los que no casan; el `_sp` del propio primer cubo se toma como
  su fichero por píxel, no se enlaza consigo. `c_sp.fits --sp c_im.fits` se toma al revés; `--sp` con un `_im` FITS
  se rechaza. Los sufijos tras `_sp` (`_sp.aligned6173.icube`, `.fcube`) se emparejan con su `_im.aligned6173`.

**Pruebas** (`tests/unit/test_per_pixel_given.py`, 14; en el código de antes fallan todas y la de la orden se
queda en el bucle de eventos con la ventana abierta sobre el `_sp`): sintéticos FITS y LP, con y sin `_im` al lado,
renombrado, con sufijo, enlazados, `--sp` al revés y el desajuste de tiempos (una WCS-TAB de 2 tiempos sobre 3
cuadros). Grupos `test_formats`, `test_axes`, `test_dataset`, `test_pixel`, `test_cli`, `test_app_start`,
`test_start_paths`, `test_link`, `test_linked_window`, `test_toolbar` en verde en el Mac.

**Sin probar:** el fichero real (se comprueba en bellatrix); un `_sp` LP sin `_im` y sin `_sp` en el nombre no se
reconoce (su cabecera sola no lo dice). Al rechazar una cabecera con otros tiempos, un cubo así deja de abrirse en
vez de abrirse con índices; si aparece alguno real, la alternativa es abrirlo sin sus tiempos.

### 2026-10-08 (3): cubos de otra cadencia, enlazados por la hora más cercana; los tiempos de un cubo de Stokes I (ROADMAP E8.4, E8.5)

**El caso.** Con los cubos CRISP de banda estrecha del 2023-05-03, en bellatrix,
`explorer nb_6173_…=0-54_stokes_corrected_im.fits nb_8542_…=0-54_…=0-28_stokesI_corrected_im.aligned6173.icube`
dejaba fuera el 8542: «84 times against 55 … other cadences are not linked yet». Y el 8542 solo, sin tiempos ni λ: no
tiene `_im_times+wvl.idlsave` propio.

**Los tiempos de un cubo derivado (E8.5).** SSTRED deja el cubo de Stokes I (`…_stokesI_…_im.icube`) junto al de los
cuatro Stokes sin fichero de tiempos. El del cubo completo (`…_stokes_…_im_times+wvl.idlsave`, medido en bellatrix:
`time` 84×20, `lambda` 20) tiene los mismos barridos y las mismas sintonías. Si sus tamaños son los del cubo (nt, nl),
se toman de él los tiempos y las λ, y la terminal lo dice una vez. Su `fac` (1.0) y su `nan_rplcmnt` (−1.77e−8)
describen el cubo de float, no el de int16: los valores siguen como están, y el aviso de cuentas no cambia. Con otros
tamaños no se usa nada.

**Otras cadencias (E8.4).** El plan de ventanas enlazadas (§3.3) lleva cada t maestro al índice más cercano de cada
cubo, con su Δt; CRISPEX hace lo mismo (`tsel_ref`, `crispex.pro:2898-2906`), el primero de dos igual de cercanos y
sin límite de distancia. Así se hace: `data/link.py` `frames` da, para cada t del primero, el t del enlazado, y
`Session.member_state` es el único sitio que lo lee. Lejos de todos sus tiempos (fuera de su serie o en un hueco), el
enlazado muestra el más cercano, como CRISPEX; la línea de arranque dice en cuántos t pasa de media cadencia y hasta
cuántos segundos. Sin tiempos en alguno de los dos, solo se enlaza con los mismos t, como antes, y el rechazo dice cuál
no los tiene. Cambia también un caso: los mismos t con horas que difieren más de media cadencia ya no se rechazan, se
enlazan por la hora.

**Medido en sintéticos** (Mac, `tests/unit/test_link.py`; un FITS de 55 barridos a 20 s y un LP de Stokes I de 84 en
dos series, los 55 primeros 6 s después de los del FITS y 29 tras 400 s, con sus tiempos en el fichero del cubo
completo):
- 6173 manda (55): el 8542 muestra 0…54;
- 8542 manda (84): el 6173 muestra 0…54 y luego 54 en los 29 últimos (hasta 986 s lejos; la línea lo dice: «at 29 of
  the 84 times … more than half its cadence away»);
- 8542 manda, enlazado un cubo solo de la segunda serie (29): 0 en los 55 primeros t, después 0…28. Antes salía 0…28
  y luego 28: el `min(t, nt−1)` de antes no miraba la hora;
- 14 s después de cada barrido (más de media cadencia): el barrido anterior, 0, 0, 1, …, 53;
- el 8542 sin fichero de tiempos: rechazado, «84 times against 55 …; it has no times to match them by».

Las seis pruebas nuevas fallan sobre `4cae1f4` y pasan ahora. **Sin medir con los cubos reales:** ni la pareja del
usuario ni `tests/real/test_link_real.py`, que ahora espera que el 8542 alineado de `data/lp` se enlace con
`stokes_6173_im.icube` por la hora (antes, rechazado por 84 frente a 17).

**Por decidir (el usuario):**
- **Δt en pantalla.** El plan lo pone en la barra de estado (etapa 6); aún solo sale en la línea de arranque.
- **Lejos de todo.** Se muestra el más cercano, como CRISPEX. Ocultarlo pasada cierta distancia, o rechazar el enlace
  si ningún t queda a menos de media cadencia, sería otra regla.
- **Un cubo LP no trae la fecha:** dos cubos LP de días distintos se comparan por la hora del día.
- **Series intercaladas.** Si el desfase entre las dos líneas de una misma secuencia está cerca de media cadencia,
  el más cercano puede saltar de un barrido al anterior entre t vecinos. En el caso real, 6173 y 8542 se observan en
  la misma secuencia (≈29.5 s); su desfase no se ha medido.

### 2026-10-08 (4): en un cubo de 4 Stokes, I negativa es relleno (ROADMAP E1.24)

**Lo que se veía.** En el cubo alineado `aligned_stokes_8542=0-54_=0-28_im.aligned6173.fcube` (LP, float32, 4
Stokes; medido en bellatrix, solo lectura), el fotograma de I en t = 0, λ = 0 tiene un 25.5 % de NaN y un 0.2 % de
valores negativos, I ≈ −1.769e-08, con Q igual a I en esos píxeles: no es dato. Su idlsave dice `nan_rplcmnt` =
−1.7691475e-08 y `fac` = 1, y los negativos son −1.76914732e-08, −1.76914714e-08, −1.76914696e-08...: el valor de
relleno arrastrado por la interpolación de la alineación al borde del campo, cerca pero no igual. La prueba exacta
de `formats.lp_values` (crudo == `nan_rplcmnt`) no los ve y llegaban como dato. Los cubos de Stokes de 6173 no
tienen I negativa: su relleno ya sale NaN.

**La regla** (el usuario): en un cubo con exactamente 4 Stokes, donde I < 0 los cuatro Stokes son NaN, como el
relleno. Muestra a muestra: I negativa en un (t, λ) borra ese (t, λ). Un cubo de un Stokes (un Doppler, una
diferencia) y los mapas (B, v) conservan sus negativos.

**Dónde vive.** `data/masking.py`, y se aplica solo en la capa de datos, de donde salen los valores:
- fotogramas (`FrameReader.read`, también los leídos por adelantado), filas, bandas de la rendija sin `_sp`, series
  (espectros y λ-t), puntos (la muestra del rango de los espectros) y bloques de filas (`RowBands`);
- los ficheros por píxel (`_sp.fits`, `_sp.icube`/`.fcube`): el bloque trae los cuatro Stokes;
- los rangos de Q U V desde fotogramas enteros: el píxel con I negativa no cuenta.
Los niveles de color salen de lo leído: sin I negativa en sus percentiles. La rejilla 2×2, el panel de la rendija y
los enlazados leen por el mismo `Dataset`.

**Q, U y V necesitan la I del mismo (t, λ).** Un bloque o una serie con todos los Stokes ya la tiene. Una serie de
un solo Stokes la pide en la misma llamada (el doble de peticiones). Un fotograma toma de `NegativeI` dónde es
negativa la I de ese (t, λ): la deja cada fotograma de I leído (índices, no la imagen: 34 kB para un 0.2 % de una
imagen 2k). Si no está, lee los dos fotogramas a la vez, en trozos en el pool como uno solo. La rejilla pide I, Q, U
y V juntos: el primero de Q, U, V lee la I y los otros esperan. Un hilo del pool (lectura adelantada, un trozo)
nunca espera: la lee otra vez, para no quedarse con un hilo que otro necesita.

**Coste** (Mac M1 Pro, SSD, ficheros en la caché del sistema; cubo LP float32 sintético de 1024×1024, t 3, Stokes 4,
λ 8; tres rondas antes/después alternadas, medianas de 48 lecturas, ms; carga 4-6, swap 7.0 de 8.2 GB con otros
procesos en marcha):

| | sin I negativa (como 6173) | con un borde del 1.2 % |
|---|---|---|
| Fotograma de I | 0.35 → 0.40 | 0.34 → 1.08 |
| Fotograma de Q, con la I leída antes | 0.34 → 0.34 | 0.34 → 0.39 |
| Fotograma de Q, sin ella | 0.34 → 0.72 | 0.34 → 1.43 |
| Rendija de Q sin `_sp` (24 bandas de 300 filas), sin I leída | 1.6 → 3.4 | 1.6 → 3.5 |
| Lo mismo con la I leída | 1.6 → 1.7 | 1.6 → 2.4 |
| Tira de 16 píxeles del `_sp.fcube` | 0.004 → 0.007 | igual |

- **Las series**, en el mismo proceso con la regla puesta y quitada (4 rondas de 200 píxeles): 0.67-1.0 ms en los dos
  casos, sin diferencia por encima del ruido.
- **Encontrar los negativos de una imagen 2k:** 1.5 ms con la comparación. Ahora primero su mínimo sin NaN: 0.28 ms
  si no hay ninguno, 2.4 ms si hay un borde. Un núcleo de numba no mejoró (2.1 ms).
- **En StorNext, sin medir.** Por inferencia: la λ-t de Q, U o V sin `_sp` hace el doble de peticiones, y una
  rendija de Q sin `_sp` lee el doble de bandas. Un paso en t viendo Q lee dos fotogramas en paralelo.

**El golden del `_sp.icube` sintético cambia.** Ese fichero escribe el relleno como 0 cuentas, y el cero del
ajuste lo deja en −7.3e-12; el prototipo lo daba como dato. Ahora es NaN, y la prueba aplica la regla a la
referencia del prototipo.

**Pruebas.** `tests/unit/test_negative_i.py`, 26:
- cubos sintéticos FITS y LP, con y sin fichero por píxel, con un borde de I negativa y Q = U = V = I;
- en el LP, el borde lleva el valor de la idlsave y copias perturbadas como las de la alineación.
- **Antes del cambio fallan 25.** En el LP el valor guardado es −1.7691473e-08 frente a un `nan_rplcmnt` de
  −1.7691475e-08: imagen de I con 438 NaN donde deben ser 508; bloque por píxel 0 NaN de 60; λ-t de Q en bloques
  de filas 0 de 15; niveles de I desde −1.769e-08; rangos de Q U V de 1.77e-08, la amplitud del borde, frente a
  7.9e-11 del mismo cubo con NaN.
- **Después pasan:** 508 de 508, 60 de 60, 15 de 15; niveles desde 6.46e-09; rangos iguales a los del cubo con NaN.
- **La de un Stokes con negativos** (y un mapa de velocidad) pasa antes y después: es la guarda.

Además, grupos de `tests/unit` de datos, núcleo y paneles, y `tests/golden`, pasan en el Mac.

**Falta.**
- El cubo real de 8542 en bellatrix (`tests/real`, y verlo).
- El coste en StorNext.
- **Decisión del usuario, sin tomar:** la regla va muestra a muestra. Si en un píxel la I es negativa solo en
  algunos λ (no visto en el borde), solo esos λ quedan NaN; borrar el píxel entero en ese t sería la otra lectura.

### 2026-10-08 (5): el Stokes a la vista en la imagen y en la λ–t (ROADMAP E4.15)

**El problema.** Al pasar de I a Q, U y V (teclas, combo, control segmentado, barra de glass) nada decía qué Stokes
se veía en la imagen ni en la λ–t (el usuario). Solo la vista 2×2 rotulaba sus paneles, con una letra.

**Lo hecho.** Un ayudante, `ui/stokeslabel.py`, el mismo para todas las vistas: «Stokes I» … «Stokes V» en la
esquina superior izquierda de la caja de la vista (8, 6 px), en la tinta del tema (235, 235, 240 en oscuro; 30, 30,
34 en claro), como las letras de la 2×2, que ahora lo usan también. Lo llevan la imagen y la λ–t de cada cubo, el
principal y los enlazados, cada uno con su propio Stokes del estado de la sesión, en cuanto cambia. Solo cuando el
eje de Stokes tiene cuatro planos: con uno, o sin eje (un mapa), no se sabe si es I, un campo magnético u otra cosa
(el usuario).

- **La pista de la rendija** estaba en (8, 8), donde va la etiqueta: baja bajo ella, a una altura que sale del margen
  del layout y de la caja del texto (39 px en el Mac). En la 2×2 estaba fija en 30, con la letra tocando el borde
  superior de la pista (medido en `4cae1f4`: caja de la letra 15-38, pista desde 30); ahora también a 39.
- **En glass** la clave de color sube a esa esquina (16, 16) y habría tapado parte de la etiqueta. Su primera fila ya
  nombra el Stokes («I», sin «Stokes»), así que la imagen principal no lleva etiqueta mientras la clave está allí. Las
  imágenes enlazadas y las λ–t sí la llevan.
- **Paneles estrechos de la 2×2:** con la ventana a 640 px cada panel mide 170 px y la etiqueta acaba en x 79; el
  candado empieza en 315 (en la imagen). Se tocarían con paneles de menos de unos 110 px.

**Medido.** `tests/unit/test_stokes_label.py`: con I → Q → U → V desde la sesión, la imagen y la λ–t del principal y
del enlazado de cuatro Stokes dicen lo mismo; el mapa y un cubo de un solo Stokes, nada, ni en la imagen ni en la
λ–t; la tinta, en oscuro y claro y en los tres aspectos, y dibujada (85-88 píxeles de tinta en la caja con la
etiqueta, 0 sin ella). Con el código de antes no hay ningún texto en esas cajas. Las 12 capturas del arnés de
comparación, contra las de `4cae1f4` (dos tandas de ese código: 1 fichero con 824 px de ruido, el de siempre): 14
ficheros distintos, solo donde están las etiquetas y la pista movida; `one_*_glass_window` idénticos (sin etiqueta
bajo la clave).

**Sin resolver.** La tinta clara del tema oscuro sobre imagen clara se lee mal: 1.45:1 sobre la λ–t gris del cubo
sintético, 1.85:1 de mediana sobre la granulación de un enlazado (por debajo de 3:1). Es lo que ya hacían las letras
de la 2×2; un halo como el de la retícula, o un fondo como el de la clave, es decisión del usuario (sin probar).

### 2026-10-10 (1): el plan de enlazado comprueba la cabecera como `Dataset.open` (ROADMAP X.13)

**El problema** (S10 de la auditoría de simplificación). `link.describe` leía los ejes como `Dataset`, pero sin
`axes.check`. Un cubo enlazado con una WCS-TAB de 2 tiempos para 3 pasos en t pasaba el plan («no times of its own:
the first cube's»), `Dataset.open` lo rechazaba después y `start()` devolvía `None`: no abría ni el primer cubo.

**Lo hecho.** `axes.read` (roles, `from_fits` o `from_lp` y `check`) es la única lectura, la de `Dataset` y la de
`describe`. El plan deja fuera ese cubo con la razón de `Dataset.open` («cannot be read as a cube (…)») y el primero
abre solo. Con cubos enlazados, un primer cubo con la cabecera que no casa se rechaza ahora en `plan_links`, antes de
crear la aplicación Qt, con el mismo mensaje. E1.23 (rechazar o abrir sin tiempos) se decide ya en un solo sitio.

**Medido** (bellatrix, sin pantalla). Dos pruebas nuevas, `test_link` y `test_app_start`, fallan antes (ok=True;
`start` devuelve `None`) y pasan después. Los grupos de link, axes, dataset, app y per_pixel: 91 passed;
`tests/real/test_link_real.py`: 7 passed. Sin prueba: el segundo `try` del plan (un cubo con un eje sin nombre leído
como t, de otra longitud que su cabecera).

### 2026-10-10 (2): run.sh no toca entornos ajenos; la rama `compare-bridges` y la higiene de la historia (ROADMAP X.6)

**El problema.** `scripts/run.sh` comparaba el `uv.lock` de su árbol con el `.lock.cksum` del entorno con el que
corría y, si difería y podía escribirlo, lanzaba su propio `setup_env.sh` sobre él, sin mirar de quién era: el de
`EXPLORER_VENV`, o el que enlaza `.venv-<plat>` en las copias de prueba de `/tmp`, se reconstruía con las versiones de
una copia vieja o experimental, bajo todos los que lo usan (F72 del prototipo).

**Lo hecho.** El entorno propio es el `.venv-<plat>` de la carpeta del árbol, comparado tras seguir enlaces
(`cd -P`). Solo ese se reconstruye, y solo en ese se añade el `explorer.app` de macOS. Uno ajeno corre como está, con
un aviso: su ruta en disco, que este código corre con sus versiones, y cómo hacerse uno propio. Avisar y no negarse:
el entorno queda intacto igual, y negarse pararía también `run.sh doctor`. Consecuencia: un entorno hecho con
`setup_env.sh --venv DIR` fuera del árbol ya no se reconstruye solo.

**Medido.** `tests/unit/test_run_sh.py`, con árboles y entornos de mentira en una carpeta temporal: con el run.sh de
antes fallan 2 de 5 (el `EXPLORER_VENV` ajeno y el enlace: «updating <ajeno>»), en el Mac y en bellatrix; después
pasan 5. Sin la comprobación en la línea del `explorer.app`, la prueba del ajeno falla.

**`test_started_by_run_sh`.** Fallaba en todo worktree y en las copias de `/tmp` sin el entorno enlazado: run.sh no
encontraba `.venv-<plat>` junto al código, salía con 1 y `doctor` no escribía su informe. Ahora la prueba le da
`EXPLORER_VENV` = el entorno de las pruebas, lo que solo es seguro con este arreglo.

**La rama `compare-bridges`** (71 commits fuera de `main`): sus 68 commits están en `main` con otros hashes (la
reescritura del 2026-10-05); no guarda código, pruebas, medidas ni notas que no estén en `main`. Lo único distinto es
el blob `e13dd22` de `tests/golden/data/synth_small/reference.npz`, con la ruta del Mac en su `meta.npy` (UTF-32: ni
el grep ni `hygiene.py`, que solo recorre `HEAD`, lo ven): el que X.11 quitó de `main`. Propuesto borrarla (decisión
del usuario). La entrada 2026-10-04 (30) cita `328bcc5` como el commit con la ruta; tras la reescritura es `b93c4a3`.

**Higiene de toda la historia**, en todas las ramas locales: 0 menciones de asistentes, de coautoría y de rutas personales
en mensajes y diffs; una sola identidad de autor; ningún fichero de auditoría versionado nunca. La única fuga, ese npz.

### 2026-10-10 (3): las ventanas de cubo en la disposición guardada; la piel de glass en sus paneles sacados (ROADMAP E8.3)

**La disposición guardada.** El estado de la ventana principal guarda el panel de la imagen de cada cubo, flotando o
no, pero no el `QMainWindow` de dentro: al arrancar otra vez, un cubo aparte volvía como su imagen sola, con su
espectro y su λ–t en las pestañas de la ventana principal (medido: imagen de 388 px en vez de 249, ningún panel en su
ventana). Ahora `LayoutStore` guarda también, en `app/<kind>/cubes/`, qué cubos son ventana propia, el estado de cada
marco y el ancho cedido por la ventana. Al restaurar, después del estado principal, hace de cada cubo una ventana otra
vez (crea sus paneles) antes de restaurar el estado de su marco: `restoreState` se salta los docks que aún no existen.
Un panel sacado de la ventana de un cubo vuelve flotando donde estaba. En glass, la ventana del cubo la recoloca glass
al arrancar si la ventana ajustada tapa sus paneles, como a sus propios paneles.

**La piel de glass.** Glass vestía solo sus tres paneles; uno sacado de la ventana de un cubo salía cuadrado, con el
título sin piel y sin la losa. Ahora lleva el mismo `PanelSkin` mientras flota (también si glass se pone con él ya
fuera) y lo pierde al volver. Al quitar glass, las pieles se quitan en orden inverso: la de un panel de cubo encontró
sus gráficas ya transparentes y debe devolver eso antes de que las de los paneles principales devuelvan el fondo
original (en el orden directo las gráficas se quedaban transparentes fuera de glass; lo comprueba la prueba).

**Medido.** Las dos pruebas nuevas fallan con el código de `0712b98` y pasan con el nuevo (bellatrix y Mac). El
arranque, píxel a píxel (Mac, sin pantalla, 19 ventanas: clásico y glass, un cubo y enlazados, restaurado de una
disposición del código anterior, cubos aparte y de vuelta): 0 px de diferencia; ruido entre dos tandas del mismo
código, 0. En bellatrix, los grupos de docks, layout, glass, linked, look, theme, titlebar, shell y arranque, y
`tests/xvfb` en un Xvfb privado (36 passed).

**Queda.** El límite de `ViewGuard` y la piel en los paneles acoplados dentro de una ventana de cubo (decisiones del
usuario). Sin probar en un Mac local: la piel sobre un panel que ya tiene su ventana nativa (en cocoa se hace
translúcido después de flotar).

### 2026-10-10 (4): el puente: el fondo al cambiar de tema, mover y redimensionar por el gestor, y la exposición negra medida (ROADMAP E6.21, E6.11, E6.19)

**E6.21, lo que faltaba.** Cada ventana X nacía con el color de ventana de Qt de fondo, pero al cambiar de tema en
marcha se quedaba con el del arranque: lo que X expone antes de que lleguen los píxeles salía del tema viejo.
`QApplication.setPalette` manda `PaletteChange` a cada ventana de nivel superior (los paneles flotantes también) ya
con el color nuevo; glass, con `setPalette` en la principal, solo a esa. El puente responde con un
`ChangeWindowAttributes` del píxel nuevo, solo si cambia: en XQuartz, una petición pequeña por cambio de tema. En Xvfb
otro cliente borra cada ventana con `ClearArea` y lee el fondo: en `main` seguía `0xefefef` tras pasar a oscuro y a
claro; con el arreglo, el del tema.

**E6.11.** Por el puente, la barra y los bordes movían y redimensionaban la ventana por su cuenta: en GNOME o KDE por
`ssh -Y` no había acople a los bordes. Portado del prototipo (`app/xbridge.py:610-632`): si el gestor anuncia
`_NET_WM_MOVERESIZE` en `_NET_SUPPORTED`, se suelta el agarre implícito de la pulsación y se le manda el mensaje
(raíz, dirección, botón, fuente 1). Si no lo anuncia (quartz-wm, sin gestor), el camino de siempre. Con un gestor
falso que informa del mensaje y de si pudo agarrar el puntero: mensaje correcto y agarre concedido. Cada pieza se ve
fallar al quitarla: sin el mensaje (código de `main`), nada llega; sin soltar el agarre, `AlreadyGrabbed`; sin dar a
Qt la liberación, Qt seguía con el botón pulsado después. Con metacity de verdad en Xvfb, arrastrar la barra al borde
izquierdo deja la ventana en la mitad izquierda (960×1080); con `main`, en (0, 230) con su tamaño. Sin probar en
GNOME o KDE reales; `_NET_SUPPORTED` se lee una vez al empezar.

**E6.19, solo medido.** Una zona de 400×300 de la ventana principal, tapada y descubierta por otro cliente, 10 veces
por proceso, ABBA. Sin enlace, 2 ms hasta verse bien. A 25 ms y 5 MB/s, 51 ms en los que el 92 % es el color de
fondo: un viaje de ida y vuelta hasta la `CopyArea` del puente. Con el pixmap trasero de cada ventana como su
`background_pixmap` (experimento en una copia), X pinta los píxeles él mismo: bien desde la primera lectura. Carga
3.9-8, sin fijar: no es una tanda de carga baja. Un panel de un solo color no distinguía las dos cosas (su fondo ya es
su contenido). Sin medir: qué pasa al crecer la ventana (el pixmap se repetiría en mosaico) y XQuartz.

**Para correr `tests/xvfb` con cookie** hacen falta también las de las pantallas de los enlaces de `bench/xlink.py`
(600-699); sin cookie, como en las suites de siempre, no.

### 2026-10-10 (5): la máscara, `--mask` (ROADMAP E8.2)

**Lo hecho.** `explorer cubo [enlazados] --mask fichero` dibuja el contorno de una máscara 0/1 sobre todas las
imágenes: la del cubo principal, las de los enlazados y las cuatro de la 2×2, en los tres aspectos.

- **Como CRISPEX** (`crispex.pro`): un cuadro, que se muestra en todos los t, o tantos como tiempos del primer cubo, y
  en cada t el suyo (`:21105-21111`); si no, se rechaza diciendo las dimensiones (`:10175-10198`).
- **Píxeles puestos:** valor ≥ 1, el nivel 1 de su `CONTOUR` (`:7174-7177`); una máscara de bytes 0/255 también vale.
- **Comprobaciones:** las de `data/link.py`. La de rejilla queda en una función, `other_grid`, que usa también el
  enlazado con el mismo mensaje; la de tiempos es `frames`, sin leer tiempos propios de la máscara (la regla de IDL).
- **Formatos:** FITS y LP, por su contenido. Al LP nunca se le aplica la idlsave de al lado: su `fac` es de un cubo.
- **Si no casa:** el visor arranca sin ella y lo dice en la terminal, como un cubo que no se puede enlazar (IDL no
  arrancaba).

El contorno va por los bordes de los píxeles, con los tramos rectos unidos; el de IDL pasa por los centros de los
píxeles del borde, medio píxel más adentro. El color, por ahora el acento del aspecto (azul en classic y modern,
naranja en glass), en una sola función: `ui/mask.py` `mask_colour`.

**Medido.** `tests/unit/test_mask.py` (17) y `test_mask_drawn.py` (4); contra `0712b98` fallan todas salvo la guarda
del mensaje de `link.plan`. Con la principal, un mapa enlazado y la 2×2, cada imagen lleva el contorno del cuadro de
su t y lo sigue (borde izquierdo 5 → 11 → 14 → 8 en t 0, 2, 3, 1). Sin `--mask`, las 36 capturas del arnés son
idénticas a `main` (dos tandas de `main` difieren en el fichero de siempre, 824 px). En bellatrix, 155 pruebas de los
grupos tocados y 7 de `tests/real/test_link_real.py`.

**Coste** (bellatrix, nodo 0, con el cerrojo, carga 4-8; una máscara de umbral de `stokes_6173_im.fits`, 186 cuadros
de 2044 × 2030, ~25 000 segmentos, hecha en `/tmp` y borrada):

| | ms |
|---|---|
| leer un cuadro | 4.6 |
| contorno, primera versión (dos `np.nonzero`) | 94.7 |
| contorno, con un `flatnonzero` | 17.7 |
| un paso en t hasta la imagen nueva, sin máscara (ABBA) | 26.5 / 26.4 |
| ídem, con máscara por t | 61.6 / 60.4 |

El reparto de esos +35 ms (lectura y contorno ~23, dibujo ~10-15) es inferido, no medido por partes. Una pista falsa:
las líneas grises con forma de contorno de una captura ampliada son de la imagen (de los 21 428 píxeles distintos sin
el contorno, 21 423 son del acento).

**Falta.** El coste por paso (fuera del hilo de la interfaz, por adelantado al reproducir, o solo lo visible: sin
probar), una tecla para ocultarla (IDL tenía una por imagen), leer los tiempos propios de una máscara FITS, que la vea
el usuario. **Por decidir:** el color, bordes o centros, arrancar sin ella o negarse, umbral ≥ 1 o > 0.

### 2026-10-10 (6): la caché de numba al arrancar y la rendija frente al prototipo (ROADMAP E6.20, E7.5)

**Condiciones:** bellatrix, bajo el cerrojo, nodo 0 (CPU pares); cubo 6173 con su fichero por píxel; carga 2.3-9: no
es una tanda de carga baja. Resultados y scripts en `bench/results/perf_2026-10-10/`. Sin cambios de código.

**E6.20, la caché de numba.**
- Todos los núcleos de explorer llevan `cache=True`. La caché está en `~/.cache/explorer/numba`, una carpeta por ruta
  del árbol (el compartido, cada copia en `/tmp`, cada worktree: 87 en bellatrix), válida mientras el fichero no
  cambie. En el árbol compartido se reutiliza: las entradas del 1 de octubre son las del `kernels.py` de hoy.
- Por el puente (Xvfb privado, sin enlace), la primera imagen en X: fría 6.99 s, caliente 2.47 s; lo que espera tras
  la imagen de Qt, 3.38 frente a 0.057 s. `warm_up` solo: frío 4.2 s (`encode` 1.4 + 1.0 s), caliente 0.23 s.
- Sin pantalla, la primera imagen: 2.37 frente a 2.11 s.
- **Las pruebas X compilan siempre:** el conftest da a cada prueba un `XDG_CACHE_HOME` vacío. `tests/xvfb` con un
  `NUMBA_CACHE_DIR` por sesión: 245 → 188 s (una pasada de cada, sin fijar).
- `warm_up` no compila las variantes de disposición 'A' de `tile_flags` y `encode` que la ejecución usa (aparecieron
  4-50 s después en la caché del usuario); su coste a media sesión, sin medir. `run.sh doctor` no calienta los
  núcleos de explorer.
- **Negativo:** calentar en un hilo al empezar adelanta la imagen en X a 6.12 s, pero retrasa la de Qt de 3.5 a 5.6
  s: el compilador quita el GIL al arranque.

**E7.5, la rendija en `main`** (`bench/slit_read.py abba`, las dos cachés calientes):

| tanda | explorer: primera / siguientes | prototipo: primera / siguientes | total explorer / prototipo |
|---|---|---|---|
| 1, 4 rondas | 25.7 / 27.3 ms | 21.9 / 14.0 ms | 141 / 239 ms |
| 2, 3 rondas | 30.4 / 38.6 ms | 22.3 / 13.7 ms | 140 / 173 ms |
| 3, 3 rondas | 35.9 / 43.8 ms | 42.1 / 23.7 ms | 130 / 124 ms |

- La primera rendija ya no está en 45-61 ms: la mejora de la rama se confirma en `main`.
- El tiempo propio de las siguientes es bimodal (14-24 o 35-55 ms): cuando la lectura acaba mientras el hilo de la
  interfaz aún pinta tras traer la pestaña de la rendija, sus resultados esperan 13-20 ms en la cola; el aviso
  `panels` de esa pestaña llega 60-130 ms después de `set_path`.
- cProfile de las rendijas terminadas: `paintEvent` acumula 208-615 ms en explorer frente a 29-35 en el prototipo,
  casi todo fuera de Python (¿el GIL de los lectores o el dibujo de Qt? sin probar).
- **Negativos:** vectorizar el bucle de `_from_blocks` es más lento (1.4 → 2.2 ms) y no cambia nada en ABBA;
  `setswitchinterval(0.001)` queda dentro del ruido.
- El tiempo propio penaliza a explorer porque su lectura es más rápida y el trabajo de la interfaz ya no se esconde
  tras la E/S; el total es igual o mejor. Por decidir: juzgar E7.5 por el total.

### 2026-10-10 (7): auditoría de simplificación, 27 commits desde `b571d12` (ROADMAP X.14)

A `0712b98`. Los duplicados, con un script de ventanas de 3 líneas normalizadas repetidas en `src/explorer` y leyendo
el código; lo muerto, con un script AST de nombres que no aparecen en `src`, `tests`, `scripts` ni `bench`,
confirmado con grep. La cobertura, con grep sobre `tests/`: la venv no tiene `coverage`. 21 hallazgos, 20 abiertos y 1
que no es defecto, en el fichero de auditoría (fuera de git).

- **Un defecto, S10:** un enlazado que el plan acepta y `Dataset.open` rechaza paraba el arranque. Arreglado (X.13).
- **Inventario de la capa de ventanas:** 11 `singleShot(0)`, 19 ramas `if self.glass`, 29 `look.has`, 25
  `isFloating`. Las esperas llevan su medida en el comentario y no se proponen quitar; sí una que depende del orden de
  la cola (S17).
- **Duplicados:** etiquetas y ejes de la λ–t copiados en el panel de la rendija; tres títulos de panel y dos dibujos
  de las marcas cerrar y flotar; `_Sink` frente a `CubeSink`; cinco LRU con presupuesto de bytes (`NegativeI` fijo en
  32 MB, sin parte del presupuesto); «soltar, mover, bloquear» cuatro veces.
- **Muerto:** `SlitPanel.set_background`, tres peticiones de `xproto` y cuatro atributos que nadie lee.

Propuesto empezar por lo muerto, los ejes de los paneles y los ayudantes de shell y cube: ~70 líneas, cada cambio con
capturas antes y después y las suites en bellatrix. Nada tocado: pendiente del visto bueno del usuario.

### 2026-10-10 (8): E6.12 y E5.16, preparadas para decidir (sin código)

**E6.12.** De los 15 hallazgos abiertos del prototipo, explorer hereda 14; F20 pasa a ser parte del diseño con el ADR
0009. Todos comprobados en el código de explorer; F24a y F35 medidos además en el Mac (sin pantalla): el separador de
los docks es de 1 px con el estilo de macOS (8 con el de explorer fuera de él), y un panel flotante es `Qt::Tool` sin
`WA_MacAlwaysShowToolWindow`, con el mecanismo que los esconde al perder el foco en el `libqcocoa` de la venv; el
efecto en pantalla no se ha visto. Propuestos: 6 cerrados como ⚪ sin coste (F9, F20n, F23f, F23g, F7, F20); 3 con una
sola sesión de medida en bellatrix (F3, F9c, F50: el tope de 12 fps viene del puente del prototipo, limitado por CPU);
4 con un vistazo del usuario (F35, F37, F38, F40); 2 decisiones de aspecto (F24a, F47e).

**E5.16.** Leído `crispex.pro`: fondo blanco y tinta negra (índices 255 y 0 de la tabla 0, `:22108`), curvas
`THICK=2` sin símbolos (`:22109`), espectro medio raya-punto (`LINE=3`, `:8425-8428`), marcadores λ y t de 2 px de la
tabla 13 índice 255 (`:8566-8570`; RGB sin verificar, falta `colors1.tbl`; el marcador t de intensidad-tiempo es
negro), cursor `+` de 1 px, negro si la media 3×3 del byte escalado es ≥ 122 y blanco si no (`:8066`, `:7887-7921`).
El classic de explorer difiere en casi todo: fondo y tinta del tema, curva de 1.5 px con puntos y rejilla
(`ui/spectra.py:197-215`), marcadores (255, 80, 80) (`ui/imageview.py:31`, `ui/pens.py:47-57`), cruz roja fija, sin
espectro medio. Por decidir, elemento a elemento, en una copia «classic IDL».

### 2026-10-10 (9): la prueba de temas en glass que fallaba a veces (ROADMAP X.12, X.15)

**La causa.** La barra de glass se oculta 2.5 s después de crear la ventana (`AutoHide`, `ui/glass.py:192`). La prueba
la mostraba otra vez antes de comparar, pero dejaba el temporizador en marcha: el de la primera ventana tenía 2.1-2.6 s
en bellatrix (1.8 s en el Mac) y saltaba durante la espera de 0.3 s antes de las capturas. Faltaba la barra en esa
ventana: un 14 % de píxeles distintos de claro a oscuro y un 6 % de oscuro a claro, en la caja exacta de la barra. En
las 130 ejecuciones instrumentadas, cada fallo coincide con la barra oculta y ningún acierto la tiene. El código hace
lo que debe; la prueba corría una carrera.

**Medido** (bellatrix, sin pantalla, sin fijar, carga 2-8; tasas de fallo, no tiempos): las dos variantes glass, 67 de
100 fallaban; con retrasos inyectados de 0 a 1.4 s, 15 de 80 (con 1.4 s se oculta la de la segunda ventana: las dos
corren la carrera); la prueba sin tocar, sola, 6 de 30; los 11 ficheros que la hacían fallar juntos, 1 de 129. No es
estado heredado de otras pruebas: es el mismo temporizador.

**Ahora** la prueba para el temporizador en las dos ventanas antes de mostrar la barra: ninguna barra oculta en 300
ejecuciones; la prueba sola, 0 de 30; los 11 ficheros juntos, 129 pasan. Classic, modern y la 2×2 de modern no tienen
`AutoHide`; no hay otro temporizador de arranque que cambie píxeles.

**Visto y sin trazar** (X.15): 2 de 400 con la ventana y la λ–t de otro tamaño (claro → oscuro, con carga 6-7).

### 2026-10-10 (10): el idlsave de un cubo alineado o `_sp`, y los nombres de 2019 (ROADMAP E1.25)

**La idea del usuario** (que un cubo `…_sp.aligned6173.icube` tome el idlsave de su observación, el nombre menos la
etiqueta) ya se cumplía. En las seis fechas de 2023-2025 enlazadas o listadas, 100 de los 101 cubos `nb_` encuentran
su idlsave y leen λ y tiempos: el alineado quitando la etiqueta, el `_sp` a través de su `_im` y el `_stokesI_` del
`_stokes_`. El que falta es uno recortado sin idlsave propio. En el árbol de reduc (48 carpetas de cubos, solo
listadas) no hay ningún `.sav`, ni ningún idlsave con la etiqueta de alineado en el nombre.

**Lo que fallaba era 2019.** El 2019-09-04, SSTRED escribió `<stem>_im_times_wvl.idlsave`, con `_` donde hoy pone `+`:
los Hα de ese día se abrían en cuentas, sin λ ni tiempos. El 8542 de ese día tiene los dos nombres, iguales salvo en
`fac`: 1 en el de `+` (el del cubo float) y 1e9 en el de `_` (el de los cubos de enteros); los de enteros tomaban el de
`+` y se quedaban en cuentas.

**Ahora** se acepta también el nombre antiguo. Si están los dos, se toma el idlsave cuyo `fac` encaja con el tipo del
cubo (distinto de 1 para enteros, 1 o ninguno para float); si no encaja exactamente uno, ninguno, y se dice. Cada cubo
dice una vez en la terminal qué idlsave tomó cuando no lleva su propio nombre, y un cubo de enteros con `fac` 1 dice
que sigue en cuentas.

**Medido** (bellatrix, solo lectura, un cuadro): el Hα y el 8542 Stokes I de 2019, escalados por 1e-9, coinciden con
su FITS hermano (medianas iguales; diferencia máxima 1.2e-4 y 1.8e-4 de la mediana, la cuantización de 1 cuenta). Un
cubo alineado tiene la escala de cuentas del no alineado: medianas 3024/3023, 847/845, 1713/1711, 4017/4016 y
1367/1367, y el mismo valor de relleno sin nada por debajo. Cinco casos nuevos de `test_formats` fallan antes y pasan
después; `tests/real`, 40 pasan. Negativo sin trazar: el 8542 alineado de 2019 en enteros frente al float difiere en
más de 1 cuenta en el 9.6 % de los píxeles (en (0, 0): 0 frente a 2796), por un relleno distinto del borde; no se
comprobó que todos sean borde.

**Sin decidir:** el `_rot5` del 2019-09-02 (mismo idlsave si se quita `_rot5`, mismas estadísticas que el alineado sin
rotar) y el cubo recortado del 2024-09-11 (su idlsave tiene 147 barridos y el cubo 86).

### 2026-10-10 (11): un `_sp` sin su `_im`: cuánto cuesta leer imágenes del fichero por píxel (ROADMAP E1.23)

**La idea** (el usuario): `explorer nb_6563_..._sp.fits` busca su `_im` y abre los dos; si no está, abrir el `_sp`
solo, «como `--no-sp` pero al revés».

**Lo que ya hay.** Comprobado en bellatrix con los 13 ficheros por píxel reales (los 12 de `data/` y el `_sp.icube` de
2025-07-05, leído en su sitio): `formats.opening` abre el `_im` de cada uno, los FITS por su cabecera y los LP por
nombre y dimensiones, también con `.aligned6173`, `cmapcorr_sp` y `meinv_…_sp`.

**La medida** (`bench/sp_frames.py`; nodo 0, cerrojo; Hα 2024-10-10 =0-48, el mismo cubo por los dos lados, todos los
cuadros iguales). Un píxel del `_sp` ocupa 2940 bytes (FITS, 13 GB) o 1470 (LP, 6.2 GB), menos que una página: un
cuadro del `_sp` toca todas las páginas del fichero.

| | FITS 13 GB | LP 6.2 GB |
|---|---|---|
| cuadro del `_im` | 8.9-21 ms | 4.8-9 ms |
| del `_sp`, en frío | 20.7 s | 10.5 s |
| del `_sp`, en la caché de páginas | 7.3-9.6 s | 4.2-4.3 s |
| del `_sp`, con el fichero ya mapeado | 59-65 ms (25-32 con 16 hilos) | 54-55 ms (22-26) |

Una pasada cuesta casi lo mismo guarde lo que guarde: 1 cuadro 4.1-4.7 s, los 15 λ de un t 4.5 s, los 49 t de una λ
6.4 s (LP, en caché). Carga 1.2-5.4 en la serie FITS; 17.8 → 5.9 en la LP, que no cuenta como carga baja, aunque los
efectos son de 100-1000×. Negativo: releer en lecturas de 256 MiB se quedó en 0.65-0.72 GB/s, sin caché (inferencia:
StorNext no pasa por la caché de páginas en lecturas tan grandes; los fallos de página sí la llenan).

**No se implementa.** Un paso en t cuesta hoy unos 22 ms; el primer cuadro del `_sp`, 4-26 s; los 22-65 ms exigen
todo el `_sp` en RAM (13 GB aquí, 176 GB el de 6173 Stokes del 2025-07-11). Para el usuario, sin probar: cuadros por
bloques en una pasada al cambiar λ o t; una copia transpuesta en su caché (disco; nunca junto a los datos de reduc); un
modo solo espectros con una imagen fija. Hoy no hay ningún `_sp` real sin su `_im` en `data/`.

### 2026-10-10 (12): la rendija del cubo en que se dibuja; el eje que no se sabe λ (ROADMAP E8.6)

**El problema** (el usuario): con Stokes y Blos enlazados, la rendija dibujada sobre el Blos daba el corte temporal de
Stokes. El panel leía siempre el primer cubo: `SlitReads` tomaba `session.main` y la t, λ y Stokes del estado
principal; el clic de una imagen enlazada llegaba a la herramienta sin decir de qué cubo era, y el panel se construía
una vez con los ejes del primero.

**Ahora** la sesión apunta el cubo de la rendija: el de la imagen que recibió el primer punto. Las lecturas pasan a ese
cubo (su fichero por píxel o sus cuadros, su caché, su λ y su Stokes) y el panel toma sus ejes y su nombre. Un mapa sin
tiempos propios, cuyos cuadros son las t del primero, se rotula con los tiempos del primero, y su panel muestra solo el
corte temporal, a todo el ancho.

**Los nombres** (el usuario: un Blos frente al tiempo no es «λ–t» ni tiene «λ index»): el eje distinto de t de un cubo
enlazado solo se llama λ cuando se sabe (λ en Å, CTYPE, `--axes` o el orden SOLARNET de tres ejes); si no, por lo que
muestra el cubo: BTYPE, la palabra del mapa o el nombre del fichero («Blos–t», «Blos index»), provisional, en una sola
función (`data/names.py` `slice_names`). El cubo principal no cambia.

**Medido** (bellatrix, sin pantalla, carga 0.4-2.8): en la ventana enlazada sintética, antes, la rendija sobre el mapa
daba un corte espectral de 5 filas (el mapa tiene 1) y un corte temporal que difería hasta 2.83 del mapa; después,
igual al mapa (|Δ| = 0); igual con el otro cubo (7 λ, a su λ). Con los cubos reales (`stokes_6173_im.icube` +
`Blos.6173_map.fcube`): sobre el Blos, corte (17, 959) de −3329 a 1947 G, título `Slit: Blos · Fe I 617.3`, t en UT;
de vuelta sobre Stokes, los cortes de antes. Sin rendija, el arranque es idéntico píxel a píxel (solo y enlazado; 0 px
entre dos tandas). Grupos de la rendija, el enlazado, la sesión, los nombres y la λ–t: 213 pasan.

**Por decidir:** la palabra para el eje que no se sabe λ; un panel de rendija por ventana de cubo (ahora uno, en la
principal); qué clic decide el cubo (ahora el primero); si el cubo principal sigue la misma regla; si «default (t,
lambda)» sin fichero de λ cuenta como λ. Sin ver: los colores en modern y glass.

### 2026-10-10 (13): series de ficheros FITS, `--series` (ROADMAP E1.26)

**El problema:** una carpeta de imágenes AIA (una por fichero) solo se abría como cubos enlazados de un cuadro.

**Ahora** `explorer --series aia*.fits` lee los ficheros como un cubo (t, y, x), sin construirlo:
- t va por la hora de la cabecera (`T_OBS`, si no `DATE-AVG`, si no `DATE-OBS`), no por el nombre: los nombres de JSOC son la hora pedida, no la observada;
- sin horas, orden de nombre y t es un índice;
- se rechazan las horas repetidas y los ficheros de otra forma, tipo, escala, `WAVELNTH`, `INSTRUME` o `BUNIT`, con los ficheros de cada grupo;
- un fichero normal se lee con un pread en su desplazamiento; uno comprimido (Rice, como los sirve JSOC), descomprimiendo con astropy.

**Medido** (bellatrix, nodo NUMA 0, cerrojo, carga 0.6–2.9):
- sintético, 4096² int16: el cuadro de la serie cuesta lo que el del cubo (47.8 frente a 51.4 ms en caliente, 85.5 frente a 86.0 ms en frío); Rice, 429 ms;
- real, 3900 ficheros AIA 171 Rice de 1986²:
  - las cabeceras leídas por astropy tardan 46 s (66 s en 16 hilos, por el GIL); leídas de sus bloques, 3.4 s; primera imagen a los 6.0 s del comando, antes 53.9 s;
  - el cuadro, 0.12 s, y no va más rápido en hilos (996 frente a 1207 ms ocho cuadros);
  - la reproducción decía 12 fps (el enlace X11) y mostraba 3.7 imágenes/s; ahora una descompresión a la vez, y el fps automático sale de lo que cuesta un cuadro: 6 fps y 5.8 imágenes/s.
- Memoria: astropy guarda la tabla comprimida de cada fichero abierto (4.9 GB con 3900); se dejan abiertos 16.

**Por decidir:**
- la rendija y el píxel en t de una serie comprimida son lentos (40 s para 600 filas × 300 ficheros; 3 s un píxel en 300 t): ¿caché descomprimida en disco (30.8 GB para los 3900)?
- enlazar una serie con otros cubos desde la línea de órdenes.

### 2026-10-10 (14): los paneles de un cubo sin λ o con una sola λ (ROADMAP E8.7)

**El problema** (el usuario): un cubo sin λ no debe abrir el panel de espectros; con una sola λ, o ninguna, un panel 2D de una sola columna o fila debe ser 1D. Antes, un mapa principal escondía al arrancar sus paneles Spectrum y λ–t vacíos, pero «reset» y la disposición guardada los volvían a mostrar vacíos, y el menú Panels los ofrecía. Un cubo de una λ tenía una λ–t de una columna, y la rendija un corte espectral de una fila. Un mapa enlazado no tenía λ–t.

**Ahora:**
- Un panel que ningún cubo tiene es un `GatedDock` que nada muestra, y no aparece en el menú.
- Con t y nl ≤ 1, la λ–t es una curva del valor en el cursor frente a t (`ui/lambda_t.py` `TimeCurve`), con el nombre que da `slice_names` (ahora también para el principal cuando tiene un plano o ninguno) y BUNIT en el eje y; el clic fija t. El núcleo la lee aunque el cubo no tenga λ.
- La rendija pierde el corte espectral de una fila en el principal, igual que en el enlazado; un mapa 2D dibuja su única fila como curva a lo largo de la rendija.

**Medido** (bellatrix, sin pantalla, carga 0.5-1.5):
- La curva en (20, 13) coincide exactamente con el fichero; un clic en x = 3.5 da t = 3.
- La curva de rendija del mapa 2D coincide con la imagen (|Δ| = 0 en 34 puntos).
- Un cubo espectral, idéntico píxel a píxel (0 px, classic y modern).
- Pruebas nuevas: 8 fallan antes y pasan después; la novena, la del cubo con λ, pasa antes y después.
- Grupos de shell, docks, layout, linked, λ–t, espectros, rendija, nombres, glass, tema, look, arranque, scheduler, sesión, 2×2, toolbar y etiqueta de Stokes: 257 pasan.
- El Blos real abierto solo sin `--axes` sigue tomando su eje «unknown» como λ: sin cambio.

**Por decidir:** el Spectrum para una sola λ; t en horizontal; el nombre y la escala del eje y en cubos Stokes; el título «λ–t» con pestañas; el eje «unknown» de un mapa LP.

### 2026-10-10 (15): escala de color: lo que hacía CRISPEX y qué cuesta una gamma (ROADMAP E5.32)

**Qué hacía el CRISPEX de IDL** (leído en `crispex.pro`). Una pestaña *Scaling* con un combo de imagen (principal,
referencia, Doppler, slit-jaw), un combo de modo de límites («first non-zero image», «current image», «per time
step»), un campo *Histogram optimisation* (1e-4), dos deslizadores *Image minimum/maximum [%]* y un deslizador
*Gamma* de 0 a 1000 que da γ = 10^(v/500 − 1), de 0.1 a 10 (24405–24448). γ se aplica al dato conservando el signo
(8027–8036); los límites son MIN/MAX tras `IRIS_HISTO_OPT` (de SolarSoft, no está en el árbol: su efecto se infiere)
de la primera imagen, recortados por los %, y luego `BYTSCL` (8043–8047). Todo va por tipo de imagen y ventana
espectral (7956–7960). Por defecto, γ = 1: lineal. Ni ecualización ni log. La sesión guarda la estructura entera
(17521) y las preferencias la γ por defecto (14705–14708). Ninguna tecla.

**Medido** (bellatrix, sin pantalla). Tres imágenes, `scaling_aia171.png`, `scaling_sst6563.png` y
`scaling_aia171_lut_banding.png`:

- **AIA 171:** con los límites de ahora (1–99 pct) el disco queda oscuro y la corona fuera del limbo no se ve; γ 0.5
  o log la sacan.
- **SST Hα:** lineal va bien. γ < 1 lava la imagen porque el relleno lleva el límite inferior a 0.
- **LUT sobre los bytes:** una LUT de 256 sobre los bytes de explorer con γ 0.3 deja 9 niveles en un recorte fuera
  del limbo, frente a 35 con γ sobre el dato. El byte 1 va a 1 y el 2 a ~48 (pendiente infinita de x^0.3 en 0; un
  byte son ~5 cuentas y el fondo tiene 4–6). Una tabla de 65536 da 42 niveles.

**Coste** (nodo 0 fijado, en serie, carga 0.7–1.2, 25 repeticiones, medianas, 2k → 2k):

- el núcleo de hoy, 40.8 ms;
- la potencia dentro del núcleo, 185.5 ms (no);
- una tabla de 65536 dentro del núcleo, 35.7 ms: más rápida que hoy, por un mecanismo sin trazar;
- numpy sobre el fotograma, 8.7 (19.7 con signo);
- una LUT de numpy después, +13.

**Resultado negativo.** La LUT de 256 «gratis» sobre los bytes no basta con γ < 1.

**Sin decidir.** Las preguntas de la sección 4. Nada se ha tocado en el código.

### 2026-10-10 (16): inventario de los controles del CRISPEX de IDL (ROADMAP E5.31)

**La pregunta.** El CRISPEX de IDL tenía un panel de control enorme; explorer quiere sus capacidades sin llenar la
interfaz (el usuario): cada opción, una fila de la tabla de acciones, que se alcanza sobre el objeto, por el menú
contextual o por el buscador, y casi nunca hace falta tocar porque el valor por defecto sale de los datos.

**Lo hecho.** Lectura de la construcción de widgets de `crispex.pro` (panel 23720-25134, preferencias 13924-14116,
seis ventanas secundarias, ratón 2233-2420, atajos 9909-9937, palabras clave 22002-22019) y de `src/explorer` en
`main` y en las ramas del día. 144 controles, cada uno con su línea, su estado en explorer, la entrada propuesta y
una frecuencia estimada (inferencia).

**Medido.** Nada se ejecutó. Recuento: 35 ✅, 28 🟡, 61 ⬜, 20 ⚪ (propios de IDL o resueltos por diseño: modos de
zoom, ventanas sueltas, preferencias de color que dan el tema y el aspecto). Entradas principales de los 124 que
aplican: D 26, B 24, C 24, O 19, barra 14, hoja de trabajo 10, tecla 7. Explorer no tiene hoy ningún menú
contextual ni ningún guardado de imagen.

**Sin resolver.** Si la hoja de exportación basta como único formulario (propuesta: sí, sin inspector lateral); si
la clave de color pasa a ser interactiva; si IRIS (8 filas ⬜) entra en el alcance; cómo lleva `ActionRegistry`
argumentos y contexto para B y C.

### 2026-10-10 (17): gamma por cubo y por Stokes, en el núcleo de reducción (ROADMAP E5.32)

**Qué.** Una γ por (cubo, Stokes), 1 por defecto, en el estado del núcleo (`ViewState.gamma`, `Session.set_gamma`).
Con límites desde 0 (I, AIA), x normalizado entre los límites y luego ^γ; con límites simétricos (Q U V),
sign(x)·|x/m|^γ, el 0 en el gris medio y x y −x en bytes espejo (b + b' = 256), como CRISPEX conserva el signo
(`crispex.pro:8027-8036`). La imagen la lee de una tabla de 65535 entradas dentro del núcleo; λ–t y los cortes de la
rendija, en numpy sobre sus arreglos pequeños.

**γ 1 no cambia nada.** No es «casi igual»: con γ 1 corre `reduce_u8_serial` como antes. Los fotogramas reducidos
son iguales byte a byte (2k y 4k, en serie y en 8 franjas). Las 36 capturas de los 12 escenarios: base frente a rama,
0 px; dos tandas de la base difieren en el fichero ruidoso de siempre, 865 px. Golden, 26 de 26.

**Coste** (bellatrix, nodo 0 fijado, ABBA, carga 3.4 → 2.6, 25 repeticiones, medianas):
- 2k → 2k: 40.9 ms con γ 1 y 34.8 con γ 0.5 en serie; 5.6 y 5.0 con 8 franjas;
- 4k → 2k: 66.2 y 58.1 ms en serie; 8.7 y 7.7 con franjas.

La tabla es más rápida que la recta, por un mecanismo aún sin trazar.

**Bandas.** En el recorte débil fuera del limbo de AIA 171 con γ 0.3 hay 42 niveles de gris; con una LUT de 256
sobre los bytes, 9.

**Teclas, provisionales** hasta que la clave de color sea interactiva:
- G y ⇧G bajan y suben γ en décimas de década (1 → 0.79 → 0.63 → 0.50) y ⌘G la vuelve a 1;
- actúan sobre la imagen bajo el puntero, su cubo y su Stokes; en la vista 2x2, el Stokes del panel;
- la barra de estado dice la γ nueva y la clave de color escribe «γ 0.5» mientras no sea 1.

**Visto.**
- AIA 171 con γ 0.5 saca la corona fuera del limbo.
- En V de 6173 con γ 0.5 el signo se conserva, pero el ruido en torno a 0 se vuelve sal y pimienta: la pendiente de
  |u|^γ es infinita en 0. Queda como decisión.

**Sin decidir.** ¿γ por λ? Guardarla con la disposición; la clave interactiva; qué hacer con el ruido de V; el paso
de las teclas.

### 2026-10-10 (18): dónde van el mínimo, el máximo y la γ: tres prototipos y su coste (ROADMAP E5.33)

**El problema.** La γ por (cubo, Stokes) funciona con G ⇧G ⌘G, pero no hay forma de ajustarla en la interfaz ni
de elegir el mínimo y el máximo (el usuario). Restricciones acordadas: no abarrotar; las opciones sobre el objeto,
en un menú contextual, en una paleta de órdenes o por defecto según los datos; la barra de herramientas no cambia;
nada de inspector fijo.

**La interfaz de hoy** (leída y capturada, `gui_now_*`):
- Solo la imagen principal tiene clave de color, y solo en modern (abajo a la izquierda) y en glass (arriba a la
  izquierda). Es de solo lectura (`WA_TransparentForMouseEvents`).
- Classic, las imágenes enlazadas, la ventana propia de un cubo y la 2×2 no tienen ninguna; todas tienen candado.
- Los límites fijos son del cubo y solo distinguen I de Q U V (`Levels._fixed`); la γ ya es por (cubo, Stokes).
- Sobre la imagen:
  - el clic derecho suelta el cursor;
  - el arrastre derecho estira el zoom (lo hace pyqtgraph por defecto y no está en la hoja `?`);
  - no hay ningún menú contextual.

**Prototipos** (copias parcheadas sobre la Shell real, AIA 171 y V de 6173 con Blos enlazado, classic y glass):
- **A:** la clave se agranda al pasar el ratón, con el histograma, la curva de transferencia y dos asas.
- **B:** una tarjeta con campos y deslizador.
- **C:** un menú con reglas de límites y γ predefinidas.
- **Visto:** en una ventana de cubo de 270 px la clave de 260 se corta; tiene que tomar el ancho del panel.

**Coste** (bellatrix):
- **Histograma**, con el nodo 0 fijado y carga 0.8:
  - sobre los datos en `[::8, ::8]`: 1.15 ms (los límites de hoy, 1.62);
  - sobre el cuadro entero: 65 ms;
  - sobre los bytes reducidos: 18 ms, y en el eje equivocado.
- **Arrastrar un límite** vuelve a pasar el núcleo de reducción: 5.4 ms por paso con la imagen en 1024 px y 16.5
  con 2048 px, pintado incluido.
- **Por el puente X11** (Xvfb `:158`, traza):
  - cada paso manda la imagen entera, 731 kB en classic y 890 en glass;
  - si solo cambia la clave, 20 kB;
  - el puente no encola: mientras envía, junta las zonas sucias (leído en el código, sin medir con un enlace lento).

**Recomendación.** A sobre cada imagen, C con clic derecho sobre la clave, B desde «Escala…»; G ⇧G ⌘G se quedan; sin
teclas para mín/máx.

**Sin decidir.** Las doce decisiones del informe `gui.md`.

### 2026-10-11 (1): decisiones del usuario sobre los pendientes del 2026-10-10

Con la página de pendientes (capturas y órdenes por punto), el usuario decidió:
- **Máscara (E8.2):** el color es el acento del aspecto, no un rojo fijo; el contorno va por los bordes de los píxeles,
  como ahora.
- **Aumento de las enlazadas (E8.3):** alejarse por debajo del propio ajuste, para un solo aumento (hecho, (2)).
- **Colores de IDL (E5.16):** el classic actual es mejor: descartado.
- **I negativa (E1.24):** por muestra, como ahora.
- **Rótulo «Stokes» (E4.15):** se lee bien.
- **Glass por el puente (E5.25) y el puente desde bellatrix (E6.21, E6.11):** sin problemas en su pantalla.
- **Nombres de un eje que no es λ:** la opción A, a probar con otros FITS ((7)).
- **Rendija:** una pestaña por cubo ((3)).
- **Una sola λ:** sin Spectrum al arrancar ((2)).
- **Gamma (E5.32):** 1 por defecto; una por cubo y por Stokes; con signo y simétrica en Q U V; 0.1 décadas por tecla;
  guardada con la disposición; no por λ; G ⇧G ⌘G se quedan y van en la hoja `?`.
- **Series (E1.26):** como mucho 100 pasos de t en los paneles temporales, con un número en el título ((4)).
- **`_sp` solo (E1.23):** un aviso al estilo de `?` con la copia transpuesta y su factor de velocidad ((5)).
- **Interfaz de la escala (E5.33):** una demo del diseño A + C + B ((6)).

Las demos 6 y 8 de la página fallaban porque los cubos sintéticos de `/tmp/…demo` no se habían escrito: el
fragmento que los crea no se ejecutó; ahora existen.

### 2026-10-11 (2): un solo aumento en las ventanas de cubo; el Spectrum de una sola λ, a petición (ROADMAP E8.3, E8.7)

**El aumento.** Una ventana de cubo mayor que la imagen principal ajustada mostraba otro aumento (3.24 px por píxel
en la principal, 7.95 en la ventana del cubo): su `ViewGuard` no la alejaba por debajo de su propio ajuste y deshacía
el realineado de `ViewSync`. Ahora el guardián de una imagen enlazada toma como suelo el ajuste de la principal
(`ViewGuard.floor`, `lowest()`): un solo aumento por grande que sea la ventana, también tras un doble clic en
cualquiera de las imágenes; la rueda se para donde se para la principal. La principal sola, como estaba. Una enlazada
más pequeña que la principal se para ahora en el aumento de la principal, no en su propio ajuste.

**Una sola λ.** Con nl = 1 en todos los cubos con espectros, el Spectrum (un punto por Stokes) ya no se abre al
arrancar, tras «reset», al restaurar la disposición ni en glass: `GatedDock.on_request`, la misma puerta que el
cubo sin λ, salvo que el menú Panels sí lo abre (cuatro Stokes en un punto aún se comparan); un «reset» o su ✕ lo
cierran otra vez. Enlazado a un cubo con varias λ, se muestra como siempre.

**Medido** (bellatrix, sin pantalla, carga 0.5-5): las pruebas nuevas fallan con `integ-1011` (7.35 frente a 19.94
px por píxel; Spectrum visible al arrancar) y pasan con el cambio; grupos linked, glass, glass_zoomed, layout,
shell, imageview, docks, stokesgrid, toolbar, gestures y without_lambda: 108 pasan. Arranque píxel a píxel (19
ventanas, clásico y glass, uno y enlazados, restaurado, cubos aparte y de vuelta): 0 px; ruido 0.

**Para decidir** (`help/small_skin_docked_vs_now.png`, datos reales, glass): la piel de glass en los paneles
acoplados dentro de una ventana de cubo, frente a los títulos del chrome de hoy.

### 2026-10-11 (3): una pestaña de rendija por cubo (ROADMAP E8.9)

**El problema** (el usuario): con cubos enlazados quiere ver la misma rendija en todos a la vez. Desde ayer (E8.6), el panel Slit muestra el cubo en que se dibujó la rendija, uno cada vez: solo el planificador del primer cubo tenía lecturas de rendija (`core/scheduler.py`, `if member == 0`).

**Ahora** cada planificador tiene sus lecturas de rendija, de su cubo (`SlitReads(cube=k)`), y ve el estado entero (el de un miembro no lleva la rendija). Con `ViewState.slit_tabs`, cada una lee su cubo; sin él, la del primero sigue al cubo dibujado como ayer y las demás no muestran nada. En la ventana, el panel Slit lleva un `PanelTabs` con una pestaña por cubo (`"slit"`, `"slit:k"`), y delante va la del cubo en que se dibuja. ⇧S o Panels → «A slit tab per cube» lo apagan. En «cada cubo en su ventana», el panel de rendija del cubo va a su ventana, bajo su λ–t, y se muestra mientras haya rendija.

**Medido** (bellatrix, `stokes_6173_im.icube` + `Blos.6173_map.fcube`, fijado al nodo 0 con el cerrojo, carga 6.6–7.9 por otros usuarios: no es carga baja; 2 tandas de 8 rendijas de 712–1382 px, dibujadas una vez en cada imagen):
- una pestaña detrás no leyó nada antes de mostrarse (16 de 16, en las dos tandas);
- traer delante la de Stokes (bloques por píxel) tardó 33–168 ms; la de Blos (cuadros), 18–70 ms;
- la pestaña del cubo dibujado: Stokes 69–322 ms, Blos 24–41 ms;
- bloques de rendija guardados tras 8 rendijas: 6975, ≈ 51 MB, acotados como antes.

Por eso solo lee la pestaña delante: cambiar de pestaña cuesta una lectura, menos que la primera de la pestaña dibujada, y leerlas todas gastaría esa lectura en cada rendija aunque no se mire.

**Pruebas:** cada pestaña igual a los datos de su cubo a lo largo de la rendija (núcleo con fichero por píxel y con cuadros; ventana con los tres cubos sintéticos). La pestaña del cubo dibujado va delante. Apagado, la pestaña única es igual a la de ayer. En su ventana, cada cubo tiene su panel. Sin rendija, el arranque es idéntico píxel a píxel (0 px solo y enlazado, 0 px entre dos tandas). Los grupos de rendija, enlazado, sesión, shell, layout, nombres y λ–t pasan en bellatrix. Dos fallos:
- la prueba de la disposición guardada comparaba la geometría de paneles ocultos (el de rendija sin rendija): ahora solo la de los visibles;
- una de la barra (`test_the_sliders_give_way_in_a_narrow_window`, 915 > 908 px) falló en el grupo con carga ~7 y pasó sola en las dos ramas: sin trazar.

**Por decidir:** la tecla ⇧S; si leer todas las pestañas al terminar la rendija (cambio instantáneo, lecturas que quizá nadie mire); en «cada cubo en su ventana» todas leen, también al dibujar (sin medir); si se guarda el interruptor con la disposición.

### 2026-10-11 (4): como mucho 100 pasos de t en los paneles temporales (ROADMAP E8.10)

**El problema** (el usuario): en una serie AIA comprimida cada t es un fichero que descomprimir. Un píxel a lo largo de 300 ficheros tardaba 3.2 s, y el corte temporal de una rendija 40.6 s: más de lo que vale mirar el panel.

**Ahora:**
- **Qué se lee:** la λ–t (o la curva del valor frente a t) y el corte temporal de la rendija leen y muestran como mucho N pasos de t, 100 al empezar. Son los centros de N intervalos iguales de t, los mismos en cada t: un paso de t no relee nada.
- **Cómo se dibuja:** cada fila se dibuja sobre la t que representa. Los ejes, la línea de la t actual y el clic siguen en la t del cubo; el clic elige el paso más cercano.
- **El número:** junto a las marcas de cerrar y flotar de los paneles λ–t y Slit, en todos los aspectos. Clic: 25, 50, 100, «all»; la rueda pasa por ellos. Un solo N para todos los cubos; por encima de 100, solo «all».
- **Lo que se lee de verdad:** la lectura pide solo esos fotogramas (`at` en `series_frames`, `RowBands` y `SeriesReader`). Con fichero por píxel, el bloque trae todas las t y se aclara para mostrarlo.

**Medido** (bellatrix, nodo NUMA 0, cerrojo, carga 3.5–9, más de 20 en la última tanda: valen los cocientes):
- AIA 171, píxel en t: 300 ficheros 3.4 s → 1.1 s; 3900 ficheros 46 s → 1.4 s.
- Rendija de 723 px en 300 ficheros: 32 s → 10 s; con N = 25, 2.5 s.
- **Negativo:** la rendija con 100 pasos sigue en 10 s, porque descomprimir las 600 filas que cruza cuesta unos 0.1 s por fichero.
- SST nb_6563 (nt 66): igual que antes, 65–88 frente a 69–80 ms.
- Un cubo con nt ≤ N, idéntico: los paneles λ–t y rendija, 0 px en 10 escenas. Solo cambia la fila del título, por el número.

**Por decidir:**
- el tope para cubos que leen todas las t sin coste (con fichero por píxel);
- N = 25 solo para la rendija;
- el título propio en el Mac local.

### 2026-10-11 (5): un `_sp` sin su `_im` se abre, con una hoja sobre lo que cuesta y la orden para transponerlo (ROADMAP E1.23)

**La petición** (el usuario, 2026-10-11): avisar en pantalla, al estilo de la hoja `?`, de que conviene crear una copia transpuesta, con el factor de velocidad estimado.

**Qué hace.** `explorer x_sp.fits` sin `x_im.fits` al lado ya no se rechaza (FITS; un LP sigue rechazado porque su cabecera no da el tamaño de la imagen). `io.PerPixelFrames` lee cada imagen en una pasada por el fichero, en bloques de 64 MB de filas, y saca de la misma pasada todas las imágenes pedidas a la vez (I con Q/U/V); sin lectura adelantada y con un lector. Los espectros, λ–t y rendijas leen el registro del píxel como con el par. Al abrir, una hoja como la de `?` (no modal; Esc o un clic la cierran) dice el coste de una imagen (tamaño entre el caudal de 4 lecturas de 8 MB; tras la primera imagen, su tiempo), el tamaño de la copia, cuánto más rápida (estimación: el número de imágenes) y la orden `explorer transpose`. Con el `_im` no hay hoja. `--sp` con el mismo fichero lo abre solo aunque tenga `_im` (así se prueba en bellatrix, donde todo `_sp` real tiene su `_im` junto al destino del enlace).

**La copia.** `explorer transpose <sp> <dir>` lee el `_sp` una vez en bloques de 256 MB y escribe en `<dir>/<stem>_im.fits.part` las filas de cada imagen; al acabar la renombra y enlaza el `_sp` a su lado. Cabecera del `_sp` con los ejes renumerados y WCS-TAB tal cual: se empareja con el `_sp` y da los mismos tiempos y λ (pruebas: igual al `_im` byte a byte). No escribe junto al `_sp`, ni en el árbol al que apunta un `_sp` enlazado (para `data/lp/…` → todo d12), ni bajo `EXPLORER_READ_ONLY`; la ruta de los datos de reduc no puede aparecer en el código (`hygiene.py`).

**Medido** (bellatrix, nodo 0, cerrojo; Hα 6563 `_sp.fits`, 12.3 GB, por un enlace; carga 4-6):

| | 1.ª | 2.ª |
|---|---|---|
| estimación al abrir | 39 s | 28 s |
| primera imagen | 26.2 s | 22.6 s |
| paso en t | 24.4-24.9 s | 20.3 s |
| bloque del píxel | 2.2 ms | 2.1 ms |

La estimación inicial se pasa por 1.2-1.5×; la hoja la sustituye por el tiempo real tras la primera imagen (19.6 s → «735× más rápida, 27 ms», del orden de los 9-21 ms medidos del `_im`). El transpositor: 470 MB sintéticos en el `/tmp` local, 0.98-1.03 s (457-479 MB/s, fuente en caché). Extrapolado, no medido: unos 30 s para 13 GB en disco local; en StorNext al menos una pasada en frío (20-26 s) más escribir 13 GB, del orden de un minuto o más.

**Pendiente:** pasar t deprisa encola una pasada por paso (no se cancelan); en un `_sp` de 4 Stokes los rangos de Q U V leerían 3 × nl imágenes (inferido, sin medir).

### 2026-10-11 (6): mínimo, máximo y γ sobre la imagen: la clave interactiva, su menú y la tarjeta (ROADMAP E5.33)

**Qué.**
- Cada imagen tiene su clave de color: la principal, las enlazadas y la ventana propia de un cubo, en classic
  (nueva, abajo a la izquierda), modern y glass (arriba a la izquierda).
- Al pasar el ratón se agranda: el histograma del cuadro (`[::8, ::8]`, la muestra de los límites automáticos), la
  curva de transferencia, en la que se ve la γ, y un asa en cada límite.
  - Arrastrar un asa fija ese límite y cierra el candado; en Q U V una sola asa mueve los dos extremos.
  - La rueda cambia la γ con el paso de G.
  - El doble clic vuelve a los límites automáticos y no toca la γ.
- El clic derecho sobre la clave abre un menú corto: la regla de límites, γ predefinidas, «Escala…» y reiniciar. En
  la imagen, el clic derecho sigue soltando el cursor.
- «Escala…» abre una tarjeta con mín y máx escritos, el deslizador logarítmico de CRISPEX y la regla.
- En la vista 2x2 no hay clave por panel: el menú se abre con clic derecho en la etiqueta del Stokes.

**Estado.**
- Regla, mín y máx por (cubo, Stokes) en la sesión, junto a la γ (`ViewState.scale`). Los límites fijos de
  `Levels`, por cubo y solo I frente a Q U V, se van.
- El candado fija o suelta el Stokes que se ve, y lo indica al cambiar de Stokes.
- La disposición guarda regla, límites y γ por nombre de fichero y Stokes, para cualquier forma de mostrar.

**Sin cambios al empezar.** Los 12 escenarios, con las claves ocultas, dan 0 px entre base y rama y entre dos tandas
de la base. Con las claves visibles, solo difieren las bandas de las claves nuevas (classic y enlazadas). La clave
de modern es idéntica.

**Por el puente X11** (Xvfb privado, traza, AIA 171, classic):
- cada paso de arrastre manda la imagen entera, ~0.8 MB;
- si el enlace da abasto, salen todos (47 MB/s en local);
- con el emisor retenido 250 ms por envío, 60 pasos dibujados salieron como 5 envíos y el último llegó 0.6 s
  después de soltar: el puente descarta los intermedios, no los encola.

**Visto.** Dos pruebas de otros ficheros fallaban solo detrás de las nuevas: un `mousePress` sin `mouseRelease` dejaba
un botón pulsado. Corregido.

**Sin decidir.** El candado por Stokes o por cubo; qué reinicia el doble clic; la clave por panel en la 2x2; «igual
para los enlazados»; si `--reset-layout` olvida la escala.

### 2026-10-11 (7): el nombre de un eje que no es λ, con ficheros reales (ROADMAP E8.8)

**La pregunta** (el usuario): la opción A (BTYPE, si no la palabra del mapa en el nombre, si no el nombre del fichero) solo se había probado con Blos.

**Medido** (bellatrix, solo cabeceras; las ventanas, sin pantalla):
- 34 ficheros de 22 tipos.
- La A da lo esperado en los mapas SST con palabra en el nombre («Blos–t», «Doppler–t») y en todo cubo con λ.
- Falla:
  - en AIA, STEREO/EUVI y GONG, el nombre del fichero («aia.lev1_euv_12…171.image–t»);
  - en EUI, «Intensity–t», porque su BTYPE es genérico;
  - en BIFROST, «lg(tg) index», aunque su CTYPE3 dice z; y «bz [True]», porque su BUNIT=T se lee como booleano;
  - en dos inversiones, «λ–t» y «λ index» sobre los parámetros: el `meinv` LP, porque el reparto por su `_sp` llama WAVE a sus 3 planos, y `WFA_inversion_8542.fits` sin cabecera, por el orden SOLARNET, que además pone un eje de 2 parámetros en los botones de Stokes I y Q.
- El cubo principal nunca usa la A para un eje de varios planos (`cube.py:92`).

**Propuesta P**, probada sobre copias parcheadas, sin commits: «AIA 171 Å–t», «EUI/FSI 174 Å–t», «EUVI 171 Å–t», «GONG Hα–t», «Blos–t» sin cambio, «Fe I 617.3 inversion (parameter–t)» con «parameter index». Una escala de color para tres parámetros satura dos de las tres columnas: mejor un selector al modo de Stokes (sin probar).

**Sin resolver:** no hay en disco ninguna inversión FITS con un EXTNAME por parámetro; qué tres parámetros guarda el `meinv` (el `.pro` que lo escribe no se puede leer).

### 2026-10-11 (8): juntar el trabajo de dos días; el lector de un `_sp` solo y los pasos de t

`integ-1011b`: `main` y las ramas del 2026-10-10 y del 2026-10-11, aplicadas en orden. Dos conflictos de texto
(`core/scheduler.py` y `core/state.py`: la rendija por cubo y la escala por (cubo, Stokes); `ui/cube.py`: dos
importaciones) se resolvieron conservando los dos cambios. Uno de comportamiento lo encontró `mypy`: el tope de pasos
de t pasa `at=` a todo lector, y `PerPixelFrames` (el lector de un `_sp` solo, hecho a la vez) no lo aceptaba: la
λ–t y la rendija de un `_sp` solo habrían fallado con `TypeError`. Ahora lo pasa a `series_frames`; la prueba nueva
de `test_per_pixel_given` falla antes y pasa después (bellatrix).

Las suites completas de la rama juntada encontraron dos fallos más (bellatrix, unit y golden: 897 pasan, 2 fallan):
- **La rendija por cubo junto al zoom de las enlazadas:** al entrar en modo rendija los paneles enlazados se encogen un
  momento; con el suelo nuevo (el ajuste de la principal), una enlazada más pequeña que la principal ya no podía
  ajustarse a sí misma y quedaba recortada, y el clic de la prueba caía fuera. Aislado probando la rendija por cubo
  con cada rama por separado: solo con `small-decisions`, y dentro de ella solo con el commit del zoom. El suelo es
  ahora el menor de los dos ajustes: una ventana de cubo grande se aleja hasta el aumento de la principal, una
  enlazada pequeña se ve entera otra vez (la prueba de la rendija falla antes y pasa después; la del aumento único
  sigue pasando).
- **`test_headerless`** esperaba que una serie temporal sin λ no leyera nada; desde E8.7 lee su curva en t: la
  expectativa, actualizada.

Con los dos arreglos: unit y golden 899 pasan (15 saltadas), `tests/real` 40, `tests/xvfb` 39 (2 saltadas).

### 2026-10-11 (9): los arreglos de la tarde; la leyenda según el usuario

Seis ramas de arreglos sobre `main` (`c223b26`), cada una con pruebas que fallan antes y pasan después, juntas en
`integ-1011c`; las suites completas en bellatrix: unit y golden 929 pasan (15 saltadas), `tests/real` 40, `tests/xvfb`
39 (2 saltadas).
- **Paneles:** en la ventana de un cubo, su panel de rendija solo con rendija; un cubo de una sola λ en su ventana, su
  Spectrum solo desde Panels; la I de glass trae el Spectrum de una sola λ cerrado con su ✕; la hoja `?` explica el
  número de pasos de t; la piel de glass se borra al quitarla (antes, una por cada flotar y acoplar).
- **Nombres:** el eje x del Spectrum y la línea de estado nombran la magnitud cuando no hay λ o no hay Stokes («Blos
  62.83 G», no «I»); `BUNIT` y `BTYPE` solo como texto (`BUNIT = T` de BIFROST se leía True); la leyenda dice la
  regla de Q U V como es («auto |x| 99 %»).
- **Lecturas:** cerrar la ventana para las lecturas largas en curso (AIA, 300 ficheros, con la rendija leyéndose: 9.0
  → 0.04-0.10 s); en un `_sp` solo, los pasos de t rápidos se juntan en una pasada (Hα real: 77.6 → 27.3 s).
- **Máscara:** su lectura y su contorno fuera del hilo de la interfaz y por adelantado: paso de t con máscara por t
  54-56 → 29-33 ms (sin máscara 28-34; bellatrix, ABBA, nodo 0, carga 6-17).
- **Pruebas que fallaban a veces:** la barra estrecha (X.16: estado heredado de `apply_theme`, no carga) y X.15 (glass
  ajustaba la ventana antes de la primera imagen si llegaba tarde: arreglado en el código). La higiene revisa todas
  las ramas y el stash (X.17); `compare-bridges` se borró y su objeto se purgó del repositorio del Mac.
- **La γ:** «γ = 0.79» (dos cifras) con la γ en cursiva serif sobre la imagen (STIX Two Text, también en el Mac; en
  Noto Sans a 11 px era una «y»). Comparadas 23 candidatas sobre AIA 171.

Al juntarlas, dos choques: la leyenda (cortar el título y la γ legible: se conservan los dos) y una prueba de anchos
que no veía los textos con γ, dibujados por trozos (ahora los lee enteros). La γ más ancha cortaba la regla de Q U V en
la leyenda abierta: allí se escribe ahora solo cuando no es 1.

**La leyenda, según el usuario (2026-10-11):** sin menú en el clic derecho por ahora (`KEY_MENU`; el de las etiquetas
de la 2×2 sigue); el doble clic vuelve a los límites automáticos y a γ = 1; la γ y su valor solo en la leyenda abierta,
y en reposo durante un segundo tras G, ⇧G o ⌘G, en todos los aspectos. Estos tres cambios pasaron los grupos de la
leyenda, el gamma y glass (124 y 87 pruebas), no la suite completa.

### 2026-10-11 (10): la leyenda abierta en el acento del aspecto; la cruz que se quedaba (ROADMAP E5.33)

**La cruz** (el usuario, en classic: al entrar en la leyenda y salir por otro sitio, la cruz roja seguía donde había
entrado el puntero). Era una zona sin repintar, y de Qt, no del puente: al salir de la leyenda abierta, la leyenda
encoge y la cruz se mueve en la misma vuelta del bucle, y la imagen repinta solo lo que la leyenda destapa; las líneas
viejas se quedan en la memoria de la ventana y el puente manda exactamente esos píxeles. Medido sin pantalla (661 px
distintos de un dibujo nuevo) y por el puente en un Xvfb privado (452 px de la línea vieja en la ventana X, que es
igual a la de Qt). El disparador, medido: un cambio de geometría de un widget sobre la imagen en la misma vuelta que
mueve un elemento de la escena; por qué Qt no repinta es inferencia.

**Un solo mecanismo** para todo lo que flota sobre una imagen (`overlays.OverImage`, `ImageView.over`): un elemento
que cambia de tamaño, de sitio o de visibilidad repinta la imagen entera, y el puntero sobre él cuenta como fuera de
la imagen (la cruz se queda donde estaba, como al salir de la imagen). Lo usan la leyenda, el candado, el rótulo de
Stokes (también en la 2×2) y el aviso de la rendija; un panel futuro entra con `view.over.add(...)`.

**El acento:** la leyenda abierta toma el del aspecto: rojo en classic (el del cursor), naranja en glass, azul en
modern; sigue a un cambio de aspecto o de tema.

**Medido** (bellatrix): 5 pruebas nuevas fallan antes (452/451 px de la línea vieja en oscuro/claro; 0 px rojos en
classic) y pasan después; grupos de la leyenda, el aspecto, glass, enlazadas, candado y rendija: 196 pasan;
`tests/xvfb`: 40 pasan. Sin nada abierto, los 12 escenarios: 0 px frente a la base.

**Por decidir:** glass pasa de azul a su naranja en la leyenda abierta; la cruz ya no sigue al puntero bajo el rótulo
de Stokes ni bajo el aviso de la rendija (con una rendija a medio dibujar tampoco).

### 2026-10-11 (11): los mapas de color en todos los aspectos (ROADMAP E5.34)

**El problema** (el usuario): en classic, C y ⇧C no hacían nada y la imagen se quedaba gris. Classic no tenía ninguna parte, y "colour" decidía dos cosas a la vez: si C cambia el mapa y con qué mapa se empieza. En la práctica modern también empieza en gris; Q U V solo empiezan en otro mapa con `EXPLORER_DIVERGING`.

**Ahora:**
- **Dos partes:** `cmap` (C/⇧C; un Stokes fuera del gris se dibuja con su mapa) y `colour` (empezar en los mapas del aspecto). Classic tiene `cmap`.
- **Una sola regla, `Shell.maps_for(s)`,** para la imagen, las enlazadas, la 2×2, λ–t, las rendijas y la leyenda. En classic, un Stokes en gris sigue el camino gris de siempre (`base_lut`), así que el arranque es el mismo código.
- **Un juego de mapas por ventana:** el mapa elegido sigue tras M y T. Un Stokes que nunca se tocó toma el arranque del aspecto. `EXPLORER_LOOK_OFF=colour` ya no quita C; `cmap` sí.

**Medido** (bellatrix, sin pantalla):
- 11 pruebas fallan con el código de main y pasan con la rama;
- 16 grupos: 248 pasan, más `test_look` (19) tras corregir dos pruebas;
- 12 escenarios: 0 px frente a la base (la base contra sí misma: el fichero ruidoso de siempre, 865 px).

**Por decidir:** la leyenda de classic en el tema claro empieza en blanco (la entrada 0 de `base_lut` es el relleno). Se deja así para no cambiar el arranque.

### 2026-10-11 (12): λ₀ en la lectura de λ y en los ejes Δλ; el número de pasos de t con su glifo (ROADMAP E5.35)

**λ₀** (el usuario: «λ₀ + X Å», no «Δλ +X Å»). La lectura de la barra dice ahora «λ₀ − 0.206 Å». Se escribe como una suma (el signo, separado) para que se lea como la longitud de onda, λ = λ₀ + Δλ. Su ayuda da λ₀ = 6173.341 Å y su línea. λ₀ es `axes.lam0_nm`: la del laboratorio, en aire, por WAVEBAND o por la única línea dentro del barrido en los LP; es la misma de la que miden Δλ y el eje de velocidades del Spectrum. Va con tres decimales en todas partes, para que λ₀ + Δλ dé la λ de la línea de estado (6173.341 − 0.206 = 6173.135).

**Los ejes:** el Spectrum, el λ–t y el corte espectral de la rendija rotulan «Δλ [Å] from λ₀ = 6173.341 Å». Se compararon tres redacciones sobre datos reales. «Δλ + 6173.34 Å [Å]» se leía como si el eje fuera Δλ+6173.

**El número de pasos de t** lleva delante un glifo dibujado como los de `ui/icons.py`: una pequeña λ–t cortada en filas («grid»). Las otras candidatas: «rows» parecía el menú ≡, «comb» una E y «dots» los ⋮. Se cambia en una línea (`icons.STEPS`). La ayuda empieza por «t steps shown at most».

**Medido** (bellatrix, sin pantalla):
- 3 pruebas nuevas fallan antes y pasan después;
- grupos toolbar, spectra, lambda_t, slit_panel, titlebar, time_cap, labels, names, without_lambda, status, playback, look y polish: pasan (118 + 41; 79 + 5 tras el glifo final);
- capturas 1400×900 con el 6173 real: solo cambian la lectura (338 px), los rótulos Δλ (804 + 804, 811 y el de la rendija, 878) y el glifo (147). El mismo código dos veces: 0 px. Un cubo sin λ: solo el glifo.

**Sin explicar:** en una tanda, el eje izquierdo de la curva de un cubo sin λ salió 7 px más ancho en algunas ejecuciones del mismo código de `main`. No viene de este cambio.

### 2026-10-11 (13): la rendija sobre un mapa enlazado, otra vez al ritmo del puntero (ROADMAP E8.11)

**El problema** (el usuario): «la rendija artificial va ahora mucho más lenta; antes se movía mucho más rápido».

**Medido** con `bench/slit_drive.py` (nuevo):
- Mueve la rendija como un usuario, en la Shell real y sin pantalla, sobre el 6173 con el Blos enlazado.
- Va en bellatrix, en el nodo 0, con el cerrojo; ABBA entre `0712b98` (main del 10 por la mañana) y `4424608`.
- Dibujada sobre el principal, en classic, modern y glass, solo y enlazado: nada cambia. Del movimiento a la banda
  pintada, 2.2-2.6 ms; al corte pintado, 24-33 ms; 38-40 de 40 cortes a ritmo de puntero; A/D igual.
- Dibujada sobre el Blos: del movimiento al corte, 31.7 → 256.8 ms; a ritmo de puntero, 39.5 → 0 cortes pintados.

**La bisección** sobre ese caso da `3d0a312` (la rendija muestra los cortes del cubo en que se dibuja). Antes, la
rendija dibujada en el Blos mostraba los del Stokes, sacados de sus bloques por píxel. Desde entonces lee el Blos,
que no tiene `_sp`, por filas, y esa lectura espera 250 ms de reposo en cada paso (`REST_S`, F71). La lectura
misma tarda 4-23 ms (17 fotogramas de 2031 × 2028).

**Ahora** decide el tiempo medido de la última lectura. Si tardó 50 ms o menos (`LIVE_MS`), el paso siguiente se lee
al momento; una lectura más lenta vuelve a la espera, y otro cubo empieza esperando.

**Resultado** (ABBA, 4 tandas):
- del movimiento al corte pintado, 260.0 → 20.8 ms;
- a ritmo de puntero, 0 → 31 de 40 cortes pintados.

Dibujada sobre el principal: 32.2 / 30.3 ms, 40 de 40.

**Descartado, medido:**
- que `62d1fba` repintara la imagen entera: 1 pintado del viewport por paso, un 1% de su área, antes y después;
- el coste de una lectura de la rendija por cubo, el tope de t y la leyenda: nada en el principal.

**Pruebas:**
- una nueva falla antes (`2 == 4`) y pasa después;
- grupos de la rendija, enlazadas, `over_image`, `scale_gui`, `time_cap` y `shell`: 169 pasan.

**Por decidir:**
- el valor de `LIVE_MS`;
- si el primer paso de un cubo también se lee al momento;
- comprobar con el usuario que dibujaba sobre el mapa. A través del puente X no se ha medido.

### 2026-10-11 (14): la línea de la rendija esperaba al panel de la rendija, en el puente (ROADMAP E6.22)

**La pregunta** (el usuario): «¿puede ser que el dibujo de la rendija espere de algún modo al del diagrama en la subventana?».
Trabaja por ssh -Y hacia XQuartz: 32-61 MB/s y 12-15 ms de ida y vuelta medidos hoy.

**Medido** con `bench/slit_link.py` (nuevo):
- explorer de verdad por el puente, sobre un Xvfb privado, con el enlace emulado de `bench/xlink.py`;
- el puntero se mueve con XTEST desde el lado del servidor;
- en cada paso se lee con GetImage cuándo llega la línea a su sitio y cuándo cambia el panel de la rendija;
- la aplicación anota cada actualización del puente (bytes por región) y cada pintado.

Condiciones: el 6173 solo, classic, en bellatrix, nodo 0, con el cerrojo, ABBA.

**Resultado:**
- `0712b98` y `4dfe362` dan lo mismo: del movimiento a la línea, 72.5 / 72.9 ms a 30 MB/s y 104.3 / 105.7 ms a 10 MB/s.
- Sin los cortes en vivo, 61.6 y 79.8 ms.

**Por qué espera:**
- El movimiento llega a Qt a los 6 ms y la línea se pinta a los 19.
- El puente no la captura hasta los ~46 ms: su temporizador de 0 ms no salta mientras corren los repintados del panel (tres por paso) y los resultados de las lecturas. Una traza de todos los eventos no muestra ningún temporizador entre medias.
- Después la línea sale en la misma actualización que los cortes, y una sola copia por ventana la muestra al final: 486 kB, 258 del panel.

**Ahora** el puente captura con una llamada encolada, que corre tras lo ya encolado:
- de la línea, 73 → 57 ms a 30 MB/s y 105 → 84 ms a 10 MB/s (tres series ABBA);
- a ritmo de puntero, el panel se ve 0 → 28 veces de 40 a 30 MB/s;
- a 10 MB/s, la cruz del cursor llega igual (170 → 167 ms), pero se ven 14.5 posiciones de 40 en lugar de 5.5;
- cuesta un 26 % más de bytes por paso (664 → 839 kB), porque los repintados intermedios del panel ahora salen.

**No se pudo:**
- reproducir la espera con un bucle sintético (el temporizador saltó a los 6.5 ms): por eso no hay una prueba que falle antes;
- el caso enlazado: la imagen del Blos está en otra ventana y el instrumento suponía una sola.

**Pruebas:** `tests/xvfb`, 39 pasan; grupos de la rendija, `over_image` y `xbridge`, 156 pasan.

**Por decidir:**
- limitar el panel mientras se dibuja, o una copia por región, con las regiones pequeñas primero;
- si la cruz debe seguir al puntero mientras se dibuja (unos 210 kB por paso con los espectros);
- con qué versión iba más rápido.

**En la pantalla del usuario** (ssh -Y a XQuartz, enlace medido ~34 MB/s y 10.8 ms): «la rendija funciona mucho más suave y rápida». Llevado a `main`.

### 2026-10-11 (15): cada repintado sale en cuanto pasan sus bytes, por el puente (ROADMAP E6.23)

**La pregunta** (el usuario, tras probar E6.22 en su pantalla): estudiar, optimizar y usar el truco de la rendija en más cosas.

**Medido** con `bench/bridge_link.py` (nuevo, generaliza `slit_link.py`):
- explorer de verdad por el puente sobre un Xvfb privado, con el enlace emulado;
- la entrada con XTEST: cursor, t, λ, zoom, arrastre, la clave y su γ, la reproducción, y un cubo enlazado en su propia ventana;
- por paso y región, cuándo cambia en el servidor (bandas finas con GetImage, 1.3 ms por lectura), los bytes, los pintados y la CPU de la interfaz;
- `--native`: lo mismo con el xcb de Qt sin puente;
- `--probe`: píxeles que el servidor muestra y Qt ya no tiene.

Condiciones: el 6173, classic, en bellatrix, nodo 0, con el cerrojo, ABBA, enlaces de 30 MB/s y 12 ms y de 10 MB/s y 15 ms.

**Dónde espera lo pequeño:**
- Una actualización por ventana se mostraba con una sola copia al final de todos sus bytes.
- El asa de la clave salía con la imagen entera en sus nuevos niveles (511 kB).
- El texto de la barra de estado tras λ salía con la imagen y los dos paneles (777 kB).

**Ahora:**
- La actualización va en trozos, uno por repintado y en el orden en que Qt pinta, cada uno con su copia en cuanto pasan sus bytes.
- El asa: 44.6 → 28.6 ms a 30 MB/s y 77.6 → 31.7 ms a 10 MB/s.
- El γ en la clave: 64.8 → 40.6 y 111 → 46.
- La imagen tras t a 10 MB/s: 129 → 114 ms; con el cubo enlazado en otra ventana, 99 → 67.
- Barrido rápido a 10 MB/s: asentado 224 → 173 ms tras el último movimiento.
- La última región de cada paso llega igual.
- Además salen menos bytes (818 → 748 kB por paso de t), sin ningún píxel desfasado según `--probe`.

**En local no cambia nada:** el cambio está en el puente. En xcb nativo, un movimiento del cursor cuesta unos 23.5 ms de CPU de la interfaz (espectros y λ–t, unos 6 ms de pintado cada uno), más que los 16 ms entre movimientos.

**Descartados:**
- Una actualización sin confirmar en vez de dos: menos cambios vistos durante el barrido.
- Limitar los paneles del cursor a uno cada 50 ms: en el puente gana (asentado 189 → 105 ms a 10 MB/s); en local pierde (33 → 46 ms) y quita fotogramas de los paneles.

**Pruebas:** `test_bridge_pieces` falla antes y pasa después; `tests/xvfb`, 40 pasan; grupos `xbridge`, 64.

**Por decidir:** el límite de los paneles solo por el puente; mirar el desgarro entre trozos en la pantalla de verdad.

**En la pantalla del usuario** (ssh -Y a XQuartz): «se ve genial»; llevado a `main`.

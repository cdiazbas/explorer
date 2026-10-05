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

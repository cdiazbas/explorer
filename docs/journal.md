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

**Implementado** (commit `5575cb0`): el puente del prototipo (`app/xbridge.py`, `xconn.py`,
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

**Medida** (commit `bb614f0`):
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
`448f060`). bellatrix, 2026-09-30 12:39–12:44, cubo de Stokes 6173, 4 rondas ABBA; offscreen y xcb
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
después (`79e47c0`): 4 s menos, según el usuario. La línea de la primera imagen cuenta desde que
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

El usuario eligió B. A queda en el historial (merge `736099e`, quitado en `594d371`).

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
  al limpiar (`27cc7b7`);
- con un popup abierto, Qt en Linux deja la ventana padre activa sin ventana con foco
  (`89a7ee6`).

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

**Implementado:** docks (`180a830`); espectros, λ–t, barra de herramientas y de estado
(`8008558`, con `e9f41f0` para el orden de los paneles); candados y F / Mayús+F (`f8d1c34`);
clics en los paneles (`7a7786c`); reproducción y la sonda del enlace sobre el cliente X del
puente (`ca1c0ce`); el rango y de un espectro a mano, en la franja de su eje (`b0af22f`).

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

**Cómo** (`c836c86`, `72293bc`): `bench/protoface.py` pone los nombres del prototipo
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
- **Menús contextuales** (corregido, `d8383c0`): el clic derecho abría el menú de pyqtgraph sobre
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
- **Temas** (`1ad83fc`): el estilo del prototipo (`app/style.py`) sobre Fusion, oscuro y claro;
  `--theme auto|dark|light|native`. La prueba de humo del prototipo comprueba ya el estilo de
  explorer, no el suyo.
- **Barra de título propia, esquinas y bordes** (`9a514bb`): `app/titlebar.py` entero. `WindowOps`
  es ahora el `Mover` del prototipo: el zoom llena el monitor por geometría (sin gestor de ventanas
  también), y existen antes de mostrar la ventana. `platform/screens.py` porta `monitor_rect`
  (cabezas Xinerama por el cliente X propio; el Dock del Mac fuera por XQuartz).
- **La disposición entre sesiones** (`ad7f472`): geometría y paneles por tipo de pantalla, esquema
  con versión en el nombre del grupo (`app/v1.<tipo>/`), `--reset-layout`.
- **La hoja `?`** (`adc50e7`): una sola tabla de teclas y ratón para los atajos, la terminal y la
  hoja.
- **Los aspectos `classic` y `modern`** (`e7ca500`), como datos que toman la ventana y sus vistas;
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
  registro. Corregido con el bucle como contexto de los temporizadores (`81a4134`), con una prueba
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
allí (`97ad195`).

**El aspecto** (`8c5b1fd`, `a26becb`, `6e293e3`):
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
  de pyqtgraph al hacer clic derecho, que `d8383c0` quitó como en el prototipo; corregida
  (`5048f74`).
- Una prueba nueva maneja el desplegable de Stokes con clics XTEST a través del puente (`337291f`).

**Encontrado con la suite de conformidad del prototipo (xcb):** λ–t reacoplado con su botón de
flotar quedaba en (590, 466) de una ventana de 1200 px. Es decir, donde había flotado, ahora como
hijo, y 40 px más allá en cada flotar y reacoplar. Los clics posteriores en λ–t caían 80 px
desplazados.
- Qt 6.11 hace lo mismo con una `QMainWindow` desnuda, en xcb y offscreen: el sitio del dock en el
  layout no ha cambiado, así que Qt no lo vuelve a colocar. Ni `invalidate()` ni repetir la
  geometría del layout lo mueven.
- El arreglo (`8a49a62`): cada dock recuerda dónde estuvo acoplado y vuelve allí cuando Qt lo deja
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

**E4.14, corregido (`af840a2`).** Con fichero por píxel, el prototipo lee el primer espectro al
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
- Corregida (`fa1b2c5`): con el arreglo, 0 FAIL en 4/4; sin él, el título falla 4/4.
- La comprobación de tiempo del cursor cuenta ahora la lectura, como en el prototipo: mediana de
  12–15 ms (límite 60).

**El hook de los mensajes** (`372ea30`): ahora exige la línea en blanco tras el asunto y, en
`[ADD]`, `[DEV]`, `[FIX]` y `[PERF]`, las líneas `Behaviour:` y `Tests:` de la ADR 0005. Los últimos
40 mensajes lo pasan.

### 2026-10-01 (4): la ventana por X11 hacia un Mac (ROADMAP E5.7–E5.9), y el paso en t (E4.13)

**E4.13, la causa del paso en t lento** (`10dfa83`). El paso en t de explorer era bimodal: la mitad
de los pasos en ~15 ms, como el prototipo, y la otra mitad en 18–20 ms.
- Descartadas: la muestra del rango y en segundo plano (16.5 frente a 17.1 ms) y el recolector de
  basura (igual de bimodal con `gc.disable()`).
- Causa: la lectura anticipada se pedía dentro del paso, y sus lecturas frenaban el pintado. Ahora se
  pide en la siguiente vuelta del bucle.
- Mediana de los 10 pasos por ejecución: de 17.9–19.3 a 13.8–15.0 ms. El prototipo, 15.8.
- Serie canónica (8 rondas ABBA; la carga subió a 19.6 durante la serie):
  - sin `_sp`: 1.100 → 0.933, explorer más rápido 8/8;
  - con `_sp`: 1.109 → 1.022, 3/8. Pendiente de repetir con carga baja.

**El techo** (`0c81d16`, E5.7): arrastrada por su barra, la ventana subía por encima de la pantalla.
Solo por X11: con quartz-wm la barra mueve la ventana por sí misma, sin límite (heredado del
prototipo). Ahora no sube del borde superior de su monitor. El usuario lo confirma en XQuartz.

**La barra de estado** (`c0f4e16`): el texto empezaba a 2 px del borde, dentro de la esquina
redondeada de 16 px. Ahora hay 8 px a cada lado. El usuario lo confirma.

**El redimensionado por los bordes** (`b254675`, `5c8059e`, E5.8):
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

**Panels colgaba el visor por el puente** (`46b49e0`), como F45 en el prototipo:
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
- **Implementación** (`97ffefa`): explorer la monta sobre su `ImageView`, cuatro veces, con los
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
  (`5330879`):
  - 2 solo en el orden de los eventos;
  - 28 solo en la barra de pestañas que el prototipo acumula;
  - 37 por leer, todos explicados:

| causa | pasos |
|---|---|
| cambios de la barra hechos a propósito: sliders al 0.95, `?`, «All» ensancha el combo (el clic cae 3 px más a la derecha) | 17 |
| margen de 8 px de la línea de estado | 1 |
| reacople del prototipo con su tamaño de flotante, que explorer corrige (`8a49a62`) | 15 |
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
  auditoría F23c), y no se portó; una prueba de X exigía *utility*. Corregido en `a4935d4`.
- **Respuestas viejas.** Sin deriva, los paneles aún saltaban 1.2 s: el puente preguntaba a X
  dónde estaba una ventana enmarcada sin esperar, y aplicaba la respuesta aunque Qt hubiera pedido
  otra posición después. Ahora se descarta (`dfb2577`).
- **Paneles antes que su ventana.** Al arrancar en glass con su disposición guardada, los paneles
  flotan antes de que exista la ventana X principal: nacían sin dueño (`e707da0`).
- **Títulos pisados.** Al arrancar en glass en Linux, el marco de app.py ponía los títulos de panel
  después del aspecto; el prototipo los pone antes (`startup.py:145`). `12992a0`.

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
vez con lo que la prueba dice desde `d8e2307`. El segundo movimiento: el cursor sigue en [54, 66]. X tiene
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

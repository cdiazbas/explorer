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
- explorer: `scripts/demo.sh --no-window` (commit `62fb3c0`), que hoy ejecuta `doctor` sobre el
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

**Implementado** (commit `1b71165`): el puente del prototipo (`app/xbridge.py`, `xconn.py`,
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

**Medida** (commit `5a22101`):
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

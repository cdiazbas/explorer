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

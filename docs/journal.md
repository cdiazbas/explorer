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

**Mac** (M1 Pro): cubo sintético (8, 4, 10, 256, 256), solo `offscreen` (cocoa abriría ventanas
en la pantalla del usuario), carga 3.3.

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

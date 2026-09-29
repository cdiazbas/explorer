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

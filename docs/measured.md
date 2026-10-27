# Decisiones medidas

Lo que explorer conserva del prototipo porque está medido. Cada fila lleva su cifra, con sus
condiciones, y dónde se midió en el diario del prototipo (`OVERVIEW.md`, en `docs/` del
proyecto, citado por fase o fecha; [ADR 0002](decisions/0002-notas-del-prototipo.md)).

- **Cambiar una fila** exige medir otra vez con el mismo método, anotarlo en el
  [journal.md](journal.md) y, si cambia una decisión, escribir un ADR.
- **Lo que resulta falso** no se borra: se tacha, con la fecha y un enlace a la entrada del
  diario que lo corrige.
- **Máquinas:** "Mac" es un M1 Pro con SSD; "bel" es bellatrix (StorNext `cvfs`); "eagle7"
  comparte el StorNext de bellatrix, pero su cifra no se compara con las de bel.

Copiado de `docs/plan.md` §4 el 2026-09-28.

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
| Mostrar un resultado salvo que ya haya uno más nuevo en pantalla (no solo el último pedido) | 188 movimientos cada 8 ms (Mac, cubo de 22 GB, sin `_sp`): espectros mostrados 1–11 → 108–131, λ–t 1–11 → 100–120 | Código del prototipo (`_lt_ready`), 09-24 |
| Rango y: crece al mover, ajuste en reposo | 57 → 26 ms por movimiento | F64 (código) |
| Caché de imágenes: el bucle entero o poco | Solo el bucle entero gana (16.5 frente a 18.4–19.8 ms) | Fase 17 |
| `MemoryGuard` vigila el swap en macOS | "Disponible" no avisa: abortó con el swap +0.57 GB y 5.6 GB "libres" | Fase 17 |
| Medidas finas (< 30 %) fijadas a un nodo NUMA (`taskset`) | Sin fijar, copiar a búfer bimodal ~960 frente a ~1270 µs por imagen de 3.9 MB, cambia entre ejecuciones (bel, 2 nodos) | Diario 09-29, E1.9 |
| Con 16 hilos, el obrero de E/S igual que el del prototipo, no más ligero | Offsets calculados antes: 8–15 % más lento (GIL) | Diario 09-29, E1.9 |
| Pool de hilos abierto para la losa de rendija | Crear 64 hilos por rendija: 10–16 % de la losa templada | Diario 09-29, E1.9 |
| Sin `_sp`, un fallo de 4 B cuesta una petición de ~4 KB (~12.5 ms), y el sistema apenas guarda | Contadores FC: 2604 peticiones y ~11 MB por λ–t; el mismo píxel vuelve a fallar tras ~10 k lecturas (~50 MB) con 38 GB libres | Diario 09-29, E1.10 |
| Sin `_sp`, el almacenamiento se satura hacia ~7000–7700 peticiones/s | λ–t en frío con 32/64/128/256 hilos: 670/462/377/367 ms (bel, fijado al nodo 0, A/A 675) | Diario 09-29, E1.10 |
| ~~No fijar 64 hilos de numba (se queda el tamaño por defecto, los núcleos)~~ (2026-09-30: sustituida por la fila siguiente, [journal.md](journal.md) E1.12) | Ganancia en frío 33 % (tarde) o 4 % (noche); más lento en el espectro (27 frente a 20 ms) y en caché (33 frente a 24 ms) | Diario 09-29, E1.10 |
| Hilos por lectura dispersa: uno por petición, hasta 128 en red (16 en local); pool de numba ≥128 | λ–t en frío por filas: 32/64/128 hilos 1.00/0.56/0.42 (A/A 0.81); espectro 64: 0.86; desde la caché del sistema 64: 1.35 | Diario 09-30, E1.12 |
| io_uring no se puede usar en bel | `kernel.io_uring_disabled=2`: `EPERM` sin root | Diario 09-29, E1.10 |
| Sin `_sp`, cada serie se lee con su fila entera (8 KB por imagen) | Primer λ–t 1.009 frente al prototipo (4/8); el vecino (x + 1) 0.10 frente a 17.6 ms (8/8); bel, fijado al nodo 0 | Diario 09-29, E1.13 |
| Bloques de 1 fila, no de 8 | 8 filas (64 KB): primer λ–t 1.339 (1/8) con el almacenamiento rápido; igual con el lento (0.96×) | Diario 09-29, E1.13 |
| El núcleo (estado, planificador, niveles, rangos y) sin Qt no encarece las lecturas | Frente a las mismas lecturas directas: en frío y en pasos dentro del ruido; +0.35 ms por movimiento a un píxel en caché (bel, 6173, fijado al nodo 0) | Diario 09-30, E2.7 |
| Por `ssh -Y` solo llega `pgr` | vispy/gfx: ventana vacía (OpenGL en el servidor); napari igual (2026-09-26) | Fase 11 |
| Puente X11 por defecto en pantalla remota | ~12 frente a ~8.5 imágenes/s; 1.3 frente a 4.8 B/px | F2, 2026-09-25 |
| Lo que escala por X11 es lo repintado | Mismos bytes con 1 o 4 ventanas; 49 ms repintando todo frente a 20 ms solo cruz + 2 paneles | Fase 17 |
| Color por el puente | ×2.4 bytes; dos tintes 1.09 B/px [sin probar en la app] | ESTUDIO_INTERFAZ §5 |
| Nunca forzar repintados | Cruz 118 → 30 ms | Fase 9 |
| Memoria del sistema por ctypes en macOS, no con `sysctl`/`vm_stat` | 14–34 ms → 0.011 ms por consulta; con procesos eran los únicos fotogramas de más de 17 ms durante la reproducción | Diario 09-24 |

**Resultados negativos que no se vuelven a proponer:**
- `memmap`;
- `fadvise`;
- bibliotecas OpenGL (vispy, gfx, napari) por `ssh -Y`: la ventana, vacía. IGLX y VirtualGL no se han medido con
  explorer; lo que hay (2026-10-27): el XQuartz del usuario tiene el GL indirecto apagado (`enable_iglx = 0`,
  arrancado con `-iglx`); en bellatrix, VirtualGL 3.1.2 está instalado pero no sirve a este usuario (por GLX no
  abre `:0`, el de gdm; por EGL, «Could not load EGL functions»); eagle7 tiene GPU (4 Tesla T4) pero ni VirtualGL
  ni servidor X;
- napari como anfitrión;
- matplotlib;
- Dash;
- VNC;
- XQuartz a 16 bits;
- reproducción fija a 20 fps;
- rejilla como objeto propio (peor);
- divergente con centro gris (no ahorra bytes).

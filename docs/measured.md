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
| Por `ssh -Y` solo llega `pgr` | vispy/gfx: ventana vacía (OpenGL en el servidor); napari igual (2026-09-26) | Fase 11 |
| Puente X11 por defecto en pantalla remota | ~12 frente a ~8.5 imágenes/s; 1.3 frente a 4.8 B/px | F2, 2026-09-25 |
| Lo que escala por X11 es lo repintado | Mismos bytes con 1 o 4 ventanas; 49 ms repintando todo frente a 20 ms solo cruz + 2 paneles | Fase 17 |
| Color por el puente | ×2.4 bytes; dos tintes 1.09 B/px [sin probar en la app] | ESTUDIO_INTERFAZ §5 |
| Nunca forzar repintados | Cruz 118 → 30 ms | Fase 9 |
| Memoria del sistema por ctypes en macOS, no con `sysctl`/`vm_stat` | 14–34 ms → 0.011 ms por consulta; con procesos eran los únicos fotogramas de más de 17 ms durante la reproducción | Diario 09-24 |

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

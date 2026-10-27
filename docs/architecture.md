# Arquitectura

Cómo es el código de explorer **hoy**. Se actualiza en el mismo commit que cambia la
arquitectura. El diseño objetivo es el de [plan.md](plan.md) §3 (congelado); aquí solo lo que ya
existe, y lo que difiere del plan, con el porqué.

**Desactualizado:** describe el código del 2026-09-29, antes del visor, y no se ha puesto al día desde entonces. Lo
vigente: las decisiones en [decisions/](decisions/), cada tarea con su evidencia en [roadmap.md](roadmap.md), y el
código.

## Estado (2026-09-29): la orden y la observabilidad; todavía sin visor

```
src/explorer/
├── _name.py        APP_NAME y prefijo de variables de entorno: el nombre en un solo sitio (ADR 0003)
├── _paths.py       cache_dir(): ~/.cache/explorer (XDG), por usuario, nunca junto al código
├── cli.py          la orden `explorer`: subórdenes perezosas; configura obs desde el entorno
├── doctor.py       `explorer doctor`: Python, versiones, entorno, caché, numba, Qt (en un proceso hijo), cubo
├── demo.py         `explorer demo`: lo más completo que haya, sobre un cubo (hoy: doctor)
├── obs/            observabilidad, solo biblioteca estándar (la puede usar cualquier capa)
│   ├── log.py      un logger por capa; consola WARNING, fichero rotado INFO; EXPLORER_LOG por capa
│   ├── spans.py    span()/timed()/counter()/budget()/summary(); aviso con desglose al pasar un presupuesto
│   └── trace.py    EXPLORER_TRACE=t.json: traza Chrome/Perfetto, una fila por hilo
└── testing/
    └── synth.py    juegos sintéticos pequeños: _im.fits con WCS-TAB, _sp.fits y _sp.icube (el prototipo los lee)
```

## Reglas que ya se cumplen

- **Importaciones perezosas:** importar `explorer.cli` no carga Qt, numba, numpy ni astropy
  (hay una prueba de ello). `explorer.obs` solo usa la biblioteca estándar (también probado).
- **Qt se prueba en un proceso aparte** en `doctor`: un Qt que aborta, por ejemplo sin
  `libxcb-cursor` o con otro Qt en `LD_LIBRARY_PATH`, se informa en vez de matar la comprobación.
- **Tramos siempre activados:** cuestan 0.7–1.4 µs cada uno ([journal.md](journal.md),
  2026-09-29).
- **Las pruebas no tocan la caché del usuario:** `tests/conftest.py` da a cada prueba su propia
  caché y un registro sin fichero.

## Diferencias con el plan

- **python-xlib va en las dependencias base, no en un extra** (plan §2): lo necesitaba el puente
  del prototipo. El reescrito no lo usa, pero el contorno de cambio de tamaño que dibuja el servidor X
  (`platform/xoutline.py`, con `platform/xlibauth.py`) sí, con cualquier pantalla X: medido en bellatrix
  (2026-10-27), 37 módulos de `Xlib` cargados con el puente y con el xcb de Qt, ninguno sin pantalla. Se queda en
  las dependencias base.
- **El puente X11 se reescribió, no se trajo partido en módulos** (plan §3.5,
  [ADR 0009](decisions/0009-puente-x11-reescrito.md)): cliente X11 propio y entrada en Qt solo
  por API pública. Directorio `platform/xbridge/` (el plan decía `x11bridge/`). El del
  prototipo, traído tal cual, queda en el historial (merge `a81c4ce`, quitado en `2f4bb2c`).
- **`obs/` es un paquete propio en la raíz del código,** no `core/telemetry.py`: lo usa también
  `data`, que no puede depender de `core` (se añadió a plan §3.8 antes de congelarlo).

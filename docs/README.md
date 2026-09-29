# Documentación de explorer

Todo lo que no es código ni configuración vive aquí; en la raíz solo queda el `README.md`.
Estos ficheros van en español; la aplicación, en inglés ([ADR 0004](decisions/0004-idioma.md)).

| Fichero | Qué es | Cuándo se toca |
|---|---|---|
| [roadmap.md](roadmap.md) | Índice de trabajo: una fila por tarea, con estado y evidencia (commit o medida) | Al abrir o cerrar una tarea |
| [handoff.md](handoff.md) | Dónde lo dejamos, para retomar en otra sesión o máquina | Al final de cada sesión (se reescribe, no crece) |
| [decisions/](decisions/) | Una decisión por fichero (ADR), con su índice | Al decidir; lo revocado se marca, no se borra |
| [architecture.md](architecture.md) | Cómo es el código hoy | En el mismo commit que cambia la arquitectura |
| [measured.md](measured.md) | Las decisiones medidas que explorer conserva, con sus cifras | Solo si una medida nueva las cambia |
| [journal.md](journal.md) | Diario de medidas de explorer | Tras cada medida |
| [plan.md](plan.md) | El diseño inicial | Nunca: congelado el 2026-09-28 |
| [ideas.md](ideas.md) | Lo que quiere el usuario, en sus palabras | El usuario |

Las notas del prototipo (`OVERVIEW.md`, `RESEARCH.md`…) siguen en `docs/` del proyecto, fuera
de este repositorio ([ADR 0002](decisions/0002-notas-del-prototipo.md)).

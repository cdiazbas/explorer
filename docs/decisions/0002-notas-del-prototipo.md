# 0002. Las notas del prototipo se quedan en el proyecto; explorer lleva su resumen

- **Estado:** Vigente
- **Fecha:** 2026-09-28
- **Decide:** el usuario (`docs/plan.md` §9, P3, opción A)

## Contexto

Las notas del prototipo (`OVERVIEW.md`, `RESEARCH.md`, `UI_CRISPEX.md`,
`PROPUESTA_SIGUIENTE_FASE.md`, `ESTUDIO_INTERFAZ.md`, `PLAN_VENTANAS_ENLAZADAS.md`,
`HANDOFF.md`, `WORKFLOW.md`) viven en `docs/` del proyecto, fuera de explorer. La
auditoría del prototipo también está ahí, sin versionar. Algunas notas tienen rutas
personales.

## Opciones

- **A. Se quedan donde están.**
  - explorer las cita por nombre y sección.
  - Lo imprescindible (las decisiones medidas y sus cifras) se copia a
    [docs/measured.md](../measured.md), para que explorer se entienda aunque se clone
    aparte.
- **B. Moverlas o copiarlas a `explorer/docs/`:** hay que revisarlas antes, y dos copias
  acaban divergiendo.

## Decisión

A.

## Consecuencias

- **Si una medida nueva cambia una cifra:** se anota en el [journal.md](../journal.md)
  de explorer y se actualiza `measured.md`. `OVERVIEW.md` sigue siendo el diario del
  prototipo.
- **La auditoría del prototipo:** no se cita desde ningún fichero de explorer. Sus lecciones
  ya están en `docs/plan.md` §1 y §11.

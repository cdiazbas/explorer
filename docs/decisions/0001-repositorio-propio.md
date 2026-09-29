# 0001. explorer es un repositorio git propio

- **Estado:** Vigente
- **Fecha:** 2026-09-28
- **Decide:** el usuario (`docs/plan.md` §9, P2, opción A)

## Contexto

explorer sustituye al prototipo, que vive en la carpeta hermana `prototype/` del mismo
proyecto. El prototipo tiene cosas que no deben entrar en un repositorio versionado:
- rutas personales en notas y resultados;
- logs con palabras que el CI de higiene rechaza;
- `crispex_idl/`, que es código de terceros.

## Opciones

- **A. Repositorio propio en `explorer/`:**
  - historial, CI y publicación independientes;
  - el prototipo se queda fuera, como laboratorio y como referencia de las comparaciones
    (`docs/plan.md` §7.1).
- **B. Un solo repositorio para todo el proyecto:** exige limpiar o excluir el prototipo
  antes del primer commit.

## Decisión

A.

## Consecuencias

- **Enlaces:** explorer no enlaza a ficheros de fuera de su carpeta. Las referencias al
  prototipo y a sus notas se dan por nombre (por ejemplo, "OVERVIEW, Fase 13").
- **Comparaciones:** `tools/golden/export_prototype.py` encuentra el prototipo con una
  ruta configurable (por defecto `../prototype`), no con una fija.
- **Sincronización con bellatrix:** va por `scripts/sync.py` de explorer, independiente de
  `prototype/actualize.py`.
- **Primer commit:** ninguno sin petición expresa del usuario. El CI de higiene
  (ROADMAP E0.5) va antes de cualquier push.

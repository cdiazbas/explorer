# 0003. Nombre provisional: `explorer`, preparado para cambiarlo

- **Estado:** Vigente (provisional: se revisa antes de publicar)
- **Fecha:** 2026-09-28
- **Decide:** el usuario (`docs/plan.md` §9, P1: "ponerle explorer y luego cambiar el nombre de
  todo")

## Contexto

`pyproject.toml` necesita un nombre para empezar (ROADMAP E0.2). El definitivo aún no está
decidido. No se ha comprobado si `explorer` está libre en PyPI.

## Opciones

- **Esperar al nombre definitivo:** bloquea toda la etapa E0.
- **Usar `explorer` ya y dejar el cambio barato.**

## Decisión

`explorer` en los tres sitios (nombre de distribución, orden de consola y paquete de
Python), con estas reglas para que cambiarlo sea mecánico:

1. **Dentro del paquete, solo importaciones relativas** (`from ..data import Dataset`). El
   nombre absoluto solo aparece en:
   - `[project.scripts]`;
   - las pruebas;
   - los contratos de `import-linter`;
   - `tools/`.
2. **Todo lo que ve el usuario sale de una constante**, `APP_NAME` en `src/explorer/_name.py`:
   - carpeta de registros y caché (`~/.cache/<app>/`);
   - organización y aplicación de `QSettings`;
   - prefijo de variables de entorno (`<APP>_LOG`…);
   - título de la ventana;
   - nombre del logger raíz.
3. **No se publica en PyPI** mientras el nombre sea provisional.
4. **Se instala siempre desde la carpeta o desde git** (`uv pip install -e .`,
   `uv tool install ./explorer`). Nunca con el nombre a secas, que podría traer un paquete
   ajeno.

## Consecuencias

- **Renombrar** será mover `src/explorer/`, cambiar `APP_NAME` y las pocas referencias
  absolutas de la regla 1, y pasar `ruff` y `pyright`.
- **Los ajustes y registros ya guardados** con el nombre viejo se pierden al renombrar,
  salvo que ese commit incluya una migración de una sola vez.
- **Antes de publicar**, ROADMAP "P1-final": el nombre definitivo, comprobado en PyPI.

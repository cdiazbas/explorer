# 0006. Comprobaciones en local, mientras no haya CI remoto

- **Estado:** Vigente
- **Fecha:** 2026-09-29
- **Decide:** el usuario (ROADMAP E0.5, "ok") sobre esta propuesta

## Contexto

El repositorio no tiene remoto, así que no hay dónde ejecutar un CI. Las reglas del usuario piden
que lo que nunca debe entrar (ficheros de auditoría, rutas personales, menciones de asistentes o
de coautoría) se compruebe automáticamente, y no dependa de acordarse.

## Decisión

- **`scripts/check.sh`:** todo lo que haría el CI, con un resumen y el número de fallos como
  código de salida:
  - higiene (`scripts/hygiene.py`, sobre los ficheros versionados y todo el historial);
  - `ruff`;
  - contratos entre capas (`lint-imports`);
  - tipos (`mypy`);
  - pruebas, sin pantalla y sin `LD_LIBRARY_PATH` heredado.

  En bellatrix la copia no lleva `.git` y la higiene se salta: se comprueba donde se hacen los
  commits.
- **Ganchos de git** (`scripts/install_hooks.sh`, porque `.git/hooks` no se versiona):
  - `pre-commit`: higiene de lo preparado y `ruff`;
  - `commit-msg`: el asunto `[TAG] una frase` del [ADR 0005](0005-commits.md) y ninguna mención
    prohibida.
- **Las palabras prohibidas se componen a trozos** en el código y en las pruebas, para que el
  guardián no se encuentre a sí mismo en el historial.
- **`mypy` y no `pyright`:** el paquete de `pyright` en PyPI descarga Node.js la primera vez que
  se usa, y en bellatrix eso complica las cosas. `mypy` es Python puro. Se revisa si hace falta
  más rigor en los tipos.
- **Reglas de `ruff` explícitas** (`E W F I B UP RUF100`): los valores por defecto de `ruff`
  cambian entre versiones (la instalada activaba muchas más, incluidas reglas de estilo como
  prohibir `dict(a=1)`). Quedan las que atrapan fallos, no el estilo del código.

## Consecuencias

- **Un commit con una ruta personal o un asunto mal formado se rechaza antes de crearse,** en
  este clon. En un clon nuevo hay que ejecutar `scripts/install_hooks.sh`.
- **Cuando haya remoto,** su CI ejecuta `scripts/check.sh` con `fetch-depth: 0` (el historial
  entero), y este ADR se revisa.

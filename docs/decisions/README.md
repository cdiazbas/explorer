# Decisiones (ADR)

Una decisión por fichero, `NNNN-titulo.md`, numerado en orden y sin reutilizar números.
Una decisión revocada no se borra: se marca **Sustituida por NNNN** y se crea la nueva.

| # | Decisión | Estado | Fecha |
|---|---|---|---|
| [0001](0001-repositorio-propio.md) | explorer es un repositorio git propio | Vigente | 2026-09-28 |
| [0002](0002-notas-del-prototipo.md) | Las notas del prototipo se quedan en el proyecto; explorer lleva su resumen | Vigente | 2026-09-28 |
| [0003](0003-nombre-provisional.md) | Nombre provisional `explorer`, preparado para cambiarlo | Vigente (provisional) | 2026-09-28 |
| [0004](0004-idioma.md) | La aplicación, en inglés; las notas, en español | Vigente | 2026-09-28 |
| [0005](0005-commits.md) | Mensajes de commit: una etiqueta y una frase | Vigente | 2026-09-28 |

## Plantilla

```markdown
# NNNN. Título

- **Estado:** Propuesta | Vigente | Sustituida por NNNN
- **Fecha:** AAAA-MM-DD
- **Decide:** quién

## Contexto
Qué problema hay y qué restricciones.

## Opciones
Cada una con lo que se sabe de ella: medido (cifra y condiciones) o sin probar.

## Decisión
Qué se hace.

## Consecuencias
Qué cambia, qué queda más difícil, qué habría que medir para revisarla.
```

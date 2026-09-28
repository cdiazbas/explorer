# 0005. Mensajes de commit: una etiqueta y una frase

- **Estado:** Vigente
- **Fecha:** 2026-09-28
- **Decide:** el usuario ("una frase con [DEV], [DOC], [ADD], etc.")

## Decisión

**Asunto:** `[TAG] una frase`.
- En inglés ([ADR 0004](0004-idioma.md)), en minúsculas, en imperativo, sin punto final.
- Como mucho 72 caracteres.

**Etiquetas** (conjunto cerrado):

| Etiqueta | Cuándo | Ejemplo |
|---|---|---|
| `[ADD]` | Funcionalidad o módulo nuevo | `[ADD] explorer doctor checks the environment, numba and Qt` |
| `[DEV]` | Cambio en código que ya existe: mejora o reorganización | `[DEV] move the reader threads into data/executors` |
| `[FIX]` | Arreglo de un fallo | `[FIX] apply BSCALE and BZERO when reading FITS cubes` |
| `[PERF]` | Cambio por rendimiento, con la medida | `[PERF] read frames with four parallel preadv calls` |
| `[TEST]` | Solo pruebas o referencias de comparación | `[TEST] compare series with the prototype on synthetic cubes` |
| `[BUILD]` | Entorno, dependencias, scripts, CI | `[BUILD] pin the measured versions in pyproject and uv.lock` |
| `[DOC]` | Solo documentación | `[DOC] record the decision on the package name` |
| `[STYLE]` | Formato o lint, sin cambio de comportamiento | `[STYLE] format with ruff` |

**Reglas:**
1. **Una etiqueta por commit.** Si encajan dos, son dos commits.
2. **Cuerpo opcional**, para el porqué (el qué ya lo dice el diff).
3. **Dos líneas de cierre en `[ADD]`, `[DEV]`, `[FIX]` y `[PERF]`:**

   ```
   Behaviour: unchanged | changes <what>
   Tests: <what proves it>
   ```

   `git log --grep='Behaviour: unchanged'` da los commits que se pueden descartar sin leerlos
   cuando aparece una regresión.
4. **`[PERF]` lleva la cifra:** antes → después, la máquina y las condiciones.
5. **Sin menciones de asistentes de IA ni líneas de coautoría.**
6. **Antes de cada commit**, comprobar que el diff no tiene rutas personales ni esas menciones.
   Cuando exista el CI (ROADMAP E0.5), lo comprueba también sobre todo el historial.
7. **Ningún `push`** sin permiso expreso para ese `push`.

## Consecuencias

- **Etiquetas nuevas:** `[ADD]`, `[FIX]`, `[PERF]`, `[TEST]` y `[BUILD]` amplían las tres de las
  reglas globales del usuario (`[DEV]`, `[STYLE]`, `[DOC]`). En este repositorio manda este ADR.
- **Commits pequeños:** una etapa del ROADMAP son varios commits, y la evidencia de cada tarea
  es su commit.

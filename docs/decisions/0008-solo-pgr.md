# 0008. Una sola superficie de imagen al principio: pyqtgraph (`pgr`)

- **Estado:** Vigente
- **Fecha:** 2026-09-30
- **Decide:** el usuario ("ok", P6 del [roadmap](../roadmap.md)), sobre esta propuesta

## Contexto

El prototipo probó varias superficies para la imagen: `pgr`, `pg`, vispy, gfx, fastplotlib y
matplotlib. explorer empieza su ventana en E3 y tiene que elegir cuáles trae.

## Opciones

- **Solo `pgr` al principio.** Es la única medida que funciona por `ssh -Y`: vispy y gfx dejaban la
  ventana vacía por X11 remoto, y el prototipo pasaba a `pgr` solo. La reducción a u8 de los píxeles
  a la vista ya está en `explorer.data.kernels`, idéntica a la del prototipo.
- **También vispy o gfx en local.** Sin medida que diga que dibujan más rápido que `pgr` en el caso
  que importa, el cursor y los pasos en t: hoy el cuello son las lecturas, no el dibujo. Traerlas
  multiplica las ramas por superficie en las vistas.

## Decisión

Solo `pgr` en E3–E5. La vista de imagen se escribe detrás de una interfaz pequeña, para que otra
superficie pueda entrar después sin tocar el núcleo.

## Consecuencias

- Menos código y una sola ruta que medir frente al prototipo.
- **Revisar si** una medida muestra que en local el dibujo de `pgr` limita el cursor o la
  reproducción. Entonces se prueba otra superficie en local, con la misma interfaz.

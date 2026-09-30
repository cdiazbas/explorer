# 0007. `explorer.core` sin Qt

- **Estado:** Vigente
- **Fecha:** 2026-09-30
- **Decide:** el usuario ("vamos con A"), sobre esta propuesta. Cambia el §3.3 de
  [plan.md](../plan.md), que ponía `Store(QObject)` con `Signal`.

## Contexto

`explorer.core` guarda el estado del visor y decide qué se lee y qué se muestra. Los criterios de
salida de E2 son pruebas de orden:
- un resultado viejo nunca llega a la pantalla;
- una ráfaga de cambios da un solo aviso;
- nada se lee sobre el relleno.

`testing.Driver` usa el core, y el contrato de capas de E0 prohíbe que `explorer.testing` importe
Qt.

## Opciones

- **A. Core sin Qt.**
  - `Store` avisa a funciones de Python.
  - Se le inyecta cuándo procesar lo pendiente: la interfaz pasa un `QTimer` de 0 ms; las pruebas,
    un `pump()` manual.
  - Se le inyecta cómo llevar un resultado al hilo principal: la interfaz, con un adaptador de Qt;
    las pruebas, con una cola.
  - Las pruebas de orden son deterministas, sin `QCoreApplication` y en milisegundos.
  - Coste: el adaptador del hilo principal en `ui/` (unas 20 líneas), con su propia prueba.
- **B. Core con `QtCore`, como decía el plan.**
  - Las señales llevan los resultados al hilo principal solas, como el `Result` del prototipo.
  - Las pruebas necesitan girar el bucle de eventos con esperas, y el orden depende de los tiempos.
  - Obliga a relajar el contrato de `explorer.testing`.

Para el usuario no cambia nada: avisar a una función o emitir una señal cuesta microsegundos en
los dos casos (no medido aquí; es la escala de una llamada de Python).

## Decisión

A:
- `explorer.core` no importa PySide6, pyqtgraph ni Xlib. Un contrato de `lint-imports` lo
  comprueba.
- El momento de procesar y el paso al hilo principal se inyectan.

## Consecuencias

- **Las pruebas del core** se escriben con un bucle manual: `Driver.pump()` y
  `Driver.wait_idle()` sobre los futuros.
- **E3 añade el adaptador de Qt** (`QTimer` de 0 ms e invocación en el hilo principal) y una prueba
  de que los resultados que llegan de otros hilos se aplican en el principal.
- **El core puede usarse sin Qt:** desde scripts, o desde un `Dataset` remoto.
- **Revisar si** el adaptador resulta frágil (resultados aplicados fuera del hilo principal) o si
  el coste de los avisos se nota en la medida de E2.7.

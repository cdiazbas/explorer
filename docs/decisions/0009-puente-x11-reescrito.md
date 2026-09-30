# 0009. El puente X11, reescrito (P4, opción B)

- **Estado:** Propuesta
- **Fecha:** 2026-09-30
- **Decide:** el usuario, tras comparar esta opción con la otra (traer el puente del prototipo tal
  cual, partido en módulos)

## Contexto

Por `ssh -Y`, el xcb de Qt tarda 2.3–2.5 s solo en arrancar (unas 150 idas y vueltas de 16 ms
hasta el XQuartz del usuario). El puente del prototipo lo evita: Qt dibuja en `offscreen` y el
puente enseña las ventanas por X11 con python-xlib. Funciona, pero:
- mete la entrada en Qt por símbolos privados (`QWindowSystemInterface` por ctypes), lo que ata
  PySide6 a una versión exacta (6.11.2);
- solo dpr = 1, sin arrastrar y soltar, sin IME, portapapeles sin INCR;
- creció como un fichero de 1575 líneas de parches de auditoría.

P4 del roadmap pregunta si traerlo tal cual o reescribirlo. Esta es la reescritura, junto al del
prototipo para poder compararlos: `--x11 bridge2` o `EXPLORER_X11=bridge2`. `auto` no la elige.

## Opciones

- **A. Traer el puente del prototipo, partido en módulos.** Lo hace otro trabajo en paralelo;
  sus cifras son las del prototipo.
- **B. Reescribirlo** (este ADR), con lo que el prototipo aprendió pero sin su código:
  `platform/xbridge2/`.

## Lo que hace B

**Módulos:**

| Módulo | Qué |
|---|---|
| `xproto.py` | Cliente X11 propio: conexión, cookie, peticiones, y respuestas, eventos y errores en un hilo lector |
| `transport.py` + `kernels.py` | Píxeles: teselas 32×32, gris a 1 B/px por RENDER, doble búfer, codificador numba; hilo y conexión propios |
| `windows.py` | Ventanas X de las ventanas de Qt: ICCCM/EWMH, geometría, estado, forma, cursor, activación |
| `qtinput.py` | La entrada X en Qt, solo con API pública |
| `keys.py` | Teclado X a teclas de Qt (sin Qt) |
| `clipboard.py` | CLIPBOARD con INCR en los dos sentidos |
| `bridge.py` | Las dos etapas (antes y después de la `QApplication`) y el flujo de eventos |

**La entrada, sin símbolos privados.** Los eventos X llegan a Qt como `QMouseEvent`,
`QWheelEvent` y `QKeyEvent` enviados (`sendEvent`) al `QWindow` de la ventana. La capa de widgets
de Qt hace con ellos casi todo lo que hacía la puerta privada, medido en `offscreen` (Qt 6.11.2):
- el widget bajo el puntero;
- el agarre implícito al arrastrar;
- Enter, Leave y Hover entre widgets;
- foco por clic;
- menú contextual;
- los popups (un clic fuera los cierra);
- las ventanas modales;
- los atajos (`QShortcut`), el texto, la autorrepetición y los códigos nativos de tecla;
- los widgets reciben el ratón como espontáneo: los tooltips salen solos tras un reposo.

Lo que Qt no hace con esos eventos lo hace B, con API pública:
- **Doble clic:** con las horas del servidor X. Los widgets ven pulsar, soltar, doble clic,
  soltar, como con xcb. El widget de esa segunda pulsación agarra el ratón (`grabMouse`) hasta
  soltar: sin eso, Qt tiraba el soltar y pyqtgraph nunca emitía el doble clic.
- **Rueda:** se sube de widget en widget hasta que uno la acepta. Qt no propaga una rueda no
  espontánea: el `QLineEdit` de un `QSpinBox` se la quedaba.
- **Posición del cursor:** `QCursor.setPos` al entrar y salir, al pulsar y soltar, y en reposo.
  En `offscreen` esa llamada produce además el Enter y Leave de la ventana.
- **Activación:** la ventana activa de Qt sigue al foco X (`requestActivate`). Sin foco X en la
  aplicación, se activa una `QWindow` sin widgets, secundaria de la última activa, para que no
  quede ninguna ventana de widgets activa sin impedir que la aplicación termine.

**Lo que no se puede por API pública,** con prueba (`tests/unit/test_xbridge2_input.py`):
- `QGuiApplication.keyboardModifiers()` sigue al ratón y a las pulsaciones de tecla, pero al
  soltar una tecla modificadora sola queda desfasado hasta el siguiente evento. Con xcb se
  limpia.
- Sin IME.
- Sin arrastrar y soltar entre aplicaciones.

**El foco al aparecer la ventana (E6.1):**
- Sin gestor de ventanas (Xvfb), B da el foco X a la ventana en cuanto es visible: la primera
  tecla llega sin clic (probado).
- Con gestor, B pide la activación por `_NET_ACTIVE_WINDOW` en cuanto la ventana se mapea, con
  una hora del servidor y `_NET_WM_USER_TIME`. También declara `WM_TAKE_FOCUS` y lo atiende, y
  responde a `_NET_WM_PING`.
- Con metacity en el mismo Xvfb (`tests/xvfb/test_bridge2_wm.py`, 3 de 3 ejecuciones), la ventana
  toma el foco X y es la activa aunque una "terminal" acabe de recibir un clic y una tecla. La
  primera tecla llega al visor.
- En esas pruebas, además:
  - el marco del gestor;
  - mover desde el gestor;
  - maximizar y restaurar desde el gestor;
  - minimizar desde Qt (Ctrl+M) y restaurar desde la barra de tareas;
  - el panel encima de su ventana;
  - el botón de cerrar con la aplicación inactiva: sale con 0.
- Si en XQuartz el Mac sigue sin traer XQuartz al frente, eso es cosa de macOS: está fuera del
  alcance de X. Lo comprueba el usuario.

**El estado iconificado se lee de `WM_STATE`, no de Map/Unmap** (lo que hacía el prototipo):
- metacity desmapea y vuelve a mapear la ventana al cambiarle el marco al maximizar;
- leído de Map/Unmap, el visor se daba por minimizado y Qt escondía la ventana.

Visto con las pruebas de metacity. También se ignoran los Show y Hide espontáneos de Qt, que llegan
al minimizar y restaurar.

**Arranque y bloqueos:**
- Todo lo que el puente pregunta al servidor al empezar (átomos, extensiones, teclado,
  monitores, puntero) sale junto: tres idas y vueltas antes de Qt. El prototipo hacía decenas,
  una por átomo.
- La conexión de imágenes se abre en su hilo mientras Qt arranca.
- Nada sondea cada 4 ms: los eventos X despiertan a la interfaz uno a uno, así que un menú con
  su propio bucle de eventos (el cuelgue de F45) sigue recibiéndolos. Un `Expose` se repinta
  desde el pixmap del servidor, sin volver a enviar píxeles.

## Medidas

bellatrix, cubo de Stokes 6173, ventana 1400×900. Fijado al nodo NUMA 0, bajo el cerrojo
compartido, 4 rondas ABBA. Los dos puentes muestran la misma ventana de explorer, cada uno en su
proceso (`bench/bridge_vs_prototype.py`). Otra conexión X relee los píxeles hasta que el
servidor tiene los de Qt.

| Medida | Xvfb directo, 1.ª serie: prototipo → B (pareado) | 2.ª serie (pareado) | Enlace emulado*: prototipo → B (pareado) |
|---|---|---|---|
| Primera imagen en el servidor X | 2.005 → 1.935 s (0.967, 4/4) | 2.123 → 2.010 s (0.947, 4/4) | 2.933 → 2.051 s (0.698, 4/4) |
| Paso en t, hasta el servidor | 30.2 → 29.9 ms (0.988, 3/4) | 29.9 → 29.8 ms (1.022, 1/4) | 76.4 → 63.9 ms (0.843, 4/4) |
| Paso en λ | 26.8 → 27.3 ms (1.056, 1/4) | 28.8 → 24.5 ms (0.883, 4/4) | 75.1 → 62.2 ms (0.828, 4/4) |
| Cambio de Stokes | 22.4 → 23.0 ms (1.038, 2/4) | 23.2 → 20.7 ms (0.898, 2/4) | 71.3 → 58.0 ms (0.820, 4/4) |
| Bytes por paso por el enlace | — | — | 758.5 → 758.6 kB (1.000) |

\* `bench/xlink.py`: 8 ms por sentido (16 ms de ida y vuelta) y 25 MB/s de subida, como el
`ssh -Y` al XQuartz del usuario (14–16 ms, 17–29 MB/s).

**Lectura:**
- En Xvfb local (sin latencia) empatan en los pasos: las dos series dan el signo cambiado. La
  carga de la máquina subió a 20–26 al final de las dos, por trabajos de otros.
- Con latencia, B gana en todo con los mismos bytes: 0.9 s menos hasta la primera imagen y
  13 ms menos por paso.
- Con el enlace emulado, un paso de B está en el mínimo físico: Qt (~18 ms) + captura y
  comparación (~5 ms) + 758 kB a 25 MB/s (30 ms) + 8 ms de ida.
- Menos bytes no se pueden sin compresión, que X11 no tiene: la imagen ya va a 1 B/px.

## Decisión (propuesta)

B, si la comprobación del usuario por `ssh -Y` (foco, menús, portapapeles, aspecto) no encuentra
algo que A haga y B no. Entonces:
- se quita la versión exacta de PySide6 que exigía el puente (`pyproject.toml`);
- `auto` elige B;
- el nombre `bridge2` desaparece.

## Consecuencias

- **PySide6 ya no queda atado a una versión por el puente:** B usa API pública de Qt 6 y su propio
  cliente X11. python-xlib queda en las pruebas, como cliente independiente.
- **Queda por hacer:**
  - dpr > 1 (B, como el prototipo, trabaja a dpr = 1);
  - la selección PRIMARY;
  - arrastrar y soltar;
  - IME.
- **Encontrado de paso, no es del puente:** en explorer un clic derecho sobre la imagen abre el
  menú de pyqtgraph. El prototipo lo apagaba (`setMenuEnabled(False)`, app/viewer.py:1023–1028).

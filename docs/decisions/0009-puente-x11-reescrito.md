# 0009. El puente X11, reescrito (P4, opción B)

- **Estado:** Vigente
- **Fecha:** 2026-09-30
- **Decide:** el usuario, 2026-09-30, tras comparar esta opción con la otra (traer el puente del
  prototipo tal cual, partido en módulos) en velocidad y en la suite de conformidad del prototipo

## Contexto

Por `ssh -Y`, el xcb de Qt tarda 2.3–2.5 s solo en arrancar (unas 150 idas y vueltas de 16 ms
hasta el XQuartz del usuario). El puente del prototipo lo evita: Qt dibuja en `offscreen` y el
puente enseña las ventanas por X11 con python-xlib. Funciona, pero:
- mete la entrada en Qt por símbolos privados (`QWindowSystemInterface` por ctypes), lo que ata
  PySide6 a una versión exacta (6.11.2);
- solo dpr = 1, sin arrastrar y soltar, sin IME, portapapeles sin INCR;
- creció como un fichero de 1575 líneas de parches de auditoría.

P4 del roadmap preguntaba si traerlo tal cual o reescribirlo. Esta es la reescritura. Se escribió
junto al del prototipo para compararlos (`--x11 bridge2` mientras duró la comparación).

## Opciones

- **A. Traer el puente del prototipo, partido en módulos.** Lo hace otro trabajo en paralelo;
  sus cifras son las del prototipo.
- **B. Reescribirlo** (este ADR), con lo que el prototipo aprendió pero sin su código:
  `platform/xbridge/` (durante la comparación, `platform/xbridge2/`).

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

**Lo que no se puede por API pública,** con prueba (`tests/unit/test_xbridge_input.py`):
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
- Con metacity en el mismo Xvfb (`tests/xvfb/test_bridge_wm.py`, 3 de 3 ejecuciones), la ventana
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

## Comparación final (2026-09-30)

**Velocidad, las tres formas de llevar la ventana.** bellatrix, cubo de Stokes 6173, ventana
1400×900, Xvfb privado tras el enlace emulado (`bench/xlink.py`: 8 ms por sentido, 25 MB/s).
Fijado al nodo NUMA 0, bajo el cerrojo, carga 0.5 al empezar. Una ejecución de calentamiento por
variante; después 6 rondas, una por cada orden de las tres. Otra conexión X relee los píxeles
hasta que el servidor tiene los de Qt. Xcb nativo con `QT_XCB_NO_MITSHM=1`: con el Xvfb en la
misma máquina, Qt usaba memoria compartida y se saltaba el enlace, cosa que por `ssh` no puede
pasar (sin la variable, se quedaba colgado en la primera imagen). Mediana de las rondas y, entre
paréntesis, la razón pareada B / A y en cuántas rondas B es más rápido. A es el puente del
prototipo traído tal cual; B, este, con las correcciones de `03bcbb1` (las dos posteriores tocan solo la entrada, que esta
medida no ejercita).

| Medida | A | B | xcb nativo |
|---|---|---|---|
| Primera imagen en el servidor X, desde que arranca el proceso | 2.98 s | 2.02 s (0.68, 6/6) | 4.93 s |
| Paso en t | 77.0 ms | 64.7 ms (0.84, 5/6) | 229.5 ms |
| Paso en λ | 74.8 ms | 63.5 ms (0.84, 6/6) | 229.3 ms |
| Cambio de Stokes | 69.8 ms | 58.9 ms (0.85, 6/6) | 225.5 ms |
| Bytes por paso por el enlace | 758 kB | 758 kB | 3107 kB |

La ventaja de B al arrancar es sobre todo la conexión: A tarda ~1.2 s en hablar con X por
python-xlib; B, ~0.25 s. Una serie anterior, con B sin corregir, dio lo mismo (0.71 y
0.83–0.87).

**Conformidad: la suite del prototipo** (`app/conformance.py`, 147 pasos de entrada X real por
XTEST, que compara lo que recibe cada widget y el estado en que queda el visor). Se corrió sobre
el visor del prototipo sin cambiarlo, con xcb, con A y con B. B entró por un adaptador de ~150
líneas fuera del repositorio que traduce dos nombres: el `BridgeMover` de la barra de título (el
`QtMover` del prototipo, el mismo que usa xcb) y el atributo de la forma (`_crispex_shape` →
`x11_shape`). Xvfb privado 3840×1080 sin gestor de ventanas; dos rondas por variante. Una
diferencia cuenta si sale en las dos rondas y no en dos ejecuciones del mismo modo (ruido:
`play_button`, `resize_top`, `spin_hold_arrow`).

| | A | B antes | B ahora |
|---|---|---|---|
| Pasos con el estado final distinto del de xcb | 2 | 51 | 2 |
| Excepciones durante la suite | 0 | 33 | 0 |
| Imagen del cursor distinta de xcb (aceptado para A por el prototipo) | 82 pasos | 78 | 73 |
| Ventana activa tras arrastrar distinta de xcb (ídem) | 49 pasos | 52 | 51 |

- Común a A y B: el portapapeles desde otro cliente X llega con los dos puentes, no con xcb
  (`clipboard_from_x`).
- Solo A: arrastrar un deslizador fuera de la ventana (`slider_drag_outside`).
- Solo B: tras los pasos del separador, la cruz del cursor queda a 1 px (`separator_grab_
  horizontal`). Xcb entrega al `QWindow` los mismos movimientos que B (medido); la diferencia
  nace al pasarlos Qt a los widgets. Sin explicar.

**Lo que la suite encontró en B, y su arreglo** (cada causa, trazada antes de tocar nada):

| Síntoma | Causa | Commit |
|---|---|---|
| Redimensionar desde una esquina | B no aplicaba las esquinas redondeadas: `offscreen` no guarda máscaras y la barra de título deja la región en un atributo | `03bcbb1` |
| La cruz en otro píxel tras arrastrar | `offscreen` contesta cada `QCursor.setPos` con un movimiento sintético que xcb nunca manda | `03bcbb1` |
| Un panel dejaba de recibir el ratón | un doble clic que acopla el panel dejaba su `grabMouse()`: el soltar iba a una ventana ya desmapeada | `03bcbb1` |
| La lista de un combo seguía abierta al irse el foco X | con un popup abierto, B no avisaba a Qt | `03bcbb1`, `89a7ee6` (Linux) |
| Excepción al subir un panel por encima del borde | `WM_NORMAL_HINTS` con x, y negativas empaquetadas sin signo | `03bcbb1` |
| La barra de título seguía resaltada al restaurar | la ventana se va de debajo del puntero quieto y `setPos` al mismo punto no hace nada | `116a384` |

## Decisión

B. Hecho el 2026-09-30:
- `auto` elige el puente por `ssh`; `--x11 bridge` es B; el nombre `bridge2` desaparece
  (`594d371`, `785521b`);
- A se quita; queda en el historial (merge `736099e`) y revertir `594d371` lo devuelve.

Pendiente:
- la comprobación del usuario por `ssh -Y` en XQuartz, que la suite (Xvfb sin gestor) no cubre;
- quitar la versión exacta de PySide6 (`pyproject.toml`), que exigía A: se decide aparte, porque
  cambia el lock;
- python-xlib, a un extra de desarrollo (lo mismo).

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

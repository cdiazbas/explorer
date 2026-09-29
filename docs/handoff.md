# Traspaso

Dónde lo dejamos, para retomar en otra sesión o en otra máquina. Se reescribe al final de
cada sesión; no crece.

## 2026-09-29

- **Hecho (2026-09-28):**
  - `explorer/` con su propio git; decisiones en `docs/decisions/` (ADR 0001–0005: repositorio
    propio, notas del prototipo, nombre provisional, idioma, commits);
  - la orden `explorer` (`--version`, `doctor`, `demo`) y `scripts/` (`setup_env.sh`,
    `run.sh`, `demo.sh`, `sync.py`);
  - funciona en el Mac (uv) y en bellatrix (conda + pip); 12 pruebas en verde en los dos.
- **Hecho (2026-09-29):**
  - las notas, movidas a `docs/` con un índice (`docs/README.md`); en la raíz solo queda el
    `README.md`;
  - `sync.py` se para si no hay conexión maestra de ssh.
- **Regla (memoria del usuario):** antes de cualquier orden remota, `ssh -O check`. Ante
  cualquier problema de conexión: parar, no reintentar, y esperar a que el usuario diga que
  sigue. Un `push` con la maestra caducada dejó un aviso de doble factor colgado, y después el
  usuario no pudo conectar durante un rato.
- **E0.4 hecha:** `obs/` (registro por capa, tramos con presupuestos, trazas); cada tramo cuesta
  0.7 µs (Mac) y 1.4 µs (bellatrix). Las pruebas ya no escriben en la caché real (`9062dcc`, `b57cbd2`).
- **E0.5 hecha:** `scripts/check.sh` (higiene, `ruff`, capas, `mypy`, pruebas) y ganchos de git
  (`scripts/install_hooks.sh`; en un clon nuevo hay que ejecutarlo). `2444f50`.
- **E0.8 hecha:** línea base del prototipo en bellatrix y en el Mac ([journal.md](journal.md)).
  **Regla:** explorer no puede ser más lento que ella, y la meta es mejorarla (`a528015`).
- **Lanzar medidas largas en bellatrix:** `ssh host 'nohup bash -c "cd … && orden" > log 2>&1 < /dev/null &'`.
  Con `cd … && nohup orden > log &`, la subshell conserva la salida de la sesión y el `ssh` no
  vuelve hasta que termina la medida (2026-09-29).
- **Siguiente:** E0.6 (`_sp`, `icube` y WCS-TAB en el sintético) y E0.7 (referencias del
  prototipo). Pequeña: E0.11 (avisar de copias huérfanas en bellatrix).
- **Del prototipo, fuera de explorer:**
  - `prototype/actualize.py` sigue apuntando a los `.md` de la raíz, que ahora están en
    `docs/` del proyecto;
  - las teclas de Stokes del prototipo quedaron dentro del bloque del eje t (`_key_table`).

  Los dos son del prototipo y los decide el usuario.

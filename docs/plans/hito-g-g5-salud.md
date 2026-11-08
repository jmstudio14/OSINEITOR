# Plan G5 · Panel de salud (Hito G)

> **Estado (07-11-2026):** hecho (✅ en el ROADMAP). Las casillas de abajo son la lista de
> ejecución original y no se marcaron.

> **Para quien lo ejecute:** hazlo tarea a tarea (`superpowers:executing-plans` o
> `superpowers:subagent-driven-development`). Los pasos usan casillas `- [ ]`.

**Objetivo:** una vista que muestra el veredicto de cada módulo según `doctor --json`, sin bloquear
la ventana.

**Arquitectura:** `CliApi.doctor()` ya existe y es síncrona; la vista la llama con `run_in_thread`
y rellena un `QAbstractTableModel`. Sin lógica de negocio nueva: solo presentación.

**Pila:** PySide6, pytest-qt (`QT_QPA_PLATFORM=offscreen`).

**Spec:** [`ROADMAP.md`](../../ROADMAP.md) (Hito G, fila G5) y [`docs/GUI.md`](../GUI.md)
(«Salud de los módulos»).

## Restricciones globales

- Qt solo en `osineitor_gui/ui/` (lo impone `tests/gui/test_rules.py`); textos con `self.tr(...)`.
- Llamadas a la CLI siempre fuera del hilo de la interfaz (`ui/worker.py::run_in_thread`).
- Veredictos del contrato (`docs/CLI_CONTRACT.md`): `ok`, `empty`, `fail`, `skipped`, `unchecked`.
  Una fila con un veredicto desconocido se muestra tal cual, sin romper la tabla (el contrato solo
  admite cambios aditivos).
- `CliApi.doctor()` devuelve código 3 como éxito (que un módulo falle no es un error de la CLI).
- Esta tarea es solo pasivo: `--active` llega con G7.
- Está lista cuando `ruff check`, `ruff format --check` y `python -m pytest -q` pasan.

## Foco de revisión

- `doctor` tarda minutos: el diálogo debe poder cerrarse mientras corre sin colgarse ni lanzar
  error al llegar el resultado (el relé de `worker.py` descarta lo de un padre ya destruido).
- Pulsar «Comprobar» dos veces seguidas no lanza dos `doctor`: el botón se desactiva mientras corre.
- Lista vacía (`[]`): la tabla queda vacía y el texto de estado lo dice, no «error».
- `CliError` (CLI caída o sin JSON): se ve en el diálogo, no en un `QMessageBox` modal que bloquee.
- Veredicto desconocido o `detail` vacío o `None`: no rompe el modelo.

## Estructura de ficheros

| Fichero | Responsabilidad |
|---|---|
| `src/osineitor_gui/ui/modules_view.py` (nuevo) | `HealthModel` y `HealthDialog` |
| `src/osineitor_gui/ui/main_window.py` | menú Herramientas ▸ Salud de los módulos |
| `tests/gui/test_modules_view.py` (nuevo) | modelo y diálogo |
| `tests/gui/test_main_window.py` | la acción abre el diálogo |

---

### Tarea 1: `HealthModel`

**Interfaces**
- Produce: `HealthModel(QAbstractTableModel)` con `set_rows(rows: list[dict]) -> None`, columnas
  `Módulo, Veredicto, Detalle, Tiempo, Peticiones` y `VERDICT_LABELS: dict[str, str]`
  (traducidos con `QCoreApplication.translate`).

- [ ] **Paso 1: tests** en `tests/gui/test_modules_view.py`:
  `test_model_shows_one_row_per_module` (3 filas, `rowCount() == 3`, columna 0 = `module`),
  `test_unknown_verdict_is_shown_as_is` (veredicto `"raro"` → texto `"raro"`),
  `test_missing_detail_is_empty_text` (`detail=None` → `""`),
  `test_fail_and_ok_have_distinct_foreground` (`ForegroundRole` de `fail` ≠ el de `ok`),
  `test_duration_is_formatted_in_ms` (`duration_ms=1234` → `"1234 ms"`).
- [ ] **Paso 2:** `python -m pytest tests/gui/test_modules_view.py -q` → falla (módulo inexistente).
- [ ] **Paso 3:** implementa `HealthModel` en `ui/modules_view.py`. Colores como los de
  `ModuleActivityModel` en `ui/models.py` (reutiliza su criterio de color, no inventes otro).
- [ ] **Paso 4:** mismo comando → pasa.
- [ ] **Paso 5:** commit `Añade el modelo de la tabla de salud de los módulos (G5)`.

### Tarea 2: `HealthDialog`

**Interfaces**
- Consume: `CliApi.doctor(modules=(), *, active=False, timeout=300.0)`, `run_in_thread`.
- Produce: `HealthDialog(api: CliApi, parent: QWidget | None = None)` con `table`, `run_button`,
  `status` (QLabel), `busy` (QProgressBar con rango 0–0) y `check() -> None`.

- [ ] **Paso 1: tests** (con `api` falso que devuelve filas fijas, sin lanzar la CLI):
  `test_check_fills_the_table` (tras `qtbot.waitUntil`, 3 filas y `run_button` habilitado),
  `test_button_is_disabled_while_running` (tras `check()`, `run_button.isEnabled()` es `False`),
  `test_second_check_while_running_is_ignored` (`api.doctor` se llama una vez),
  `test_cli_error_is_shown_inline` (`CliError("boom")` → `status.text()` contiene `boom`, el botón
  vuelve a estar activo y no se abre ningún `QMessageBox`),
  `test_empty_result_says_so` (`[]` → `status.text()` no vacío y sin la palabra «error»),
  `test_closing_while_running_does_not_crash` (cerrar el diálogo, esperar al hilo con
  `QThreadPool.globalInstance().waitForDone()`, sin excepción).
- [ ] **Paso 2:** ejecuta → falla.
- [ ] **Paso 3:** implementa `HealthDialog`: no modal, tamaño 720×420, `check()` desactiva el botón,
  muestra `busy` y llama a `run_in_thread(lambda: api.doctor(), self._done, self._failed, self)`.
  El diálogo no arranca solo: el usuario pulsa «Comprobar».
- [ ] **Paso 4:** ejecuta → pasa.
- [ ] **Paso 5:** prueba de integración con la CLI real de `tests/gui/fakecli.py`
  (`use_modules(monkeypatch, "fast,bad")`): `test_dialog_against_the_real_cli` comprueba que las
  filas son los nombres `{"fast", "bad"}`; no se afirman los veredictos (dependen de `canary`).
- [ ] **Paso 6:** commit `Añade el diálogo de salud de los módulos (G5)`.

### Tarea 3: menú Herramientas

**Interfaces**
- Consume: `HealthDialog`. Produce: `MainWindow.action_health` y el menú «Herramientas».

- [ ] **Paso 1: test** en `tests/gui/test_main_window.py`: `test_health_action_opens_the_dialog`
  (con CLI: `action_health.trigger()` crea un `HealthDialog` visible; sin CLI la acción está
  deshabilitada).
- [ ] **Paso 2:** ejecuta → falla.
- [ ] **Paso 3:** en `_build_actions` crea `action_health` (deshabilitada si `self.cli is None`) y
  en `_build_menus` añade el menú `&Herramientas` entre Ver y Ayuda. Guarda el diálogo en
  `self._health` y reutilízalo si ya existe (no abras uno por clic).
- [ ] **Paso 4:** ejecuta `python -m pytest tests/gui -q` → todo en verde.
- [ ] **Paso 5:** documentación: marca G5 como ✅ en `ROADMAP.md` (fila y «Estado»), actualiza
  `docs/GUI.md` (tabla de partes, «Hecho (G5)» y «Pendiente») y añade la línea a `CHANGELOG.md`.
  Corrige `CLAUDE.md` (sección GUI: «faltan las vistas de G4 a G7» → ya quedó desactualizada tras
  G4; ajústala al estado real).
- [ ] **Paso 6:** `ruff check . && ruff format --check . && python -m pytest -q` → verde.
- [ ] **Paso 7:** commit `Añade el panel de salud de los módulos (G5)`.

## Qué no cubre

- `doctor --active` (G7). Cancelar un `doctor` en curso: `CliApi.run` es síncrona y no admite
  cancelación; cerrar el diálogo deja que el proceso termine solo (máx. 300 s por el `timeout`).
- Verlo en Windows con pantalla: lo cubre G9.

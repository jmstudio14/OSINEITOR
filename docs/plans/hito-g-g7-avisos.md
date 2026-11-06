# Plan G7 · Avisos legales y `--active` (Hito G)

> **Para quien lo ejecute:** hazlo tarea a tarea (`superpowers:executing-plans` o
> `superpowers:subagent-driven-development`). Los pasos usan casillas `- [ ]`.

**Objetivo:** aviso legal obligatorio en el primer arranque y confirmación explícita antes de
activar módulos activos o redes privadas, con el selector de módulos del diálogo «Nuevo scan».

**Arquitectura:** las reglas ya viven en `ScanRequest` (`ConfirmationRequired`) y los textos en
`osineitor_gui/legal.py`. Este plan solo añade diálogos: la vista pregunta y marca `confirm_*`;
nunca decide.

**Pila:** PySide6, pytest-qt.

**Spec:** [`ROADMAP.md`](../../ROADMAP.md) (Hito G, fila G7) y [`docs/GUI.md`](../GUI.md)
(«Primer arranque», «Diálogo Nuevo scan»; criterio de aceptación 4).

## Restricciones globales

- La regla de seguridad la impone `ScanRequest.validate()`; ninguna vista pone `confirm_active` o
  `confirm_private` a `True` sin que el usuario haya pulsado el botón de confirmar.
- El botón por defecto de toda confirmación de riesgo es **Cancelar** (Enter no confirma).
- Rechazar el aviso del primer arranque cierra la aplicación sin crear la ventana ni lanzar la CLI.
- `LEGAL_VERSION` sube → se vuelve a pedir (`GuiSettings.needs_legal`).
- Textos de `osineitor_gui/legal.py` tal cual; en `ui/` con `self.tr(...)`.
- Está lista cuando `ruff check`, `ruff format --check` y `python -m pytest -q` pasan.

## Foco de revisión

- Cerrar el aviso con Esc o con la X cuenta como rechazo, no como aceptación.
- Aceptar y que el guardado de `settings.json` falle (disco de solo lectura): la aplicación sigue,
  pero volverá a preguntar; no se ignora el error en silencio (se avisa en la barra de estado).
- Marcar «activos», aceptar el diálogo de riesgo, **desmarcar** y volver a aceptar el scan:
  `active` es `False` y `confirm_active` no queda a `True` de la vez anterior.
- Marcar «activos», rechazar la confirmación: la casilla se desmarca sola y no se lanza nada.
- Selección explícita de un módulo activo sin la casilla general de activos: el diálogo exige la
  casilla (los módulos activos están deshabilitados hasta confirmar).
- Módulo que requiere key y no la tiene: visible pero deshabilitado, con el motivo en el tooltip,
  y no se puede seleccionar con teclado.
- Propósito con comillas, emojis, `--active` o un guion inicial: viaja como un único argumento y
  nunca se interpreta como opción (`--purpose` lleva el valor pegado en `argv`, no por shell).
- Catálogo de módulos que no llega (CLI caída): el diálogo sigue funcionando sin selector (scan con
  los módulos por defecto) y lo dice.

## Estructura de ficheros

| Fichero | Responsabilidad |
|---|---|
| `src/osineitor_gui/ui/legal_dialog.py` | modo «aceptación obligatoria» |
| `src/osineitor_gui/ui/risk_dialog.py` (nuevo) | `confirm_active(parent)`, `confirm_private(parent)` |
| `src/osineitor_gui/ui/new_scan_dialog.py` | selector de módulos, casillas de riesgo y propósito |
| `src/osineitor_gui/scan_request.py` | campo `purpose` |
| `src/osineitor_gui/ui/main_window.py` | carga el catálogo y lo pasa al diálogo |
| `src/osineitor_gui/app.py` | puerta del primer arranque |
| `tests/gui/test_legal_dialog.py`, `test_risk_dialog.py` (nuevos), `test_new_scan_dialog.py`, `test_app.py` (nuevo) | pruebas |

---

### Tarea 1: aviso del primer arranque

**Interfaces**
- Produce: `LegalDialog(parent=None, *, require_acceptance: bool = False)`. Con `True`: botones
  «Acepto» (`AcceptRole`) y «Salir» (`RejectRole`, por defecto), sin botón Cerrar.
  `app.ensure_legal(settings: GuiSettings) -> bool`: devuelve `True` si ya estaba aceptado o el
  usuario acepta (y entonces llama a `settings.accept_legal()` y `settings.save()`).

- [ ] **Paso 1: tests**: `test_dialog_reject_by_escape_is_rejection`, `test_accept_button_accepts`,
  `test_default_button_is_exit`, `test_ensure_legal_skips_when_accepted` (sin diálogo, `True`),
  `test_ensure_legal_saves_acceptance` (con `monkeypatch` de `LegalDialog.exec` → Accepted:
  `settings.legal_accepted == LEGAL_VERSION` y el fichero lo recoge),
  `test_ensure_legal_rejected_returns_false_and_saves_nothing`,
  `test_main_does_not_create_window_when_rejected` (`monkeypatch` de `ensure_legal` → `False`:
  `main()` devuelve `0` y `MainWindow` no se instancia),
  `test_new_legal_version_asks_again` (`legal_accepted = LEGAL_VERSION - 1` → pregunta).
- [ ] **Paso 2:** ejecuta → falla. **Paso 3:** implementa; en `main()` llama a `ensure_legal` tras
  `apply_theme` y antes de localizar la CLI. **Paso 4:** pasa.
- [ ] **Paso 5:** commit `Pide aceptar el aviso legal en el primer arranque (G7)`.

### Tarea 2: confirmaciones de riesgo

**Interfaces**
- Produce: `confirm_active(parent) -> bool` y `confirm_private(parent) -> bool`. Cada una muestra
  `legal.ACTIVE_WARNING` / `legal.PRIVATE_WARNING` en un `QMessageBox` con los botones «Entiendo el
  riesgo y continúo» (`AcceptRole`) y «Cancelar» (por defecto).

- [ ] **Paso 1: tests** (el `QMessageBox` se prueba con `QTimer.singleShot` que pulsa el botón):
  `test_confirm_active_true_only_on_explicit_button`, `test_enter_cancels` (el botón por defecto
  es el de cancelar), `test_warning_text_is_the_legal_constant`.
- [ ] **Paso 2-4:** falla → implementa → pasa. **Paso 5:** commit
  `Añade las confirmaciones de módulos activos y redes privadas (G7)`.

### Tarea 3: selector de módulos y casillas de riesgo en «Nuevo scan»

**Interfaces**
- Consume: lista de `CliApi.modules()` (`name`, `description`, `passive`, `requires_key`,
  `key_configured`), `confirm_active`, `confirm_private`.
- Produce: `NewScanDialog(parent=None, modules: list[dict] | None = None)`; atributos `module_list`
  (`QListWidget` con casillas), `active_box`, `private_box`; `request()` rellena `modules`,
  `active`, `confirm_active`, `allow_private`, `confirm_private`.

- [ ] **Paso 1: tests**: `test_no_catalog_hides_the_selector_and_says_so`,
  `test_modules_without_key_are_disabled_with_reason` (`flags` sin `ItemIsEnabled` y tooltip con el
  nombre de la key),
  `test_active_modules_disabled_until_active_box_is_confirmed`,
  `test_active_box_confirmed_sets_both_flags` (con `confirm_active` → `True`),
  `test_active_box_declined_unchecks_itself` (`confirm_active` → `False`: casilla desmarcada,
  `request().active is False`, `confirm_active is False`),
  `test_unchecking_active_resets_the_confirmation`,
  `test_private_box_follows_the_same_rule`,
  `test_selected_modules_go_to_the_request` (solo los marcados, en orden),
  `test_ticking_nothing_means_cli_defaults` (`modules == ()`).
  La regla de oro se prueba con la capa sin Qt: `test_view_cannot_skip_confirmation` crea el
  diálogo, fuerza `active_box.setChecked(True)` con la confirmación rechazada y comprueba que
  `request.to_args()` no incluye `--active`.
- [ ] **Paso 2:** ejecuta → falla.
- [ ] **Paso 3:** implementa. Marcar `active_box` llama a `confirm_active(self)`; si devuelve
  `False`, `setChecked(False)` sin reentrar (bloquea señales). `_active_confirmed` se pone a
  `True` solo si el usuario confirmó y vuelve a `False` al desmarcar. Sustituye la etiqueta fija
  «Solo se usan módulos pasivos.» por un texto que dependa del estado de la casilla.
- [ ] **Paso 4:** ejecuta → pasa.
- [ ] **Paso 5:** commit `Añade el selector de módulos y las opciones de riesgo (G7)`.

### Tarea 4: la ventana principal pasa el catálogo

**Interfaces**
- Consume: `MainWindow.api.modules()` con `run_in_thread` al arrancar (si hay CLI).
- Produce: `MainWindow.catalog: list[dict] | None`, que `_new_scan` entrega a `NewScanDialog`.

- [ ] **Paso 1: tests** en `test_main_window.py`: `test_catalog_loads_on_startup`,
  `test_new_scan_receives_the_catalog`, `test_catalog_failure_leaves_none_and_new_scan_still_opens`.
- [ ] **Paso 2-4:** falla → implementa → pasa (sin `QMessageBox` modal si falla: mensaje en la barra
  de estado).
- [ ] **Paso 5:** commit `Carga el catálogo de módulos al abrir la ventana (G7)`.

### Tarea 5: `doctor --active` en el panel de salud (solo si G5 está hecho)

- [ ] **Paso 1: test** en `tests/gui/test_modules_view.py`: `test_active_check_needs_confirmation`
  (casilla «Incluir módulos activos» → si `confirm_active` devuelve `False`, `api.doctor` no se
  llama con `active=True`).
- [ ] **Paso 2-4:** falla → añade la casilla a `HealthDialog` reutilizando `confirm_active` →
  pasa. **Paso 5:** commit.

### Tarea 6: propósito del scan (`--purpose`)

Decidido: entra en G7. La GUI no puede saber si `require_purpose` está activo (vive en
`config.toml` o en `OSINEITOR_REQUIRE_PURPOSE`, y no sale por `--json`), así que el campo es
**opcional en la vista** y es la CLI la que rechaza (código 2, «los scans de email exigen
--purpose») cuando falta; la GUI muestra ese mensaje.

**Interfaces**
- Produce: `ScanRequest.purpose: str | None = None`; `to_args()` añade `--purpose <texto>` antes
  del `--`. `validate()` replica la regla de la CLI (`_purpose` en `cli.py`): 1 a 500 caracteres
  tras recortar, sin retornos de carro, saltos de línea ni NUL; si no, `InvalidRequest`. Cuadro «Propósito» en
  `NewScanDialog` (`purpose`, `QLineEdit`), con un texto de ayuda que dice que los scans de email y
  username lo exigen si tu configuración lo pide.

- [ ] **Paso 1: tests** en `tests/gui/test_scan_request.py`: `test_purpose_goes_before_the_separator`,
  `test_purpose_is_stripped`, `test_blank_purpose_is_omitted` (solo espacios → sin `--purpose`; un
  campo vacío no es un error), `test_purpose_over_500_chars_is_invalid`,
  `test_purpose_with_newline_or_nul_is_invalid`, `test_purpose_starting_with_dash_is_one_argument`
  (`"-x --active"` queda como un único argumento tras `--purpose`, sin activar nada).
  En `test_new_scan_dialog.py`: `test_purpose_field_reaches_the_request`,
  `test_invalid_purpose_is_shown_inline`. En `test_scan_view.py` o `test_process.py`, contra la CLI
  real de `fakecli.py` con `OSINEITOR_REQUIRE_PURPOSE=1` en el entorno:
  `test_email_scan_without_purpose_fails_with_the_cli_message` (el estado final es «fallido» y
  `session.message` incluye `--purpose`) y `test_email_scan_with_purpose_succeeds`.
- [ ] **Paso 2:** ejecuta → falla. **Paso 3:** implementa. **Paso 4:** pasa.
- [ ] **Paso 5:** actualiza el aviso del roadmap (fase 2, F2.6: «Riesgo conocido: la GUI aún no pasa
  `--purpose`») y de `docs/GUI.md` («Qué no está verificado»).
- [ ] **Paso 6:** commit `Pasa el propósito del scan desde la ventana (G7)`.

### Tarea 7: cierre

- [ ] Documentación: ROADMAP (G7 ✅ y «Estado»), `docs/GUI.md` («Hecho (G7)»; quita de «Pendiente»
  el aviso legal, el selector y las confirmaciones), `CHANGELOG.md`, y `CLAUDE.md` (estado de la GUI).
- [ ] `ruff check . && ruff format --check . && python -m pytest -q` → verde.
- [ ] Commit `Cierra G7: avisos legales y confirmación de --active`.

## Fuera de este plan

`--scope` y `--evidence` tampoco se exponen en la ventana; no figuran en G7 y se dejan fuera.

# Plan G6 · Ajustes y API keys (Hito G)

> **Estado (07-11-2026):** hecho (✅ en el ROADMAP). Las casillas de abajo son la lista de
> ejecución original y no se marcaron.

> **Para quien lo ejecute:** hazlo tarea a tarea (`superpowers:executing-plans` o
> `superpowers:subagent-driven-development`). Los pasos usan casillas `- [ ]`.

**Objetivo:** guardar y borrar las API keys de los módulos desde la ventana, sin mostrar nunca una
key guardada, y dejar las preferencias de la aplicación (tema, directorio de exportación) en un
solo diálogo.

**Arquitectura:** `CliApi.modules()`, `config_set` (la key viaja por stdin) y `config_unset` ya
existen. La vista agrupa los módulos por **nombre de key** (`requires_key`, p. ej. `hibp` lo
comparten varios módulos) y cada fila guarda o borra esa key en un hilo de trabajo.

**Pila:** PySide6, pytest-qt. Sin dependencias nuevas.

**Spec:** [`ROADMAP.md`](../../ROADMAP.md) (Hito G, fila G6) y [`docs/GUI.md`](../GUI.md)
(«Ajustes y API keys»; criterio de aceptación 5).

## Restricciones globales

- **Nunca se muestra una key guardada**: ni en la tabla, ni en un tooltip, ni en un mensaje de error,
  ni en el registro. La CLI tampoco las devuelve (`config show` solo da nombres).
- La key viaja por stdin (`CliApi.config_set`); jamás por la línea de comandos.
- El campo de la key es de tipo contraseña (`QLineEdit.EchoMode.Password`) y se vacía tras guardar.
- `requires_key` del contrato es `string | null`: `null` = el módulo no necesita key.
- Llamadas a la CLI fuera del hilo de la interfaz (`run_in_thread`); textos con `self.tr(...)`.
- Está lista cuando `ruff check`, `ruff format --check` y `python -m pytest -q` pasan.

## Foco de revisión

- Key con espacios o saltos de línea alrededor (pegado desde un correo): se recorta; una key vacía
  o solo espacios no se envía y se avisa.
- Una key que contiene la cadena que aparecería en un error de la CLI: el mensaje mostrado al
  usuario no la repite (se prueba con un `CliError` cuyo `stderr` incluye la key).
- Dos módulos con la misma key (`hibp`, `hibp_pastes`): una sola fila, y guardarla marca ambos.
- `modules()` falla o la CLI no está: el diálogo muestra el error y deja los botones deshabilitados.
- Guardar y borrar seguidos sobre la misma fila no deja la fila en estado incoherente (botones
  deshabilitados mientras una operación está en curso).
- Tras guardar, el estado «configurada» sale de la respuesta de la CLI (`configured`), no de lo que
  el usuario escribió.

## Estructura de ficheros

| Fichero | Responsabilidad |
|---|---|
| `src/osineitor_gui/keys.py` (nuevo, sin Qt) | `KeyRow` y `group_keys(modules) -> list[KeyRow]` |
| `src/osineitor_gui/ui/settings_dialog.py` (nuevo) | `SettingsDialog`: pestañas «API keys» y «General» |
| `src/osineitor_gui/ui/main_window.py` | acción Herramientas ▸ Ajustes… |
| `tests/gui/test_keys.py`, `tests/gui/test_settings_dialog.py` (nuevos) | lógica y vista |

---

### Tarea 1: agrupar módulos por key (sin Qt)

**Interfaces**
- Produce: `KeyRow(name: str, modules: tuple[str, ...], configured: bool)` (dataclass congelada) y
  `group_keys(modules: list[dict]) -> list[KeyRow]`, ordenada por `name`. `configured` es verdadero
  solo si **todos** los módulos de ese nombre tienen `key_configured`.

- [ ] **Paso 1: tests** en `tests/gui/test_keys.py`: `test_modules_without_key_are_ignored`,
  `test_modules_sharing_a_key_make_one_row` (`hibp` y `hibp_pastes` → una fila con ambos nombres),
  `test_rows_are_sorted_by_key_name`, `test_configured_needs_every_module_configured`,
  `test_result_validates_against_modules_output` (usa `tests.test_contract.validate("modules_output",
  ...)` sobre la entrada).
- [ ] **Paso 2:** ejecuta → falla. **Paso 3:** implementa en `keys.py`. **Paso 4:** pasa.
- [ ] **Paso 5:** commit `Agrupa los módulos por API key para la vista de ajustes (G6)`.

### Tarea 2: pestaña «API keys»

**Interfaces**
- Consume: `group_keys`, `CliApi.modules/config_set/config_unset`, `run_in_thread`.
- Produce: `SettingsDialog(api: CliApi, settings: GuiSettings, parent=None)` con `keys_table`,
  `key_input` (contraseña), `save_button`, `delete_button`, `message` (QLabel) y `reload()`.

- [ ] **Paso 1: tests** con un `api` falso que registra las llamadas:
  `test_lists_one_row_per_key_with_state` (columnas Key, Módulos, Estado «configurada»/«falta»),
  `test_save_sends_the_stripped_value_and_clears_the_field` (`config_set("hibp", "abc")` para
  `"  abc \n"`; `key_input.text() == ""`),
  `test_empty_key_is_not_sent` (cero llamadas, `message` lo explica),
  `test_key_never_appears_in_widgets` (tras guardar `"sk-SECRETO"`, ningún `QLabel`, celda del modelo
  ni `toolTip` del diálogo contiene `sk-SECRETO`),
  `test_cli_error_does_not_echo_the_key` (`CliError` con `stderr="fallo con sk-SECRETO"`: `message`
  no contiene `sk-SECRETO`; se muestra un texto genérico más el código de salida),
  `test_delete_calls_config_unset_and_marks_missing`,
  `test_buttons_disabled_while_an_operation_runs`,
  `test_modules_error_disables_the_buttons`.
- [ ] **Paso 2:** ejecuta → falla.
- [ ] **Paso 3:** implementa la pestaña. Tras `config_set`/`config_unset` ejecuta `reload()` (vuelve a
  pedir `modules()`), así el estado sale de la CLI. El error nunca interpola `stderr` ni el valor:
  usa el texto fijo «No se pudo guardar la key» y el código de salida si existe.
- [ ] **Paso 4:** ejecuta → pasa.
- [ ] **Paso 5:** prueba de integración con la CLI real y `OSINEITOR_CONFIG_DIR` apuntando a
  `tmp_path`: guardar `hibp` por el diálogo → `api.config_show()["keys"]` contiene `hibp`; borrar →
  ya no.
- [ ] **Paso 6:** commit `Añade la pestaña de API keys (G6)`.

### Tarea 3: pestaña «General» y acción de menú

**Interfaces**
- Consume: `GuiSettings` (`theme`, `last_export_dir`), `apply_theme`.

- [ ] **Paso 1: tests**: `test_general_tab_changes_theme_and_saves` (elegir «Oscuro» → `settings.theme
  == "dark"` y el fichero de `settings_path()` lo recoge),
  `test_settings_action_opens_the_dialog` (en `test_main_window.py`; sin CLI la acción sigue
  disponible, pero la pestaña de keys muestra el error de la CLI).
- [ ] **Paso 2:** ejecuta → falla.
- [ ] **Paso 3:** añade la pestaña (tema con el mismo mecanismo que `MainWindow._set_theme`; reutiliza
  esa función en vez de duplicarla: expónla como método público `set_theme`) y la acción
  `action_settings` (`Ctrl+,`) en el menú Herramientas, que G5 ya crea. Si G5 no está hecho, crea
  el menú aquí.
- [ ] **Paso 4:** `python -m pytest tests/gui -q` → verde.
- [ ] **Paso 5:** documentación: ROADMAP (G6 ✅; el Administrador de credenciales queda fuera de alcance y
  se anota así en la fila), `docs/GUI.md`, `CHANGELOG.md`.
- [ ] **Paso 6:** `ruff check . && ruff format --check . && python -m pytest -q` → verde.
- [ ] **Paso 7:** commit `Añade el diálogo de ajustes y API keys (G6)`.

## Qué no cubre

- Administrador de credenciales de Windows: decidido que **no** entra en G6 (las keys siguen en el
  fichero de configuración de la CLI, vía `config set --stdin`). Si se retoma, sería soporte de
  `keyring` en la propia CLI, que cambia `config.py` y el contrato.

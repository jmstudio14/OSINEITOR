# Aplicación de escritorio (Hito G)

Aplicación nativa de **Windows 10/11 x64** (ventana propia, menús, barras y diálogos) que
**controla la CLI por debajo**. Este documento es el diseño y el traspaso entre las dos mitades del
trabajo:

| Parte | Qué es | Dónde | Estado |
|---|---|---|---|
| **PR-E1** | Capa **no visual**, en Python puro y sin Qt | `src/osineitor_gui/` | **Hecha** y cubierta por tests |
| **PR-E2** | **Vistas y aspecto** con PySide6 | `src/osineitor_gui/ui/`, `app.py` | Pendiente: se hace en Windows, con la ventana delante |
| PR-F | Instalador (PyInstaller + Inno Setup) | `packaging/windows/` | Después de PR-E2 |

Stack: Python 3.13, **PySide6** (Qt 6, widgets), PyInstaller en modo carpeta e Inno Setup.

## Reglas de arquitectura

1. **La GUI solo habla con la CLI** mediante el contrato de [CLI_CONTRACT.md](CLI_CONTRACT.md). Del
   motor importa únicamente `osineitor.models.detect_type` y `osineitor.__version__`; un test
   (`tests/gui/test_rules.py`) lo hace cumplir.
2. **Qt solo en `osineitor_gui/ui/` y `osineitor_gui/app.py`.** Todo lo que se pueda decidir sin
   pantalla vive en la capa no visual, que se prueba en la CI. Otro test lo impone.
3. **Las vistas no deciden reglas de seguridad.** Que `--active` y `--allow-private` exijan
   confirmación lo impone `ScanRequest`; la vista solo pregunta al usuario y marca `confirm_*`.
4. **Textos en español** y, en `ui/`, con `self.tr(...)`; sin internacionalización por ahora. La
   capa no visual (sin Qt) no usa `tr()`: `legal` y los mensajes de `ScanRequest` son cadenas ya
   hechas que la vista muestra tal cual.
5. **Las API keys nunca pasan por la línea de comandos** (la ven otros procesos): se guardan con
   `CliApi.config_set`, que las envía por stdin.
6. **Nada de trabajo largo en el hilo de la interfaz.** Las llamadas de `CliApi` son síncronas:
   llámalas desde un hilo de trabajo (`QThreadPool`/`QRunnable`).

```
OSINEITOR.exe (GUI, sin consola)      osineitor.exe (CLI, misma carpeta)
 ┌────────────────────────────┐         ┌──────────────────────┐
 │ ui/  (PySide6)  ← PR-E2    │         │ motor, módulos, SQLite│
 │ osineitor_gui/ (sin Qt)    │ stdout  │                      │
 │  CliProcess ───────────────┼──NDJSON─┤ --ndjson             │
 │  CliApi  ──────────────────┼──JSON───┤ --json               │
 │                            ├─stdin──►│ --control-stdin      │
 └────────────────────────────┘         └──────────────────────┘
```

## La capa no visual (`osineitor_gui`)

| Módulo | Para qué sirve |
|---|---|
| `cli_locator.locate_cli()` | Encuentra la CLI: `osineitor.exe` junto al ejecutable (empaquetado) → `python -m osineitor` → PATH. Lanza `CliNotFound` con un mensaje apto para mostrar |
| `scan_request.ScanRequest` | Opciones de un scan → argumentos de la CLI. Valida y exige confirmación de `--active` y `--allow-private` (`ConfirmationRequired`). `detect_kind(texto)` para mostrar el tipo mientras se escribe |
| `process.CliProcess` | Lanza un scan, entrega eventos, `cancel()` ordenado (con escalada a `terminate`/`kill`), `kill()`, `wait()` |
| `events` | Dataclasses de los eventos y `parse_event`, tolerante con lo que no conoce |
| `session.ScanSession` | Estado que pintan las vistas: módulos, entidades, progreso, filtros. Sirve igual para un scan en vivo y uno guardado (`load_result`) |
| `api.CliApi` | Órdenes `--json`: `version`, `modules`, `history`, `show`, `doctor`, `export`, `config_show`, `config_set`, `config_unset` |
| `settings.GuiSettings` | Preferencias de la aplicación (tema, aviso legal aceptado, geometría…) en `%APPDATA%\osineitor-gui\settings.json` |
| `legal` | Textos del aviso legal y de las advertencias de `--active` / `--allow-private` |

### Hilos: el único punto delicado

`CliProcess` llama a `on_event`, `on_stderr` y `on_exit` **desde hilos de fondo**, no desde el de la
interfaz. Con Qt, el callback solo debe emitir una señal (la conexión entre hilos es en cola, y la
señal llega ya al hilo de la interfaz):

```python
from PySide6.QtCore import QObject, Signal

from osineitor_gui.process import CliProcess


class ScanRunner(QObject):
    event = Signal(object)  # un osineitor_gui.events.Event
    finished = Signal(int)  # código de salida

    def __init__(self, args: list[str]) -> None:
        super().__init__()
        self._proc = CliProcess(
            args,
            on_event=self.event.emit,
            on_exit=self.finished.emit,
        )

    def start(self) -> None:
        self._proc.start()

    def cancel(self) -> None:
        self._proc.cancel()

    @property
    def stderr_tail(self) -> list[str]:
        return self._proc.stderr_tail
```

Flujo de un scan: `ScanRequest(...).to_args()` → `ScanRunner` → cada evento a
`session.feed(evento)` y la vista se refresca → al terminar, `session.process_exited(código,
runner.stderr_tail)`, que convierte en «fallido» un scan cuya CLI se cayó sin cerrarlo.

## Diseño de la ventana

**Ventana principal** (`QMainWindow`):

- **Menú Archivo:** Nuevo scan (`Ctrl+N`), Abrir scan guardado…, Exportar scan… (JSON, Markdown,
  HTML; `CliApi.export`), Salir.
- **Menú Ver:** Tema (Sistema / Claro / Oscuro), mostrar u ocultar los paneles.
- **Menú Herramientas:** Salud de los módulos, Ajustes y API keys.
- **Menú Ayuda:** Uso responsable (`legal.LEGAL_TEXT`), Acerca de (`osineitor_gui.__version__`).
- **Barra de herramientas:** Nuevo scan, Cancelar (activo solo con un scan en marcha), Exportar.
- **Panel izquierdo (dock): Historial.** `CliApi.history()`; doble clic abre el scan con
  `CliApi.show()` y `session.load_result()`.
- **Centro: pestañas, una por scan.** Tabla de entidades (tipo, valor, fuente) con filtro por tipo
  (con recuentos de `counts_by_type()`) y cuadro de búsqueda (`session.filtered(...)`). Debajo, el
  **panel de detalle** de la entidad seleccionada: clave-valor de `data`, fuente y origen (`parent`).
- **Panel inferior (dock): Actividad por módulo.** Una fila por módulo de `session.modules`:
  estado (`running`, `ok`, `empty`, `error`, `quota`, `skipped`, `pending`) con color, entidades,
  peticiones, caché, tiempo y mensaje. Un `error` o `quota` se ve a simple vista.
- **Barra de estado:** progreso (`session.done` / `session.total`), entidades, peticiones y
  estado del scan. Si `session.incomplete`, un aviso visible («resultado incompleto: cancelado /
  presupuesto agotado / fallido») también en la pestaña.

**Diálogo «Nuevo scan»:** objetivo (con el tipo detectado en vivo, `detect_kind`), tipo
(Automático, Dominio, IP, Email, Username), profundidad (1–4), módulos (lista de `CliApi.modules()`
con casillas; los que necesitan API key y no la tienen se muestran deshabilitados con el motivo),
presupuesto (entidades, peticiones, segundos; 0 = sin límite), «no guardar», «sin caché» /
«refrescar».

- **Módulos activos:** la casilla abre un diálogo con `legal.ACTIVE_WARNING` y botones explícitos;
  solo si el usuario acepta se marca `confirm_active`. Igual con `allow_private` y
  `legal.PRIVATE_WARNING`.
- Un `InvalidRequest` se muestra bajo el campo; no se lanza nada.

**Primer arranque:** diálogo modal con `legal.LEGAL_TEXT` hasta que se acepta
(`settings.accept_legal()` + `save()`); si se rechaza, la aplicación se cierra. Se vuelve a pedir
si sube `LEGAL_VERSION`.

**Salud de los módulos:** `CliApi.doctor()` en un hilo, con indicador de espera (puede tardar
minutos). Tabla con el veredicto (`ok`, `empty`, `fail`, `skipped`, `unchecked`), detalle y tiempo.

**Ajustes y API keys:** lista de módulos con key (`CliApi.modules()`, campos `requires_key` y
`key_configured`); cada fila permite guardar (`config_set`, campo de contraseña) o borrar
(`config_unset`). **Nunca se muestra una key guardada.**

**Errores de la CLI:** `CliNotFound` y `CliError` se muestran en un diálogo con el mensaje y, si lo
hay, el `stderr`. Un scan que acaba con `state == "failed"` muestra `session.message`.

**Tema:** claro, oscuro o el del sistema (`settings.theme`); guarda y restaura la geometría de la
ventana (`window_geometry`, en base64).

## Traspaso a PR-E2 (VS Code + Claude Code, en Windows)

Prepara el entorno una vez:

```powershell
git clone https://github.com/jmstudio14/OSINEITOR.git
cd OSINEITOR
py -3.13 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev,gui]"
python -m pytest -q
osineitor doctor
```

Si la comprobación base falla, resuélvelo antes de tocar la interfaz. La salida de
`osineitor doctor` es además la primera prueba real de las fuentes: pégala en un issue si algo falla.

**Lo que hay que construir** (todo bajo `src/osineitor_gui/`):

```
app.py            QApplication, tema, instancia única, AppUserModelID de Windows, arranque
ui/
  runner.py       ScanRunner: el adaptador Qt de arriba
  models.py       QAbstractTableModel sobre ScanSession (entidades y módulos) + proxy de filtro
  main_window.py  menús, barras, docks y pestañas
  new_scan_dialog.py, scan_view.py, entity_detail.py, modules_view.py,
  settings_dialog.py, legal_dialog.py, about_dialog.py
```

más el lanzador `osineitor-gui = osineitor_gui.app:main` en `pyproject.toml` (`[project.gui-scripts]`).

**Criterios de aceptación**

1. `osineitor-gui` abre la ventana sin consola y muestra el aviso legal la primera vez.
2. Un scan a `example.com` muestra entidades y la actividad por módulo **mientras corre**, y el
   botón Cancelar lo detiene guardando lo obtenido (la pestaña lo marca como cancelado).
3. El historial abre un scan guardado con el mismo aspecto que uno en vivo.
4. `--active` y `--allow-private` no se pueden activar sin la confirmación.
5. Guardar y borrar una API key funciona y la key no aparece en ningún sitio de la interfaz.
6. Tema claro y oscuro legibles; la ventana recuerda su tamaño; escala bien a 150 % de DPI.
7. Los tests de la capa no visual siguen en verde y Qt no se importa fuera de `ui/` y `app.py`.

**Pruebas:** añade `pytest-qt` a las dependencias de desarrollo y prueba las vistas con
`QT_QPA_PLATFORM=offscreen`. Cada modelo y vista se prueba con una `ScanSession` alimentada a mano;
no hace falta lanzar la CLI.

**Lista de comprobación manual en Windows** (antes de dar PR-E2 por terminado):

- [ ] Abrir, cerrar y reabrir: recuerda el tamaño y el tema.
- [ ] Scan a `example.com` con módulos pasivos; ver la actividad en vivo.
- [ ] Cancelar a mitad de un scan; comprobar que aparece en el historial como cancelado.
- [ ] Scan a un dominio con TLD sin RDAP (`.es`): el módulo `rdap` sale como omitido, no como vacío.
- [ ] Exportar a HTML y abrirlo.
- [ ] Guardar una API key y borrarla; `osineitor config show` coincide.
- [ ] Intentar `--active`: pide confirmación y, si se rechaza, no se lanza.
- [ ] Modo oscuro y DPI al 150 %.
- [ ] Cerrar la ventana con un scan en marcha: la CLI no queda huérfana (`tasklist`).

## Qué no está verificado

- **Nada de esto se ha visto en una ventana.** La capa no visual se prueba contra la CLI real en la
  CI de Windows y Linux; Qt no entra en esa CI hasta PR-E2.
- La latencia de lanzar un proceso de la CLI por cada orden en Windows (con antivirus) no está
  medida. Si el historial o la lista de módulos tardan, cachear en la GUI.
- `CREATE_NO_WINDOW` evita la ventana de consola, pero que no parpadee solo se comprueba a ojo.
- La GUI aún no pasa `--purpose`, `--scope` ni `--evidence`, y `CliApi` no expone `osineitor verify`.
- Fuera de alcance por ahora: grafo, hallazgos, procedencia en la interfaz, internacionalización y
  actualizaciones automáticas.

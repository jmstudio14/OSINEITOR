# Aplicación de escritorio (Hito G)

Aplicación nativa de **Windows 10/11 x64** (ventana propia, menús, barras y diálogos) que
**controla la CLI por debajo**. Este documento es el diseño y el traspaso entre las dos mitades del
trabajo:

| Parte | Qué es | Dónde | Estado |
|---|---|---|---|
| **PR-E1** | Capa **no visual**, en Python puro y sin Qt | `src/osineitor_gui/` | **Hecha** y cubierta por tests |
| **PR-E2** | **Vistas y aspecto** con PySide6 | `src/osineitor_gui/ui/`, `app.py` | **En curso**: ventana principal (G2), scan en vivo (G3) y historial, detalle y exportación (G4) y panel de salud (G5) y ajustes con API keys (G6) y avisos legales con `--active` (G7) hechos; faltan solo la instancia única y exponer `--scope` / `--evidence` |
| PR-F | Instalador (PyInstaller + Inno Setup) | `packaging/windows/` | **Hecho** (G8); sin ejecutar aún en la CI |

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
osineitor-gui.exe (GUI, sin consola)  osineitor.exe (CLI, misma carpeta)
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
| `cli_locator.locate_cli()` | Encuentra la CLI: `osineitor.exe` junto al ejecutable (empaquetado) → `python -P -m osineitor` → PATH (solo carpetas absolutas, y en Windows exige el `osineitor.exe` exacto). Lanza `CliNotFound` con un mensaje apto para mostrar |
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
  estado (`running`, `ok`, `empty`, `error`, `quota`, `skipped`, `pending`; con el scan acabado,
  `pending` se muestra «sin ejecutar») con color, entidades,
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

## Rediseño visual (centro de operaciones)

Sustituye al aspecto nativo y actualiza el diseño de arriba donde difieren. Se conservan los
menús, las reglas de arquitectura y todas las funciones.

- **Sistema de diseño:** `ui/theme.py` (tokens `DARK` y `LIGHT`, tema oscuro por defecto,
  `install`, `apply_theme`) y `ui/assets/theme.qss`, plantilla sin colores sueltos. Estilo
  base Fusion. Los widgets no usan `setStyleSheet`: declaran `role`, `kind` o `tone`
  (`widgets.set_style`). `ui/icons.py` tinta los Lucide de `assets/icons`; `assets/qss` son los
  glifos que la hoja de estilo solo puede cargar de un fichero. Inter y JetBrains Mono van en
  `assets/fonts` con sus licencias OFL. Un test exige el contraste WCAG en ambos temas.
- **Severidad:** `critical`, `high`, `medium` (token `warning`), `low` (`info`) e `info`
  (`neutral`), en `theme.SEVERITY_TONES`. El color marca, el texto va en tinta normal: nunca
  solo color. El ámbar y el naranja de la paleta quedan cerca (ΔE 9,6); por eso cada segmento
  lleva leyenda, tooltip y separación, y hay lista con los valores.
- **Layout:** `ui/sidebar.py` (`Sidebar`, `TopBar`). `MainWindow.stack` tiene Panel, pestañas,
  historial, búsqueda, casos, vigilancia, salud, ajustes y el vacío de Scans. Por debajo de 1100 px
  la barra lateral se contrae (salvo que el usuario haya elegido: `settings.sidebar`) y la superior
  solo muestra iconos; los KPI se recolocan (6, 3 o 2 por fila) y bajo 760 px el detalle de un scan
  pasa debajo. `_update_state` no toca la página: un scan en marcha refresca cada 100 ms y sacaría al
  usuario de la que esté viendo.
- **Panel:** `osineitor_gui/dashboard.py` (sin Qt) y `ui/dashboard_view.py` con `ui/charts.py`
  (QPainter: PySide6-Essentials no trae QtCharts). No hay puntuación inventada: el estado general es
  el peor hallazgo real. Las cifras salen de `history --json` (`status`, `severity`, `by_type`,
  `modules`); `show` solo se pide para los títulos, y solo de scans con hallazgos, en cadena desde la
  UI, con caché por id, token de generación, parada al cerrar y únicamente con el panel a la vista.
  Medido con 10 scans: los indicadores tardaban 7,9 s y ahora 1,4 s.
- **Pestañas de un scan guardado:** `ui/scan_insights.py` (`risk` y `timeline`), con carga perezosa.
- **Casos y Vigilancia:** `ui/cases_panel.py` y `ui/watch_panel.py`. Vigilancia solo consulta: `watch
  run` envía avisos reales, puede usar módulos activos y no se puede cancelar, así que se queda en la
  CLI. Sin `watch.yml` se ve un estado vacío, no un error.
- **Instancia única:** `ui/single_instance.py`, con candado y servidor derivados de `settings_dir()`:
  los tests y `smoke.py` no chocan con la aplicación abierta. Si el candado falla por otro motivo, la
  aplicación abre igual.
- **Hilos:** `ui/worker.py`. Los hilos del pool solo dejan el resultado en una `SimpleQueue` y un
  `QTimer` la vacía en el hilo de la UI. Un hilo no puede saber si un `QObject` sigue vivo: emitir una
  señal desde él daba `Signal source has been deleted` al cerrar.
- **Búsqueda:** `CliApi.search` pasa la consulta tras `--`; un dato nunca es una opción. Igual
  `case_new`, `case_add` y `case_note`.
- **Tablas:** `ui/tables.py`. Proxy para ordenar (`SORT_ROLE` da el valor crudo) y sin orden
  inicial; `source_row` traduce el índice; `RowsModel` evita un modelo por tabla; `_RowHover` resalta
  la fila. Sin paginación: `QTableView` virtualiza y la CLI no tiene `offset` (el historial trae
  hasta 500).
- **Datos de terceros:** `widgets.label` y `widgets.safe_tooltip`, nunca texto enriquecido.
- **Traducciones:** `theme.install` carga `qtbase_es` para los botones estándar.

**Fuera por no existir la función:** notificaciones, perfil de usuario, incidentes y red. **No
aplica:** móvil y tablet (aplicación de Windows).

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
  new_scan_dialog.py, scan_view.py, entity_detail.py, modules_view.py, history_panel.py,
  settings_dialog.py, legal_dialog.py, risk_dialog.py, theme.py, worker.py
```

más el lanzador `osineitor-gui = osineitor_gui.app:main` en `pyproject.toml` (`[project.gui-scripts]`).

**Hecho (G2):** `app.py`, `ui/theme.py`, `ui/main_window.py` y `ui/legal_dialog.py`, y el lanzador. La ventana tiene los menús Archivo (Salir), Ver ▸ Tema y Ayuda (Uso responsable, Acerca de), la barra de herramientas y la barra de estado con la CLI localizada; solo incluye acciones que ya funcionan. «Acerca de» es un `QMessageBox.about`, sin fichero propio. **Hecho (G3):** `ui/runner.py` (`ScanRunner`), `ui/models.py` (`EntityTableModel`, `ModuleActivityModel`), `ui/scan_view.py` y `ui/new_scan_dialog.py`. «Nuevo scan» (`Ctrl+N`) abre una pestaña por scan con la tabla de entidades (filtro por tipo con recuentos y búsqueda), la actividad por módulo y el aviso de resultado incompleto; la barra de estado muestra entidades, peticiones, estado y progreso. Cancelar detiene la CLI de forma ordenada; cerrar una pestaña o la ventana con un scan en marcha pide confirmación, cancela y, si la CLI no sale en 5 s, la mata. El diálogo es **mínimo y solo pasivo**: objetivo (con el tipo detectado), tipo, profundidad, presupuesto, «no guardar», «sin caché» y «refrescar».

*Desviación del diseño:* la actividad por módulo va dentro de cada pestaña (un `QSplitter` bajo la tabla de entidades) y no en un dock global, porque cada pestaña es un scan distinto. La vista se repinta como mucho cada 100 ms, no por evento.

**Hecho (G4):** `ui/worker.py` (`run_in_thread`: las llamadas síncronas de `CliApi` van al pool de hilos y el resultado vuelve al hilo de la interfaz por una cola), `ui/history_panel.py` y `ui/entity_detail.py`. El dock Historial lista `CliApi.history()` (se carga al arrancar y cuando termina un scan en vivo que se guardó; botón Actualizar); el doble clic abre el scan con `CliApi.show()` y `ScanView.from_result()` en una pestaña con el mismo aspecto que uno en vivo, o activa la que ya lo muestra. Archivo ▸ Abrir scan guardado… muestra el dock y lo recarga. Archivo ▸ Exportar scan… (activo solo con un scan guardado y terminado) pregunta el fichero y el formato (JSON, Markdown, HTML) y llama a `CliApi.export()`. Un fallo de la CLI se muestra en un diálogo.

*Desviación del diseño:* el panel de detalle va a la derecha de la tabla de entidades (un `QSplitter` horizontal) y no debajo, para no apretar tres paneles en vertical. Muestra fuente, origen y los campos de `data`; la confianza y las observaciones quedan fuera.

**Hecho (G5):** `ui/modules_view.py` (`HealthModel` y `HealthDialog`) y la acción Herramientas ▸ Salud de los módulos… El diálogo no arranca solo: «Comprobar» lanza `CliApi.doctor()` en un hilo de trabajo, con un indicador de espera, y rellena la tabla (módulo, veredicto, detalle, tiempo, peticiones). Un fallo de la CLI se ve en el propio diálogo, no en un cuadro modal. Al hacerse G5 solo comprobaba módulos pasivos (desde G7 tiene la casilla «Incluir módulos activos») y un `doctor` en curso no se puede cancelar: cerrar el diálogo deja que el proceso termine solo (máx. 300 s). La ventana reutiliza un único diálogo.

**Hecho (G6):** `keys.py` (capa sin Qt: `group_keys` agrupa `CliApi.modules()` por nombre de key, porque varios módulos comparten la misma) y `ui/settings_dialog.py` (`SettingsDialog`, con `KeysModel`), abierto desde Herramientas ▸ Ajustes… (`Ctrl+,`). La pestaña «API keys» tiene una fila por key con su estado; «Guardar» envía el valor recortado a `CliApi.config_set` (stdin) y «Borrar» llama a `config_unset`, ambos en un hilo de trabajo y con los botones desactivados mientras corren. Tras cada cambio se vuelve a pedir `modules()`: el estado «configurada» sale de la CLI, no de lo que se escribió. La key vive solo en un campo de contraseña que se vacía al guardar; ninguna tabla, etiqueta ni tooltip la contiene y un error de la CLI se muestra con un texto fijo y el código de salida, sin repetir `stderr`. La pestaña «General» elige el tema; el diálogo emite `theme_changed` y la ventana principal lo aplica y lo guarda (`MainWindow.set_theme`, que también marca el menú Ver ▸ Tema). El diálogo se reutiliza y recarga las keys cada vez que se abre.

*Fuera de alcance:* guardar las keys en el Administrador de credenciales de Windows. La CLI ya da prioridad a `OSINEITOR_<NOMBRE>_KEY` sobre el fichero, pero una key guardada solo por la GUI no valdría para la CLI usada desde una terminal; hacerlo bien exige soporte de `keyring` en la propia CLI y cambiar el contrato.

**Hecho (G7):** `ui/risk_dialog.py` (`confirm_active`, `confirm_private`: un `QMessageBox` con el texto de `legal.ACTIVE_WARNING` / `PRIVATE_WARNING`, «Entiendo el riesgo y continúo» y «Cancelar», que es el botón por defecto y el de Escape: Enter no confirma), `LegalDialog(require_acceptance=True)` y `app.ensure_legal(settings)`, que `main()` llama tras aplicar el tema y antes de localizar la CLI (rechazarlo, con «Salir», Esc o la X, cierra sin crear la ventana ni lanzar la CLI; si no se puede guardar la aceptación, avisa y sigue, y volverá a pedirse). «Nuevo scan» recibe el catálogo de `CliApi.modules()` (la ventana lo carga al abrirse; si falla, se avisa en la barra de estado y el diálogo se abre sin selector): una lista con casillas (los módulos activos están deshabilitados hasta confirmar «módulos activos» y se desmarcan al quitarla; los que necesitan una key que falta, deshabilitados con el motivo), las casillas «módulos activos» y «redes privadas» —solo se marcan si el usuario confirma; al desmarcarlas se olvida la confirmación y volver a marcarlas la pide de nuevo— y el cuadro «Propósito». `ScanRequest.purpose` replica la regla de la CLI (de 1 a 500 caracteres, sin saltos de línea ni NUL) y se pasa como un único argumento (`--purpose`, antes de `--`). El panel de salud tiene la casilla «Incluir módulos activos», con la misma confirmación, y pasa `active=True` a `doctor`. El propósito es opcional en la vista porque la GUI no conoce `require_purpose` (vive en la configuración de la CLI): si falta y se exige, el scan falla con el mensaje de la CLI, que se ve en la pestaña.

**Hecho (G8):** `packaging/windows/`. `osineitor.spec` (PyInstaller, modo carpeta) define dos ejecutables que comparten `dist/OSINEITOR/`: `osineitor.exe` (la CLI, con consola) y `osineitor-gui.exe` (sin consola). No pueden llamarse `OSINEITOR.exe` y `osineitor.exe`: NTFS no distingue mayúsculas. `locate_cli` ya busca `osineitor.exe` junto a la GUI. Los módulos se importan por nombre, así que el `.spec` los pasa como `hiddenimports` desde `modules/_manifest.py` (el motor ya usaba esa lista congelado). `build.ps1 -Version x.y.z` construye y crea el ZIP portable; `smoke.py <carpeta>` comprueba versión, número de módulos, presets, un scan sin red y que la GUI sigue viva a los 3 s (con el aviso legal ya aceptado en un directorio temporal); `osineitor.iss` (Inno Setup) instala por usuario, sin UAC, con la CLI en el PATH del usuario como tarea opcional y sin borrar los datos al desinstalar; `checksums.py` escribe `SHA256SUMS.txt`. El job `windows` de `release.yml` lo encadena y, con una etiqueta, crea la Release de GitHub con instalador, ZIP y sumas (ver [PUBLICACION.md](PUBLICACION.md)).

**Ajustes de la GUI:** `settings.json` (tema, aviso legal aceptado y otras preferencias) vive en `%APPDATA%\osineitor-gui`; la variable `OSINEITOR_GUI_CONFIG_DIR` cambia esa carpeta (los tests y `smoke.py` la usan).

**Hecho:** la instancia única y `--scope` y `--evidence` en «Nuevo scan».

**Criterios de aceptación**

1. `osineitor-gui` abre la ventana sin consola y muestra el aviso legal la primera vez.
2. Un scan a `example.com` muestra entidades y la actividad por módulo **mientras corre**, y el
   botón Cancelar lo detiene guardando lo obtenido (la pestaña lo marca como cancelado).
3. El historial abre un scan guardado con el mismo aspecto que uno en vivo.
4. `--active` y `--allow-private` no se pueden activar sin la confirmación.
5. Guardar y borrar una API key funciona y la key no aparece en ningún sitio de la interfaz.
6. Tema claro y oscuro legibles; la ventana recuerda su tamaño; escala bien a 150 % de DPI.
7. Los tests de la capa no visual siguen en verde y Qt no se importa fuera de `ui/` y `app.py`.

**Pruebas:** `pip install -e ".[dev,gui-test]"` y prueba las vistas con
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
- [ ] Teclado físico: recorrer todas las páginas con Tab; Enter no confirma los avisos de riesgo.
- [ ] Lector de pantalla (NVDA o Narrador): navegación, tablas, gráficos con flechas y avisos.
- [ ] DPI real al 150 % en un monitor físico, y abrir dos veces: se activa la misma ventana.
- [ ] Instalar con el asistente (no en silencio), SmartScreen y antivirus; desinstalar.

## Qué no está verificado

- **Instalador (G8):** compilado con Inno Setup 6.7.3, instalado y desinstalado en silencio en local, con `smoke.py` sobre lo instalado. Falta el job `windows` de la CI (`release.yml` aún no está en `main`), la Release, el asistente interactivo, SmartScreen y los antivirus. Sin firmar y sin icono propio.
- **Comprobado en la ventana real de Windows:** scan pasivo a `example.com`, cancelación, exportar a HTML, informe abierto en un navegador en ambos temas y capturas de las páginas en claro y oscuro, parte de ellas al 150 % (`QT_SCALE_FACTOR`). UI Automation: 0 controles interactivos sin nombre en 9 páginas. Tabulador y atajos, con pulsaciones simuladas. Los tests de Qt corren en la CI (trabajo `gui`).
- **Sin comprobar:** teclado físico, un lector de pantalla escuchado de verdad, monitor real al 150 % y la lista manual (G9). La plataforma `offscreen` ignora el esquema de color.
- La latencia de lanzar un proceso de la CLI por cada orden en Windows (con antivirus) no está
  medida. Si el historial o la lista de módulos tardan, cachear en la GUI.
- `CREATE_NO_WINDOW` evita la ventana de consola, pero que no parpadee solo se comprueba a ojo.
- Fuera de alcance por ahora: grafo, procedencia en la interfaz, internacionalización y
  actualizaciones automáticas.

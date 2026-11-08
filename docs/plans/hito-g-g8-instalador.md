# Plan G8 · Instalador de Windows (Hito G)

> **Estado (07-11-2026):** escrito (✅ en el ROADMAP), pero sin ejecutar del todo: el paquete de
> PyInstaller y `smoke.py` pasaron en local; no se ha compilado el `.iss`, ni instalado, ni ejecutado
> el job `windows` de `release.yml` (ver «Qué no está verificado» en [GUI.md](../GUI.md)). Las
> casillas de abajo son la lista de ejecución original y no se marcaron.

> **Para quien lo ejecute:** hazlo tarea a tarea (`superpowers:executing-plans` o
> `superpowers:subagent-driven-development`). Los pasos usan casillas `- [ ]`.

**Objetivo:** publicar, desde la CI y al crear una etiqueta, un instalador `.exe` (Inno Setup), un
ZIP portable y el fichero de SHA-256 de ambos.

**Arquitectura:** PyInstaller en modo carpeta con **dos ejecutables que comparten una sola carpeta
de dependencias**: la GUI (sin consola) y la CLI (con consola, la que lanza la GUI y la que sirve
desde una terminal). `osineitor_gui/cli_locator.py` ya busca la CLI junto al ejecutable de la GUI.
Inno Setup empaqueta esa carpeta. Todo se construye en un job de `windows-latest`.

**Pila:** Python 3.13, PyInstaller, Inno Setup 6, GitHub Actions.

**Spec:** [`ROADMAP.md`](../../ROADMAP.md) (Hito G, fila G8) y [`docs/GUI.md`](../GUI.md) (PR-F).

## Restricciones globales

- Solo Windows 10/11 x64. El instalador sin firmar muestra SmartScreen: se documenta, no se evita
  (la firma es tarea del autor, ver «Fuera de este hito» en el roadmap).
- **Los dos ejecutables no pueden llamarse igual salvo mayúsculas**: NTFS no distingue, así que
  `OSINEITOR.exe` (como dice hoy `docs/GUI.md`) y `osineitor.exe` colisionarían en la misma
  carpeta. Nombres: `osineitor.exe` (CLI, que es lo que busca `locate_cli`) y
  `osineitor-gui.exe` (GUI). Corrige el diagrama de `docs/GUI.md`.
- Nada de red durante la construcción salvo `pip` e Inno Setup (instalado en el runner).
- No se incluye ningún secreto ni la base de datos de nadie; la configuración y los datos del
  usuario viven en `%APPDATA%`/`%LOCALAPPDATA%` y el desinstalador no los borra sin preguntar.
- El tag `vX.Y.Z` debe coincidir con `pyproject.toml` (la comprobación ya existe en `release.yml`).
- Datos que el paquete necesita en tiempo de ejecución (`presets/*.yml`, `data/rules/`,
  `tech_signatures.json`, `sites.json`, `wmn.json`, esquemas) deben estar en el bundle.
- Está lista cuando `ruff check`, `ruff format --check`, `python -m pytest -q` pasan y el job de
  Windows construye y supera la prueba de humo del paquete.

## Foco de revisión

- **Descubrimiento de módulos congelado:** el registro descubre módulos por el sistema de ficheros
  o `importlib`; dentro de PyInstaller eso puede devolver cero módulos sin error. La prueba de humo
  exige todos los módulos (62 hoy; el recuento de `osineitor modules --json`, que `tests/test_docs.py` ya compara
  con el README).
- Ficheros de datos ausentes en el bundle: la prueba de humo ejecuta un `doctor`/`presets` real
  y comprueba el preset `passive`.
- Ruta con espacios y con acentos (`C:\Users\José María\AppData\...`): instalar y arrancar ahí.
- Dos instancias del instalador, o instalar sobre una versión anterior: actualiza sin duplicar
  accesos directos ni dejar el `AppId` distinto.
- Desinstalar con la aplicación abierta: el instalador avisa o la cierra, no deja ficheros.
- La CLI congelada no abre ventana de consola cuando la lanza la GUI (`CREATE_NO_WINDOW`, ya en
  `process.popen_flags`); desde una terminal sí imprime.
- El ZIP portable y el instalador contienen **los mismos** ficheros (mismo SHA-256 por fichero).

## Estructura de ficheros

| Fichero | Responsabilidad |
|---|---|
| `packaging/windows/osineitor.spec` (nuevo) | PyInstaller: dos `Analysis`/`EXE` y un `COLLECT` común |
| `packaging/windows/osineitor.iss` (nuevo) | Inno Setup: carpeta → instalador |
| `packaging/windows/smoke.py` (nuevo) | prueba de humo del paquete ya construido |
| `packaging/windows/build.ps1` (nuevo) | orquesta la construcción (local y CI) |
| `.github/workflows/release.yml` | job `windows` tras `build`, sube los artefactos a la release |
| `tests/test_packaging.py` (nuevo) | comprueba lo comprobable sin Windows |
| `docs/PUBLICACION.md`, `docs/USO.md`, `README.md`, `CHANGELOG.md` | cómo instalar y verificar |

---

### Tarea 1: spec de PyInstaller y construcción local

**Interfaces**
- Produce: `packaging/windows/build.ps1 -Version <x.y.z>` que deja `dist\osineitor\` con
  `osineitor.exe` y `osineitor-gui.exe`.

- [ ] **Paso 1: test** en `tests/test_packaging.py` (corre en cualquier SO):
  `test_spec_names_the_two_executables` (el `.spec` contiene `name="osineitor"` y
  `name="osineitor-gui"` y no hay dos nombres que coincidan sin distinguir mayúsculas),
  `test_gui_exe_has_no_console_and_cli_has` (`console=False` / `console=True`),
  `test_pyinstaller_is_not_a_runtime_dependency` (no figura en `dependencies`; sí en un extra
  `build` de `pyproject.toml`).
- [ ] **Paso 2:** ejecuta → falla.
- [ ] **Paso 3:** crea el `.spec`: `collect_data_files("osineitor")` y `collect_submodules(
  "osineitor.modules")` para el bundle de la CLI; `osineitor_gui` y `PySide6` (solo
  `QtCore/QtGui/QtWidgets`; el extra ya es `PySide6-Essentials`) para la GUI; `COLLECT` con ambos
  `EXE`. Añade el extra `build = ["pyinstaller>=6"]` a `pyproject.toml`.
- [ ] **Paso 4:** ejecuta → pasa. **Paso 5:** en Windows, `build.ps1` y comprobar a mano que
  `dist\osineitor\osineitor.exe version --json` imprime la versión.
- [ ] **Paso 6:** commit `Añade el spec de PyInstaller con CLI y GUI (G8)`.

### Tarea 2: prueba de humo del paquete

**Interfaces**
- Produce: `python packaging/windows/smoke.py <carpeta>` → código 0 si todo cumple, 1 con el motivo
  en stderr.

Comprobaciones, en este orden: existen ambos `.exe`; `osineitor.exe version --json` == versión de
`pyproject.toml`; `modules --json` devuelve todos los módulos (62 hoy) y valida contra `modules_output`;
`presets --json` contiene `passive`; una ejecución real **sin red** con el módulo local
`discord_snowflake` (el humo no sale a Internet); y `osineitor-gui.exe` arranca con
`QT_QPA_PLATFORM=offscreen`: se lanza el proceso, se comprueba a los 3 s que sigue vivo y se
termina (sin tocar `app.py`; una opción `--smoke` en la aplicación sería un cambio fuera de este
plan y pediría tu OK).

- [ ] **Paso 1: tests** `tests/test_packaging.py::test_smoke_*` sobre una carpeta falsa con scripts
  `.bat` como ejecutables (solo Windows, `skipif` en otros): falta el `.exe` → código 1 y mensaje;
  versión distinta → código 1; menos módulos de los esperados → código 1.
- [ ] **Paso 2-4:** falla → implementa → pasa.
- [ ] **Paso 5:** ejecuta el humo sobre el `dist` real (Windows) y anota la salida.
- [ ] **Paso 6:** commit `Añade la prueba de humo del paquete de Windows (G8)`.

### Tarea 3: instalador de Inno Setup

- [ ] **Paso 1: test** `test_iss_is_consistent`: el `.iss` usa `AppId` fijo (GUID constante),
  `AppVersion` tomada de un define que `build.ps1` rellena desde `pyproject.toml`, `ArchitecturesAllowed=x64compatible`,
  `PrivilegesRequired=lowest` (instalación por usuario, sin UAC) y apunta a `osineitor-gui.exe`;
  `UninstallDelete` no toca `%APPDATA%`.
- [ ] **Paso 2:** ejecuta → falla. **Paso 3:** escribe el `.iss`: acceso directo en el menú Inicio
  (`osineitor-gui.exe`), casilla opcional «Añadir la CLI al PATH del usuario», idioma español,
  `CloseApplications=yes`.
- [ ] **Paso 4:** pasa. **Paso 5:** en Windows compila con `ISCC.exe`, instala, abre, desinstala y
  comprueba que no queda nada en la carpeta de instalación (lo cubre G9 con más detalle).
- [ ] **Paso 6:** commit `Añade el instalador de Inno Setup (G8)`.

### Tarea 4: ZIP portable y SHA-256

- [ ] **Paso 1: test** `test_checksums_file_format` sobre una función de `build.ps1` replicada en
  Python en `packaging/windows/checksums.py` (`write_checksums(paths, out) -> None`, formato
  `<sha256>  <nombre>` por línea, orden alfabético): comprobar con ficheros de prueba y con
  `sha256sum -c` / `Get-FileHash` equivalente.
- [ ] **Paso 2-4:** falla → implementa → pasa. Nombres de artefacto:
  `OSINEITOR-<versión>-setup.exe`, `OSINEITOR-<versión>-portable.zip`, `SHA256SUMS.txt`.
- [ ] **Paso 5:** commit `Genera el ZIP portable y las sumas SHA-256 (G8)`.

### Tarea 5: CI de lanzamiento

- [ ] **Paso 1: test** `test_release_workflow_has_windows_job_after_tests`: `release.yml` define el
  job `windows` con `runs-on: windows-latest`, `needs: build` y sube los tres artefactos; el job de
  PyPI **no** depende de `windows` (un fallo del instalador no bloquea PyPI) y ningún paso usa
  secretos de firma.
- [ ] **Paso 2:** ejecuta → falla.
- [ ] **Paso 3:** añade el job: `pip install -e ".[gui,build]"`, `build.ps1`, `smoke.py`, `ISCC`,
  `checksums.py`, `actions/upload-artifact@v4` y adjunta a la release de GitHub
  (`gh release upload`, permisos `contents: write` solo en este job).
- [ ] **Paso 4:** pasa. **Paso 5:** prueba en una rama con una etiqueta `v0.0.0-test` en un fork o con
  `workflow_dispatch` (añade el disparador manual sin publicar) y revisa los artefactos.
- [ ] **Paso 6:** commit `Construye el instalador de Windows en la CI de lanzamiento (G8)`.

### Tarea 6: documentación y cierre

- [ ] `docs/PUBLICACION.md` (cómo se construye y publica), `docs/USO.md`/`README.md` (instalar,
  verificar el SHA-256 con `Get-FileHash`, aviso de SmartScreen), `docs/GUI.md` (nombres de los
  ejecutables, PR-F hecho), `ROADMAP.md` (G8) y `CHANGELOG.md`.
- [ ] `ruff check . && ruff format --check . && python -m pytest -q` → verde.
- [ ] Commit `Cierra G8: instalador de Windows`.

## Qué no cubre

- Firma de código (tarea del autor), actualizaciones automáticas (fuera del hito), instalador para
  ARM64 o macOS/Linux.
- Verlo instalado en un Windows real: lo hace G9.

## Riesgos

- Es la tarea con más incertidumbre del hito: nadie ha congelado aún este código. Si el descubrimiento
  de módulos falla en el bundle, el arreglo toca `registry.py` (código del motor, fuera del alcance de
  este plan): **para y pregunta** antes de modificarlo.
- Antivirus: los `.exe` de PyInstaller sin firmar generan falsos positivos con frecuencia. Se
  documenta; no hay mitigación técnica dentro de este plan.

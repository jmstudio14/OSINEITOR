# Changelog

Todos los cambios relevantes del proyecto. Formato basado en
[Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y versionado
[SemVer](https://semver.org/lang/es/).

## [Sin publicar]

### Corregido

- **`dns`:** si el resolvedor contesta `REFUSED`, el error lo dice («el resolvedor DNS rechazó la
  consulta de <dominio> (REFUSED)») en vez de «tiempo agotado o sin servidores». Afecta también a
  `osineitor doctor`.

## [0.2.0] - 2026-10-29

Fases 1a (seguridad y datos) y 1b (fiabilidad) del roadmap y contrato CLI↔GUI (v0.2.0).

### Añadido

- **Contrato CLI↔GUI (Hito G1, F1.17, F8.4):** [`docs/CLI_CONTRACT.md`](docs/CLI_CONTRACT.md) y
  [`docs/cli-contract.schema.json`](docs/cli-contract.schema.json), validado en los tests contra la
  salida real de la CLI.
  - `--ndjson` (eventos `scan.start`, `module.start/end`, `entity`, `progress`, `notice`,
    `scan.end`), `--quiet`, `--control-stdin` y `--no-color`.
  - `--json` también en `modules`, `history`, `show`, `doctor`, `config show`, `version` y
    `export`. `config show --json` solo lista nombres de keys.
  - **Cancelación ordenada:** `{"cmd": "cancel"}` por stdin, el cierre de stdin y Ctrl+C detienen
    el scan, guardan lo ya obtenido y terminan con código 130. Probado con un proceso hijo real.
  - **Códigos de salida:** `0` ok, `1` error interno, `2` uso incorrecto, `3` algún módulo falló,
    `4` resultado incompleto por presupuesto, `130` cancelado. `ScanResult.status`
    (`complete`/`truncated`/`cancelled`) acompaña a cada resultado en JSON.
- ROADMAP: **Hito G · Aplicación de escritorio para Windows** (G1–G9), con la excepción al
  principio 8; F11.1 «interfaz web local» queda obsoleto.

- **Health check semanal (F1.3):** el workflow `.github/workflows/doctor.yml` ejecuta
  `osineitor doctor` cada lunes (y a demanda) y mantiene un único issue con la etiqueta
  `salud-fuentes` con las fuentes que fallan; lo actualiza mientras sigan fallando y lo cierra
  cuando se recuperan. Un fallo de fuente no pone el job en rojo.

- **Estado por módulo (F1.1):** cada ejecución deja un `ModuleRun` (`ok`, `empty`, `error`,
  `quota`, `skipped`) con entidades, peticiones, aciertos de caché y duración; se muestra en una
  tabla tras el scan y se guarda en la nueva tabla `module_runs`. Nueva excepción `ModuleQuota`
  (HTTP 429) y helper `status_error`.
- **`osineitor doctor` (F1.2):** prueba cada módulo con un valor de prueba conocido (o comprueba
  que la fuente responde) y sale con código 3 si alguno falla.
- **Migraciones de esquema (F1.4):** `PRAGMA user_version` con migraciones transaccionales; una
  base de la v0.1.0 se actualiza sin perder datos y una de una versión más nueva se rechaza.
- **Caché HTTP (F1.5):** respuestas GET de fuentes pasivas y sin key, 6 h, en `cache.db`, sin
  guardar URLs ni claves. `--no-cache`, `--refresh` y `osineitor cache clear|info`.
- **Límites por fuente (F1.6):** cada módulo accede a HTTP mediante su propia vista
  (`HttpClient.bind`) con caché, contador de peticiones y `min_interval` propios.
- **Timeout por módulo (F1.7):** 180 s por defecto (240 s `crtsh`/`wayback`, 400 s
  `username_sites`); al excederlo se registra como error y el scan continúa.
- **Falsos positivos en usernames (F1.10):** cada positivo se contrasta con un username
  inexistente; si el sitio también lo encuentra se descarta; el perfil lleva `verified`.
- `modules/_manifest.py`: lista explícita de módulos para el ejecutable empaquetado, con un test
  que la contrasta con el disco.

- **Saneado de entradas (F1.11):** el username se codifica como un único segmento en las URLs
  de las ~460 firmas; un valor no válido se rechaza como error de uso antes de lanzar nada.
- **Normalización de entidades (F1.12):** dominios en minúsculas y punycode (IDNA 2008), IPs,
  emails y URLs en forma canónica. `münchen.de` y `xn--mnchen-3ya.de` son la misma entidad.
- **Guardia de red (F1.13):** ninguna petición va a IPs privadas, loopback, link-local ni al
  servicio de metadatos cloud, tampoco a través de redirecciones (que ahora se siguen y
  comprueban salto a salto). `--allow-private` lo desactiva. Las redirecciones a otro origen no
  reenvían cabeceras de la petición.
- **Presupuesto de escaneo (F1.14):** `--max-entities` (2000), `--max-requests` (3000) y
  `--max-time` (900 s), `0` = sin límite. Al agotarse, el scan se detiene de forma ordenada,
  conserva lo ya terminado y queda marcado como incompleto (`truncated`).
- `osineitor/errors.py` con las excepciones compartidas y `ModuleSkipped` para «no aplica».
- `Module.try_emit` para datos de terceros que pueden no ser válidos.
- CI en Windows (3.11 y 3.13) además de Linux, y `.gitattributes` con finales de línea LF.
- `docs/PRUEBAS_WINDOWS.md`: estado de verificación en vivo de cada módulo (varios no se han
  podido comprobar desde el entorno de desarrollo), pasos para clonar en VS Code y probar desde
  Windows, y tabla para registrar los resultados.

- **Capa no visual de la aplicación de escritorio (G2–G7, parte sin pantalla)** en
  `src/osineitor_gui/`, en Python puro y probada contra la CLI real: localizador de la CLI,
  `CliProcess` (eventos, cancelación ordenada con escalada a `terminate`/`kill`), `CliApi` para las
  órdenes `--json`, `ScanRequest` (valida y exige confirmar `--active` y `--allow-private`),
  `ScanSession` (estado para las vistas, igual para scans en vivo y guardados), `GuiSettings` y
  textos legales. [`docs/GUI.md`](docs/GUI.md) recoge el diseño de la ventana y el traspaso a las
  vistas. Extra opcional `gui` (`PySide6-Essentials`), aún sin usar.
- `config set NOMBRE --stdin` lee la API key de stdin para que no aparezca en la línea de
  comandos, y `config unset NOMBRE` la elimina; ambas con `--json`.

### Cambiado

- **Documentación:** el README se reorganiza como portada (estado del proyecto, instalación,
  inicio rápido, módulos y limitaciones) y el detalle de uso pasa a [`docs/USO.md`](docs/USO.md).
  La guía para añadir un módulo pasa a `CONTRIBUTING.md`, actualizada (manifiesto, `canary`,
  `ModuleQuota`). Un test comprueba que los enlaces y las órdenes de la documentación existen.

- **Códigos de salida:** un scan que termina con módulos fallidos devuelve ahora `3` (antes `0`) y
  uno truncado `4`; `doctor` con fallos devuelve `3` (antes `2`). Los scripts que comprobaban el
  código de salida deben tolerarlo.
- Versión `0.2.0`; `jsonschema` entra en las dependencias de desarrollo.

- **RDAP (F1.18):** el módulo consulta el bootstrap de IANA (con caché de 7 días) y para los TLD
  sin servidor RDAP (`.es`, `.io`, `.de`…) queda **omitido con un aviso** en lugar de devolver
  un vacío silencioso.
- **Rutas multiplataforma (F1.16):** configuración en `%APPDATA%\osineitor` y datos en
  `%LOCALAPPDATA%\osineitor` en Windows (con `platformdirs`); en Linux no cambia. Se pueden
  fijar con `OSINEITOR_CONFIG_DIR` y `OSINEITOR_DATA_DIR`.
- `crtsh` descarta los hostnames no válidos en lugar de emitirlos.
- `dns` falla con error cuando el resolvedor no responde (antes devolvía un vacío que parecía
  «sin registros»). Un 429 de cualquier fuente se registra ahora como `quota`, no como error.
- `username_sites` conserva los perfiles ya encontrados si se agota el presupuesto.
- Dependencias nuevas: `platformdirs` e `idna`.

### Corregido

- **Windows:** la CLI forzaba la codificación local (cp1252) cuando su salida iba a una tubería,
  de modo que un `✓` o una letra cirílica provocaban un `UnicodeEncodeError`. Ahora escribe
  siempre en UTF-8. Añadido `python -m osineitor`.
- Un username derivado de un email con caracteres como `/`, `?` o `#` ya no puede alterar la
  ruta de las URLs consultadas.

## [0.1.1] - 2026-10-29

Fase 0 del roadmap, la parte que no necesita red.

### Añadido

- `tests/test_cli.py`: tests de todas las órdenes de la CLI con módulos falsos (cobertura de
  `cli.py` del 99 %) (F0.4).
- `scripts/rdap_coverage.py` y `docs/RDAP_COBERTURA.md`: cobertura RDAP por TLD según el
  bootstrap de IANA del 28-10-2026 (F0.6).
- `scripts/fp_baseline.py`: medición de la línea base de falsos positivos de `username_sites`
  (F0.5). El script está listo; la medición hay que hacerla desde una red con acceso a los sitios.
- `tests/test_scripts.py` y la dependencia de desarrollo `pytest-cov`.
- `ROADMAP.md` con las fases posteriores al MVP, basado en una investigación del estado del
  arte OSINT y en un análisis de carencias del código: 12 fases (0 a 11), 134 entregables con
  prioridad *M*/*S*/*C*, deuda técnica D8–D14 y un corte recomendado en v0.5.0.

### Corregido

- `docs/MODULES.md`: la limitación de `rdap` ahora lista los TLD sin RDAP verificados en IANA
  (antes mencionaba solo `.es`).

## [0.1.0] - 2026-10-28

Primera versión.

### Añadido

- Núcleo: modelo de entidades, engine con pivoteo por niveles (`--depth`), deduplicación y fusión
  de datos entre fuentes, descubrimiento automático de módulos y persistencia en SQLite.
- CLI: `scan` (detección automática del tipo), `domain`, `ip`, `email`, `username`, `modules`,
  `history`, `show`, `export`, `config set|show` y `version`.
- Módulos sin API key: `rdap`, `dns`, `crtsh`, `wayback`, `http_fingerprint` (activo), `ipinfo`,
  `internetdb`, `email_validate`, `gravatar` y `username_sites` (firmas de Sherlock, MIT).
- Módulos con API key: `shodan`, `abuseipdb`, `greynoise`, `hibp`, `hunter_verify` y
  `hunter_domain`.
- Informes exportables a JSON, Markdown y HTML.
- CI con ruff y pytest en Python 3.11 y 3.13.

[Sin publicar]: https://github.com/jmstudio14/OSINEITOR/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/jmstudio14/OSINEITOR/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/jmstudio14/OSINEITOR/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/jmstudio14/OSINEITOR/releases/tag/v0.1.0

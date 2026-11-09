# Arquitectura

## Visión general

```
CLI (cli.py) ──► Engine (engine.py) ──► Módulos (modules/**)
     │                 │                     │
     │                 │                     ├─► HttpClient (http.py) ─► APIs externas
     │                 │                     └─► Resolver DNS (dnspython)
     │                 ▼
     │           ScanResult (models.py)
     ▼
Storage (storage.py, SQLite) ──► Informes (report/: JSON, Markdown, HTML, CSV, grafo, STIX, MISP)
```

| Fichero | Responsabilidad |
|---|---|
| `models.py` | `EntityType`, `Entity`, `ScanEvent`, `ModuleRun`, `ScanResult` y `detect_type()` |
| `config.py` | API keys y ajustes desde TOML o variables de entorno; rutas por sistema (`platformdirs`) |
| `errors.py` | Excepciones: `ModuleError`, `ModuleSkipped`, `ModuleQuota`, `NetworkGuardError`, `BudgetExceeded`, `InvalidEntityValue`, `ExportUnavailable` |
| `sanitize.py` | Saneado de usernames y codificación de valores que viajan a URLs |
| `normalize.py` | Forma canónica de cada tipo de entidad: dominios (IDNA), IPs, emails, URLs, ASN, redes CIDR, huellas de certificado, teléfonos (E.164) y textos |
| `presets.py` | Presets de escaneo (`--preset`): YAML incluidos en `data/presets/` y los del usuario |
| `datasets.py` | `osineitor update-data`: datasets de terceros con versión, hash y licencia registrados |
| `netguard.py` | Guardia de red: rechaza IPs privadas, loopback y metadatos cloud |
| `budget.py` | Presupuesto del scan: entidades, peticiones y tiempo |
| `confidence.py` | Nivel de confianza (`bajo`/`medio`/`alto`) de cada entidad |
| `evidence.py` | Evidencias de `--evidence`: URL sin keys, SHA-256 y comprobación posterior (`osineitor verify`) |
| `scope.py` | Alcance declarado de `--scope scope.yml`: qué dominios y redes entran en un scan |
| `logs.py` | Registro estructurado (`--verbose`, `--log-file`) con las API keys enmascaradas |
| `http.py` | Cliente `httpx` asíncrono: guardia, redirecciones comprobadas, reintentos, límite por host y presupuesto |
| `modules/base.py` | Contrato `Module` (`emit` y `try_emit`) y `Context` |
| `modules/_external.py` | `ExternalToolModule`: base para adaptadores de herramientas externas |
| `modules/_manifest.py` | Lista explícita de ficheros de módulos (un test la contrasta con el descubrimiento) |
| `registry.py` | Descubre las subclases de `Module` en `osineitor.modules` y las de los plugins del grupo de *entry points* `osineitor.modules` |
| `engine.py` | Ejecuta los módulos, pivota por niveles, deduplica y registra incidencias |
| `events.py` | Eventos del contrato CLI y `NdjsonSink` (salida NDJSON) |
| `control.py` | Lectura de órdenes por stdin (`--control-stdin`) para cancelar un scan |
| `cache.py` | Caché HTTP en SQLite (`cache.db`) |
| `doctor.py` | Comprobaciones de `osineitor doctor` sobre cada módulo |
| `scanner.py` | `Scanner`: API de librería (`scan`, `ascan`, `cancel`); la vigilancia la reutiliza |
| `findings.py` | Motor de hallazgos: reglas YAML de `data/rules/` evaluadas sobre las entidades (las usa el analizador `findings` y las alertas de `watch`) |
| `diff.py` | `osineitor diff`: entidades y hallazgos nuevos, desaparecidos y modificados entre dos scans |
| `risk.py` | `osineitor risk`: puntuación orientativa de 0 a 100 por dominio o IP |
| `resolve.py` | `osineitor resolve`: hipótesis de cuentas que podrían ser de la misma persona |
| `timeline.py` | `osineitor timeline`: fechas de los datos de un scan en orden cronológico |
| `tool_import.py` | `osineitor import subfinder` y `import maigret`: leen la salida JSON de esas herramientas y la convierten en un `ScanResult` (sin red, sin pivoteo) |
| `mcp_server.py` | `osineitor mcp`: servidor MCP por stdio (consulta y scans pasivos; sin módulos activos) |
| `pivots.py` | `osineitor suggest`: propone qué investigar a continuación sin ejecutarlo |
| `targets.py` | Lee la lista de `scan --targets-file` |
| `nmap_import.py` | `osineitor import nmap`: lee un XML de Nmap y lo convierte en un `ScanResult` (sin red, sin pivoteo) |
| `crypto_address.py` | Reconoce y valida direcciones de criptomonedas |
| `watch.py` | Vigilancia continua (`osineitor watch`): qué es nuevo y qué avisar ([VIGILANCIA.md](VIGILANCIA.md)) |
| `notify.py` | Notificadores de la vigilancia: webhook, correo SMTP y fichero NDJSON |
| `ai.py` | Resumen con IA (`osineitor summarize`): consentimiento, hechos numerados y validación de citas ([IA.md](IA.md)) |
| `storage.py` | Guarda y recupera scans en SQLite |
| `report/` | Exportadores a JSON, Markdown, HTML (con grafo interactivo), CSV, grafos (GraphML, GEXF, Cypher), STIX 2.1, MISP, superficie de ataque y resumen ejecutivo |
| `cli.py` | Comandos de Typer y salida con Rich |
| `__main__.py` | Permite ejecutar la CLI con `python -m osineitor` |

La aplicación de escritorio vive aparte, en `src/osineitor_gui/`, y solo habla con la CLI
mediante el contrato; su diseño está en [GUI.md](GUI.md).

## Modelo de datos

Todo lo que se descubre es una `Entity`:

| Campo | Descripción |
|---|---|
| `type` | `domain`, `ip`, `email`, `username`, `url`, `profile`, `service`, `vulnerability`, `breach`, `record`, `asn`, `netblock`, `certificate`, `technology`, `organization`, `person`, `phone`, `crypto_address`, `file`, `location` o `finding` |
| `value` | Valor identificador (`example.com`, `1.1.1.1:443`, `CVE-2024-0001`…) |
| `data` | Diccionario libre con los detalles que aporta la fuente |
| `source` | Nombre del primer módulo que la vio |
| `parent` | Clave de la entidad de la que se derivó (traza del pivoteo) |
| `observations` | Todas las veces que un módulo la vio: `module`, `query` (clave de la entidad sobre la que corrió) y `at` (UTC) |
| `confidence` | `bajo`, `medio` o `alto`; lo calcula el motor al terminar el scan (`confidence.py`). `null` en scans antiguos |
| `first_seen`, `last_seen` | Primera y última `at` de las observaciones (se derivan, no se guardan). `null` si el dato es de un scan anterior a las observaciones |

La clave de identidad es `"<type>:<value en minúsculas>"`. Las entidades `record` agrupan la
información de una fuente sobre otra entidad (p. ej. `dns:example.com`).

**Observaciones.** `Module.emit` crea cada entidad con una observación `(módulo, entidad consultada,
hora)`. Si otro módulo —o el mismo desde otra entidad— vuelve a ver lo mismo, el motor no crea un
duplicado: suma su observación a la existente (`Engine._observe`). El mismo módulo sobre la misma
entidad consultada cuenta una sola vez. `Entity.sources` devuelve los módulos distintos, en orden de
llegada, y es lo que muestran la tabla de la CLI y los informes; para un dato guardado antes de
existir las observaciones cae en `source`. `source` se mantiene (contrato aditivo) y no cambia.
`first_seen` y `last_seen` son la frescura **del scan**; las fechas que aportan los terceros
(`rdap.created`, `shodan.last_update`, `wayback.first_seen`…) siguen en `data` con su propio nombre.

**Confianza.** `Engine.run` asigna a cada entidad un nivel con `confidence.assess` al terminar:
puntos = fuentes distintas + 1 si alguna es autoritativa (`Module.authority`: `dns`, `rdap`,
`whois`, `mail_security`, `http_fingerprint`, `email_validate`, `ptr`, `web_meta`,
`analytics_ids`, `takeover` y `tech_detect`; el resto `aggregated`); 3 o más es `alto`, 2 `medio`, 0 o 1
`bajo`. Si el dato es de hace más de 90 días baja un nivel: la fecha es la que aporta el tercero
(`last_update`, `last_seen`, `last_reported`, `seen`) o, si no la hay, `last_seen`. Un módulo nuevo
que lea de quien administra el dato debe declarar `authority = "authoritative"`. Es una heurística
para priorizar la revisión, no una probabilidad de que el dato sea cierto.

**Evidencias.** Con `--evidence` el motor crea cada `RunStats` con una lista (`RunStats.evidence`);
`HttpClient._send` añade a ella la respuesta definitiva de cada salto y los módulos sin `ctx.http`
(`dns`, `email_validate`) usan `Module.record_evidence`. Al terminar la ejecución, `Engine._record`
copia esas `Evidence` a `ScanResult.evidence` con el módulo y la entidad consultada, que son los
mismos `module` y `query` de las `Observation`. El cuerpo no sale en JSON. Ver
[EVIDENCIA.md](EVIDENCIA.md).

**Alcance.** `--scope scope.yml` carga un `scope.Scope` (YAML con `domains`, `ips` y `exclude`, leído
con `yaml.safe_load` y validado de forma estricta). `Engine._absorb` consulta `Scope.allows` antes de
admitir una entidad nueva: la que cae fuera no entra en `result.entities`, así que tampoco se pivota
ni se emite por NDJSON; solo deja un evento `skipped` por clave. El host que decide es el propio valor
(dominio, IP), la parte tras `@` (email), el host de la URL o el de `host:puerto` (service); un dominio
cuenta si es igual o subdominio de uno declarado, no por sufijo de texto. Los tipos sin host (`record`,
`profile`, `username`, `breach`, `vulnerability`) heredan. Una lista ausente no restringe ese tipo y
`exclude` gana siempre. La semilla fuera de alcance es un error de uso. **Límite:** el alcance filtra
lo que se descubre, no hacia dónde redirige un servidor: eso lo sigue controlando la guardia de red.

## Contrato de un módulo

```python
class Module(ABC):
    name: ClassVar[str]  # único; se usa en --module
    description: ClassVar[str]
    consumes: ClassVar[frozenset[EntityType]]
    produces: ClassVar[frozenset[EntityType]]
    requires_key: ClassVar[str | None] = None
    passive: ClassVar[bool] = True
    timeout: ClassVar[float] = 180.0  # segundos máximos por ejecución
    cache_ttl: ClassVar[int] = 6 * 3600  # caché de respuestas GET; 0 la desactiva
    min_interval: ClassVar[float] = 0.0  # segundos mínimos entre peticiones a su fuente
    direct_dns: ClassVar[bool] = False  # sale a la red sin `ctx.http`: se omite con --proxy
    analyzer: ClassVar[bool] = False  # pase final offline sobre lo ya recogido (ver abajo)
    authority: ClassVar[Literal["authoritative", "aggregated"]] = "aggregated"  # pesa en confianza
    canary: ClassVar[str | None] = None  # valor de prueba para `doctor`
    probe_url: ClassVar[str | None] = None  # alternativa: solo comprobar que la fuente responde

    def accepts(self, entity) -> bool: ...  # filtro extra sobre consumes
    async def run(self, entity) -> list[Entity]: ...

    @classmethod
    def unavailable(cls) -> str | None: ...  # motivo por el que no puede correr aquí; None si puede
```

- `self.ctx` da acceso a `config`, `http` y `resolver`. El engine da a cada módulo su propio
  `ctx.http` (`SourceHttp`): aplica la caché y `min_interval` de su fuente y cuenta sus peticiones.
  Un módulo con API key o activo nunca usa caché.
- `self.api_key` devuelve la key de `requires_key`.
- `self.emit(parent, tipo, valor, **datos)` crea una entidad con `source` y `parent` rellenos.
- `self.record_evidence(url, cuerpo)` guarda para `--evidence` lo que no pasa por `ctx.http` (las
  consultas DNS); las peticiones HTTP las captura el cliente.
- `unavailable()` permite a un módulo declararse inutilizable en este equipo (p. ej. falta su
  herramienta externa): el engine lo omite con ese motivo y `doctor` lo marca `omitido`.
- `accepts()` evita trabajo redundante al pivotear. Los módulos de dominio usan
  `is_root_domain()` para no relanzar crt.sh, Wayback o RDAP sobre cada subdominio descubierto
  (que llevan `data["subdomain"] = True`).

## Engine y pivoteo

1. Al construirse, el engine descarta los módulos activos (salvo `--active`), los que no tienen
   su API key, los de conexión directa si hay `--proxy` y los que declaran `unavailable()`, y los
   registra como eventos `skipped`.
2. Nivel 1: ejecuta en paralelo todos los módulos que aceptan la entidad semilla. Si la semilla es
   una URL, su host (dominio o IP) entra también en el nivel 1 (`models.decompose`).
3. Las entidades nuevas forman el siguiente nivel. Se repite hasta `depth` niveles o hasta que no
   aparezca nada nuevo.
4. **Deduplicación:** si una entidad ya existe, no se vuelve a investigar; sus datos se fusionan
   rellenando los campos vacíos de la existente. Si dos fuentes discrepan en un campo, gana la de
   menor `rank` (el orden de los módulos), llegue cuando llegue.
5. **Errores:** cualquier excepción de un módulo se captura y se guarda como evento `error`; el scan
   continúa. `ModuleSkipped` se registra como `skipped` (no aplica), no como error.
6. **Estado por módulo:** cada ejecución (módulo × entidad) deja un `ModuleRun` con su estado
   (`ok`, `empty`, `error`, `skipped`, `quota`), entidades, peticiones, aciertos de caché y
   duración. Los módulos que no arrancaron (activo sin `--active`, sin key) también constan.
   Un módulo que excede su `timeout` se cancela y queda como `error`.
7. **Analizadores:** al terminar los niveles, un pase final ejecuta los módulos con
   `analyzer = True` sobre la semilla y todo lo recogido. Su contexto es `Offline` (cualquier uso de
   `http` o `resolver` es un `ModuleError`), no consumen presupuesto de peticiones y siguen
   corriendo aunque se haya agotado (salvo cancelación). Lo que emiten no se pivota.
8. **Presupuesto:** si se agota (entidades, peticiones o tiempo) el scan se detiene de forma
   ordenada: se cancelan los módulos pendientes, **se conserva lo que ya había terminado** y el
   resultado queda con `truncated = true` y un evento `budget`.

**Herramientas externas.** `ExternalToolModule` (`modules/_external.py`) ejecuta un binario que
instala el usuario: sin shell, con el `timeout` del módulo (al agotarse se mata el proceso), sin
las variables `OSINEITOR_*` en el entorno y con la salida interpretada como JSON o NDJSON. Declara
`binary` y, si hace falta, `min_version`; sin el binario o con una versión menor el módulo queda
`omitido`, no `error`. Su tráfico no pasa por `ctx.http` (ni presupuesto, ni guardia de red, ni
evidencia): con `--proxy` se omite. No se empaqueta ningún binario.

Todo valor de entidad se **normaliza al crearse** (`normalize.canonical`), así que dos escrituras
del mismo dato son una sola entidad. Los datos de terceros se emiten con `Module.try_emit`, que
descarta un valor no válido sin perder el resto del resultado.

Concurrencia: 10 tareas de módulo simultáneas como máximo; además `HttpClient` limita a 4
peticiones simultáneas por host y reintenta (2 veces, con espera exponencial) ante errores de red
y respuestas 429/5xx. `username_sites` usa su propio límite de 30 comprobaciones simultáneas.

Ejemplo con `osineitor scan alguien@acme.io --depth 2`:

```
email alguien@acme.io
├─ email_validate ─► domain acme.io ─► dns ─► ip 203.0.113.10 (no se expande: nivel 3)
│                 └► username alguien ─► username_sites ─► profile https://github.com/alguien
└─ gravatar ─► profile https://gravatar.com/alguien
```

## Eventos y cancelación

`Engine` acepta `on_event`, un callback que recibe los eventos del contrato
([CLI_CONTRACT.md](CLI_CONTRACT.md)): `scan.start`, `module.start/end`, `entity` y `progress`.
`events.NdjsonSink` los escribe como NDJSON en stdout; el CLI añade `notice` y `scan.end`, que
necesitan datos que el motor no tiene (el aviso legal, el `scan_id` tras guardar).

`Engine.cancel()` detiene el scan de forma ordenada: espera a que se resuelva la petición de
cancelar, cancela las tareas en curso, **conserva lo que ya había terminado** y añade un evento
`cancelled`. `ScanResult.status` resume el resultado (`cancelled` > `truncated` > `complete`).
`control.watch_stdin` lanza un hilo demonio que lee stdin con `os.read` (no con `sys.stdin`, para no
abortar el intérprete al salir) y llama a `cancel` al recibir `{"cmd": "cancel"}` o al cerrarse
stdin. `cli.exit_code_for` traduce el resultado al código de salida.

## Persistencia

SQLite en `osineitor.db` dentro del directorio de datos (`%LOCALAPPDATA%\osineitor` en Windows,
`~/.local/share/osineitor` en Linux), o la ruta de `--db`. Tablas:

- `scans`: objetivo, profundidad y fechas; `scope` (JSON) con el alcance declarado, desde la
  versión 6, y `purpose` con el propósito del scan, desde la 7.
- `entities`: entidades del scan; `data` y `observations` en JSON (esta, desde la versión 3; los
  scans anteriores quedan con `[]` y se muestran con su `source`). `confidence` es el nivel
  `bajo`/`medio`/`alto`, desde la versión 5 (los scans anteriores quedan sin nivel).
- `events`: errores, módulos omitidos y, según cómo termine el scan, un evento `budget`
  (truncado) o `cancelled`.
- `module_runs`: el `ModuleRun` de cada ejecución (estado, entidades, peticiones, caché, ms).
- `evidence`: respuesta original de cada fuente con su SHA-256 y el cuerpo (BLOB), desde la
  versión 4. Solo se rellena con `--evidence`.
- `watch_targets` y `watch_seen`, desde la versión 8: por objetivo vigilado, la última ejecución y
  las claves de entidad que la vigilancia ya conoce. `osineitor purge` no las toca.
- `watch_pending`, desde la versión 9: entidades nuevas que esperan una segunda ejecución
  (`confirm`).
- `cases`, `case_scans` y `case_notes`, desde la versión 10: los casos, los scans que agrupan y sus
  notas; la versión 10 añade también el índice `idx_entities_value` para `osineitor search`.

**Migraciones.** El esquema se versiona con `PRAGMA user_version`: `storage.MIGRATIONS` es una
lista donde la posición es la versión y cada migración se aplica en una transacción. Una base de
la v0.1.0 (versión 0) se actualiza sola sin perder datos; una de una versión más nueva se rechaza.
El esquema está hoy en la versión 11 (índices para `history --json`). Nunca se edita una migración ya publicada: los cambios van al final de la lista. Un tipo de
entidad nuevo no necesita migración: `entities.type` es texto sin restricción y el valor se
normaliza al cargarlo. Una base con tipos nuevos no la lee un OSINEITOR anterior.

**Caché HTTP.** `cache.db` (mismo directorio) guarda respuestas GET con éxito y su caducidad,
indexadas por el hash de la petición. No guarda la URL ni cabeceras, así que una API key que
viajara en la consulta no queda en disco.

## Configuración

Orden de prioridad para cada key: variable `OSINEITOR_<NOMBRE>_KEY` → sección `[keys]` de
`config.toml` del directorio de configuración (`%APPDATA%\osineitor` en Windows). La sección
`[settings]` admite `timeout` (segundos), `user_agent` y `require_purpose`.

**Presets.** `--preset NOMBRE` aplica un perfil (módulos, profundidad, presupuesto y si admite
módulos activos). Los incluidos están en `src/osineitor/data/presets/`; los tuyos van en
`presets/*.yml` del directorio de configuración y uno con el mismo nombre sustituye al incluido.
Lo que indiques en la línea de órdenes manda sobre el preset, y `allow_active: true` solo
*admite* los módulos activos: sigue haciendo falta `--active`. `osineitor presets` los lista.

**Datasets.** `osineitor update-data` descarga los datasets de terceros a `datasets/` del
directorio de datos y anota en `manifest.json` su versión, SHA-256, licencia y URL. Solo instala
los de licencia compatible con MIT, más los feeds públicos de rangos de IP (licencia `public-feed`,
sin hash fijo porque cambian a diario); los demás se rechazan sin descargar. Quien los lee usa
`datasets.installed_path`, que ignora un fichero cuyo hash no coincide con el registrado. Un
dataset con `discover` averigua su URL en cada comprobación (Azure, desde la página de descarga) y
no descarga si coincide con la del manifiesto. El callback de la CLI llama a
`datasets.auto_update` al arrancar cada orden: comprueba `AUTO_UPDATE` como mucho una vez al día
(sello `datasets/auto-update.json`), salvo con `--proxy`, en `mcp`, en `update-data` o con
`OSINEITOR_NO_AUTO_UPDATE`. Si la página no trae el enlace, `_azure_guess` prueba con HEAD la ruta
conocida para los últimos 14 días. Los fallos y los rangos con más de 14 días
(`datasets.azure_published`) se avisan por stderr.

Las variables `OSINEITOR_CONFIG_DIR` y `OSINEITOR_DATA_DIR` sustituyen los directorios de
configuración y de datos (base de datos y caché) por la ruta indicada.

## Decisiones de diseño

- **Plugins por tipos de entidad** en lugar de flujos fijos: añadir una fuente no requiere tocar
  el engine y el pivoteo sale del propio contrato.
- **Pasivo por defecto**: el reconocimiento no debe alertar al objetivo salvo que se pida.
- **SQLite y ficheros planos**: sin servicios externos que instalar.
- **Firmas de usernames de Sherlock**: mantener cientos de firmas a mano no es viable; se reutiliza
  un conjunto mantenido por la comunidad.

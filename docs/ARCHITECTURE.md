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
Storage (storage.py, SQLite) ──► Informes (report/: JSON, Markdown, HTML)
```

| Fichero | Responsabilidad |
|---|---|
| `models.py` | `EntityType`, `Entity`, `ScanEvent`, `ModuleRun`, `ScanResult` y `detect_type()` |
| `config.py` | API keys y ajustes desde TOML o variables de entorno; rutas por sistema (`platformdirs`) |
| `errors.py` | Excepciones: `ModuleError`, `ModuleSkipped`, `ModuleQuota`, `NetworkGuardError`, `BudgetExceeded`, `InvalidEntityValue` |
| `sanitize.py` | Saneado de usernames y codificación de valores que viajan a URLs |
| `normalize.py` | Forma canónica de dominios (IDNA), IPs, emails y URLs |
| `netguard.py` | Guardia de red: rechaza IPs privadas, loopback y metadatos cloud |
| `budget.py` | Presupuesto del scan: entidades, peticiones y tiempo |
| `http.py` | Cliente `httpx` asíncrono: guardia, redirecciones comprobadas, reintentos, límite por host y presupuesto |
| `modules/base.py` | Contrato `Module` (`emit` y `try_emit`) y `Context` |
| `modules/_manifest.py` | Lista explícita de ficheros de módulos (un test la contrasta con el descubrimiento) |
| `registry.py` | Descubre las subclases de `Module` en `osineitor.modules` |
| `engine.py` | Ejecuta los módulos, pivota por niveles, deduplica y registra incidencias |
| `events.py` | Eventos del contrato CLI y `NdjsonSink` (salida NDJSON) |
| `control.py` | Lectura de órdenes por stdin (`--control-stdin`) para cancelar un scan |
| `cache.py` | Caché HTTP en SQLite (`cache.db`) |
| `doctor.py` | Comprobaciones de `osineitor doctor` sobre cada módulo |
| `storage.py` | Guarda y recupera scans en SQLite |
| `report/` | Exportadores a JSON, Markdown y HTML |
| `cli.py` | Comandos de Typer y salida con Rich |

La aplicación de escritorio vive aparte, en `src/osineitor_gui/`, y solo habla con la CLI
mediante el contrato; su diseño está en [GUI.md](GUI.md).

## Modelo de datos

Todo lo que se descubre es una `Entity`:

| Campo | Descripción |
|---|---|
| `type` | `domain`, `ip`, `email`, `username`, `url`, `profile`, `service`, `vulnerability`, `breach` o `record` |
| `value` | Valor identificador (`example.com`, `1.1.1.1:443`, `CVE-2024-0001`…) |
| `data` | Diccionario libre con los detalles que aporta la fuente |
| `source` | Nombre del módulo que la produjo |
| `parent` | Clave de la entidad de la que se derivó (traza del pivoteo) |

La clave de identidad es `"<type>:<value en minúsculas>"`. Las entidades `record` agrupan la
información de una fuente sobre otra entidad (p. ej. `dns:example.com`).

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
    canary: ClassVar[str | None] = None  # valor de prueba para `doctor`
    probe_url: ClassVar[str | None] = None  # alternativa: solo comprobar que la fuente responde

    def accepts(self, entity) -> bool: ...  # filtro extra sobre consumes
    async def run(self, entity) -> list[Entity]: ...
```

- `self.ctx` da acceso a `config`, `http` y `resolver`. El engine da a cada módulo su propio
  `ctx.http` (`SourceHttp`): aplica la caché y `min_interval` de su fuente y cuenta sus peticiones.
  Un módulo con API key o activo nunca usa caché.
- `self.api_key` devuelve la key de `requires_key`.
- `self.emit(parent, tipo, valor, **datos)` crea una entidad con `source` y `parent` rellenos.
- `accepts()` evita trabajo redundante al pivotear. Los módulos de dominio usan
  `is_root_domain()` para no relanzar crt.sh, Wayback o RDAP sobre cada subdominio descubierto
  (que llevan `data["subdomain"] = True`).

## Engine y pivoteo

1. Al construirse, el engine descarta los módulos activos (salvo `--active`) y los que no tienen
   su API key, y los registra como eventos `skipped`.
2. Nivel 1: ejecuta en paralelo todos los módulos que aceptan la entidad semilla.
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
7. **Presupuesto:** si se agota (entidades, peticiones o tiempo) el scan se detiene de forma
   ordenada: se cancelan los módulos pendientes, **se conserva lo que ya había terminado** y el
   resultado queda con `truncated = true` y un evento `budget`.

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

- `scans`: objetivo, profundidad y fechas.
- `entities`: entidades del scan; `data` en JSON.
- `events`: errores, módulos omitidos y, según cómo termine el scan, un evento `budget`
  (truncado) o `cancelled`.
- `module_runs`: el `ModuleRun` de cada ejecución (estado, entidades, peticiones, caché, ms).

**Migraciones.** El esquema se versiona con `PRAGMA user_version`: `storage.MIGRATIONS` es una
lista donde la posición es la versión y cada migración se aplica en una transacción. Una base de
la v0.1.0 (versión 0) se actualiza sola sin perder datos; una de una versión más nueva se rechaza.
Nunca se edita una migración ya publicada: los cambios van al final de la lista.

**Caché HTTP.** `cache.db` (mismo directorio) guarda respuestas GET con éxito y su caducidad,
indexadas por el hash de la petición. No guarda la URL ni cabeceras, así que una API key que
viajara en la consulta no queda en disco.

## Configuración

Orden de prioridad para cada key: variable `OSINEITOR_<NOMBRE>_KEY` → sección `[keys]` de
`config.toml` del directorio de configuración (`%APPDATA%\osineitor` en Windows). La sección
`[settings]` admite `timeout` (segundos) y `user_agent`.

Las variables `OSINEITOR_CONFIG_DIR` y `OSINEITOR_DATA_DIR` sustituyen los directorios de
configuración y de datos (base de datos y caché) por la ruta indicada.

## Decisiones de diseño

- **Plugins por tipos de entidad** en lugar de flujos fijos: añadir una fuente no requiere tocar
  el engine y el pivoteo sale del propio contrato.
- **Pasivo por defecto**: el reconocimiento no debe alertar al objetivo salvo que se pida.
- **SQLite y ficheros planos**: sin servicios externos que instalar.
- **Firmas de usernames de Sherlock**: mantener cientos de firmas a mano no es viable; se reutiliza
  un conjunto mantenido por la comunidad.

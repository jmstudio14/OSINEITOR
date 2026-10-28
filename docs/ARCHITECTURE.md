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
| `models.py` | `EntityType`, `Entity`, `ScanEvent`, `ScanResult` y `detect_type()` |
| `config.py` | API keys y ajustes desde TOML o variables de entorno; rutas XDG |
| `http.py` | Cliente `httpx` asíncrono con reintentos y límite de concurrencia por host |
| `modules/base.py` | Contrato `Module`, `ModuleError` y `Context` |
| `registry.py` | Descubre las subclases de `Module` en `osineitor.modules` |
| `engine.py` | Ejecuta los módulos, pivota por niveles, deduplica y registra incidencias |
| `storage.py` | Guarda y recupera scans en SQLite |
| `report/` | Exportadores a JSON, Markdown y HTML |
| `cli.py` | Comandos de Typer y salida con Rich |

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
    name: ClassVar[str]                      # único; se usa en --module
    description: ClassVar[str]
    consumes: ClassVar[frozenset[EntityType]]
    produces: ClassVar[frozenset[EntityType]]
    requires_key: ClassVar[str | None] = None
    passive: ClassVar[bool] = True

    def accepts(self, entity) -> bool: ...   # filtro extra sobre consumes
    async def run(self, entity) -> list[Entity]: ...
```

- `self.ctx` da acceso a `config`, `http` y `resolver`.
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
   rellenando solo los campos vacíos de la existente.
5. **Errores:** cualquier excepción de un módulo se captura y se guarda como evento `error`; el scan
   continúa.

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

## Persistencia

SQLite en `$XDG_DATA_HOME/osineitor/osineitor.db` (por defecto `~/.local/share/...`), o la
ruta de `--db`. Tablas:

- `scans`: objetivo, profundidad y fechas.
- `entities`: entidades del scan; `data` en JSON.
- `events`: errores y módulos omitidos.

## Configuración

Orden de prioridad para cada key: variable `OSINEITOR_<NOMBRE>_KEY` → sección `[keys]` de
`$XDG_CONFIG_HOME/osineitor/config.toml`. La sección `[settings]` admite `timeout` (segundos) y
`user_agent`.

## Decisiones de diseño

- **Plugins por tipos de entidad** en lugar de flujos fijos: añadir una fuente no requiere tocar
  el engine y el pivoteo sale del propio contrato.
- **Pasivo por defecto**: el reconocimiento no debe alertar al objetivo salvo que se pida.
- **SQLite y ficheros planos**: sin servicios externos que instalar.
- **Firmas de usernames de Sherlock**: mantener cientos de firmas a mano no es viable; se reutiliza
  un conjunto mantenido por la comunidad.

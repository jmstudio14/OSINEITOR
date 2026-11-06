# API de librería y plugins

OSINEITOR se puede usar desde Python sin pasar por la CLI y ampliarse con módulos de terceros
sin tocar su código.

## `Scanner`

```python
from osineitor import Scanner

result = Scanner(depth=2).scan("example.com")  # síncrona
result = await Scanner(depth=2).ascan("example.com")  # asíncrona, dentro de un bucle asyncio

for entity in result.entities:
    print(entity.type, entity.value, entity.confidence, entity.sources)
```

Es la misma maquinaria que `osineitor scan`: módulos incluidos y de plugins, guardia de red (no se
llega a redes privadas), presupuesto, caché, alcance y evidencias. Devuelve un `ScanResult` (el
mismo modelo que produce `--json`, ver [CLI_CONTRACT.md](CLI_CONTRACT.md)).

### Parámetros del constructor

Todos son de solo palabra clave.

| Parámetro | Por defecto | Qué hace |
|---|---|---|
| `depth` | `1` | Niveles de pivoteo |
| `active` | `False` | Permite los módulos que contactan al objetivo |
| `only` | `None` | Nombres de módulos a usar (los demás no corren) |
| `max_entities`, `max_requests`, `max_seconds` | 2000, 3000, 900 | Presupuesto; `None` = sin límite |
| `allow_private` | `False` | Permite redes privadas |
| `use_cache`, `refresh` | `True`, `False` | Caché de respuestas |
| `proxy` | `None` | Proxy HTTP(S) o SOCKS |
| `evidence` | `False` | Guarda la respuesta original de cada fuente (desactiva la caché) |
| `scope` | `None` | `osineitor.scope.Scope`: lo que cae fuera no entra |
| `purpose` | `None` | Para qué se hace el scan (1–500 caracteres, una línea) |
| `config` | `None` | `osineitor.config.Config`; por defecto, la del usuario (API keys incluidas) |
| `on_entity` | `None` | Función llamada con cada entidad nueva |
| `on_event` | `None` | Función llamada con los eventos de la CLI (`scan.start`, `progress`…) |

### Métodos

- `scan(target, type=None)`: ejecuta el scan y devuelve el resultado. No se puede llamar desde un
  bucle asyncio en marcha (lanza `RuntimeError`): allí se usa `ascan`.
- `ascan(target, type=None)`: lo mismo con `await`.
- `cancel()`: detiene el scan en curso conservando lo recogido (`result.status == "cancelled"`).
  Se puede llamar desde otro hilo.

Sin `type`, se deduce de `target` igual que en la CLI (`example.com` → dominio, `1.1.1.1` → IP…);
con él se fuerza: `scan("john", "username")`. Un `Scanner` se puede reutilizar, pero no ejecutar
dos scans a la vez (el segundo lanza `RuntimeError`); para paralelizar, un `Scanner` por scan.

### Errores

Una petición no válida lanza `ScanInputError` (subclase de `ValueError`) antes de abrir ninguna
conexión: objetivo mal formado, módulo desconocido, propósito inválido, objetivo fuera del
alcance, o falta de propósito en un scan de personas con `require_purpose` activo.

### Guardar y exportar

Un scan de la librería **no se guarda** solo:

```python
from osineitor import report
from osineitor.storage import Storage

with Storage() as storage:  # la misma base que usa la CLI
    scan_id = storage.save(result)
open("informe.html", "w", encoding="utf-8").write(report.render(result, "html"))
```

`report.FORMATS` lista los formatos (`json`, `md`, `html`, `csv`, `csv-relations`, `csv-findings`,
`graphml`, `gexf`, `cypher`).

### Qué es estable

Los nombres de `osineitor.__all__` (`Scanner`, `ScanInputError`, `ScanResult`, `Entity`,
`EntityType`) y los campos del modelo `ScanResult`, que siguen las reglas del contrato de la CLI:
solo cambios aditivos. El resto de módulos (`engine`, `http`…) son internos y pueden cambiar.

## Plugins

Un paquete de PyPI puede aportar módulos declarándolos en el grupo de *entry points*
`osineitor.modules`. Al instalarlo con `pip` aparecen en `osineitor modules` (marcados «plugin») y
corren en los scans, sin modificar OSINEITOR.

```toml
# pyproject.toml del plugin
[project]
name = "osineitor-mi-fuente"
dependencies = ["osineitor"]

[project.entry-points."osineitor.modules"]
mi_fuente = "osineitor_mi_fuente.fuente:MiFuente"   # una clase Module
otras = "osineitor_mi_fuente.otras"                  # o un módulo: se toman sus clases Module
```

```python
# osineitor_mi_fuente/fuente.py
from osineitor.models import EntityType
from osineitor.modules.base import Module


class MiFuente(Module):
    name = "mi_fuente"
    description = "Qué hace, en una línea"
    consumes = frozenset({EntityType.DOMAIN})
    produces = frozenset({EntityType.RECORD})
    canary = "example.com"  # o probe_url, para `osineitor doctor`

    async def run(self, entity):
        response = await self.ctx.http.get(f"https://api.ejemplo.test/{entity.value}")
        return [self.emit(entity, EntityType.RECORD, "mi_fuente:" + entity.value)]
```

Las reglas del contrato de un módulo (`passive`, `authority`, `requires_key`, `ModuleError`,
`ModuleSkipped`, `try_emit`, todas las peticiones por `ctx.http`…) son las de
[MODULES.md](MODULES.md) y de [`CLAUDE.md`](https://github.com/jmstudio14/OSINEITOR/blob/main/CLAUDE.md).

Reglas del descubrimiento:

- Un plugin que falla al cargarse, no es una subclase concreta de `Module`, no define `name`,
  `description` o `consumes`, o repite un nombre ya usado (de un módulo incluido o de otro
  plugin), **se omite entero** y `osineitor modules` avisa por stderr; los demás siguen
  funcionando.
- Un plugin no puede sustituir a un módulo incluido.
- **Un plugin es código de terceros que se ejecuta con tus permisos**, igual que cualquier paquete
  de PyPI. Instala solo los que conozcas. Sus peticiones pasan por el mismo `ctx.http` (guardia de
  red, presupuesto y evidencia), pero nada impide que un plugin hostil use otras vías.
- **Sin comprobar en un ejecutable empaquetado:** los tests instalan un paquete real en el
  `sys.path`, pero no se ha probado con la versión congelada.

# Contribuir a OSINEITOR

Gracias por querer mejorar OSINEITOR. Esta guía explica cómo preparar el entorno, qué se espera
de un cambio y cómo añadir una fuente nueva.

## Antes de empezar

- Lee el [uso responsable](docs/USO_RESPONSABLE.md). No se aceptarán módulos que extraigan datos
  personales de sitios que lo prohíben, que eludan autenticación o captchas, o que ataquen al
  objetivo (fuerza bruta, explotación, DoS).
- Para cambios grandes (nuevo frente, cambios en el engine o en el modelo de datos) abre antes un
  issue y acordad el enfoque.

## Entorno de desarrollo

Requiere Python 3.11 o superior.

```bash
git clone https://github.com/jmstudio14/OSINEITOR.git
cd OSINEITOR
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
```

## Comprobaciones obligatorias

Lo mismo que ejecuta la CI, en Windows y Linux con Python 3.11 y 3.13 (Windows es la plataforma
principal):

```bash
ruff check .
ruff format --check .
python -m pytest -q
```

## Reglas para los cambios

- **Tests sin red.** Simula HTTP con `respx` y DNS con `FakeResolver` (`tests/conftest.py`).
  Un test que dependa de un servicio externo fallará en CI tarde o temprano.
- **Un módulo, un fichero**, en `src/osineitor/modules/<frente>/`. El registro lo descubre solo,
  pero el ejecutable empaquetado no puede buscar en disco: añade también el fichero a
  `src/osineitor/modules/_manifest.py` (un test lo exige).
- **Errores esperados con `ModuleError`** (key inválida, servicio caído) y `ModuleQuota` si la
  fuente rechaza por límite de uso, con un mensaje en español que diga qué ha pasado.
  `status_error("servicio", respuesta)` elige entre ambos según el código HTTP.
- **Declara cómo probarlo con `osineitor doctor`:** un `canary` (valor de prueba seguro) o, si no
  lo hay, un `probe_url`.
- **Pasivo por defecto.** Si el módulo envía tráfico al objetivo, marca `passive = False`.
- **Sin dependencias nuevas** salvo que estén justificadas en el PR.
- Documenta el módulo en [docs/MODULES.md](docs/MODULES.md) y en la tabla de módulos del README.
- Añade una entrada en la sección `Sin publicar` de [CHANGELOG.md](CHANGELOG.md).

## Añadir una fuente

1. Crea `src/osineitor/modules/<frente>/<fuente>.py` con una subclase de `Module` (ejemplo más
   abajo y contrato en [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#contrato-de-un-módulo)) y
   añádela a `modules/_manifest.py`.
2. Si necesita API key, define `requires_key = "<nombre>"` y añade el nombre a la lista de keys de
   la [guía de uso](docs/USO.md#api-keys-y-rutas) y a `tests/conftest.py` (variables de entorno
   que se limpian en cada test).
3. Escribe tests para el caso con datos, el caso vacío (404 o sin resultados) y al menos un error.
4. Comprueba que aparece en `osineitor modules` y que `osineitor doctor -m <nombre>` la prueba.

### Ejemplo de módulo

```python
from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module, status_error


class MiFuente(Module):
    name = "mi_fuente"
    description = "Qué aporta"
    consumes = frozenset({EntityType.DOMAIN})
    produces = frozenset({EntityType.RECORD})
    requires_key = None  # o "nombre_de_la_key"
    passive = True
    canary = "example.com"  # valor de prueba seguro para `osineitor doctor`

    async def run(self, entity: Entity) -> list[Entity]:
        r = await self.ctx.http.get(f"https://api.ejemplo/{entity.value}")
        if r.status_code != 200:
            raise status_error("api.ejemplo", r)  # 429 → ModuleQuota; el resto, ModuleError
        return [self.emit(entity, EntityType.RECORD, f"mi_fuente:{entity.value}", **r.json())]
```

Los datos que devuelven terceros se emiten con `self.try_emit` (un valor raro no debe perder el
resto) y todo lo que vaya a una URL se codifica con `sanitize.quote_segment`. Cualquier otra
excepción se captura y se registra sin detener el scan.

## Commits y pull requests

- Mensajes de commit en español, en imperativo o descriptivos, explicando el *qué* y el *porqué*.
- Un PR por cambio coherente. Rellena la plantilla e indica cómo lo has probado, incluida la prueba
  real contra el servicio si la hiciste.

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

Lo mismo que ejecuta la CI en Python 3.11 y 3.13:

```bash
ruff check .
ruff format --check .
python -m pytest -q
```

## Reglas para los cambios

- **Tests sin red.** Simula HTTP con `respx` y DNS con `FakeResolver` (`tests/conftest.py`).
  Un test que dependa de un servicio externo fallará en CI tarde o temprano.
- **Un módulo, un fichero**, en `src/osineitor/modules/<frente>/`. El registro lo descubre solo;
  no hay que darlo de alta en ningún sitio.
- **Errores esperados con `ModuleError`** (cuota agotada, key inválida, servicio caído) y mensaje
  en español que diga qué ha pasado.
- **Pasivo por defecto.** Si el módulo envía tráfico al objetivo, marca `passive = False`.
- **Sin dependencias nuevas** salvo que estén justificadas en el PR.
- Documenta el módulo en [docs/MODULES.md](docs/MODULES.md) y en la tabla del README.
- Añade una entrada en la sección `Sin publicar` de [CHANGELOG.md](CHANGELOG.md).

## Añadir una fuente

1. Crea `src/osineitor/modules/<frente>/<fuente>.py` con una subclase de `Module`
   (ejemplo en el [README](README.md#añadir-un-módulo) y contrato en
   [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#contrato-de-un-módulo)).
2. Si necesita API key, define `requires_key = "<nombre>"` y añade el nombre a la lista de keys del
   README y a `tests/conftest.py` (variables de entorno que se limpian en cada test).
3. Escribe tests para el caso con datos, el caso vacío (404 o sin resultados) y al menos un error.
4. Comprueba que aparece en `osineitor modules`.

## Commits y pull requests

- Mensajes de commit en español, en imperativo o descriptivos, explicando el *qué* y el *porqué*.
- Un PR por cambio coherente. Rellena la plantilla e indica cómo lo has probado, incluida la prueba
  real contra el servicio si la hiciste.

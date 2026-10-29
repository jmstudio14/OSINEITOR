# CLAUDE.md

Guía para agentes que trabajen en este repositorio.

## Qué es

CLI OSINT en Python (`src/osineitor`). Investiga dominios, IPs, emails y usernames con módulos
independientes y pivota entre las entidades descubiertas. Detalles en
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Comandos

```bash
pip install -e '.[dev]'
ruff check . && ruff format --check .
python -m pytest -q      # usa python -m: el pytest global puede ser otro intérprete
```

## Convenciones

- Código, comentarios, mensajes de CLI y commits en español. Longitud de línea: 100 (ruff).
- Un módulo = una subclase de `Module` en `src/osineitor/modules/<frente>/`. Se descubre solo,
  pero añade también su fichero a `modules/_manifest.py` (un test lo exige) y declara `canary` o
  `probe_url` para `osineitor doctor`.
- Crea entidades con `self.emit(parent, tipo, valor, **datos)`; los datos con valor vacío se
  ignoran en la salida.
- Las excepciones viven en `osineitor/errors.py`. Fallos esperados → `ModuleError`; «no aplica» →
  `ModuleSkipped`. El engine captura cualquier excepción; no la silencies dentro
  del módulo salvo que el resultado sea realmente "desconocido" (como en `username_sites`).
- Módulos que contactan al objetivo: `passive = False`.
- Datos de terceros: emítelos con `try_emit` (un valor raro no debe perder el resto), valida los
  hostnames con `normalize.canonical_hostname` y codifica todo lo que vaya a una URL con
  `sanitize.quote_segment`. Nunca construyas URLs concatenando entradas sin codificar.
- Todas las peticiones salen por `ctx.http` (guardia de red y presupuesto); no uses `httpx` directo.
- Tests sin red: `respx` para HTTP, `FakeResolver` de `tests/conftest.py` para DNS.
- Al añadir o cambiar módulos, actualiza README, `docs/MODULES.md` y `CHANGELOG.md`.

## Límites

- No añadir fuentes que extraigan datos personales de sitios que lo prohíben, eludan captchas o
  autenticación, ni técnicas ofensivas. Ver [docs/USO_RESPONSABLE.md](docs/USO_RESPONSABLE.md).
- `src/osineitor/modules/username/data/sites.json` es un fichero de terceros (Sherlock, MIT): no
  editarlo a mano; se actualiza descargándolo de nuevo.

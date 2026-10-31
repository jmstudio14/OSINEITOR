# CLAUDE.md

Guía para agentes que trabajen en este repositorio.

## Qué es

CLI OSINT en Python (`src/osineitor`). Investiga dominios, IPs, emails y usernames con módulos
independientes y pivota entre las entidades descubiertas. Detalles en
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Estado y planes en [ROADMAP.md](ROADMAP.md).

## Comandos

```bash
pip install -e '.[dev]'
ruff check . && ruff format --check .
python -m pytest -q      # usa python -m: el pytest global puede ser otro intérprete
python -m pytest tests/test_contract.py -q   # un solo fichero
```

Plataforma soportada: Windows (Python ≥ 3.11); CI también corre Linux y macOS, así que no uses
código solo-POSIX. Una tarea está lista cuando `ruff check`, `ruff format --check` y `pytest`
pasan, que es lo que ejecuta CI.

## Convenciones

- Código, comentarios, mensajes de CLI y commits en español. Longitud de línea: 100 (ruff).
- Un módulo = una subclase de `Module` en `src/osineitor/modules/<frente>/`. Se descubre solo,
  pero añade también su fichero a `modules/_manifest.py` (un test lo exige) y declara `canary` o
  `probe_url` para `osineitor doctor`.
- Crea entidades con `self.emit(parent, tipo, valor, **datos)`; los datos con valor vacío se
  ignoran en la salida.
- Las excepciones viven en `osineitor/errors.py`. Fallos esperados → `ModuleError`; «no aplica» →
  `ModuleSkipped`; la fuente que rechaza por límite de uso (HTTP 429) → `ModuleQuota`. El engine
  captura cualquier excepción; no la silencies dentro del módulo salvo que el resultado sea
  realmente "desconocido" (como en `username_sites`).
- Módulos que contactan al objetivo: `passive = False`.
- Datos de terceros: emítelos con `try_emit` (un valor raro no debe perder el resto), valida los
  hostnames con `normalize.canonical_hostname` y codifica todo lo que vaya a una URL con
  `sanitize.quote_segment`. Nunca construyas URLs concatenando entradas sin codificar.
- Todas las peticiones salen por `ctx.http` (guardia de red y presupuesto); no uses `httpx` directo.
- Declara `authority = "authoritative"` solo si la respuesta viene de quien administra el dato
  (DNS, RDAP, el propio objetivo); el valor por defecto `"aggregated"` es para bases de terceros.
  Pesa en la confianza (`confidence.py`).
- Lo que pasa por `ctx.http` ya deja evidencia con `--evidence`; si consultas DNS fuera de
  `ctx.http`, llama a `self.record_evidence(...)`. Detalles en
  [docs/EVIDENCIA.md](docs/EVIDENCIA.md).
- Tests sin red: `respx` para HTTP, `FakeResolver` de `tests/conftest.py` para DNS.
- Al añadir o cambiar módulos, actualiza README, `docs/MODULES.md` y `CHANGELOG.md`.
- Toda salida estructurada de la CLI (`--json`, `--ndjson`) sigue el contrato de
  [docs/CLI_CONTRACT.md](docs/CLI_CONTRACT.md): cambios solo aditivos, y el esquema
  `docs/cli-contract.schema.json` se actualiza en el mismo PR.

## Aplicación de escritorio (`src/osineitor_gui`)

Diseño y traspaso en [docs/GUI.md](docs/GUI.md). Reglas: la GUI solo habla con la CLI (del motor
importa únicamente `detect_type` y `__version__`); Qt solo en `osineitor_gui/ui/` y `app.py`; las
reglas de seguridad (confirmar `--active`) viven en `ScanRequest`, no en las vistas; las API keys
viajan por stdin; textos en español con `tr()` en `ui/` (la capa sin Qt pasa textos ya hechos).

Estado: la capa sin Qt (PR-E1) está hecha; `ui/` y `app.py` (PR-E2) están pendientes y no existen
aún. Instala PySide6 con `pip install -e '.[gui]'` (no viene en `.[dev]`).

## Límites

- No añadir fuentes que extraigan datos personales de sitios que lo prohíben, eludan captchas o
  autenticación, ni técnicas ofensivas. Ver [docs/USO_RESPONSABLE.md](docs/USO_RESPONSABLE.md).
- `src/osineitor/modules/username/data/sites.json` es un fichero de terceros (Sherlock, MIT): no
  editarlo a mano; se actualiza descargándolo de nuevo.

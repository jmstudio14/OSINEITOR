# Changelog

Todos los cambios relevantes del proyecto. Formato basado en
[Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y versionado
[SemVer](https://semver.org/lang/es/).

## [Sin publicar]

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

[Sin publicar]: https://github.com/jmstudio14/OSINEITOR/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/jmstudio14/OSINEITOR/releases/tag/v0.1.0

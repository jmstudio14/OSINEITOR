# Changelog

Todos los cambios relevantes del proyecto. Formato basado en
[Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y versionado
[SemVer](https://semver.org/lang/es/).

## [Sin publicar]

### Añadido

- `ROADMAP.md` con las fases 0–9 posteriores al MVP, basado en una investigación del estado
  del arte OSINT.

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

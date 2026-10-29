# Changelog

Todos los cambios relevantes del proyecto. Formato basado en
[Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y versionado
[SemVer](https://semver.org/lang/es/).

## [Sin publicar]

Fase 1a del roadmap (seguridad y datos).

### Añadido

- **Saneado de entradas (F1.11):** el username se codifica como un único segmento en las URLs
  de las ~460 firmas; un valor no válido se rechaza como error de uso antes de lanzar nada.
- **Normalización de entidades (F1.12):** dominios en minúsculas y punycode (IDNA 2008), IPs,
  emails y URLs en forma canónica. `münchen.de` y `xn--mnchen-3ya.de` son la misma entidad.
- **Guardia de red (F1.13):** ninguna petición va a IPs privadas, loopback, link-local ni al
  servicio de metadatos cloud, tampoco a través de redirecciones (que ahora se siguen y
  comprueban salto a salto). `--allow-private` lo desactiva. Las redirecciones a otro origen no
  reenvían cabeceras de la petición.
- **Presupuesto de escaneo (F1.14):** `--max-entities` (2000), `--max-requests` (3000) y
  `--max-time` (900 s), `0` = sin límite. Al agotarse, el scan se detiene de forma ordenada,
  conserva lo ya terminado y queda marcado como incompleto (`truncated`).
- `osineitor/errors.py` con las excepciones compartidas y `ModuleSkipped` para «no aplica».
- `Module.try_emit` para datos de terceros que pueden no ser válidos.
- CI en Windows (3.11 y 3.13) además de Linux, y `.gitattributes` con finales de línea LF.
- `docs/PRUEBAS_WINDOWS.md`: estado de verificación en vivo de cada módulo (varios no se han
  podido comprobar desde el entorno de desarrollo), pasos para clonar en VS Code y probar desde
  Windows, y tabla para registrar los resultados.

### Cambiado

- **RDAP (F1.18):** el módulo consulta el bootstrap de IANA (con caché de 7 días) y para los TLD
  sin servidor RDAP (`.es`, `.io`, `.de`…) queda **omitido con un aviso** en lugar de devolver
  un vacío silencioso.
- **Rutas multiplataforma (F1.16):** configuración en `%APPDATA%\osineitor` y datos en
  `%LOCALAPPDATA%\osineitor` en Windows (con `platformdirs`); en Linux no cambia. Se pueden
  fijar con `OSINEITOR_CONFIG_DIR` y `OSINEITOR_DATA_DIR`.
- `crtsh` descarta los hostnames no válidos en lugar de emitirlos.
- `username_sites` conserva los perfiles ya encontrados si se agota el presupuesto.
- Dependencias nuevas: `platformdirs` e `idna`.

### Corregido

- **Windows:** la CLI forzaba la codificación local (cp1252) cuando su salida iba a una tubería,
  de modo que un `✓` o una letra cirílica provocaban un `UnicodeEncodeError`. Ahora escribe
  siempre en UTF-8. Añadido `python -m osineitor`.
- Un username derivado de un email con caracteres como `/`, `?` o `#` ya no puede alterar la
  ruta de las URLs consultadas.

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

# Plan de la fase 6 · Nuevos frentes (v0.7.0)

Sale del [ROADMAP](../../ROADMAP.md) (fase 6). Criterios comunes a todo módulo nuevo, de
[`CLAUDE.md`](../../CLAUDE.md) y de las fases anteriores:

- Una subclase de `Module` en `src/osineitor/modules/<frente>/`, añadida a `modules/_manifest.py`.
- `canary` o `probe_url` para `osineitor doctor`; `min_interval` si la fuente tiene límite.
- Tests sin red (`respx`); datos de terceros con `try_emit`; todo valor en URL con
  `sanitize.quote_segment`; nada de `httpx` directo.
- README, `docs/MODULES.md` (fuente, datos, límites, términos y licencia) y `CHANGELOG.md`.
- Criterio de salida: `ruff check .`, `ruff format --check .` y `python -m pytest -q` en verde.

## Estado

| ID | P | Módulo | Estado | Decisión |
|---|---|---|---|---|
| F6.5 | M | `phone_parse` | ✅ | `phonenumbers` en local; nueva dependencia |
| F6.6 | M | `crypto_detect` | ✅ | Suma de comprobación propia (base58check, bech32, bech32m) |
| F6.9 | M | `file_meta` | ✅ | Solo biblioteca estándar: JPEG/EXIF, PDF, Office, OpenDocument |
| F6.7 | S | `btc_explorer` | ✅ | mempool.space |
| F6.2 | S | `gleif` | ✅ | Solo se comprobó en real la estructura de `/lei-records` (texto completo); el filtro por nombre y las rutas `direct-parent` y `direct-children` salen de la documentación |
| F6.10 | S | `file_hash` | ✅ | Hashes en local; `virustotal` y `abusech` consultan el SHA-256 (D1) |
| F6.11 | S | `geo_point` | ✅ | En local; el GPS del EXIF entra como `location` |
| F6.17 | C | `image_links` | ✅ | Solo enlaces |
| F6.1 | S | `opensanctions` | ✅ | D1: `/match/default`, solo `match: true`; CC BY-NC documentada |
| F6.15 | S | `github_code` | ✅ | D1: reglas en memoria; nunca el valor, ni con `--evidence` |
| F6.12 | S | `capture` | ✅ | Probado en vivo; pantallazo con el extra `capture`; `verify` comprueba los ficheros |
| F6.3 | C | `librebor` | ⛔ | API de pago |
| F6.4 | C | `opencorporates` | ⛔ | API de pago |
| F6.8 | C | `eth_explorer` | 🟡 | D1: Etherscan V2; sin etiquetas (solo Pro Plus) |
| F6.13 | C | `search_dorks` | ✅ | D1: Brave Search; ver la decisión abajo |
| F6.14 | C | `doc_harvest` | ✅ | Probado en vivo; CDX por tipo MIME y descarga del objetivo |
| F6.16 | C | `cloud_storage_refs` | ✅ | Probado en vivo contra S3, GCS y Azure |
| F6.18 | C | `ext_exiftool` | ✅ | Probado en vivo con ExifTool 13.61; ruta por stdin |

## Decisiones

- **Detección automática en `scan`.** `detect_type` reconoce, por este orden: teléfono (`+` o
  `00`), dirección cripto con suma válida, coordenadas `lat,lon` y ruta de fichero existente; el
  resto sigue como antes. Una ruta solo cuenta si tiene `/` o `\` y el fichero existe: sin eso, un
  username como `john` pasaría a ser un fichero si hubiera uno con ese nombre en la carpeta.
- **Normalización.** Las coordenadas se guardan con 6 decimales y se rechazan fuera de rango; una
  ruta de fichero ya no colapsa los espacios (el módulo no podría abrirla).
- **Privacidad.** `PHONE` se añade a `PURPOSE_REQUIRED_FOR`: un teléfono es un dato personal, igual
  que el email o el username.
- **Ficheros.** Nada de red: ni el contenido ni la ruta salen del equipo. `file_meta` rechaza XML
  con `DOCTYPE` o entidades, limita lo que lee de un fichero y de cada miembro de un zip, y se
  limita a los formatos que cubre con la biblioteca estándar. Su `canary` es su propio código
  fuente, que siempre existe.
- **Pivotes.** El GPS de un JPEG sale como `location` y `geo_point` lo amplía; un `gleif` con LEI
  exacto y único emite matriz y filiales como `organization`, que pivotan de nuevo. Con una
  coincidencia aproximada no se siguen las relaciones, para no atribuir la cadena de otra empresa.
- **Organizaciones de GitHub.** `gleif` las ignora (`data["platform"]`): no son personas jurídicas.
- **Ethereum y Monero** solo se validan por forma; la suma EIP-55 pide Keccak-256, que no está en
  `hashlib`. No se añade una dependencia para eso.
- **Empaquetado.** `phonenumbers` carga sus datos por regiones de forma perezosa: el ejecutable de
  la aplicación de escritorio (PR-E2, ya escrita: `packaging/windows/`) la incluye entera
  (`--collect-all phonenumbers` en PyInstaller).

- **F6.13, decisión: se implementa con Brave Search (08-11-2026).** Es una API oficial, sin scraping,
  que documenta `site:`, `filetype:` e `intitle:`. Ya no tiene plan gratuito (5 $/mes de crédito, unas
  1.000 búsquedas), así que las plantillas son pocas y fijas: 5 peticiones por dominio.
- **Verificación D1.** El usuario decidió el 08-11-2026 aceptar los módulos con key escritos con la
  documentación oficial y respuestas simuladas, marcados como tales, en lugar de dejarlos fuera.
- **`github_code` y `--evidence`.** La evidencia guardaba la respuesta cruda, con el secreto: por eso
  `ctx.http` admite `evidence_body=False`, que guarda un texto fijo con su huella y `verify` sigue cuadrando.
- **`capture` y `verify`.** Los ficheros viven fuera de la base, así que `verify` rehace sus hashes aparte
  y `evidence_digest` no los cubre. WARC escrito con la biblioteca estándar (validado con `warcio`).
- **Lo que cambió la prueba real:** Azure contesta igual a un contenedor privado y a uno inexistente
  (`unknown`, no `denied`); ExifTool sale con 1 en un formato desconocido y, en Windows, no encuentra una
  ruta con tildes pasada como argumento (va por stdin); el CDX da 504 con un filtro `(?i)` por extensión y
  agota el tiempo con `matchType=domain` (se filtra por tipo MIME sobre `<dominio>/*`).

## Entregables no incluidos

- **F6.3 y F6.4.** APIs de pago sin acceso para probarlas; el roadmap los marca como opcionales.
- **F6.8, etiquetas.** `getaddresstag` solo está en el plan Pro Plus.

## Verificación

1. Detección de tipos y normalización: `tests/modules/test_f6_local.py`.
2. Módulos locales (teléfono, cripto, coordenadas, enlaces, ficheros), con fixtures de EXIF, PDF,
   DOCX y ODT generadas en el test; XML con entidades rechazado.
3. Ficheros sin red: un test intercepta cualquier petición durante `file_hash` y `file_meta`, y
   otro lanza un `scan` completo de un JPEG.
4. Fuentes con red (`btc_explorer`, `gleif`) con `respx`: `tests/modules/test_f6_sources.py`.
5. Docs: `tests/test_docs.py` exige que README y `docs/MODULES.md` listen los módulos reales.
6. Módulos con key (D1): `tests/modules/test_f6_keyed.py`, incluido el secreto en los bytes de la base.
7. Módulos activos y ExifTool: `tests/modules/test_f6_active.py`; los del navegador y ExifTool reales se
   omiten si no están instalados.
8. Suite completa con `ruff check .`, `ruff format --check .` y `python -m pytest -q`.

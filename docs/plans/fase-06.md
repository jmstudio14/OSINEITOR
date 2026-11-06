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
| F6.10 | S | `file_hash` | 🟡 | Hashes en local; falta el pivote a reputación |
| F6.11 | S | `geo_point` | ✅ | En local; el GPS del EXIF entra como `location` |
| F6.17 | C | `image_links` | ✅ | Solo enlaces |
| F6.1 | S | `opensanctions` | ⛔ | Sin verificar: formato de la key y términos de uso no comprobables |
| F6.15 | S | `github_code` | ⛔ | Aplazado: reglas de detección de secretos y guía de divulgación |
| F6.12 | S | `capture` | ⛔ | Aplazado: navegador headless, WARC y `osineitor verify` |
| F6.3 | C | `librebor` | ⛔ | API de pago |
| F6.4 | C | `opencorporates` | ⛔ | API de pago |
| F6.8 | C | `eth_explorer` | ⬜ | Aplazado: Etherscan cambió de versión de API; sin verificar |
| F6.13 | C | `search_dorks` | ⛔ | *Spike* con puerta de decisión sin hacer |
| F6.14 | C | `doc_harvest` | ⬜ | Depende de F6.13 o de Wayback; descarga de documentos del objetivo |
| F6.16 | C | `cloud_storage_refs` | ⬜ | Aplazado: comprobación activa de buckets |
| F6.18 | C | `ext_exiftool` | ⬜ | Aplazado: sin formato de salida verificado |

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
  la aplicación de escritorio (PR-E2, aún sin escribir) tendrá que incluirla entera
  (`--collect-all phonenumbers` en PyInstaller).

## Entregables bloqueados o aplazados

- **F6.1 `opensanctions`.** Hace falta la key y los términos para uso no comercial; sin ellos no se
  puede comprobar ni el formato de la respuesta ni qué se puede guardar.
- **F6.3 y F6.4.** APIs de pago; el roadmap los marca como opcionales.
- **F6.8 `eth_explorer`.** Etherscan unificó sus APIs en una versión nueva y no hay forma de
  comprobar aquí qué endpoint es el vigente.
- **F6.12 `capture`.** Exige un navegador *headless* (extra `osineitor[capture]`), formato WARC y la
  verificación con `osineitor verify`; es una tarea propia.
- **F6.13 `search_dorks` y F6.14 `doc_harvest`.** La decisión sobre la API de búsqueda sigue
  pendiente; `doc_harvest` descarga documentos del objetivo y hereda ese bloqueo.
- **F6.15 `github_code`.** El criterio exige no escribir ningún secreto; hay que definir primero
  las reglas de detección y la guía de divulgación responsable.
- **F6.16 `cloud_storage_refs`, F6.18 `ext_exiftool`.** Aplazados.
- **F6.10, pivote a reputación.** Falta consultar el hash en VirusTotal y abuse.ch.

## Verificación

1. Detección de tipos y normalización: `tests/modules/test_f6_local.py`.
2. Módulos locales (teléfono, cripto, coordenadas, enlaces, ficheros), con fixtures de EXIF, PDF,
   DOCX y ODT generadas en el test; XML con entidades rechazado.
3. Ficheros sin red: un test intercepta cualquier petición durante `file_hash` y `file_meta`, y
   otro lanza un `scan` completo de un JPEG.
4. Fuentes con red (`btc_explorer`, `gleif`) con `respx`: `tests/modules/test_f6_sources.py`.
5. Docs: `tests/test_docs.py` exige que README y `docs/MODULES.md` listen los módulos reales.
6. Suite completa con `ruff check .`, `ruff format --check .` y `python -m pytest -q`.

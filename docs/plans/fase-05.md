# Plan de la fase 5 · Identidades: email, usernames y personas (v0.6.0)

Sale del [ROADMAP](../../ROADMAP.md) (fase 5). Criterios comunes a todo módulo nuevo, de
[`CLAUDE.md`](../../CLAUDE.md) y de la fase 4:

- Una subclase de `Module` en `src/osineitor/modules/<frente>/`, añadida a `modules/_manifest.py`.
- `canary` o `probe_url` para `osineitor doctor`; `min_interval` si la fuente tiene límite.
- Tests sin red (`respx`); datos de terceros con `try_emit`; todo valor en URL con
  `sanitize.quote_segment`; nada de `httpx` directo.
- README, `docs/MODULES.md` (fuente, datos, límites, términos y licencia) y `CHANGELOG.md`.
- Criterio de salida: `ruff check .`, `ruff format --check .` y `python -m pytest -q` en verde.
- Límites de la sección 8 del roadmap: nada de scraping de redes sociales con sesión, de sondeo
  SMTP ni de contraseñas de filtraciones.

## Estado

| ID | P | Módulo | Estado | Decisión |
|---|---|---|---|---|
| F5.9 | M | `username_variants`, `email_candidates` | ✅ | Entidad `person` y comando `person`; solo generan |
| F5.2 | S | `github_email` | ✅ | Búsqueda de commits por email; logins como `username` |
| F5.3 | S | `username_wmn` | ✅ | `wmn.json` sin modificar; «confirmado» = fusión por URL |
| F5.7 | S | `github_user` | ✅ | Perfil, organizaciones, blog y emails de commits |
| F5.10 | S | `fediverse` | ✅ | Cierre del roadmap: `bluesky` (API pública, handle `usuario.bsky.social` o con dominio propio) junto a `fediverse`. |
| F5.11 | S | `dev_registries` | ✅ | Cierre del roadmap: `dev_registries` añade PyPI (página pública de perfil) y Stack Overflow (solo nombres visibles idénticos, sin `verified`). |
| F5.13 | C | `hibp_pastes` | ✅ | Resumen del endpoint `pasteaccount`, misma key `hibp` |
| F5.14 | C | `discord_snowflake` | ✅ | En local |
| F5.8 | S | `hudsonrock` | ⛔ | Evaluado y no incluido (ver más abajo) |
| F5.4 | S | extracción de perfil | ✅ | Cierre del roadmap: `profile_extract` lee las APIs oficiales de DEV Community y Codeberg (nombre, bio, web, usernames declarados); no extrae nada de páginas HTML. |
| F5.5 | S | pivote recursivo | ✅ | Cierre del roadmap: los usernames que declara `profile_extract` se emiten como entidades y el motor los pivota hasta la profundidad del scan. |
| F5.1 | C | `leakcheck` | ✅ | Cierre del roadmap: `leakcheck` con la API pública, que solo devuelve nombres de fuentes y fechas. |
| F5.12 | C | `pgp_keyserver` | ✅ | Cierre del roadmap: `pgp_keyserver` con `keys.openpgp.org` (índice legible por máquina, solo identidades verificadas). |
| F5.6 | C | `--tags` y `--top` | ⬜ | Evaluado y no incluido (ver más abajo) |
| F5.15 | C | `ext_maigret` | ✅ | Cierre del roadmap: `ext_maigret` lee el informe `--json simple` que Maigret escribe en una carpeta temporal. |

## Decisiones

- **`person` como entidad.** El nombre completo es el valor; `--domain` viaja en `data["domain"]`
  (se canonicaliza con `canonical_hostname`). `email_candidates` solo acepta una persona con
  dominio. Los candidatos se marcan `candidate=True` con su patrón y nunca se verifican.
- **Tope de candidatos.** 12 por módulo y mínimo 3 caracteres: más candidatos solo multiplican las
  peticiones de los módulos de username sin aportar hallazgos. Se usan el primer y el último
  apellido; las partículas («de», «van»...) se descartan.
- **`person` exige propósito** (`PURPOSE_REQUIRED_FOR`), como email y username.
- **`doctor`** siembra la persona de prueba para los módulos que solo consumen `person`.
- **WhatsMyName.** CC BY-SA 4.0 no cabe en `COMPATIBLE_LICENSES`, así que el fichero va en el
  paquete (sin pasar por `update-data`), sin modificar y con atribución en
  `modules/username/data/README.md`. El módulo hereda de `username_sites` (mismo control con un
  username inexistente) y solo cambia la detección y la construcción de la petición. Se omiten los
  sitios NSFW y los marcados con `protection`: no se eluden Cloudflare, captchas ni similares.
- **«Confirmado».** No hay un campo nuevo: si las dos fuentes dan la misma URL, el motor fusiona
  la entidad, que queda con dos fuentes y confianza `medio` (frente a `bajo` con una sola). Si las
  URLs difieren, la coincidencia no se detecta; es una limitación documentada.
- **`fediverse` es activo.** Contacta con el host del dominio del email, que puede ser el objetivo.
- **`dev_registries`** no emite los emails de los mantenedores de npm (privacidad) y no pierde las
  demás fuentes si una falla.
- **`hibp_pastes`** guarda nº, fuentes y fechas; nunca los identificadores de los *pastes*.
- **`github_user`** descarta las direcciones `noreply` de GitHub, que no identifican a nadie.

## Entregables bloqueados o aplazados

Revisado en el cierre del roadmap (07-11-2026; ver [`cierre-roadmap.md`](cierre-roadmap.md)):

- **F5.8 `hudsonrock`.** La API documentada es de pago y su respuesta incluye contraseñas; la
  clave gratuita se pide con un correo corporativo. Los términos y una respuesta real no están
  verificados. No se implementa: el criterio del roadmap exige un test que demuestre que no se
  guardan secretos, y sin la respuesta real ese test no prueba nada.
- **F5.6.** Sherlock no tiene categorías ni popularidad y solo WhatsMyName tiene categorías; un
  filtro que afectase a una sola fuente daría una idea falsa de la cobertura. `--only username_wmn`
  ya limita a una fuente.
- Hechos en el cierre: F5.1, F5.4, F5.5, F5.10 (Bluesky), F5.11 (PyPI y Stack Overflow), F5.12 y
  F5.15. F5.4 y F5.5 se resolvieron con APIs oficiales (DEV Community y Codeberg) y no con parsers
  de páginas HTML de terceros.

## Verificación

1. Generadores sin red ni SMTP: `tests/test_person.py`.
2. Fuentes de identidad con `respx`: `tests/modules/test_identity_sources.py`.
3. WhatsMyName: `tests/modules/test_username_wmn.py`, incluida la fusión con Sherlock.
4. Docs: `tests/test_docs.py` exige que README y `docs/MODULES.md` listen los módulos reales.
5. Suite completa con `ruff check .`, `ruff format --check .` y `python -m pytest -q`.

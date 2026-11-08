# Plan de la fase 11 · Producto 1.0 (v1.0.0)

Sale del [ROADMAP](../../ROADMAP.md) (fase 11). Criterios comunes, de
[`CLAUDE.md`](../../CLAUDE.md) y de las fases anteriores:

- Salida estructurada de la CLI solo con cambios aditivos.
- README, `docs/` y `CHANGELOG.md` al día.
- Criterio de salida: `ruff check .`, `ruff format --check .` y `python -m pytest -q` en verde.

## Estado

| ID | P | Entregable | Estado | Decisión |
|---|---|---|---|---|
| F11.2 | M | Publicación en PyPI | ⚠️ Parcial | Paquete verificado en local; flujo `release.yml` escrito y **sin ejecutar** (necesita la cuenta de PyPI del mantenedor) |
| F11.4 | M | Sitio de documentación | ✅ | MkDocs, `mkdocs build --strict` limpio, referencia de módulos generada desde el código, tutorial |
| F11.6 | M | Compromiso de estabilidad | ✅ | `docs/ESTABILIDAD.md`: CLI, formatos de exportación y API de librería; obsolescencia de dos menores |
| F11.3 | S | Imagen Docker | ✅ | Dos etapas, usuario sin privilegios; **sin construir** (no hay Docker en el equipo) |
| F11.5 | C | Internacionalización | ⬜ | Aplazado: es *Could*; duplicaría toda la documentación y los mensajes de la CLI |
| F11.1 | — | Interfaz web local | ➖ | Obsoleto por el Hito G |

## Decisiones

- **No se sube la versión a 1.0.0 ni se publica.** Publicar en PyPI es público y casi irreversible, y
  declarar «1.0» es la promesa de estabilidad: lo decide quien mantiene el proyecto. `docs/PUBLICACION.md`
  deja los pasos. La guía de migración y el compromiso de estabilidad están escritos para entrar en
  vigor con esa versión.
- **F11.2 parcial, no hecho.** Lo que se puede comprobar sin cuenta de PyPI se comprobó: el wheel y el
  sdist se construyen sin avisos, `twine check` pasa, el wheel contiene todos los ficheros de datos y,
  instalado en un entorno limpio, ejecuta `osineitor version`, lista todos los módulos y carga los
  presets. Un test impide que un fichero `.json` o `.yml` nuevo quede fuera de `package-data`.
- **Firma = atestaciones PEP 740.** `pypa/gh-action-pypi-publish` genera con *trusted publishing*
  atestaciones firmadas con Sigstore y PyPI las muestra como procedencia. Alternativa descartada:
  firmar aparte con `sigstore-python` y adjuntar los `.sigstore` a una release de GitHub; añade un
  segundo mecanismo que mantener para el mismo resultado.
- **Publicación de confianza, sin token.** El trabajo `publish` solo pide `id-token: write`, vive en
  el entorno `pypi` (que puede exigir aprobación manual) y repite en el `build` ruff, pytest y la
  comprobación de que la etiqueta coincide con la versión.
- **Licencia SPDX.** `license = { file = ... }` está obsoleto y setuptools dejará de aceptarlo el
  18-02-2027; se cambió a `license = "MIT"` + `license-files`, lo que exige `setuptools>=77`.
- **Enlaces de `docs/` a ficheros fuera de la carpeta → URL de GitHub.** MkDocs solo ve `docs/`;
  esos enlaces (`../ROADMAP.md`, `../SECURITY.md`…) fallan en el sitio. Se convirtieron en vez de
  quitar el modo estricto o ignorar los avisos. Las anclas con acento siguen siendo las de GitHub
  gracias a `slugify_unicode`.
- **Referencia de módulos generada con un hook**, no con un fichero versionado: no puede desfasarse
  del código y no añade dependencias a MkDocs (`File.generated`). Solo lista los módulos incluidos,
  no los de plugins instalados. La escrita (`MODULES.md`) sigue siendo la que explica límites y
  licencias.
- **Los planes de cada fase quedan fuera del sitio** (`exclude_docs`): son notas de desarrollo con
  enlaces a ficheros del repositorio.
- **Estabilidad: lo cubierto es lo que tiene contrato.** CLI y códigos de salida, esquema `--json` y
  NDJSON, formatos de exportación estructurados y `osineitor.__all__` más el contrato de `Module`. Se
  excluye explícitamente el texto legible, `Entity.data` y el esquema de la base de datos. Dos tests
  fallan si la API pública o un código de salida nuevo no se añaden al documento.
- **Docker: construir el wheel, no copiar el árbol.** La etapa final solo recibe el wheel, así que la
  imagen es lo que `pip install` instalaría. Usuario `uid 10001`, datos en el volumen `/data`, claves
  por variables de entorno.

## Verificación

- `tests/test_release.py`: `pyproject.toml` listo para PyPI, todos los ficheros de datos declarados,
  `release.yml` sin token y con atestaciones, la etiqueta se compara con la versión, la CI construye
  paquete, documentación e imagen, el Dockerfile corre sin privilegios, cada documento está en la
  navegación del sitio, la referencia generada lista todos los módulos, ESTABILIDAD nombra la API
  pública y los códigos de salida, y MIGRACION cubre los cambios incompatibles del CHANGELOG.
- `tests/test_docs.py`: también valida las órdenes del tutorial.
- Comprobado a mano, con herramientas fuera del proyecto: `python -m build`, `twine check`,
  instalación del wheel en un entorno limpio y `mkdocs build --strict` (sin avisos).
- **No comprobado:** el flujo `release.yml` completo y la publicación; `docker build` y `docker run`; los
  tres trabajos nuevos de la CI (`package`, `docs`, `docker`) en GitHub. «Instalación con
  `pip install osineitor` y `docker run` probadas en CI» queda por tanto sin cumplir hasta el primer
  ciclo real de CI y de publicación.

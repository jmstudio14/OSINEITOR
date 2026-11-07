# Changelog

Todos los cambios relevantes del proyecto. Formato basado en
[Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y versionado
[SemVer](https://semver.org/lang/es/).

## [Sin publicar]

Todo lo hecho tras la v0.5.0, por fase del roadmap: los entregables *S* de la fase 4 (v0.5.1) y
las fases 5 a 11 (v0.6.0 a v1.0.0) en lo que no depende de cuentas o de red real. Nada de esto está
publicado ni se ha probado contra los servicios reales; el detalle de cada fase y sus límites está
en `docs/plans/fase-NN.md`. Las secciones van de la fase más reciente a la más antigua.

### Cierre del roadmap (pendientes y parciales)

Plan en `docs/plans/cierre-roadmap.md`. Se rellena según se cierra cada bloque.

- **DNS wildcard (F1.15):** `dns` sondea una etiqueta aleatoria de la zona de cada subdominio; si el
  subdominio solo resuelve a las IP del wildcard, lo marca (`wildcard: true`) y no pivota a esas
  IP. Un sondeo por zona y escaneo.
- **Límites por fuente (F1.6):** `shodan` (1/s), `hibp` y `hibp_pastes` (plan más bajo, 10/min
  compartidos), `hunter_verify` y `hunter_domain`, `wayback` (CDX, 60/min) y `crtsh` declaran su
  `min_interval` según la documentación de cada servicio.
- **Supresión de ruido en `watch` (F9.4):** `confirm: N` por objetivo (alertar solo si la entidad
  se ve en N ejecuciones seguidas) y `quiet: HH:MM-HH:MM` por notificador (ventana de silencio sin
  pérdida de alertas). `watch run --json` añade `pending` y `held` por objetivo. Migración 9 de la
  base de datos (`watch_pending`).
- **Casos (F7.2), búsqueda global (F7.5) y correlación (F7.6):** `osineitor case new/add/note/show/list`
  agrupa scans con descripción, etiquetas y notas; `osineitor search VALOR` dice en qué scans y casos
  aparece un dato (también la semilla); `case add` y `case show` avisan de los datos
  identificadores que ya figuran en otro caso. Migración 10 (tablas `cases`, `case_scans`,
  `case_notes` e índice por valor). Salidas `--json` en el contrato (`case_show_output`,
  `case_list_output`, `search_output`).
- **Línea temporal (F7.4):** `osineitor timeline N` ordena las fechas de los datos del scan
  (registro, certificados, Wayback, filtraciones, actividad cripto…), con las futuras marcadas. Salida
  `--json` en el contrato (`timeline_output`).
- **Exportación a STIX 2.1 y a MISP (F8.1 y F8.2):** `osineitor export N -f stix` y `-f misp`
  generan un bundle STIX y un evento MISP con los dominios, IP, URL, emails y CVE del scan. Las
  librerías `stix2` y `pymisp` son extras opcionales (`osineitor[stix]`, `osineitor[misp]`) y entran
  en `dev`. En MISP nada se marca como indicador de detección y el evento no se comparte.
- **Importación de Subfinder y Maigret y lista de objetivos (F8.7):** `osineitor import subfinder`
  (`-oJ`) y `osineitor import maigret` (`--json simple|ndjson`) guardan su salida como un scan, sin
  ejecutar nada; Amass no se importa porque su JSON no tiene un formato estable que comprobar.
  `osineitor scan --targets-file lista.txt` lanza un scan por objetivo (hasta 200), sin que uno
  inválido frene a los demás.
- **Riesgo por activo (F7.9):** `osineitor risk N` puntúa de 0 a 100 cada dominio o IP según sus
  hallazgos (ponderados por la confianza del dato afectado) y su exposición (servicios y CVE), con el
  desglose del porqué. Es una heurística de priorización sin contrastar con scans reales. Salida
  `--json` en el contrato (`risk_output`).
- **Vigilancia de filtraciones (F9.7):** un email en `watch.yml` alerta (`new-breach`, severidad alta)
  de las filtraciones de `leakcheck` o `hibp` que no figuraban en la ejecución anterior; lo ya filtrado
  al fijar la línea base no alerta. Los infostealers no están cubiertos (ver
  `docs/MODULES.md#fuentes-evaluadas-y-no-incluidas`).
- **Más fuentes (F4.21, F4.22, F5.1, F5.12):** `leakcheck` (filtraciones por email, API pública
  sin datos), `pgp_keyserver` (clave PGP con identidad verificada), `reverse_ip` (hostnames en la
  misma IP; una IP con más de 50 queda en un resumen) y `analytics_ids` (IDs de Google Analytics,
  Tag Manager, Ads y AdSense de la portada; activo).
- **Extracción de perfil y pivote recursivo (F5.4, F5.5):** `profile_extract` completa el perfil de
  DEV Community y Codeberg con lo que el dueño publicó (nombre, bio, web) leyendo sus APIs
  oficiales, sin tocar HTML ni guardar emails, y emite como `username` los de X y GitHub que
  enlazó para que el motor los investigue en el siguiente nivel.
- **Adaptador de Maigret (F5.15):** `ext_maigret` ejecuta el `maigret` instalado por el usuario
  (sin recursión ni extracción), lee su informe `--json simple` de una carpeta temporal y emite
  los perfiles que dio por encontrados. `ExternalToolModule` separa ahora la comprobación del
  binario (`_executable`) para los adaptadores cuyo informe no sale por stdout.
- **Bluesky y más registros de desarrollo (F5.10, F5.11):** el módulo `bluesky` lee el perfil
  público de un username (`<usuario>.bsky.social` o un handle con dominio propio). `dev_registries`
  añade PyPI (su página pública de perfil) y Stack Overflow (solo nombres visibles idénticos,
  marcados `match: display_name` y sin `verified`).
- **Servidor MCP (F10.4):** `osineitor mcp` expone por stdio, a agentes de IA, la consulta de scans
  guardados, la búsqueda, los hallazgos, la sugerencia de pivotes y el lanzamiento de scans
  **pasivos**. No hay forma de pedir módulos activos ni de investigar ficheros locales, y cada scan
  tiene tope de profundidad, entidades, peticiones y tiempo. Ver `docs/MCP.md`.
- **Sugerencia de pivotes (F10.5):** `osineitor suggest N` propone qué investigar a continuación
  (datos sin investigar, módulos pasivos disponibles y el comando) sin ejecutar nada. Salida `--json`
  en el contrato (`suggest_output`).
- **Resolución de entidades (F7.10):** `osineitor resolve N` agrupa cuentas que comparten email
  de origen, username o nombre, siempre como hipótesis con sus señales y una puntuación que no pasa de
  0,95. Los informes `md` y `executive` las incluyen etiquetadas. Salida `--json` en el contrato
  (`resolve_output`).
- **Informes de superficie de ataque y ejecutivo (F7.12 y F7.7):** `osineitor export N -f
  attack-surface` y `-f executive` generan dos informes en Markdown pensados para leerse: el inventario
  de lo expuesto con los hallazgos priorizados, y un resumen para quien decide con límites y anexos.
- **Vigilancia de dominios parecidos (F9.6):** `lookalike_domains` emite además un `record`
  `lookalike:<parecido>` por cada dominio registrado, y `alerts.yml` trae dos reglas nuevas:
  `new-lookalike-domain` (media) y `new-lookalike-domain-with-mail` (alta, si tiene MX).

### Añadido

- **`web_meta` (F4.5, activo):** `robots.txt`, sitemaps y `security.txt` (RFC 9116). Emite las
  rutas `Disallow` concretas y las URLs de los sitemaps como `url`, y el contacto `mailto:` como
  `email`. Descarta las respuestas HTML de relleno y no sigue sitemaps de otros dominios.
- **`takeover` (F4.6, activo):** detecta subdominios con CNAME a un servicio donde el recurso ya no
  está reclamado (12 servicios; destino NXDOMAIN o mensaje de la página). Solo detecta, nunca
  reclama.
- **`ptr` (F4.7):** DNS inverso de la IP; el nombre sale como `domain` marcado `subdomain`.
- **`ripestat` (F4.8):** ASN, prefijo, país de registro e historial de enrutamiento con RIPEstat.
  Emite `asn` y `netblock`.
- **`dnsbl` (F4.9):** Spamhaus ZEN, SpamCop, UCEPROTECT nivel 1 y DroneBL. Un código `127.255.255.x`
  de Spamhaus (resolvedor público rechazado) se informa como cuota, no como «listada».
- **`asn_netblock` (F4.16):** de IP a ASN y prefijo (Team Cymru, por DNS) y de ASN a hasta 50
  prefijos (RIPEstat), los más amplios primero.
- **`cloud_attribution` (F4.17, parcial):** analizador que etiqueta CDN y nube a partir del CNAME y
  de la huella HTTP. **Falta** el etiquetado de IP con los rangos publicados por los proveedores.
- **`urlscan` (F4.1):** escaneos públicos de urlscan.io; solo cuentan los hosts del objetivo. Key
  opcional.
- **`otx` (F4.2):** pulses y DNS pasivo de AlienVault OTX (key gratuita `otx`).
- **`virustotal` (F4.3):** reputación y subdominios (key `virustotal`); espacia 15 s las peticiones
  por el límite del plan gratuito (4 por minuto).
- **`censys` (F4.15):** servicios, ASN y país de la IP con Censys Platform (key `censys`, y
  `censys_org` opcional). **Parseo no comprobado contra la API real.**
- **`abusech` (F4.10):** IOC de ThreatFox y URLhaus (key `abusech`). Solo metadatos.
- **`tech_detect` (F4.18, activo):** más de 50 tecnologías por firmas propias
  (`tech_signatures.json`), con versión y evidencia. No usa `webappanalyzer` (GPL-3.0).
  `http_fingerprint` conserva sus 17 firmas. También emite como `technology` (categoría `plugin` o
  `theme`, hasta 50) los plugins y temas de WordPress que la propia portada enlaza en
  `/wp-content/`, con la versión del `?ver=` si la lleva; sin peticiones extra ni enumeración.
- **`favicon_pivot` (F4.19, activo):** MurmurHash3 del favicon (implementación propia) y búsqueda
  `http.favicon.hash` en Shodan; requiere una cuenta con acceso a la búsqueda.
- **`lookalike_domains` (F4.20):** hasta 300 permutaciones del dominio y comprobación por DNS de las
  registradas. Un único `record`, sin entidades `domain`. No usa dnstwist.
- **`ext_subfinder` (F4.24):** adaptador de Subfinder (solo fuentes pasivas). `ext_amass` queda
  pendiente: no hay un formato JSON estable verificado.
- `attack-surface` y `domain-recon` incluyen los módulos nuevos que les corresponden.
- `docs/plans/fase-04.md`: plan de la fase con las decisiones y los entregables bloqueados
  (F4.21, F4.22, F4.23 y los rangos de IP de F4.17).

### Hito G del roadmap (aplicación de escritorio)

- **Ventana principal (G2):** `osineitor-gui` (`[project.gui-scripts]`, sin consola) abre una ventana PySide6 con los menús Archivo (Salir), Ver ▸ Tema (Sistema, Claro, Oscuro) y Ayuda (Uso responsable, Acerca de), la barra de herramientas y una barra de estado que muestra la CLI localizada. Recuerda el tema y la geometría. Si no encuentra la CLI, lo dice en un diálogo y abre igualmente. Solo incluye acciones que ya funcionan.
- **Scan en vivo (G3):** en `osineitor-gui`, Archivo ▸ Nuevo scan (`Ctrl+N`) lanza un scan pasivo (objetivo con el tipo detectado, tipo, profundidad, presupuesto, «no guardar», «sin caché», «refrescar») en una pestaña con la tabla de entidades (filtro por tipo con recuentos y búsqueda), la actividad por módulo con el estado en color, el aviso de resultado incompleto y el progreso en la barra de estado. Cancelar detiene la CLI guardando lo obtenido. Cerrar una pestaña o la ventana con un scan en marcha pide confirmación y no deja la CLI huérfana. Aún sin selector de módulos, `--active` / `--allow-private` ni detalle de entidad.
- **Historial, detalle y exportación (G4):** `osineitor-gui` tiene un panel lateral Historial con los scans guardados (se carga al arrancar y tras cada scan guardado; Archivo ▸ Abrir scan guardado… lo muestra y recarga). Un doble clic abre el scan en una pestaña con el mismo aspecto que uno en vivo, sin duplicarla. Al seleccionar una entidad, un panel de detalle muestra su fuente, su origen y los campos de `data`. Archivo ▸ Exportar scan… escribe JSON, Markdown o HTML de un scan guardado. Las llamadas a la CLI no bloquean la ventana. Sin confianza ni observaciones en el detalle.
- **Panel de salud (G5):** Herramientas ▸ Salud de los módulos… abre un diálogo que lanza `doctor` bajo demanda (puede tardar minutos, sin bloquear la ventana) y muestra el veredicto, el detalle, el tiempo y las peticiones de cada módulo. Solo comprueba módulos pasivos; no se puede cancelar un `doctor` en curso (cerrar el diálogo deja que termine solo).
- **Ajustes y API keys (G6):** Herramientas ▸ Ajustes… (`Ctrl+,`) abre un diálogo con dos pestañas. «API keys» lista una fila por key (varios módulos pueden compartir la misma, p. ej. `hibp`), con su estado, y permite guardarla (campo de contraseña; viaja a la CLI por stdin) o borrarla, sin bloquear la ventana. La key nunca se muestra, ni en un error: si la CLI falla solo se ve un texto fijo y el código de salida. El estado «configurada» sale siempre de la CLI. «General» cambia el tema. No guarda las keys en el Administrador de credenciales de Windows.
- **Avisos legales, `--active` y propósito (G7):** el primer arranque de `osineitor-gui` muestra el aviso de uso responsable con «Acepto» / «Salir»; rechazarlo (Salir, Esc o cerrar) cierra la aplicación sin abrir la ventana, y se vuelve a pedir si el texto cambia de versión. «Nuevo scan» gana un selector de módulos (los que necesitan una API key que falta aparecen deshabilitados con el motivo), las casillas «Incluir módulos activos» y «Permitir redes privadas», cada una tras una confirmación cuyo botón por defecto es Cancelar, y un cuadro «Propósito» (`--purpose`, opcional en la ventana: si tu configuración lo exige para email o username, la CLI rechaza el scan y se ve su mensaje). El panel de salud también confirma antes de `doctor --active`. Las reglas siguen en `ScanRequest`: la vista solo pregunta.
- **Instalador de Windows (G8):** `packaging/windows/` construye con PyInstaller (extra `build`) una carpeta con `osineitor-gui.exe` (sin consola) y `osineitor.exe` (la CLI), un ZIP portable y, con Inno Setup, un instalador por usuario sin UAC (la CLI en el PATH del usuario es opcional y la desinstalación no borra los datos). `smoke.py` prueba el paquete (versión, módulos, presets, un scan sin red y que la GUI arranca). El job `windows` de `release.yml` lo construye en CI y, al empujar una etiqueta, crea una Release de GitHub con el instalador, el ZIP y `SHA256SUMS.txt`; PyPI no depende de él. `workflow_dispatch` construye sin publicar. Sin firmar: Windows mostrará SmartScreen.
- El extra `gui` exige `PySide6-Essentials>=6.8` (el esquema de color) y `dev` incluye `pytest-qt`. Los tests de `tests/gui/test_main_window.py` corren sin pantalla y se omiten si no está PySide6; la CI actual no instala el extra `gui`.

### Fase 11 del roadmap (producto 1.0, v1.0.0)

- **Paquete listo para PyPI (F11.2):** licencia como expresión SPDX (`license = "MIT"`; la forma de
  tabla está obsoleta y setuptools la retirará en 2027), clasificadores y URLs del proyecto. Flujo
  `.github/workflows/release.yml`: al crear una etiqueta `vX.Y.Z` comprueba que coincide con la
  versión, pasa ruff y pytest, construye, revisa con `twine check` y publica con *trusted
  publishing* y atestaciones firmadas con Sigstore, sin ningún token guardado. **Sin publicar y
  sin ejecutar**: ver `docs/PUBLICACION.md`.
- **Imagen Docker (F11.3):** `Dockerfile` de dos etapas (solo el wheel pasa a la imagen final) que
  corre como usuario sin privilegios y guarda los datos en `/data`. La CI construye el paquete, la
  documentación y la imagen. **Sin construir en local** (no hay Docker en este equipo).
- **Sitio de documentación (F11.4):** `mkdocs.yml`, un tutorial y la referencia de módulos generada
  desde el código (`scripts/mkdocs_hooks.py`). Se construye con `mkdocs build --strict`. Los enlaces
  de `docs/` a ficheros fuera de esa carpeta pasan a ser URL de GitHub para que el sitio no los
  rompa. Extra opcional `docs`.
- **Compromiso de estabilidad (F11.6):** `docs/ESTABILIDAD.md` fija qué cubre SemVer (CLI, formatos de
  exportación y API de librería) y la política de obsolescencia de dos versiones menores. Un test
  comprueba que nombra toda la API pública y todos los códigos de salida.
- `docs/MIGRACION.md` (cambios incompatibles desde 0.x), `docs/PUBLICACION.md` y
  `docs/plans/fase-11.md`. No se sube la versión a 1.0.0 ni se publica nada: queda para quien
  mantiene el proyecto. Sin hacer F11.5 (internacionalización).

### Fase 10 del roadmap (asistencia con IA, v0.11.0)

- **`osineitor summarize <scan>` (F10.1, F10.7):** resumen en lenguaje natural de un scan guardado.
  El modelo solo recibe hechos numerados (`[E3] …`), con los hallazgos y su evidencia primero.
  Desactivado hasta crear `ai.yml`; sin dependencias nuevas.
- **Citas verificadas (F10.2):** `ai.validate` descarta toda frase sin cita, con una cita
  inexistente o con una IP, un CVE, un correo o un host que no figura en los hechos citados. Solo
  se muestra lo validado; las descartadas se listan con su motivo (`rejected` en `--json`).
- **Modelos locales y remotos (F10.3):** Ollama (local), OpenAI compatible y Anthropic. Un
  proveedor remoto exige `consent_remote: true`; la clave se lee de una variable de entorno y
  nunca sale en un error; las peticiones pasan por la guardia de red.
- **Evaluación (F10.6):** `scripts/eval_ai.py` y el corpus `tests/ai_eval/corpus.json`; los
  números están en `docs/IA.md`. No se ha probado contra ningún modelo real.
- Código de salida nuevo `12` (solo `summarize`) y salida `--json` `summary_output` (cambio
  aditivo del contrato).
- `docs/IA.md` y `docs/plans/fase-10.md`: quedan sin hacer F10.4 (servidor MCP) y F10.5.

### Fase 9 del roadmap (monitorización, v0.10.0)

- **`osineitor watch run|list|check` (F9.1):** repite los scans de `watch.yml` (cada objetivo con
  su `every`, preset, módulos y profundidad), compara con lo que la vigilancia ya conoce y anota
  el estado. La primera ejecución solo fija la línea base. Migración 8 de la base de datos
  (`watch_targets`, `watch_seen`).
- **Reglas de alerta (F9.2):** `data/rules/alerts.yml` (subdominio, IP, servicio, CVE y filtración
  nuevos) con el mismo motor que los hallazgos; un hallazgo nuevo alerta con su severidad. Lo ya
  conocido no se repite y lo que desaparece en un scan limpio se olvida.
- **Notificaciones (F9.3):** webhook (`generic`, `slack`, `discord`, `teams`), correo SMTP y fichero
  NDJSON, con `min_severity` por notificador. Una alerta que no llega a ninguno se reintenta en la
  siguiente ejecución. Los errores de entrega no revelan URLs ni contraseñas.
- **Códigos de salida nuevos de `watch run`:** `10` (hay alertas) y `11` (alguna no se entregó);
  salidas `--json` `watch_output`, `watch_list_output` y `purge_output` (cambio aditivo).
- **`osineitor purge --older-than 90d` (F9.5):** retención de scans, con `--dry-run`.
- `docs/VIGILANCIA.md` (formato, funcionamiento y despliegue) y `docs/plans/fase-09.md`: quedan
  sin hacer F9.4, F9.6 y F9.7.

### Fase 8 del roadmap (interoperabilidad, v0.9.0)

- **API de librería (F8.5):** `from osineitor import Scanner`; `scan()` síncrona, `ascan()`
  asíncrona y `cancel()` desde otro hilo. Misma maquinaria que la CLI (módulos, guardia de red,
  presupuesto, alcance, evidencias); una petición inválida lanza `ScanInputError`. Los nombres
  públicos se cargan al pedirlos, así que `import osineitor` sigue siendo ligero. Ver
  `docs/API.md`.
- **Plugins externos (F8.6):** los paquetes que declaran el grupo de *entry points*
  `osineitor.modules` añaden módulos sin tocar el código. Un plugin roto o con un nombre repetido
  se omite y `osineitor modules` avisa por stderr. `modules --json` gana el campo `plugin`
  (cambio aditivo del contrato).
- **Formatos de grafo (F8.3):** `export -f graphml|gexf|cypher`.
- **Importación de Nmap (F8.7, parcial):** `osineitor import nmap scan.xml` guarda como un scan los
  hosts activos, sus nombres y sus puertos abiertos de un XML de `nmap -oX`. Solo lee el fichero (máx.
  32 MiB, sin `DOCTYPE` ni entidades); no ejecuta Nmap, no pivota y no guarda la línea de comandos
  de Nmap. El objetivo es un `record` con el SHA-256 del fichero. Su `--json` usa el esquema
  `scan_result` ya existente (sin cambios en el contrato).
- `docs/plans/fase-08.md`: plan de la fase. Quedan sin hacer F8.1 (STIX), el resto de F8.7
  (`--targets-file`, Subfinder, Amass y Maigret) y F8.2 (MISP).

### Fase 7 del roadmap (hallazgos y análisis, v0.8.0)

- **`findings` (F7.8):** analizador con 15 reglas declarativas en YAML
  (`data/rules/default.yml`): cada coincidencia es un `finding` con severidad, entidad afectada,
  evidencia y recomendación. Los hallazgos entran en la base, el JSON, los informes y el resumen.
  Una regla con formato inválido se rechaza al cargar. Nuevo operador `root_domain` (sin lista de
  sufijos públicos).
- **`osineitor diff A B` (F7.3):** entidades nuevas, desaparecidas y modificadas entre dos scans,
  con los hallazgos aparte. Salida `--json` descrita en el esquema del contrato
  (`diff_output`, cambio aditivo).
- **Exportación CSV (F7.11):** `export -f csv|csv-relations|csv-findings`. Las celdas que
  empiezan por `=`, `+`, `-` o `@` se neutralizan para las hojas de cálculo.
- **Grafo interactivo en el informe HTML (F7.1):** nodos por entidad y aristas por pivoteo, con
  filtros por tipo y fuente, arrastre y zoom. JavaScript propio y en línea, sin librerías ni CDN;
  los datos van con `<` escapado. Probado con 500 entidades. Dibuja como máximo 1500.
- `docs/plans/fase-07.md`: plan de la fase. Quedan sin hacer los entregables *S* (F7.2, F7.4,
  F7.5, F7.6, F7.7, F7.9, F7.10 y F7.12).

### Fase 6 del roadmap (nuevos frentes, v0.7.0)

- **Nuevos tipos detectados por `scan`:** teléfono (`+` o `00`), dirección de criptomoneda
  (Bitcoin, Ethereum, Litecoin, Dogecoin, Monero), coordenadas `lat,lon` y ruta de un fichero local
  existente (con `/` o `\`). Un teléfono exige `--purpose` si `require_purpose` está activo.
- **`phone_parse` (F6.5):** país, región, tipo de línea, operador de origen y formatos, en local.
  **Nueva dependencia:** `phonenumbers`.
- **`crypto_detect` (F6.6):** cadena y formato; suma de comprobación de Bitcoin, Litecoin y
  Dogecoin (base58check, bech32 y bech32m). Ethereum y Monero solo por forma.
- **`btc_explorer` (F6.7):** saldo, transacciones y actividad con mempool.space.
- **`file_meta` (F6.9):** EXIF (con GPS), PDF, Office y OpenDocument en local, sin dependencias.
  Rechaza XML con entidades. Un test comprueba que no abre conexiones.
- **`file_hash` (F6.10, parcial):** MD5, SHA-1 y SHA-256 en local; falta el pivote a reputación.
- **`geo_point` (F6.11):** coordenadas en grados-minutos-segundos y enlaces a mapas.
- **`image_links` (F6.17):** enlaces de búsqueda inversa de imágenes; no sube nada.
- **`gleif` (F6.2):** LEI y relaciones matriz–filial de una organización.
- Las coordenadas se normalizan a 6 decimales y una ruta de fichero conserva sus espacios.
- `docs/plans/fase-06.md`: plan de la fase con lo aplazado (F6.1, F6.3, F6.4, F6.8, F6.12 a F6.16
  y F6.18).

### Fase 5 del roadmap (identidades, v0.6.0)

- **Entidad `person` y comando `osineitor person "Nombre Apellido" [--domain d]` (F5.9):**
  `username_variants` genera hasta 12 variantes de username y `email_candidates`, con `--domain`,
  los emails candidatos. Solo generan: no hacen peticiones ni verifican por SMTP. Exigen
  `--purpose` si `require_purpose` está activo.
- **`username_wmn` (F5.3):** ~590 firmas de WhatsMyName (CC BY-SA 4.0, `wmn.json` sin modificar y
  con atribución en `modules/username/data/README.md`). Omite los sitios de contenido adulto y los
  marcados con protección (Cloudflare, captcha...). Verifica cada positivo con un username de
  control, igual que `username_sites`. Un perfil que ven los dos módulos se fusiona y sube a
  confianza `medio`: ese es el «confirmado».
- **`github_user` (F5.7):** perfil público de GitHub, organizaciones, blog y emails de commits
  públicos (se descartan las direcciones `noreply`). Key `github` opcional.
- **`github_email` (F5.2):** commits públicos de GitHub por email: nombres, repositorios y logins.
  Espacia 6 s las búsquedas por el límite de 10 por minuto.
- **`fediverse` (F5.10, activo):** Mastodon `accounts/lookup` y WebFinger sobre el host del email.
  Bluesky queda pendiente (spike).
- **`dev_registries` (F5.11):** perfiles y paquetes en npm, crates.io y Docker Hub. No emite los
  emails de los mantenedores. PyPI y Stack Exchange quedan pendientes.
- **`hibp_pastes` (F5.13):** resumen de los *pastes* del email (nº, fuentes, fechas); no guarda los
  identificadores. Misma key `hibp`.
- **`discord_snowflake` (F5.14):** fecha de creación de la cuenta a partir de su ID, en local.
- El preset `person` incluye los módulos nuevos.
- `docs/plans/fase-05.md`: plan de la fase con los entregables bloqueados o aplazados (F5.1, F5.4,
  F5.5, F5.6, F5.8, F5.12, F5.15).

### Fase 0 del roadmap (validación en campo, v0.1.1)

- **Fixtures reales (F0.2):** `scripts/record_fixtures.py` ejecuta un módulo contra un objetivo público y guarda las respuestas HTTP y DNS en `tests/fixtures/<módulo>/<caso>.json`, sin cookies ni cabeceras de petición. `tests/modules/test_recorded.py` las reproduce con 12 tests para `dns`, `rdap`, `crtsh`, `wayback`, `ipinfo`, `internetdb`, `gravatar`, `email_validate`, `http_fingerprint` y `username_sites`.
- **Prueba en vivo (F0.1, parcial):** esos 10 módulos se ejecutaron contra su servicio real desde Windows el 05-11-2026 y se parsean sin discrepancias (F0.3). Los 6 con API key siguen sin probar. Detalle en `docs/PRUEBAS_WINDOWS.md`.
- **Falsos positivos de usernames (F0.5):** tasa residual medida del 0,26 % (6 de 2286 comprobaciones, 5 usernames) en `docs/FALSOS_POSITIVOS.md`.
- **`doctor` corregido:** sin `-m` fallaba al empezar con `ValidationError: username no válido: 'Banco Santander, S.A.'` porque el `canary` de `gleif` se sembraba como username. Ahora `doctor.seed_entity` siembra con el tipo que consume el módulo cuando es de texto libre (persona u organización). Con todos los módulos pasivos y sin key tarda 41 s.

## [0.5.0] - 2026-10-31

Fase 4 del roadmap (dominio e infraestructura), parte de la v0.5.0: los cinco entregables de
prioridad M. Los módulos de la v0.5.1 siguen pendientes.

### Añadido

- **`mail_security` (F4.4):** MTA-STS, TLS-RPT, BIMI y selectores DKIM comunes, solo con consultas
  DNS (no descarga la política MTA-STS). Deja un `record` `mail_security:<dominio>`.
- **`whois` (F4.11):** WHOIS por el puerto 43 para `.be`, `.co`, `.de`, `.eu`, `.io`, `.it`, `.me`,
  `.mx` y `.pt`, que no tienen RDAP. Registrador, fechas, estado y nameservers; descarta siempre
  los datos del titular y no emite emails. Un TLD sin servidor configurado queda `omitido` con un
  aviso. **El `.es` no se puede consultar:** su WHOIS es un servicio de pago de Red.es con acceso
  restringido por IP, y el módulo lo indica en lugar de fallar en silencio. El socket va fuera de
  `ctx.http`, así que con `--proxy` se omite (`direct_dns`).
- **`saas_footprint` (F4.13):** primer analizador offline. Deduce proveedores de correo, DNS,
  identidad y colaboración desde MX, NS, `include:` del SPF y TXT de verificación, con una tabla de
  firmas propia y versionada (`modules/domain/data/saas_signatures.json`). Emite `technology`.
- **`cert_details` (F4.12):** certificados de Certificate Transparency (crt.sh) como entidad
  `certificate` (huella SHA-256 calculada sobre el DER, sin dependencias nuevas), con emisor,
  validez, SAN y aviso de caducidad (`valido`, `caduca_pronto`, `caducado`). Los SAN pasan como
  `domain` y permiten pivotar a otros dominios. Censys queda para F4.15.
- **`cve_enrich` (F4.14):** CVSS (NVD), EPSS (FIRST) y marca KEV (CISA) sobre las entidades
  `vulnerability`, fusionados en la propia entidad. Clave `nvd` opcional. **Se aparta del roadmap:**
  es un módulo normal con red, no un analizador, porque un analizador no puede usar la red y no hay
  un dataset de CVSS con licencia compatible con MIT.
- Los presets `domain-recon`, `attack-surface` y `email-audit` incluyen los módulos nuevos que les
  corresponden.

### Cambiado

- El aviso de `rdap` para un TLD sin RDAP ya no promete un WHOIS futuro: remite al módulo `whois`.

## [0.4.0] - 2026-10-31

Fases 2 (procedencia y confianza) y 3 (modelo ampliado, presets y adaptadores) del roadmap.
Incluye lo que habría sido la 0.3.0, que no se publicó por separado.

### Añadido

- **Tipos de entidad ampliados (F3.1):** `asn`, `netblock`, `certificate`, `technology`,
  `organization`, `person`, `phone`, `crypto_address`, `file`, `location` y `finding` (este último
  reservado para F7.8), cada uno con su normalización (ASN `AS13335`, CIDR sin bits de host,
  teléfono E.164, huella SHA-256 en minúsculas...). No requiere migración de la BD.
- **Presets de escaneo (F3.2):** `--preset NOMBRE` en `domain`, `ip`, `email`, `username` y `scan`, y
  la orden `osineitor presets`. Siete incluidos (`passive`, `quick`, `domain-recon`,
  `attack-surface`, `person`, `email-audit`, `full`) y YAML propios en el directorio de
  configuración, que sustituyen a un incluido del mismo nombre. Lo escrito en la línea de órdenes
  manda sobre el preset; `allow_active` solo admite los módulos activos, no los activa.
- **Analizadores offline (F3.3):** `Module.analyzer = True`. Corren en un pase final sobre lo
  recogido, con un contexto sin red (usar `http` o `resolver` es un `ModuleError`) y sin gastar
  presupuesto. `osineitor modules` los marca (campo `analyzer` en `--json`).
- **Adaptadores de herramientas externas (F3.4):** `ExternalToolModule` (`modules/_external.py`):
  ejecución sin shell, versión mínima, timeout, salida JSON o NDJSON. Sin el binario el módulo
  queda `omitido` y `osineitor doctor` lo indica.
- **`osineitor update-data` (F3.5):** descarga datasets de terceros (hoy, las firmas de Sherlock)
  y registra versión, SHA-256 y licencia en `manifest.json`; rechaza las licencias incompatibles
  con MIT. `username_sites` usa la copia descargada solo si su hash coincide.
- **Objetivos URL, CIDR y ASN en `scan` (F3.6):** una URL se descompone en su host (dominio o IP);
  un CIDR o un ASN se aceptan como semilla, aunque aún ningún módulo los consume.
- **Filtros de salida (F3.7):** `--only-types` y `--exclude` en los escaneos, `show` y `export`.
  Solo recortan lo que se imprime o exporta; la BD, `--ndjson` y el código de salida no cambian.
- **Anexo de evidencias en los informes (F2.7):** los informes HTML y Markdown terminan con una
  sección «Evidencias»: módulo, entidad consultada, URL, fecha UTC, estado, bytes y SHA-256 completo
  de cada respuesta guardada con `--evidence`, más la huella del conjunto y cómo comprobarla con
  `osineitor verify`. Sin evidencias lo dice en una línea. Los cuerpos no van en el informe. Todo el
  contenido se escapa.
- **Propósito del scan (F2.6):** `--purpose "TEXTO"` (o `OSINEITOR_PURPOSE`) en los scans guarda
  con ellos para qué se hicieron (máx. 500 caracteres); se ve en `show`, en los informes MD y HTML y
  en `scan.start`. El ajuste `require_purpose` (`[settings]` de `config.toml`, o
  `OSINEITOR_REQUIRE_PURPOSE`, que manda sobre el fichero) hace obligatorio el propósito en los scans
  de email y username: sin él, código 2 antes de consultar nada. Base de datos a la versión 7
  (`scans.purpose`). Contrato CLI↔GUI, solo aditivo: `purpose` en `scan.start` y `scan_result`. La GUI
  aún no pasa `--purpose`.
- **Alcance declarado (F2.5):** `--scope scope.yml` (o `OSINEITOR_SCOPE`) en los scans limita la
  investigación a los `domains` y `ips` (IP o CIDR) del fichero, con `exclude`. Lo que cae fuera no
  entra en el resultado ni se pivota, y deja un evento «fuera de alcance» por clave. Los dominios se
  comparan como igual o subdominio (no por sufijo de texto). Un fichero inválido o un objetivo fuera
  del alcance es un error de uso (código 2). Nueva dependencia `pyyaml>=6`. Base de datos a la
  versión 6 (`scans.scope`). Contrato CLI↔GUI, solo aditivo: `scope` en `scan.start` y
  `scan_result`. No controla las redirecciones HTTP a hosts ajenos.
- **Confianza (F2.3):** cada entidad lleva un nivel `bajo`, `medio` o `alto` según las fuentes distintas
  que la vieron, si alguna es autoritativa (atributo nuevo `Module.authority`: `dns`, `rdap`,
  `http_fingerprint`, `email_validate`) y la antigüedad del dato (más de 90 días baja un nivel). Se
  muestra en la tabla de la CLI y en los informes MD y HTML. Base de datos a la versión 5 (los scans
  antiguos quedan sin nivel). Contrato CLI↔GUI: `entity.confidence` opcional; el evento NDJSON `entity`
  lo trae a `null` porque se calcula al terminar el scan.
- **Frescura (F2.4):** cada entidad expone `first_seen` y `last_seen` (primera y última observación
  del scan, UTC; `null` en scans anteriores) en `--json` y NDJSON, y los informes MD y HTML añaden la
  columna «Visto». Se derivan de las observaciones: sin migración. Las fechas de terceros siguen en
  `data` con su nombre. Contrato CLI↔GUI: campos opcionales nuevos en `entity`.
- **Evidencia con hash (F2.2):** `--evidence` en los scans guarda la respuesta original de cada
  fuente (HTTP y consultas DNS, también las negativas) con su SHA-256, la URL consultada sin API
  keys, la fecha UTC y el módulo y la entidad que la provocaron. Desactiva la caché. Nueva orden
  `osineitor verify N [--digest HUELLA]` que recalcula los hashes y sale con el código `5` si algo
  no coincide; la huella de evidencias se imprime al terminar el scan para anotarla fuera de la base
  de datos. Base de datos a la versión 4 (tabla `evidence`). Contrato CLI↔GUI, solo aditivo:
  `evidence` y `evidence_digest` en `scan_result`, `evidence_digest` en `scan.end`, esquema
  `verify_output` y código de salida 5. Guía en `docs/EVIDENCIA.md`.
- **Observaciones múltiples (F2.1):** cada entidad guarda en `observations` todas las veces que un
  módulo la vio (módulo, entidad consultada y hora UTC) en lugar de solo la primera fuente. Un mismo
  dato visto por varios módulos, o por uno desde varias entidades, ya no pierde esa información. La
  columna «Fuente» de la CLI y de los informes MD y HTML lista todos los módulos. Base de datos a la
  versión 3 (migración automática; los scans antiguos quedan sin observaciones y muestran su
  `source`). Contrato CLI↔GUI: `entity.observations` es un campo nuevo y opcional; el evento NDJSON
  `entity` trae solo la primera observación (se emite al descubrirla) y la lista completa va en
  `--json`. `source` no cambia.

### Cambiado

- Con `--proxy`, los módulos de conexión directa se omiten con el mensaje «conexión directa: no se
  enruta por --proxy» (antes mencionaba solo DNS).
- En `scan`, un username con la forma `AS1234` se interpreta como ASN; para tratarlo como username
  hay que usar `osineitor username`.

### Corregido

- **`dns`:** si el resolvedor contesta `REFUSED`, el error lo dice («el resolvedor DNS rechazó la
  consulta de <dominio> (REFUSED)») en vez de «tiempo agotado o sin servidores». Afecta también a
  `osineitor doctor`.

## [0.2.0] - 2026-10-29

Fases 1a (seguridad y datos) y 1b (fiabilidad) del roadmap y contrato CLI↔GUI (v0.2.0).

### Añadido

- **Contrato CLI↔GUI (Hito G1, F1.17, F8.4):** [`docs/CLI_CONTRACT.md`](docs/CLI_CONTRACT.md) y
  [`docs/cli-contract.schema.json`](docs/cli-contract.schema.json), validado en los tests contra la
  salida real de la CLI.
  - `--ndjson` (eventos `scan.start`, `module.start/end`, `entity`, `progress`, `notice`,
    `scan.end`), `--quiet`, `--control-stdin` y `--no-color`.
  - `--json` también en `modules`, `history`, `show`, `doctor`, `config show`, `version` y
    `export`. `config show --json` solo lista nombres de keys.
  - **Cancelación ordenada:** `{"cmd": "cancel"}` por stdin, el cierre de stdin y Ctrl+C detienen
    el scan, guardan lo ya obtenido y terminan con código 130. Probado con un proceso hijo real.
  - **Códigos de salida:** `0` ok, `1` error interno, `2` uso incorrecto, `3` algún módulo falló,
    `4` resultado incompleto por presupuesto, `130` cancelado. `ScanResult.status`
    (`complete`/`truncated`/`cancelled`) acompaña a cada resultado en JSON.
- ROADMAP: **Hito G · Aplicación de escritorio para Windows** (G1–G9), con la excepción al
  principio 8; F11.1 «interfaz web local» queda obsoleto.

- **Proxy y Tor (F1.8):** `--proxy` (o `OSINEITOR_PROXY`) en `scan`, `domain`, `ip`, `email`,
  `username` y `doctor` envía todas las peticiones por un proxy `socks5(h)://` o `http(s)://`
  (nueva dependencia `httpx[socks]`). Con proxy los nombres los resuelve el proxy: la guardia de red
  deja de usar el DNS local (las IP literales privadas siguen bloqueadas) y los módulos con DNS
  directo (`dns`, `email_validate`, atributo nuevo `direct_dns`) se omiten. Un proxy caído no cae a
  conexión directa. Un valor inválido es un error de uso (código 2) y la contraseña del proxy nunca
  llega al registro. Probado con un servidor SOCKS5 de prueba; no con Tor real.
- **Registro estructurado (F1.9):** opciones globales `--verbose`/`-v` (JSON por `stderr`) y
  `--log-file RUTA` (JSON en fichero) con cada petición HTTP, cada módulo y el inicio y fin del scan.
  Nunca guarda consultas de URL, cabeceras ni cuerpos, y enmascara con `***` cualquier API key
  configurada. Sin las opciones no se escribe nada. Nuevo módulo `osineitor/logs.py`.
- **Barra de progreso (F1.17):** en una terminal el scan dibuja una barra en `stderr`
  (módulos completados, entidades y peticiones), alimentada por los eventos `progress`. No aparece
  con `--json`, `--ndjson`, `--quiet` ni con `stdout`/`stderr` redirigidos. Mientras está activa,
  las entidades en vivo se imprimen por la consola de la barra para no corromperla.
- **Health check semanal (F1.3):** el workflow `.github/workflows/doctor.yml` ejecuta
  `osineitor doctor` cada lunes (y a demanda) y mantiene un único issue con la etiqueta
  `salud-fuentes` con las fuentes que fallan; lo actualiza mientras sigan fallando y lo cierra
  cuando se recuperan. Un fallo de fuente no pone el job en rojo.

- **Estado por módulo (F1.1):** cada ejecución deja un `ModuleRun` (`ok`, `empty`, `error`,
  `quota`, `skipped`) con entidades, peticiones, aciertos de caché y duración; se muestra en una
  tabla tras el scan y se guarda en la nueva tabla `module_runs`. Nueva excepción `ModuleQuota`
  (HTTP 429) y helper `status_error`.
- **`osineitor doctor` (F1.2):** prueba cada módulo con un valor de prueba conocido (o comprueba
  que la fuente responde) y sale con código 3 si alguno falla.
- **Migraciones de esquema (F1.4):** `PRAGMA user_version` con migraciones transaccionales; una
  base de la v0.1.0 se actualiza sin perder datos y una de una versión más nueva se rechaza.
- **Caché HTTP (F1.5):** respuestas GET de fuentes pasivas y sin key, 6 h, en `cache.db`, sin
  guardar URLs ni claves. `--no-cache`, `--refresh` y `osineitor cache clear|info`.
- **Límites por fuente (F1.6):** cada módulo accede a HTTP mediante su propia vista
  (`HttpClient.bind`) con caché, contador de peticiones y `min_interval` propios.
- **Timeout por módulo (F1.7):** 180 s por defecto (240 s `crtsh`/`wayback`, 400 s
  `username_sites`); al excederlo se registra como error y el scan continúa.
- **Falsos positivos en usernames (F1.10):** cada positivo se contrasta con un username
  inexistente; si el sitio también lo encuentra se descarta; el perfil lleva `verified`.
- `modules/_manifest.py`: lista explícita de módulos para el ejecutable empaquetado, con un test
  que la contrasta con el disco.

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

- **Capa no visual de la aplicación de escritorio (G2–G7, parte sin pantalla)** en
  `src/osineitor_gui/`, en Python puro y probada contra la CLI real: localizador de la CLI,
  `CliProcess` (eventos, cancelación ordenada con escalada a `terminate`/`kill`), `CliApi` para las
  órdenes `--json`, `ScanRequest` (valida y exige confirmar `--active` y `--allow-private`),
  `ScanSession` (estado para las vistas, igual para scans en vivo y guardados), `GuiSettings` y
  textos legales. [`docs/GUI.md`](docs/GUI.md) recoge el diseño de la ventana y el traspaso a las
  vistas. Extra opcional `gui` (`PySide6-Essentials`), aún sin usar.
- `config set NOMBRE --stdin` lee la API key de stdin para que no aparezca en la línea de
  comandos, y `config unset NOMBRE` la elimina; ambas con `--json`.

### Cambiado

- **Documentación:** el README se reorganiza como portada (estado del proyecto, instalación,
  inicio rápido, módulos y limitaciones) y el detalle de uso pasa a [`docs/USO.md`](docs/USO.md).
  La guía para añadir un módulo pasa a `CONTRIBUTING.md`, actualizada (manifiesto, `canary`,
  `ModuleQuota`). Un test comprueba que los enlaces y las órdenes de la documentación existen.

- **Códigos de salida:** un scan que termina con módulos fallidos devuelve ahora `3` (antes `0`) y
  uno truncado `4`; `doctor` con fallos devuelve `3` (antes `2`). Los scripts que comprobaban el
  código de salida deben tolerarlo.
- Versión `0.2.0`; `jsonschema` entra en las dependencias de desarrollo.

- **RDAP (F1.18):** el módulo consulta el bootstrap de IANA (con caché de 7 días) y para los TLD
  sin servidor RDAP (`.es`, `.io`, `.de`…) queda **omitido con un aviso** en lugar de devolver
  un vacío silencioso.
- **Rutas multiplataforma (F1.16):** configuración en `%APPDATA%\osineitor` y datos en
  `%LOCALAPPDATA%\osineitor` en Windows (con `platformdirs`); en Linux no cambia. Se pueden
  fijar con `OSINEITOR_CONFIG_DIR` y `OSINEITOR_DATA_DIR`. `config.toml` (con las API keys) queda
  legible solo por el usuario actual: en Windows se le quita la herencia de ACL con `icacls`; en
  el resto nace ya con `0600`. Si no se puede restringir, avisa en lugar de callar. La CI incluye
  también macOS.
- `crtsh` descarta los hostnames no válidos en lugar de emitirlos.
- `dns` falla con error cuando el resolvedor no responde (antes devolvía un vacío que parecía
  «sin registros»). Un 429 de cualquier fuente se registra ahora como `quota`, no como error.
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

[Sin publicar]: https://github.com/jmstudio14/OSINEITOR/compare/v0.5.0...HEAD
[0.5.0]: https://github.com/jmstudio14/OSINEITOR/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/jmstudio14/OSINEITOR/compare/v0.2.0...v0.4.0
[0.2.0]: https://github.com/jmstudio14/OSINEITOR/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/jmstudio14/OSINEITOR/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/jmstudio14/OSINEITOR/releases/tag/v0.1.0

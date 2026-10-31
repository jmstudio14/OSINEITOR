# Changelog

Todos los cambios relevantes del proyecto. Formato basado en
[Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y versionado
[SemVer](https://semver.org/lang/es/).

## [Sin publicar]

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

[Sin publicar]: https://github.com/jmstudio14/OSINEITOR/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/jmstudio14/OSINEITOR/compare/v0.2.0...v0.4.0
[0.2.0]: https://github.com/jmstudio14/OSINEITOR/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/jmstudio14/OSINEITOR/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/jmstudio14/OSINEITOR/releases/tag/v0.1.0

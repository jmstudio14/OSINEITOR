<div align="center">

# OSINEITOR

**Herramienta OSINT modular: investiga dominios, IPs, emails y nombres de usuario desde fuentes
abiertas y pivota automáticamente entre lo que descubre.**

[![CI](https://github.com/jmstudio14/OSINEITOR/actions/workflows/ci.yml/badge.svg)](https://github.com/jmstudio14/OSINEITOR/actions/workflows/ci.yml)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
![Windows | Linux | macOS](https://img.shields.io/badge/plataforma-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey)
[![Licencia MIT](https://img.shields.io/badge/licencia-MIT-green)](LICENSE)
![Estado: en desarrollo](https://img.shields.io/badge/estado-en%20desarrollo-orange)

[Instalación](#instalación) · [Inicio rápido](#inicio-rápido) · [Módulos](#módulos) ·
[Guía de uso](docs/USO.md) · [Roadmap](ROADMAP.md)

</div>

---

## ¿Qué es?

OSINEITOR ejecuta una colección de módulos independientes, cada uno con una fuente abierta (DNS,
RDAP, Certificate Transparency, Shodan InternetDB, Gravatar, cientos de sitios web…), y **encadena
los resultados**: lo que un módulo descubre se convierte en el objetivo de los siguientes. Cada
investigación se guarda y se exporta como informe (JSON, Markdown, HTML, CSV, STIX, MISP, superficie
de ataque o resumen ejecutivo) o como grafo (GraphML, GEXF o Cypher).

```
dominio ─► IPs ─► puertos y servicios        email ─► username ─► perfiles en ~460 sitios
        └► subdominios ─► IPs                      └► dominio ─► registros DNS
```

Está pensado para **reconocimiento propio y con autorización** (auditoría de tu infraestructura,
bug bounty, investigación de tu propia huella digital) y como proyecto de aprendizaje. No es un
producto para terceros ni un servicio.

> **Aviso legal.** OSINEITOR solo consulta fuentes abiertas y APIs públicas. Úsalo sobre objetivos
> propios o con autorización expresa. Investigar a personas físicas está sujeto al RGPD y a la
> legislación local; tú eres responsable del uso que hagas de la herramienta. Lee el
> [uso responsable](docs/USO_RESPONSABLE.md).

## Estado del proyecto

Versión **0.5.0**, en desarrollo. Lo que hay y lo que no:

| Área | Estado |
|---|---|
| CLI con 71 módulos en 10 frentes | Disponible |
| Procedencia y confianza (observaciones, evidencia con hash, confianza, alcance, propósito) | Disponible desde la 0.4.0 |
| Modelo ampliado, presets, analizadores offline, adaptadores de herramientas externas, `update-data` y filtros de salida | Disponible desde la 0.4.0 |
| Fuentes nuevas, hallazgos con reglas, `diff`, informes CSV y de grafo, librería y plugins, vigilancia (`watch`), resúmenes con IA opcionales, paquete y documentación (fases 4 a 11 del [roadmap](ROADMAP.md)) | Hecho en el repositorio, **sin publicar** ([CHANGELOG](CHANGELOG.md)) |
| Tests y CI en Windows, Linux y macOS (Python 3.11 y 3.13) | En verde (unos 1600 tests, sin red) |
| Funcionamiento contra las fuentes reales | **Parcial**: los 10 módulos originales sin API key se probaron en vivo desde Windows y tienen fixtures reales ([detalle](docs/PRUEBAS_WINDOWS.md)); `capture`, `doc_harvest`, `cloud_storage_refs`, `ext_exiftool` y `geoip_offline` también se probaron en vivo; los módulos con key y el resto de fuentes de las fases 4 a 11, solo con respuestas simuladas. `osineitor doctor` lo comprueba desde tu red |
| Aplicación de escritorio para Windows | En curso: [capa interna, ventana principal, scan en vivo, historial, exportación, salud, ajustes y avisos legales listos](docs/GUI.md) (`osineitor-gui`); faltan las pruebas manuales en Windows |
| Paquete en PyPI | Preparado ([flujo de publicación](docs/PUBLICACION.md)), **sin publicar** |
| Instalador de Windows | No disponible todavía |

Plataforma principal: **Windows 10/11**. Linux y macOS se prueban en la CI, pero no son el objetivo.

## Características

- **Diez frentes, 71 módulos:** dominios e infraestructura, IPs y servicios, emails y
  filtraciones, usernames, organizaciones, teléfonos, criptomonedas, ficheros, coordenadas y análisis offline. Los módulos son ficheros independientes que se descubren solos.
- **Pivoteo configurable** (`--depth`) con deduplicación y fusión de lo que cada fuente aporta.
- **Fiable y honesto con los fallos:** cada módulo informa de si respondió con datos, sin datos, con
  error o por cuota, para no confundir «no hay resultados» con «la fuente falló». `osineitor
  doctor` comprueba las fuentes. Tiempo máximo por módulo y caché de respuestas.
- **Contenido:** presupuesto de entidades, peticiones y tiempo por scan; el resultado queda marcado
  como incompleto si se agota.
- **Seguro por defecto:** módulos pasivos salvo `--active`; ninguna petición va a redes privadas,
  loopback ni metadatos de nube, tampoco por redirecciones; entradas saneadas y normalizadas.
- **Integrable:** salida `--json` y `--ndjson` (eventos en streaming) con
  [esquema JSON](docs/cli-contract.schema.json), cancelación ordenada y códigos de salida
  documentados.
- **Hallazgos y cambios:** reglas YAML que convierten las entidades en hallazgos con severidad y
  recomendación, y `osineitor diff` para ver qué cambió entre dos scans.
- **Vigilancia:** `osineitor watch` repite scans y avisa solo de lo nuevo, por webhook, correo o
  fichero ([detalle](docs/VIGILANCIA.md)).
- **Exportable y extensible:** CSV y grafos (GraphML, GEXF, Cypher), `from osineitor import Scanner`
  y módulos de terceros como plugins ([API](docs/API.md)).
- **IA opcional y desactivada por defecto:** `osineitor summarize` resume un scan con un modelo local
  o remoto (este último solo con tu consentimiento en la configuración) y solo muestra frases con
  cita verificada ([detalle](docs/IA.md)).

## Instalación

Requiere **Python 3.11 o superior** y Git. Todavía no hay paquete publicado: se instala desde el
código.

**Windows (PowerShell):**

```powershell
git clone https://github.com/jmstudio14/OSINEITOR.git
cd OSINEITOR
py -3.13 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
osineitor version
```

Si PowerShell bloquea la activación, ejecuta antes `Set-ExecutionPolicy -Scope Process Bypass`.

**Linux / macOS:**

```bash
git clone https://github.com/jmstudio14/OSINEITOR.git
cd OSINEITOR
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
osineitor version
```

**Instalador de Windows:** al publicar una versión, la página de Releases de GitHub ofrecerá
`OSINEITOR-x.y.z-setup.exe` (instalación por usuario, sin permisos de administrador), un ZIP
portable y `SHA256SUMS.txt`. Comprueba la descarga con
`Get-FileHash .\OSINEITOR-x.y.z-setup.exe -Algorithm SHA256` y compara con ese fichero. Los
ejecutables no están firmados: Windows mostrará el aviso de SmartScreen («Más información» →
«Ejecutar de todas formas») y algún antivirus puede marcarlos. Todavía no hay ninguna Release
publicada.

Extras: `pip install -e ".[dev]"` (tests y linter), `".[gui]"` (PySide6, para la aplicación de
escritorio `osineitor-gui`), `".[build]"` (PyInstaller, para construir el paquete de Windows) y
`".[docs]"` (para construir el sitio de documentación con `mkdocs`), `".[stix]"` y `".[misp]"`
(para `export -f stix` y `export -f misp`) y `".[capture]"` (Playwright, para el pantallazo del
módulo `capture`; además hace falta `playwright install chromium`).

**Con Docker** (la imagen se construye en local; no está publicada en ningún registro). Corre sin
privilegios y deja los scans en el volumen `/data`:

```bash
docker build -t osineitor .
docker run --rm -v osineitor-data:/data osineitor domain example.com
```

## Inicio rápido

```bash
osineitor doctor                        # ¿qué fuentes responden desde tu red?
osineitor scan example.com              # detecta el tipo y pivota (profundidad 2)
osineitor email alguien@example.com     # validez, perfiles y brechas
osineitor username johndoe              # presencia en cientos de sitios
osineitor scan +34612345678                # teléfono: país, tipo de línea y formatos
osineitor scan ./foto.jpg                   # fichero local: EXIF y hashes (nada se sube)
osineitor person "Ana García López" --domain example.com   # variantes de usuario y emails candidatos
osineitor export 1 -f html              # informe del primer scan guardado
```

Salida real y abreviada de `osineitor email test@example.com -m email_validate`, un módulo que no
necesita red de terceros: primero las entidades según se descubren y al final el estado de cada
módulo.

```
  record        email:test@example.com  (email_validate)
  domain        example.com  (email_validate)
  username      test  (email_validate)
[…tablas por tipo de entidad…]
┏━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━━┓
┃ Módulo         ┃ Estado ┃ Entidades ┃ Peticiones ┃ Caché ┃ Tiempo ┃
┡━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━━┩
│ email_validate │ ok×1   │         3 │          0 │     0 │  0.0 s │
└────────────────┴────────┴───────────┴────────────┴───────┴────────┘
```

## Uso

| Quiero… | Orden |
|---|---|
| Investigar un objetivo, deduciendo su tipo | `osineitor scan OBJETIVO` |
| Investigar un tipo concreto | `osineitor domain`, `ip`, `email` o `username` |
| Usar un perfil de escaneo | `osineitor domain example.com --preset quick` · `osineitor presets` |
| Actualizar los datasets de terceros | `osineitor update-data` |
| Ver o recuperar scans anteriores | `osineitor history` · `show N` · `export N -f json\|md\|html\|csv\|csv-relations\|csv-findings\|graphml\|gexf\|cypher\|stix\|misp\|attack-surface\|executive` · `diff A B` |
| Analizar un scan guardado | `osineitor risk N` · `timeline N` · `resolve N` · `suggest N` |
| Buscar entre los scans guardados | `osineitor search TEXTO` |
| Agrupar scans en casos | `osineitor case new` · `case add` · `case note` · `case show` · `case list` |
| Importar resultados de otras herramientas | `osineitor import nmap` · `import subfinder` · `import maigret` |
| Consultar scans desde un agente de IA | `osineitor mcp` ([detalle](docs/MCP.md)) |
| Comprobar que las evidencias no se han alterado | `osineitor verify N` |
| Ver los módulos y mis API keys | `osineitor modules` · `config show` · `config unset NOMBRE` |
| Comprobar que las fuentes responden | `osineitor doctor` |
| Gestionar la caché | `osineitor cache info` · `cache clear` |
| Vigilar objetivos y recibir avisos de cambios | `osineitor watch run` · `watch list` · `watch check` |
| Borrar scans antiguos | `osineitor purge --older-than 90d` |
| Resumir un scan con IA (opcional, con citas verificadas) | `osineitor summarize 3` |

Opciones que más se usan en los scans:

| Opción | Efecto |
|---|---|
| `--depth N` | Niveles de pivoteo (1–4). Cada nivel multiplica las peticiones |
| `-m MÓDULO` | Ejecuta solo ese módulo (repetible) |
| `--active` | Permite los módulos que contactan al objetivo |
| `--max-entities` · `--max-requests` · `--max-time` | Presupuesto del scan (`0` = sin límite) |
| `--refresh` · `--no-cache` | Ignora o desactiva la caché de respuestas |
| `--evidence` | Guarda la respuesta original de cada fuente con su SHA-256 (`osineitor verify`) |
| `--scope scope.yml` | Limita el scan a los dominios y redes declarados (lo de fuera se descarta) |
| `--purpose "TEXTO"` | Anota para qué haces el scan (exigible en emails, usernames, personas y teléfonos) |
| `--targets-file FICHERO` | Lanza el mismo scan sobre varios objetivos (`scan`) |
| `--domain DOMINIO` | Dominio sobre el que generar emails candidatos (`person`) |
| `--proxy URL` · `--allow-private` | Sale por un proxy · permite redes privadas (solo con tu autorización) |
| `--db RUTA` · `--no-save` | Usa otra base de datos SQLite · no guarda el scan |
| `--preset NOMBRE` | Aplica un perfil: módulos, profundidad y presupuesto (`osineitor presets`) |
| `--only-types` · `--exclude` | Muestran u ocultan tipos de entidad en la salida |
| `--json` · `--ndjson` | Salida para otros programas |

Todas las órdenes y su comportamiento (estado de cada módulo, presupuesto, caché, red, entradas)
están en la **[guía de uso](docs/USO.md)**.

## Módulos

| Frente | Módulo | Fuente | API key |
|---|---|---|---|
| Dominio | `rdap` | RDAP (rdap.org): registrador, fechas, nameservers | — |
| Dominio | `dns` | A/AAAA/CNAME/MX/NS/TXT/CAA, SPF, DMARC | — |
| Dominio | `crtsh` | Subdominios por Certificate Transparency | — |
| Dominio | `wayback` | URLs archivadas; destaca rutas sensibles (`.env`, `.sql`, `/admin`…) | — |
| Dominio | `http_fingerprint` | Servidor, tecnologías, cabeceras de seguridad (**activo**) | — |
| Dominio | `hunter_domain` | Emails públicos del dominio y su patrón | `hunter` |
| Dominio | `mail_security` | MTA-STS, TLS-RPT, BIMI y selectores DKIM comunes (solo DNS) | — |
| Dominio | `whois` | WHOIS (puerto 43) de los TLD sin RDAP: registrador, fechas, estado | — |
| Dominio | `saas_footprint` | Proveedores de correo, DNS, identidad y colaboración deducidos del DNS | — |
| Dominio | `analytics_ids` | IDs de Google Analytics, Tag Manager, Ads y AdSense de la página (**activo**) | — |
| Dominio | `cert_details` | Certificados en CT: huella SHA-256, emisor, validez, SAN y aviso de caducidad | — |
| Dominio | `web_meta` | `robots.txt`, `sitemap.xml` y `security.txt` (**activo**) | — |
| Dominio | `takeover` | Subdominios con CNAME a un servicio sin reclamar (**activo**) | — |
| Dominio | `urlscan` | Escaneos públicos de urlscan.io: IPs, subdominios y URLs | opcional `urlscan` |
| Dominio | `otx` | Pulses y DNS pasivo (AlienVault OTX) | `otx` |
| Dominio | `virustotal` | Reputación de un dominio, IP o hash de fichero y subdominios (VirusTotal) | `virustotal` |
| Dominio | `tech_detect` | Tecnologías por firmas propias: CMS, frameworks, CDN… y plugins y temas de WordPress de la portada (**activo**) | — |
| Dominio | `favicon_pivot` | Hosts con el mismo favicon, vía Shodan (**activo**) | `shodan` |
| Dominio | `lookalike_domains` | Dominios parecidos ya registrados (defensivo, solo DNS) | — |
| Dominio | `ext_subfinder` | Subdominios con Subfinder (binario del usuario) | — |
| Dominio | `search_dorks` | Documentos e índices públicos del dominio con plantillas (API de Brave Search) | `brave` |
| Dominio | `github_code` | Menciones del dominio en código de GitHub y reglas de secretos; nunca guarda el valor | `github` |
| Dominio | `doc_harvest` | Descarga documentos públicos del dominio y extrae sus metadatos (**activo**) | — |
| Dominio | `cloud_storage_refs` | Acceso público de los buckets de S3, GCS y Azure citados en URLs (**activo**) | — |
| Dominio | `capture` | Guarda una URL como evidencia: cuerpo, cabeceras, WARC y pantallazo (**activo**) | — |
| Dominio | `cloud_attribution` | CDN y nube deducidos del CNAME, la huella HTTP y los rangos de IP de AWS, GCP, Azure y Cloudflare | — |
| IP | `censys` | Servicios, ASN y país (Censys Platform) | `censys` |
| IP | `abusech` | IOC en ThreatFox y URLhaus y hash de fichero en MalwareBazaar (abuse.ch) | `abusech` |
| IP | `ptr` | DNS inverso | — |
| IP | `reverse_ip` | Hostnames alojados en la misma IP (HackerTarget) | — |
| IP | `ripestat` | ASN, prefijo, país de registro e historial de enrutamiento (RIPEstat) | — |
| IP | `asn_netblock` | De IP a ASN y prefijo (Team Cymru) y de ASN a sus prefijos | — |
| IP | `dnsbl` | Listas negras DNS (Spamhaus ZEN, SpamCop, UCEPROTECT, DroneBL) | — |
| IP | `ipinfo` | Geolocalización, ASN, hostname | opcional `ipinfo` |
| IP | `geoip_offline` | Geolocalización con una base GeoLite2 local, sin enviar la IP a terceros | — (colocas tú la base) |
| IP | `internetdb` | Puertos, CPEs y CVEs (Shodan InternetDB) | — |
| IP | `cve_enrich` | CVSS (NVD), EPSS y marca KEV de cada CVE | opcional `nvd` |
| IP | `shodan` | Servicios con producto/versión, SO, CVEs | `shodan` |
| IP | `abuseipdb` | Puntuación y reportes de abuso | `abuseipdb` |
| IP | `greynoise` | ¿Escáner masivo o servicio legítimo conocido? | `greynoise` |
| Email | `email_validate` | Sintaxis, MX, desechable; pivota a dominio y username | — |
| Email | `gravatar` | Perfil público y cuentas enlazadas | — |
| Email | `hibp` | Brechas de datos (Have I Been Pwned) | `hibp` |
| Email | `hunter_verify` | Entregabilidad y fuentes públicas | `hunter` |
| Email | `leakcheck` | Nombres de las filtraciones en las que aparece el email (LeakCheck, API pública; sin datos) | — |
| Email | `pgp_keyserver` | Clave PGP pública con identidad verificada en keys.openpgp.org | — |
| Email | `hibp_pastes` | Apariciones del email en *pastes* (solo un resumen, sin identificadores) | `hibp` |
| Email | `github_email` | Commits públicos de GitHub con ese email: nombres, repositorios, logins | opcional `github` |
| Email | `fediverse` | Cuenta de Mastodon o fediverso de `usuario@instancia` (**activo**, contacta al host) | — |
| Email | `email_candidates` | Candidatos de email de una persona sobre un dominio (sin red ni SMTP) | — |
| Username | `username_sites` | Presencia en ~460 sitios (firmas de Sherlock) | — |
| Username | `username_wmn` | Presencia en ~600 sitios (firmas de WhatsMyName); coincidir con Sherlock da confianza `medio` | — |
| Username | `ext_maigret` | Cuentas con Maigret (binario del usuario; sin recursión) | — |
| Username | `github_user` | Perfil de GitHub: nombre, empresa, blog, organizaciones y emails de commits | opcional `github` |
| Username | `bluesky` | Perfil público de Bluesky: nombre, bio, fecha de alta y actividad | — |
| Username | `dev_registries` | Perfiles y paquetes en npm, crates.io, Docker Hub y PyPI; nombres iguales en Stack Overflow | — |
| Username | `profile_extract` | Nombre, bio, web y usernames que el dueño declaró en DEV Community y Codeberg; se pivotan | — |
| Username | `discord_snowflake` | Fecha de creación de una cuenta de Discord a partir de su ID (sin red) | — |
| Username | `username_variants` | Variantes de usuario a partir de un nombre completo (sin red) | — |
| Org | `gleif` | LEI de una organización y relaciones matriz–filial (GLEIF) | — |
| Org | `opensanctions` | Coincidencias en listas de sanciones y de personas expuestas (OpenSanctions) | `opensanctions` |
| Teléfono | `phone_parse` | País, región, tipo de línea, operador de origen y formatos (sin red) | — |
| Cripto | `crypto_detect` | Cadena y formato de una dirección; valida la suma (sin red) | — |
| Cripto | `btc_explorer` | Saldo, transacciones y actividad de una dirección de Bitcoin (mempool.space) | — |
| Cripto | `eth_explorer` | Saldo y primera y última actividad de una dirección de Ethereum (Etherscan) | `etherscan` |
| Fichero | `file_meta` | EXIF, PDF, Office y OpenDocument de un fichero local (sin red) | — |
| Fichero | `file_hash` | MD5, SHA-1 y SHA-256 de un fichero local (sin red) | — |
| Fichero | `ext_exiftool` | Metadatos con ExifTool de formatos que `file_meta` no cubre (binario del usuario, sin red) | — |
| Fichero | `image_links` | Enlaces de búsqueda inversa de una imagen por URL (sin red) | — |
| Análisis | `findings` | Hallazgos con severidad y recomendación según reglas YAML (sin red) | — |
| Geo | `geo_point` | Coordenadas: grados-minutos-segundos y enlaces a mapas (sin red) | — |

Los módulos **pasivos** solo hablan con terceros. Los **activos** (`http_fingerprint`, `web_meta`,
`analytics_ids`, `takeover`, `tech_detect`, `favicon_pivot`, `fediverse`, `capture`, `doc_harvest` y
`cloud_storage_refs`) envían tráfico al objetivo y solo se ejecutan con `--active`. Un módulo sin su API key se omite y se indica
en la salida. Qué datos aporta cada uno y sus límites: [referencia de módulos](docs/MODULES.md).

## Configuración

```bash
osineitor config set shodan TU_KEY      # guarda la key en el directorio de configuración
osineitor config show                   # keys enmascaradas (se ven solo los 4 primeros caracteres)
export OSINEITOR_SHODAN_KEY=TU_KEY      # alternativa: variable de entorno (tiene prioridad)
```

| | Windows | Linux |
|---|---|---|
| Configuración y keys | `%APPDATA%\osineitor\config.toml` | `~/.config/osineitor/config.toml` |
| Historial (SQLite) y cachés | `%LOCALAPPDATA%\osineitor\` | `~/.local/share/osineitor/` |

El fichero de keys **no se cifra**: se restringe a tu usuario (`0600` en Linux y macOS, `icacls`
en Windows). Nombres de key,
`--stdin` para no dejar la key en la línea de comandos y rutas alternativas: [guía de
uso](docs/USO.md#api-keys-y-rutas).

## Uso desde otros programas

La CLI es la interfaz estable sobre la que se construye la aplicación de escritorio, y sirve igual
a tus scripts: `--ndjson` emite un evento JSON por línea mientras corre el scan, `--json` un único
documento, `--control-stdin` permite cancelar guardando lo ya obtenido y los códigos de salida
distinguen un fallo de un resultado incompleto (`0` ok, `3` algún módulo falló, `4` incompleto,
`130` cancelado; `verify`, `watch run` y `summarize` añaden `5`, `10`–`11` y `12`). Contrato completo: [CLI_CONTRACT.md](docs/CLI_CONTRACT.md).

## Limitaciones conocidas

- **Las fuentes reales solo se han comprobado en parte.** Los 10 módulos originales sin API key se
  ejecutaron en vivo; el resto (los 6 con key y las fuentes de las fases 4 a 11) solo se prueba
  con respuestas simuladas. Ejecuta `osineitor doctor` y revisa
  [las pruebas en Windows](docs/PRUEBAS_WINDOWS.md).
- **Usernames:** la detección se basa en el código de estado o en el texto de la respuesta. WAFs,
  captchas y cambios en los sitios producen falsos positivos y negativos. Cada positivo se
  contrasta con un username inexistente y se descarta si el sitio también lo «encuentra», pero la
  tasa real de falsos positivos **no está medida**. Verifica a mano cualquier perfil.
- **Muchos TLD no tienen RDAP** (`.es`, `.io`, `.de`…): `rdap` lo indica como omitido y el módulo
  `whois` cubre una parte de ellos ([cobertura](docs/RDAP_COBERTURA.md)).
- **crt.sh y Wayback** son servicios gratuitos que a menudo responden lento o con errores 5xx; el
  scan continúa y la incidencia queda anotada.
- Las cuotas gratuitas de ipinfo, GreyNoise y Hunter son bajas.
- Los valores por defecto del presupuesto, la caché (6 h) y los tiempos máximos son estimaciones
  sin medir.

## Hoja de ruta

El plan completo, con criterios de aceptación y lo que queda fuera de alcance, está en el
**[roadmap](ROADMAP.md)**. Lo más próximo:

1. **Aplicación de escritorio para Windows** (en curso): el instalador está escrito; faltan
   ejecutarlo en la CI y las pruebas manuales.
2. **Publicar la 1.0:** paquete en PyPI e imagen Docker; el flujo está escrito y falta ejecutarlo
   ([publicación](docs/PUBLICACION.md)).
3. Las fuentes evaluadas y no incluidas por depender de cuentas, claves o red real que no se han
   podido verificar (OpenSanctions, OpenCorporates, Etherscan, captura con navegador,
   `--tags`/`--top`…): ver el roadmap y la [referencia de módulos](docs/MODULES.md#fuentes-evaluadas-y-no-incluidas).

## Desarrollo

```bash
pip install -e ".[dev]"
ruff check . && ruff format --check .
python -m pytest -q
```

Los tests no hacen peticiones reales: el HTTP se simula con `respx` y el DNS con un resolver en
memoria. Para añadir una fuente nueva, sigue [CONTRIBUTING.md](CONTRIBUTING.md); el diseño está en
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Documentación

| Documento | Contenido |
|---|---|
| [Tutorial](docs/TUTORIAL.md) | Una primera investigación de principio a fin |
| [Guía de uso](docs/USO.md) | Órdenes, opciones, presupuesto, caché, red y códigos de salida |
| [Referencia de módulos](docs/MODULES.md) | Fuentes, datos que aportan y limitaciones |
| [Arquitectura](docs/ARCHITECTURE.md) | Motor, pivoteo, modelo de datos y persistencia |
| [Asistencia con IA](docs/IA.md) | `osineitor summarize`: activación, consentimiento, validación de citas y evaluación |
| [Servidor MCP](docs/MCP.md) | `osineitor mcp`: consulta de scans y scans pasivos para agentes de IA, y lo que no pueden hacer |
| [Vigilancia continua](docs/VIGILANCIA.md) | `osineitor watch`: alertas, notificadores y despliegue con cron o GitHub Actions |
| [API de librería y plugins](docs/API.md) | `from osineitor import Scanner` y cómo añadir módulos desde un paquete |
| [Contrato de la CLI](docs/CLI_CONTRACT.md) | Eventos NDJSON, salidas JSON y cancelación |
| [Evidencia](docs/EVIDENCIA.md) | `--evidence`: respuestas originales con SHA-256 y `osineitor verify` |
| [Cobertura RDAP](docs/RDAP_COBERTURA.md) | Qué TLD tienen RDAP y cuáles cubre `whois` |
| [Aplicación de escritorio](docs/GUI.md) | Diseño y estado de la interfaz gráfica |
| [Compromiso de estabilidad](docs/ESTABILIDAD.md) | Qué cubre SemVer desde 1.0 y la política de obsolescencia |
| [Migración desde 0.x](docs/MIGRACION.md) | Cambios que pueden romper scripts al actualizar |
| [Publicar una versión](docs/PUBLICACION.md) | PyPI con publicación de confianza y atestaciones Sigstore |
| [Pruebas en Windows](docs/PRUEBAS_WINDOWS.md) | Qué se ha comprobado en vivo y qué falta |
| [Falsos positivos de usernames](docs/FALSOS_POSITIVOS.md) | Línea base medida de `username_sites` |
| [Uso responsable](docs/USO_RESPONSABLE.md) | Autorización, RGPD y usos no aceptables |
| [Roadmap](ROADMAP.md) · [Changelog](CHANGELOG.md) | Hacia dónde va y qué ha cambiado |

## Seguridad y contribuciones

Para informar de una vulnerabilidad, mira [SECURITY.md](SECURITY.md) (no abras un issue público).
Las contribuciones son bienvenidas: [CONTRIBUTING.md](CONTRIBUTING.md) y
[código de conducta](CODE_OF_CONDUCT.md).

## Licencia y créditos

[MIT](LICENSE) © 2026 jmstudio14.

Las firmas de detección de usernames proceden de [Sherlock](https://github.com/sherlock-project/sherlock)
(MIT) y de [WhatsMyName](https://github.com/WebBreacher/WhatsMyName) (CC BY-SA 4.0, © Micah Hoffman,
fichero `wmn.json` sin modificar); ver `src/osineitor/modules/username/data/README.md`.

La aplicación de escritorio incluye las fuentes Inter y JetBrains Mono (SIL OFL 1.1) y un
subconjunto de los iconos Lucide (ISC); las licencias están junto a ellos en
`src/osineitor_gui/ui/assets/`.

`geoip_offline` lee una base que el paquete no incluye. This product includes GeoLite Data created by
MaxMind, available from [https://www.maxmind.com](https://www.maxmind.com).

# Referencia de módulos

Para cada módulo: qué consume, qué produce, de dónde saca los datos y sus limitaciones.
`osineitor modules` muestra el estado actual (incluido si falta la API key) y `osineitor doctor`
prueba cada uno contra su fuente (valor de prueba: `example.com`, `1.1.1.1` o `test@example.com`;
`whois` usa `google.io`; `username_sites` y `username_wmn` solo comprueban que `github.com` responde, porque sus
~460 y ~590 peticiones no son una prueba de salud, y `cve_enrich` consulta la API de EPSS). Todos los módulos pasivos y sin key cachean sus respuestas 6 horas, salvo
`username_sites` y `username_wmn`.

Los módulos de plugins externos (paquetes que declaran el grupo de *entry points*
`osineitor.modules`) aparecen en `osineitor modules` marcados como «plugin»; cómo escribirlos está
en [API.md](API.md#plugins).

Hay dos tipos especiales de módulo: los **analizadores** (`analyzer = True`) leen lo ya recogido
en un pase final, sin red (`saas_footprint` y `cloud_attribution`), y los adaptadores de
**herramientas externas** (`ExternalToolModule`; por ahora `ext_subfinder` y `ext_maigret`) ejecutan un binario
instalado por el usuario y quedan `omitido` si falta. Ver [Arquitectura](ARCHITECTURE.md).

Pesan más en la [confianza](ARCHITECTURE.md) de un dato los módulos **autoritativos**, cuya respuesta
viene de quien administra el dato: `dns`, `rdap`, `whois`, `mail_security`, `http_fingerprint`,
`email_validate`, `ptr`, `web_meta`, `analytics_ids`, `takeover` y `tech_detect`. El resto son bases de terceros (`aggregated`).

## Dominio

### `rdap`
- **Consume:** dominio raíz. **Produce:** `record` `rdap:<dominio>`, `email` de contactos.
- **Fuente:** [rdap.org](https://rdap.org), que redirige al servidor RDAP del registro.
- **Datos:** registrador, fechas de creación, caducidad y última modificación, estado,
  nameservers, DNSSEC y contactos (registrante, administrativo, técnico) si son públicos.
- **Límites:** con el RGPD la mayoría de registros ocultan los contactos; es normal que no salgan
  emails.
  **Muchos TLD no tienen servidor RDAP.** Según el bootstrap de IANA del 28-10-2026 no lo tienen
  `.es`, `.io`, `.de`, `.mx`, `.it`, `.co`, `.me`, `.cl`, `.pt`, `.ru` ni `.cn`; sí `.com`, `.fr`,
  `.uk`, `.ar` y `.br`. Para esos dominios el módulo queda **omitido** (`skipped: el TLD .es no
  tiene servidor RDAP…`) en lugar de devolver un vacío silencioso. El bootstrap se descarga de
  IANA y se guarda 7 días en el directorio de datos; si no se puede obtener, se intenta la
  consulta igualmente. Algunos de esos TLD los cubre el módulo [`whois`](#whois).

### `dns`
- **Consume:** dominio y subdominios. **Produce:** `record` `dns:<dominio>`, `ip`.
- **Fuente:** resolver DNS del sistema (dnspython). Con `--proxy` se omite (consulta DNS directa).
- **Datos:** A, AAAA, CNAME, MX, NS, TXT, CAA, política SPF y DMARC (`_dmarc.<dominio>`).
- **Pivote:** cada IP de A/AAAA pasa al siguiente nivel.
- **Wildcard (F1.15):** en un subdominio, sondea una etiqueta aleatoria de su zona (una vez por zona
  y escaneo). Si el subdominio solo resuelve a las IP del wildcard lo marca `wildcard: true` (en el
  `record` y en el propio `domain`) y **no pivota** a esas IP. Un subdominio con una IP propia, o
  una zona sin wildcard, no cambia. El dominio raíz no se sondea.
- **Errores:** si ningún tipo de registro obtiene respuesta, falla en vez de devolver un vacío.
  El mensaje distingue `REFUSED` (el servidor rechaza el nombre) de un tiempo agotado.

### `crtsh`
- **Consume:** dominio raíz. **Produce:** `domain` (subdominios, máx. 500).
- **Fuente:** logs de Certificate Transparency vía [crt.sh](https://crt.sh).
- **Límites:** crt.sh suele ir lento o devolver 5xx con dominios grandes (timeout de 60 s). Incluye
  subdominios históricos que pueden no existir ya.

### `wayback`
- **Consume:** dominio raíz. **Produce:** `record` `wayback:<dominio>`, `url` sensibles (máx. 200).
- **Fuente:** API CDX de la [Wayback Machine](https://web.archive.org) (máx. 5000 URLs).
- **Datos:** número de URLs archivadas, primera y última captura, y URLs que coinciden con patrones
  sensibles: ficheros (`.env`, `.sql`, `.bak`, `.zip`, `.log`, `.git`…), paneles (`/admin`,
  `/wp-login`, `/phpmyadmin`, `/graphql`, `/swagger`…) y parámetros (`token=`, `apikey=`,
  `password=`…).

### `http_fingerprint` (activo)
- **Consume:** dominio y subdominios. **Produce:** `record` `http:<dominio>`.
- **Fuente:** petición GET directa al sitio (HTTPS y, si falla, HTTP). Solo con `--active`.
- **Datos:** código de estado, URL final, título, cabeceras `Server` y `X-Powered-By`, tecnologías
  detectadas por firma (WordPress, Next.js, Cloudflare…) y cabeceras de seguridad que faltan.

### `hunter_domain` (key `hunter`)
- **Consume:** dominio raíz. **Produce:** `record` `hunter:<dominio>`, `email`.
- **Fuente:** API `domain-search` de [Hunter](https://hunter.io).
- **Datos:** organización, patrón de emails (`{first}.{last}`…) y emails públicos con nombre,
  cargo y confianza. El plan gratuito devuelve 10 emails y tiene pocas búsquedas al mes.

### `mail_security`
- **Consume:** dominio raíz. **Produce:** `record` `mail_security:<dominio>`.
- **Fuente:** consultas DNS TXT al resolver del sistema (dnspython); con `--proxy` se omite. No
  contacta con el dominio ni descarga la política MTA-STS por HTTPS.
- **Datos:** `MTA_STS` (`_mta-sts.<d>`), `TLS_RPT` (`_smtp._tls.<d>`), `BIMI` (`default._bimi.<d>`)
  y `DKIM`: la lista de selectores hallados entre ~15 de uso común (`default`, `google`,
  `selector1`, `selector2`, `k1`, `k2`, `s1`, `s2`…). Un selector cuenta si su TXT lleva `p=`.
- **Límites:** DKIM no se puede enumerar: un dominio con un selector propio no aparecerá. Sin
  ninguna política ni selector devuelve vacío; si el resolvedor no responde, falla.
- **Términos y datos:** DNS público, sin cuota propia ni licencia aplicable.

### `whois`
- **Consume:** dominio raíz. **Produce:** `record` `whois:<dominio>`.
- **Fuente:** WHOIS por el puerto 43 del registro del TLD, para los TLD de la tabla
  `modules/domain/data/whois_servers.json`: `.be`, `.co`, `.de`, `.eu`, `.io`, `.it`, `.me`, `.mx`
  y `.pt`. Es un socket directo: no pasa por la guardia de red ni el presupuesto de peticiones, y
  con `--proxy` se omite. La evidencia (`--evidence`) lleva `method` `WHOIS`.
- **Datos:** registrador, fechas de creación, caducidad y modificación (normalizadas a ISO 8601),
  estado, nameservers y DNSSEC, según lo que publique cada registro (`.de` no da registrador ni
  fechas de creación). **Privacidad:** solo se leen esos campos; el titular y los contactos
  (nombre, organización, dirección, email, teléfono) se descartan siempre y no se emite ningún
  `email`.
- **Límites:** un TLD que no está en la tabla queda **omitido** con un aviso (los que tienen RDAP
  los cubre `rdap`). **`.es` no se puede consultar:** el WHOIS del `.es` es un servicio de pago de
  Red.es con acceso restringido por IP y el `.es` no tiene RDAP; el módulo lo dice en el aviso en
  lugar de intentar la conexión. Se espacian 2 s las consultas al mismo servidor, y una respuesta
  de límite de uso se registra como cuota. No se sigue la delegación dinámica de IANA: solo
  valen los servidores de la tabla.
- **Términos y datos:** cada registro limita el uso a fines informativos y prohíbe la consulta
  masiva y el envío de publicidad; los datos son de su registro y no se redistribuyen.

### `saas_footprint` (analizador)
- **Consume:** el `record` `dns:<dominio>` que deja `dns`. **Produce:** `technology` (nombre del
  proveedor) con `category` (`email`, `dns`, `identity` o `collaboration`), `evidence` (qué registro
  casó) y `signatures` (versión de la tabla). Lo que emite no se pivota.
- **Fuente:** ninguna: lee lo ya recogido, sin red ni presupuesto. Firmas propias y versionadas en
  `modules/domain/data/saas_signatures.json` (MX, NS, `include:` del SPF y TXT de verificación).
  Solo produce algo si `dns` también corre.
- **Límites:** deduce el proveedor por convención de nombres; un proveedor que reenvía a otro, o un
  TXT de verificación antiguo, indican uso pasado, no necesariamente actual.
  `google-site-verification=` también lo usa Search Console.
- **Términos y datos:** tabla propia, bajo la licencia del proyecto (MIT).

### `cert_details`
- **Consume:** dominio raíz. **Produce:** `certificate` (valor: huella SHA-256), `domain` (SAN).
- **Fuente:** logs de Certificate Transparency vía [crt.sh](https://crt.sh): una consulta
  `?q=<dominio>` y, por cada uno de los 20 certificados más recientes, la descarga del PEM
  (`?d=<id>`) para calcular la huella SHA-256 sobre el DER, la misma que enseñan los navegadores.
- **Datos:** emisor, nombre común, serie, `not_before`, `not_after`, `san`, `expires_in_days` y
  `status` (`valido`, `caduca_pronto` a 30 días o menos, `caducado`). Cada SAN pasa como `domain`
  (con `subdomain` solo si cuelga del dominio investigado): así se llega a otros dominios que
  comparten certificado.
- **Límites:** crt.sh es un servicio voluntario, lento y sin SLA (un PEM puede tardar decenas de
  segundos); se espacia 1 s entre peticiones y las descargas tienen 150 s en total: los
  certificados que no lleguen a tiempo se omiten sin perder los ya bajados.
  Un precertificado y su certificado final comparten serie pero tienen huella distinta, y los dos
  salen. Si falla la descarga de un certificado se conservan los demás; si fallan todos, error.
  Censys como segunda fuente queda para F4.15.
- **Términos y datos:** crt.sh no publica cuota; los logs de CT son públicos.

### `analytics_ids` (activo)
- **Consume:** dominio raíz. **Produce:** `record` `analytics:<ID>`.
- **Fuente:** la página de inicio del propio dominio (HTTPS y, si no responde, HTTP).
- **Datos:** IDs de Google Analytics 4 (`G-`), Universal Analytics (`UA-`), Google Ads (`AW-`),
  Tag Manager (`GTM-`) y AdSense (`ca-pub-`), con su tipo y el dominio donde aparecen. Los
  patrones de `G-` y `GTM-` exigen un dígito para no confundirse con clases CSS.
- **Límites:** solo lee el HTML de la portada, no los scripts que carga ni otras páginas. No
  busca otros dominios con el mismo ID: ninguna fuente gratuita de esa búsqueda inversa se ha
  verificado. Cada ID es un `record`, no se pivota.

### `web_meta` (activo)
- **Consume:** dominio raíz. **Produce:** `record` `web_meta:<dominio>`, `url`, `email`.
- **Fuente:** el propio sitio: `/robots.txt`, los sitemaps (los declarados en robots.txt que sean
  del mismo sitio, o `/sitemap.xml`) y `/.well-known/security.txt` o `/security.txt` (RFC 9116).
  Prueba HTTPS y, si no responde, HTTP. Solo con `--active`.
- **Datos:** rutas `Disallow` concretas (sin comodines), URLs de los sitemaps (hasta 50 en total
  como `url`), contacto, caducidad (`security_expired`), política y clave de `security.txt`, y el
  email de un contacto `mailto:`.
- **Límites:** una respuesta HTML se descarta (muchos sitios devuelven su portada para cualquier
  ruta). Cada fichero se lee hasta 1 MB y se visitan como máximo 3 sitemaps. No sigue sitemaps
  de otros dominios. Si el sitio no responde por HTTP(S) falla; sin ninguno de los tres ficheros,
  vacío.
- **Términos y datos:** son ficheros que el sitio publica para ser leídos; unas 6 peticiones
  como máximo por dominio.

### `takeover` (activo)
- **Consume:** dominio (cualquier subdominio). **Produce:** `record` `takeover:<host>`.
- **Fuente:** DNS (CNAME y existencia del destino) y la portada del propio subdominio. Solo con
  `--active`; con `--proxy` se omite (DNS directo).
- **Datos:** servicio (GitHub Pages, Heroku, S3, Shopify, Fastly, Zendesk, Surge, Bitbucket, Ghost,
  Pantheon, Tumblr y varios de Azure), CNAME y la evidencia: destino inexistente (NXDOMAIN) y/o
  la página con el mensaje de recurso sin reclamar. Tabla de firmas versionada en el código.
- **Límites:** **solo detecta, nunca intenta reclamar el recurso.** Es una pista, no una prueba:
  un servicio puede cambiar su mensaje de error (falso negativo) y el CNAME a Azure sin texto
  de comprobación solo cuenta si el destino ya no existe. Un fallo del resolvedor no cuenta como
  colgante.
- **Términos y datos:** consulta DNS pública y una petición a un host del propio objetivo.

### `urlscan` (key opcional `urlscan`)
- **Consume:** dominio raíz. **Produce:** `record` `urlscan:<dominio>`, `ip`, `domain`
  (subdominios) y `url`.
- **Fuente:** búsqueda de [urlscan.io](https://urlscan.io/docs/api/) (`domain:<dominio>`, 100
  resultados). Con key (`config set urlscan`) sube la cuota.
- **Datos:** número de escaneos, primera y última fecha, países, y hasta 20 IP, subdominios y URLs
  vistos en escaneos públicos.
- **Límites:** solo cuentan los resultados cuyo host es el objetivo o un subdominio suyo; un
  escaneo ajeno que solo menciona el dominio se descarta. Sin key la cuota es baja (429 → cuota
  agotada). Un escaneo es una foto de un momento: las IP pueden haber cambiado.
- **Términos y datos:** los escaneos son públicos y los envía cualquier usuario; urlscan.io
  limita el uso de la API según el plan.

### `otx` (key `otx`)
- **Consume:** dominio raíz o IP. **Produce:** `record` `otx:<valor>`, `domain` e `ip`.
- **Fuente:** API de [AlienVault OTX](https://otx.alienvault.com): `indicators/domain/<d>/general`,
  `.../passive_dns` e `indicators/IPv4|IPv6/<ip>/general`. Key gratuita.
- **Datos:** número de *pulses* (informes de amenazas que lo citan), reputación y país (IP), y del
  DNS pasivo hasta 50 subdominios del objetivo y las IP a las que resolvieron.
- **Límites:** un dominio o IP sin *pulses* ni DNS pasivo útil devuelve vacío. Los *pulses* los
  publica cualquiera: son una pista, no un veredicto. Del DNS pasivo solo se aceptan los hosts del
  objetivo.
- **Términos y datos:** uso de la API sujeto a los términos de OTX; no se
  redistribuyen los *pulses*.

### `virustotal` (key `virustotal`)
- **Consume:** dominio raíz o IP. **Produce:** `record` `virustotal:<valor>` y `domain`.
- **Fuente:** API v3 de [VirusTotal](https://docs.virustotal.com/reference/overview): `domains/<d>`,
  `domains/<d>/subdomains?limit=40` e `ip_addresses/<ip>`.
- **Datos:** detecciones (`malicious`, `suspicious`, `harmless`), reputación, fecha del último
  análisis, registrador y categorías (dominio), propietario del AS, ASN y país (IP), y hasta 40
  subdominios.
- **Límites:** el plan gratuito permite **4 peticiones por minuto y 500 al día**: el módulo
  espacia 15 s sus peticiones (un dominio tarda ≈ 30 s) y un 429 se informa como cuota agotada.
- **Términos y datos:** la API gratuita es para uso no comercial y no se puede usar en productos
  o servicios; los datos pertenecen a VirusTotal.

### `tech_detect` (activo)
- **Consume:** dominio raíz. **Produce:** `technology`.
- **Fuente:** la portada del sitio (HTTPS y, si falla, HTTP) contrastada con las firmas propias de
  `modules/domain/data/tech_signatures.json` (más de 50 tecnologías: CMS, comercio electrónico,
  frameworks, servidores, CDN, analítica…). Solo con `--active`.
- **Datos:** nombre, categoría, versión (cuando la firma la captura) y la evidencia (cabecera,
  cookie, `meta`, script o HTML). Además, los plugins y temas de WordPress que la portada enlaza
  bajo `/wp-content/plugins/` y `/wp-content/themes/` salen como `WordPress plugin: <slug>` y
  `WordPress theme: <slug>` (categoría `plugin` o `theme`, hasta 50, evidencia `html`), con la
  versión del primer `?ver=` de sus ficheros si lo lleva. Sin peticiones extra.
- **Límites:** solo mira la portada, así que no ve lo que carga otra página. **No enumera plugins:**
  solo aparecen los que la portada carga, y el `?ver=` es el que pone el plugin a sus ficheros, no
  siempre su versión (una pista, no una prueba). Solo WordPress; no cubre Joomla ni Drupal. Una firma es una
  pista: un sitio puede ocultar o falsear una cabecera. **No usa `webappanalyzer`** (GPL-3.0, no
  compatible con la licencia MIT del proyecto), de modo que la cobertura es la de las firmas
  propias. `http_fingerprint` conserva sus 17 firmas.
- **Términos y datos:** una petición al sitio del objetivo; las firmas son del proyecto.

### `favicon_pivot` (activo, key `shodan`)
- **Consume:** dominio raíz. **Produce:** `record` `favicon:<dominio>` e `ip`.
- **Fuente:** descarga `/favicon.ico` del sitio, calcula su MurmurHash3 de 32 bits (sobre el
  Base64 con saltos de línea, como Shodan) y busca `http.favicon.hash:<hash>` en la API de
  búsqueda de Shodan. Solo con `--active`.
- **Datos:** hash, tamaño del icono, número de hosts con el mismo icono y hasta 50 IP con sus
  puertos y nombres.
- **Límites:** **la búsqueda de Shodan exige una cuenta con acceso a ella (no la gratuita)**: sin
  él, el módulo falla con un aviso claro. Un icono muy común (el de un CMS o un framework) devuelve
  hosts sin relación con el objetivo: trátalo como una pista. Se descarta un favicon que sea HTML
  o pese más de 256 KiB. Censys no se usa para esta búsqueda.
- **Términos y datos:** una petición al sitio y una a Shodan por dominio.

### `lookalike_domains`
- **Consume:** dominio raíz. **Produce:** `record` `lookalike:<dominio>` (resumen, con la lista
  `registered`) y un `record` `lookalike:<parecido>` por cada dominio registrado, para que `watch`
  (reglas `new-lookalike-domain*`) detecte uno nuevo por su clave.
- **Fuente:** solo DNS (NS, A, AAAA y MX) al resolvedor del sistema; con `--proxy` se omite. No
  hace ninguna petición HTTP.
- **Datos:** hasta 300 permutaciones (omisión, repetición, transposición, teclas vecinas,
  homógrafos —los cirílicos como punycode—, guion y otros TLD); de los registrados, sus NS, IP y
  MX. Un dominio con MX puede recibir correo y es un riesgo mayor de suplantación.
- **Límites:** es una comprobación **defensiva de dominios propios o autorizados**. Deja un
  `record` y **no emite `domain`**: no se pivota hacia un dominio que puede ser hostil. «Registrado»
  significa que tiene NS: un dominio registrado sin delegar no aparece. Los homógrafos son una
  tabla corta, no la lista completa de Unicode.
- **Términos y datos:** DNS público; son hasta unas 1.000 consultas por dominio.

### `ext_subfinder` (herramienta externa)
- **Consume:** dominio raíz. **Produce:** `domain` (subdominios).
- **Fuente:** el binario `subfinder` ([ProjectDiscovery](https://github.com/projectdiscovery/subfinder))
  que instala el usuario y que se ejecuta como `subfinder -d <dominio> -silent -json`, sin shell.
  Solo usa fuentes pasivas. Quedan `omitido` si no está instalado, y con `--proxy` el módulo se
  omite (su tráfico no pasa por `ctx.http`).
- **Datos:** subdominios del objetivo, con las fuentes que los dieron. Se descarta lo que no sea
  el dominio o un subdominio suyo.
- **Límites:** no se comprueba la versión mínima, porque no se ha verificado cuál es. Sus fuentes
  pueden necesitar keys propias en la configuración de Subfinder. Su tráfico no deja evidencia
  (`--evidence`). `ext_amass` queda pendiente.

### `cloud_attribution` (analizador)
- **Consume:** `record` de `dns` y de `http_fingerprint`. **Produce:** `technology`.
- **Fuente:** nada nuevo: lee el `CNAME` del DNS y las tecnologías de la huella HTTP ya recogidos.
  No hace ninguna petición.
- **Datos:** proveedor (CloudFront, Cloudflare, Akamai, Fastly, Azure CDN y Front Door, Imperva,
  Sucuri, Bunny, StackPath, ELB, S3, Traffic Manager, App Service, App Engine, Heroku, Vercel,
  Netlify, GitHub Pages), categoría `cdn` o `cloud` y la evidencia.
- **Límites:** **sin los rangos de IP de los proveedores.** El roadmap (F4.17) pide etiquetar IP
  con los rangos que publican AWS, GCP, Azure y Cloudflare; quedan pendientes hasta resolver el
  *spike* de sus feeds y su licencia (ver `docs/plans/fase-04.md`). Hoy solo detecta por CNAME y
  por la huella HTTP.

## IP

### `ipinfo` (key opcional `ipinfo`)
- **Consume:** IP. **Produce:** `record` `ipinfo:<ip>`.
- **Fuente:** [ipinfo.io](https://ipinfo.io). Sin token funciona con cuota reducida.
- **Datos:** hostname, ciudad, región, país, coordenadas, organización/ASN, zona horaria, anycast.
  Las IP privadas o reservadas se marcan como `bogon`.

### `internetdb`
- **Consume:** IP. **Produce:** `record`, `service` (`<ip>:<puerto>`), `vulnerability` (CVE).
- **Fuente:** [Shodan InternetDB](https://internetdb.shodan.io), gratuita y sin key.
- **Datos:** puertos abiertos, hostnames, CPEs, tags y CVEs según el último escaneo de Shodan.
  Puede estar desactualizada varias semanas.

### `shodan` (key `shodan`)
- **Consume:** IP. **Produce:** `record`, `service`, `vulnerability`.
- **Fuente:** API `/shodan/host` de [Shodan](https://shodan.io).
- **Datos:** organización, ISP, ASN, SO, y por servicio: puerto, transporte, producto, versión y
  título HTTP. Se fusiona con `internetdb` cuando ambos ven el mismo puerto.
- **Límites:** según el plan de la cuenta, este endpoint puede no estar disponible (devuelve 401).

### `cve_enrich` (key opcional `nvd`)
- **Consume:** `vulnerability` cuyo valor sea un id `CVE-AAAA-NNNN`. **Produce:** la misma
  `vulnerability`, con campos nuevos que se fusionan en ella.
- **Fuente:** [NVD API 2.0](https://nvd.nist.gov/developers/vulnerabilities) (CVSS),
  [FIRST](https://www.first.org/epss/) (EPSS) y el catálogo KEV de
  [CISA](https://www.cisa.gov/known-exploited-vulnerabilities-catalog).
- **Datos:** `cvss`, `cvss_version` y `cvss_severity` (la versión más reciente que tenga la CVE:
  4.0, 3.1, 3.0 o 2.0); `epss`, `epss_percentile` y `epss_date`; `kev` (siempre presente si el
  catálogo respondió) y, si está, `kev_due_date` y `kev_ransomware`.
- **No es un analizador:** el ROADMAP lo planteaba así, pero un analizador no puede usar la red y
  NVD no ofrece un dataset instalable con licencia compatible. Es un módulo normal, así que solo
  corre si `--depth` llega a la capa siguiente a `internetdb` o `shodan`.
- **Límites:** NVD permite 5 peticiones cada 30 s sin key y 50 con ella (key `nvd`, que viaja en
  la cabecera `apiKey`): se espacian 6,5 s (0,7 s con key) y se consultan como máximo 30 CVE por
  escaneo; el resto lleva solo EPSS y KEV. El catálogo KEV (~1 MB) se descarga una vez por escaneo.
  Si una fuente falla se conservan los datos de las otras; si fallan todas, error (cuota si alguna
  lo era). Una CVE reciente puede no tener aún EPSS ni CVSS.
- **Términos y datos:** los datos de NVD son de dominio público (uso sujeto a sus términos de API);
  KEV es CC0; EPSS es de uso libre ([FIRST](https://www.first.org/epss/faq)) y se cita su origen.
  Nada de esto se redistribuye en el paquete.

### `abuseipdb` (key `abuseipdb`)
- **Consume:** IP. **Produce:** `record` `abuseipdb:<ip>`.
- **Fuente:** API `check` de [AbuseIPDB](https://www.abuseipdb.com) (últimos 90 días).
- **Datos:** puntuación de abuso (0–100), número de reportes y de reportadores, último reporte,
  tipo de uso, ISP, dominio y si es nodo Tor. Plan gratuito: 1000 consultas al día.

### `greynoise` (key `greynoise`)
- **Consume:** IP. **Produce:** `record` `greynoise:<ip>`.
- **Fuente:** API Community de [GreyNoise](https://www.greynoise.io).
- **Datos:** si la IP genera ruido de Internet (escáneres, bots), si es un servicio legítimo
  conocido (`riot`), clasificación y nombre. Un 404 significa que GreyNoise no la ha visto.

### `censys` (key `censys`)
- **Consume:** IP. **Produce:** `record` `censys:<ip>` y `service`.
- **Fuente:** `GET /v3/global/asset/host/<ip>` de la API de
  [Censys Platform](https://docs.censys.com/reference/get-started), con un token personal
  (`config set censys`) y, si hace falta, el identificador de organización (`config set
  censys_org`).
- **Datos:** ASN, nombre del AS, prefijo BGP, país y hasta 50 servicios (puerto, transporte,
  protocolo y producto). Complementa a Shodan.
- **Límites:** **la forma de la respuesta se ha tomado de la documentación y no se ha comprobado
  contra la API real**; el parseo es tolerante y `osineitor doctor` es la prueba. Los créditos y el
  acceso a la API del plan gratuito dependen de la cuenta. Los certificados los cubre
  `cert_details` con crt.sh.
- **Términos y datos:** sujeto a los términos de Censys y al consumo de créditos de la cuenta.

### `abusech` (key `abusech`)
- **Consume:** dominio raíz o IP. **Produce:** `record` `abusech:<valor>`.
- **Fuente:** `POST` a ThreatFox (`search_ioc`, coincidencia exacta) y a URLhaus (`host`), de
  [abuse.ch](https://abuse.ch). Desde 2025 ambas exigen una `Auth-Key` gratuita.
- **Datos:** número de IOC en ThreatFox, familias de malware, tipos de amenaza, fechas y
  etiquetas; URL maliciosas en URLhaus y cuántas siguen en línea. Solo metadatos: no se descargan
  muestras ni se siguen las URL.
- **Límites:** sin coincidencias, vacío. Un IOC puede ser un falso positivo o estar caducado.
- **Términos y datos:** datos de abuse.ch bajo CC0; el uso de la API sigue sus términos.

### `reverse_ip`
- **Consume:** IP pública. **Produce:** `domain`, `record`.
- **Fuente:** `api.hackertarget.com/reverseiplookup/`, la API gratuita de HackerTarget (cuota
  diaria limitada por IP de origen; al agotarla el módulo queda en `cuota`).
- **Datos:** los hostnames que comparten la IP, como `domain` con `via: reverse_ip`. Si son más de
  50 es un alojamiento compartido o una CDN: no se emiten dominios (el motor pivotaría sobre
  terceros sin relación con el objetivo) y queda un `record` `reverse_ip:<ip>` con el recuento y
  una muestra de 20.
- **Límites:** las IP privadas se omiten sin enviarlas. Los errores de la API llegan como texto
  con código 200; se reconocen el de cuota agotada, el de «sin registros» y los que empiezan por
  `error`. La cobertura es la de HackerTarget: un hostname que no conozca no aparece.

### `ptr`
- **Consume:** IP pública. **Produce:** `record` `ptr:<ip>`, `domain` (marcado `subdomain`).
- **Fuente:** consulta DNS PTR (`in-addr.arpa` o `ip6.arpa`) al resolvedor del sistema; con
  `--proxy` se omite. Una IP privada queda omitida: no se filtra su consulta al resolvedor.
- **Límites:** el PTR lo controla el dueño de la IP y puede ser basura o no coincidir con el
  nombre directo; los nombres no válidos se descartan. No hay confirmación de DNS directo.
- **Términos y datos:** DNS público, sin cuota ni licencia aplicable.

### `ripestat`
- **Consume:** IP pública. **Produce:** `record` `ripestat:<ip>`, `netblock`, `asn`.
- **Fuente:** [RIPEstat](https://stat.ripe.net/docs/data_api) (`prefix-overview`, `rir-geo` y
  `routing-history`), API de datos abierta de RIPE NCC, sin key.
- **Datos:** prefijo, si está anunciado, ASN y titular, país de registro, primera y última vez
  que se vio anunciado y orígenes vistos (hasta 10).
- **Límites:** 3 peticiones por IP, espaciadas 0,2 s. Los datos de enrutamiento son de la vista
  de RIPE, no del RIR de la IP.
- **Términos y datos:** RIPEstat pide identificar la aplicación (`sourceapp=osineitor`) y limita
  el uso intensivo; los datos son de RIPE NCC (sus condiciones de uso aplican).

### `asn_netblock`
- **Consume:** IP pública o ASN. **Produce:** `netblock`, `asn`.
- **Fuente:** Team Cymru por DNS (`origin.asn.cymru.com`, `asn.cymru.com`) para IP→ASN y prefijo;
  RIPEstat `announced-prefixes` para ASN→prefijos. La consulta de Team Cymru es DNS directo: con
  `--proxy` el módulo se omite entero.
- **Datos:** prefijo, ASN (hasta 5 origen), país, registro, fecha de asignación y titular. Desde
  un ASN, hasta 50 prefijos, los más amplios primero.
- **Límites:** un prefijo no válido de la fuente se descarta. El tope de 50 deja fuera
  prefijos específicos de AS grandes (`announced_prefixes` lleva el total).
- **Términos y datos:** Team Cymru ofrece este servicio gratuito para uso razonable; evita
  consultas masivas.

### `dnsbl`
- **Consume:** IPv4 pública. **Produce:** `record` `dnsbl:<ip>`.
- **Fuente:** listas DNS `zen.spamhaus.org`, `bl.spamcop.net`, `dnsbl-1.uceprotect.net` y
  `dnsbl.dronebl.org`, consultadas por DNS; con `--proxy` se omite.
- **Datos:** listas en las que figura y el código devuelto (con su significado para ZEN: SBL,
  XBL, PBL…); `unanswered` lista las que no respondieron. Sin listas, vacío.
- **Límites:** solo IPv4. **Spamhaus rechaza las consultas desde resolvedores públicos
  (8.8.8.8, 1.1.1.1…):** devuelve `127.255.255.x`, que el módulo trata como cuota agotada, no
  como «listada»; hace falta un resolvedor propio. UCEPROTECT nivel 1 lista por IP.
- **Términos y datos:** Spamhaus ZEN es gratuito solo para uso no comercial y bajo volumen; revisa
  los términos de cada lista antes de un uso intensivo.

## Email

### `email_validate`
- **Consume:** email. **Produce:** `record` `email:<email>`, `domain`, `username`.
- **Datos:** sintaxis, registros MX, si es proveedor gratuito o desechable. Con `--proxy` se
  omite (el MX se consulta por DNS directo).
- **Pivote:** el dominio (salvo proveedores gratuitos o desechables) y la parte local como
  username (sin la etiqueta `+…`, mínimo 3 caracteres).

### `gravatar`
- **Consume:** email. **Produce:** `profile`, `username`.
- **Fuente:** perfil público de [Gravatar](https://gravatar.com) (hash SHA-256 del email).
- **Datos:** nombre, ubicación, descripción y cuentas enlazadas (GitHub, X, etc.).

### `hibp` (key `hibp`)
- **Consume:** email. **Produce:** `breach`.
- **Fuente:** API v3 de [Have I Been Pwned](https://haveibeenpwned.com) (de pago).
- **Datos:** por brecha: nombre, dominio, fecha, cuentas afectadas, tipos de datos expuestos y si
  está verificada.

### `hunter_verify` (key `hunter`)
- **Consume:** email. **Produce:** `record` `hunter:<email>`, `url` de fuentes públicas.
- **Fuente:** API `email-verifier` de [Hunter](https://hunter.io).
- **Datos:** estado (`valid`, `invalid`, `accept_all`…), puntuación, webmail o desechable, y
  páginas públicas donde aparece el email.

### `leakcheck`
- **Consume:** email. **Produce:** `breach`.
- **Fuente:** API pública de [LeakCheck](https://leakcheck.io) (`/api/public`), sin key. Su
  documentación la describe como gratuita también para uso comercial, con 1 petición por segundo y
  con la condición de enlazar «Powered by LeakCheck» en un sitio web; devuelve solo los nombres de
  las fuentes y las categorías de datos, nunca los datos.
- **Datos:** un `breach` por fuente, con su fecha (`AAAA-MM`) y `via: leakcheck`. No guarda las
  categorías de datos: la API las da en conjunto, no por filtración. Un mismo incidente puede
  llamarse distinto aquí y en `hibp`, así que puede aparecer dos veces.
- **Límites:** «Not found» es «sin resultados»; cualquier otro error de la API es un error del
  módulo. Se limita a 200 filtraciones.

### `pgp_keyserver`
- **Consume:** email. **Produce:** `record` `pgp:<huella>`.
- **Fuente:** `keys.openpgp.org/pks/lookup?op=index&options=mr`. Ese servidor solo devuelve una
  clave por email si el dueño verificó esa dirección y autorizó publicarla.
- **Datos:** huella (40 o 64 hexadecimales), algoritmo (RSA, DSA, ECDH, ECDSA, EdDSA), bits, fecha
  de creación y hasta 10 identidades (`Nombre <email>`).
- **Límites:** el servidor admite una consulta por email y minuto. El formato de la respuesta es
  el del borrador HKP que documenta el servidor; la prueba usa ese formato, porque no se ha
  observado una respuesta real con clave. Una clave sin identidad verificada no aparece.

### `hibp_pastes` (key `hibp`)
- **Consume:** email. **Produce:** `record` `hibp_pastes:<email>`.
- **Fuente:** endpoint `pasteaccount` de [Have I Been Pwned](https://haveibeenpwned.com), con la
  misma key que `hibp`.
- **Datos:** nº de *pastes*, fuentes (Pastebin, Slexy...) y fechas del primero y del último. No
  guarda los identificadores ni los títulos de los *pastes*.

### `github_email`
- **Consume:** email. **Produce:** `record` `github_email:<email>`, `username`.
- **Fuente:** búsqueda de commits de la API de GitHub (`author-email:`). Key `github` opcional.
- **Datos:** nº de commits, nombres de autor, hasta 10 repositorios, fechas del primero y del
  último, y hasta 5 logins que pivotan como `username`.
- **Límites:** 10 búsquedas por minuto sin key, por eso espacia 6 s las peticiones. Solo ve
  commits públicos cuyo email no está oculto.

### `fediverse` (activo)
- **Consume:** email. **Produce:** `profile`.
- **Fuente:** `GET /api/v1/accounts/lookup` de Mastodon y, si falla, WebFinger, en el host del
  dominio del email (`usuario@instancia`).
- **Datos:** nombre visible, biografía sin HTML, fecha de alta, seguidores y publicaciones.
- **Límites:** es **activo**: contacta con el servidor del dominio del email, que puede ser el
  objetivo. Los dominios de correo corrientes (Gmail...) no son instancias y no devuelven nada.
  Bluesky no está soportado.

### `email_candidates`
- **Consume:** person (con `--domain`). **Produce:** `email`.
- **Datos:** hasta 12 candidatos (`ana.garcia@`, `agarcia@`, `anagarcia@`...), marcados
  `candidate=True` con su patrón. Sin red: **no se verifican** (ni por SMTP) y la mayoría no
  existirán.

## Username

### `username_sites`
- **Consume:** username. **Produce:** `profile`.
- **Fuente:** ~460 sitios con las firmas de [Sherlock](https://github.com/sherlock-project/sherlock)
  (`modules/username/data/sites.json`, sin los marcados como NSFW). `osineitor update-data` las
  actualiza en tu directorio de datos y el módulo usa esa copia si su hash coincide con el
  registrado.
- **Detección:** según la firma, por código de estado 2xx, por ausencia de un mensaje de error en
  la página o por ausencia de redirección.
- **Verificación:** cada positivo se vuelve a consultar con un username aleatorio inexistente
  (`x` + 14 hex). Si el sitio también lo «encuentra», la firma da falsos positivos y el hallazgo
  se descarta; si lo distingue, el perfil lleva `verified=True`; si no se pudo comprobar (la
  firma rechaza el username de control o la petición falló), se conserva con `verified=None`.
- **Límites:** WAFs, captchas y rediseños producen falsos positivos y negativos. Las respuestas
  403/429 y los errores de red se tratan como "desconocido" y no se reportan. Verifica cada perfil
  a mano.

### `username_wmn`
- **Consume:** username. **Produce:** `profile`.
- **Fuente:** ~590 sitios con las firmas de [WhatsMyName](https://github.com/WebBreacher/WhatsMyName)
  (`modules/username/data/wmn.json`, CC BY-SA 4.0, con atribución en el `README.md` de esa
  carpeta). Se omiten los sitios de contenido adulto y los que WhatsMyName marca con `protection`
  (Cloudflare, captcha, DDoS-Guard...): no se eluden esas defensas.
- **Detección:** el código de estado y el texto de «existe» (`e_code`, `e_string`) deben coincidir
  y no debe aparecer el de «no existe» (`m_string`). No sigue redirecciones. Los sitios con
  cuerpo `POST` y cabeceras propias se consultan tal cual los define la firma.
- **Verificación:** la misma que `username_sites`: cada positivo se contrasta con un username
  inexistente y se descarta si el sitio también lo «encuentra».
- **Confirmado:** el perfil lleva la URL de la firma (`uri_pretty` si existe). Si `username_sites`
  encuentra la misma URL, el motor fusiona las dos entidades y queda con las dos fuentes y
  confianza `medio`. Si las URLs difieren (barra final, otro subdominio), no se detecta la
  coincidencia.
- **Límites:** los mismos que `username_sites`. No entra en `update-data` (su licencia no es
  compatible con ese catálogo).

### `github_user`
- **Consume:** username. **Produce:** `profile`, `organization`, `email`, `url`.
- **Fuente:** API de GitHub (usuario, organizaciones y eventos públicos). Key `github` opcional:
  de 60 a 5.000 peticiones por hora.
- **Datos:** nombre, empresa, blog, ubicación, bio, usuario de X, repositorios, seguidores y fecha
  de alta; hasta 20 organizaciones; hasta 10 emails de los commits de sus eventos recientes, sin
  las direcciones `noreply` de GitHub.
- **Límites:** solo los últimos eventos públicos, así que los emails son los de la actividad
  reciente.

### `ext_maigret` (herramienta externa)
- **Consume:** username. **Produce:** `profile`.
- **Fuente:** el binario `maigret` ([soxoj/maigret](https://github.com/soxoj/maigret)) que instala
  el usuario, ejecutado sin shell como `maigret --json simple -fo <carpeta temporal>
  --no-progressbar --no-color --no-recursion --no-extracting -- <usuario>`. Maigret no imprime el
  informe por stdout: lo escribe en `<carpeta>/report_<usuario>_simple.json`, que el módulo lee y
  borra. Queda `omitido` si no está instalado y, con `--proxy`, también (su tráfico no pasa por
  `ctx.http`).
- **Datos:** un perfil por cada sitio que Maigret da por `Claimed`, con `site` y `via: maigret`.
  Se descartan las URL que no sean http(s). No lleva `verified`: Maigret no confirma que sea la
  misma persona.
- **Límites:** desactiva la recursión y la extracción de Maigret para que no investigue por su
  cuenta otros usernames; los pivotes los decide el motor. No se comprueba la versión mínima, porque
  no se ha verificado cuál es. Tiene un timeout de 600 s. Su tráfico no deja evidencia
  (`--evidence`) ni cuenta en el presupuesto de peticiones. Las firmas de sitios que usa son las
  suyas, no las de `username_sites`, así que puede repetir hallazgos. Para importar un informe ya
  generado sin ejecutarlo, usa `osineitor import maigret`.

### `bluesky`
- **Consume:** username. **Produce:** `profile`.
- **Fuente:** API pública de Bluesky (`public.api.bsky.app`), sin sesión ni clave.
- **Datos:** un username sin punto se consulta como `<usuario>.bsky.social`; uno con puntos, como
  handle completo (dominio propio). Emite el perfil con nombre, bio, fecha de alta, seguidores,
  seguidos, publicaciones y el DID.
- **Límites:** solo comprueba que existe el handle, no que sea la misma persona. Un username con
  guion bajo u otro carácter que un handle no admite se omite. Un 429 es una cuota agotada.

### `dev_registries`
- **Consume:** username. **Produce:** `profile`.
- **Fuente:** búsqueda por mantenedor de npm, usuarios de crates.io y de Docker Hub, la página
  pública de perfil de PyPI (no tiene API de usuarios) y la API de Stack Exchange.
- **Datos:** hasta 20 paquetes o repositorios por registro y, según el registro, nombre, empresa,
  ubicación y fecha de alta. No emite los emails de los mantenedores de npm. De Stack Overflow,
  hasta 3 perfiles cuyo nombre visible coincide exactamente, con reputación, ubicación y fecha de
  alta, marcados `match: display_name` y sin `verified`.
- **Límites:** el nombre de usuario de un registro no tiene por qué ser la misma persona, y en
  Stack Overflow no hay usernames: un nombre repetido no prueba nada. Si una fuente falla, las
  demás se conservan; solo es un error si fallan todas.

### `profile_extract`
- **Consume:** username. **Produce:** `profile`, `username` y `url`.
- **Fuente:** las APIs públicas oficiales de DEV Community (`/api/users/by_username`) y de Codeberg
  (`/api/v1/users/<usuario>`). No lee páginas HTML. GitLab no se incluye: su API pública de
  usuarios solo confirma que la cuenta existe.
- **Datos:** el perfil (`https://dev.to/<usuario>` o `https://codeberg.org/<usuario>`, el mismo
  que dan Sherlock y WhatsMyName, así que se fusionan) con nombre visible, bio, ubicación y fecha
  de alta; la web declarada como `url`; y, en DEV Community, los usernames de X y de GitHub que el
  dueño enlazó, como `username` con `platform` y `declared_on`. La bio de Codeberg se reduce a
  texto plano y se recorta a 300 caracteres.
- **Pivote recursivo:** esos `username` los investiga el motor en el siguiente nivel, dentro del
  límite de profundidad del scan. Es una hipótesis: que alguien enlace una cuenta en su perfil no
  prueba que el perfil de partida sea de la persona investigada, y los datos se arrastran con la
  misma duda. Un handle igual al username investigado no se repite.
- **Límites:** nunca guarda el email que devuelva una API (Codeberg lo expone a veces). Si una
  fuente falla, la otra se conserva; solo es un error si fallan las dos.

### `discord_snowflake`
- **Consume:** username numérico de 17 a 20 dígitos. **Produce:** `record` `discord:<id>`.
- **Datos:** fecha de creación de la cuenta decodificada del ID. En local, sin red.
- **Límites:** descarta los IDs fuera del rango posible (anteriores a mayo de 2015 o futuros).

### `username_variants`
- **Consume:** person. **Produce:** `username`.
- **Datos:** hasta 12 variantes (`ana.garcia`, `agarcia`, `ana_garcia`...) de al menos 3
  caracteres, marcadas `candidate=True` con su patrón. Sin red. Ignora partículas como «de» o
  «van» y combina el nombre con el primer y el último apellido.

## Análisis

### `findings` (analizador)
- **Consume:** `record`, `certificate`, `vulnerability`, `url` y `service` (los tipos que citan
  las reglas). **Produce:** `finding`. Lo que emite no se pivota y no tiene confianza.
- **Fuente:** ninguna: lee lo ya recogido, sin red ni presupuesto. Las reglas son declarativas, en
  `src/osineitor/data/rules/default.yml`; el formato (campos, operadores, validación) está en
  `src/osineitor/findings.py`.
- **Datos:** `rule`, `title`, `severity`, `recommendation`, `affected` (claves de las entidades
  que lo justifican) y `evidence` (los campos que lo prueban). El valor es `regla: sujeto`.
- **Reglas incluidas (15):** DMARC ausente o `p=none`; SPF `+all`/`?all`; sin MTA-STS;
  certificado caducado o a ≤ 30 días; dominio que expira en ≤ 60 días; CVE en KEV; EPSS ≥ 0,5;
  CNAME colgante; URL sensible archivada; IP en lista negra; cabeceras de seguridad ausentes;
  servicio de administración expuesto; `security.txt` caducado.
- **Límites:** solo ve lo que otros módulos recogieron (sin `dns` no hay hallazgos de DMARC). Un
  certificado «caducado» puede ser uno antiguo ya sustituido. La regla de DMARC solo mira
  dominios `nombre.tld` (un solo punto), así que no cubre `ejemplo.co.uk`.
- **Términos y datos:** reglas propias, bajo la licencia del proyecto (MIT).

## Organización

### `gleif`
- **Consume:** organization (no las de GitHub). **Produce:** `record` `gleif:<LEI>`, `organization`.
- **Fuente:** API pública de [GLEIF](https://www.gleif.org) (`/api/v1/lei-records`), sin key. Los
  datos LEI son de dominio público (CC0, [términos de GLEIF](https://www.gleif.org/en/lei-data/gleif-terms)).
- **Datos:** LEI, razón social, país y ciudad del domicilio, jurisdicción, estado de la entidad y
  del registro, nº de registro mercantil y fechas.
- **Coincidencia:** primero por nombre legal exacto; si no hay, hasta 3 candidatos por texto
  completo, marcados `match=approximate`. Solo con **un único** LEI exacto se siguen la matriz
  directa (`relationship=parent`) y hasta 20 filiales directas (`relationship=subsidiary`), que
  pivotan como `organization`.
- **Límites:** solo cubre entidades que tienen LEI (grandes y financieras sobre todo). Los
  registros mercantiles de pymes y autónomos no están (ver `librebor` y `opencorporates` en el
  roadmap).

## Teléfono

### `phone_parse`
- **Consume:** phone. **Produce:** `record` `phone:<E.164>`.
- **Fuente:** biblioteca [`phonenumbers`](https://github.com/daviddrysdale/python-phonenumbers)
  (puerto de libphonenumber de Google), en local y sin red.
- **Datos:** validez y posibilidad, prefijo, región, país y zona (en español), tipo de línea,
  zonas horarias y formatos internacional, nacional y RFC 3966.
- **Límites:** el operador es el de la **asignación original** del rango: no refleja la
  portabilidad. Un número válido no implica que esté en servicio. Es un dato personal: con
  `require_purpose` activo, un scan de teléfono exige `--purpose`.

## Criptomonedas

### `crypto_detect`
- **Consume:** crypto_address. **Produce:** `record` `crypto:<dirección>`.
- **Datos:** cadena (Bitcoin, Ethereum, Litecoin, Dogecoin, Monero) y formato (`p2pkh`, `p2sh`,
  `bech32`, `bech32m`...). Bitcoin, Litecoin y Dogecoin se validan con su suma de comprobación;
  Ethereum y Monero solo por forma (`checksum_verified=false`), porque la suma EIP-55 pide
  Keccak-256.
- **Límites:** sin red. Una dirección de otra cadena (Solana, Tron...) no se reconoce.

### `btc_explorer`
- **Consume:** crypto_address (solo Bitcoin). **Produce:** `record` `btc:<dirección>`.
- **Fuente:** API de [mempool.space](https://mempool.space/docs/api/rest), sin key.
- **Datos:** saldo, total recibido y enviado (satoshis), nº de transacciones confirmadas y sin
  confirmar, y fecha de la última actividad.
- **Límites:** la primera actividad solo se informa si la dirección tiene 25 transacciones o menos
  (las que caben en la primera página); con más, queda vacía en lugar de adivinarla. Una
  dirección no identifica a nadie por sí sola.

## Ficheros y coordenadas

Los módulos de ficheros trabajan **en local**: no abren conexiones y ni el contenido ni la ruta del
fichero salen del equipo (hay un test que lo comprueba interceptando la red). Su valor de prueba en
`doctor` es su propio código fuente.

### `file_meta`
- **Consume:** file. **Produce:** `record` `file_meta:<ruta>`, `location`.
- **Formatos:** JPEG con EXIF (cámara, software, fechas, autor, números de serie y GPS), PDF con el
  diccionario Info en texto claro, DOCX/XLSX/PPTX (`docProps`) y ODT/ODS/ODP (`meta.xml`). El
  formato se detecta por los primeros bytes, no por la extensión.
- **Datos:** autor, último autor, software, empresa, fechas de creación y modificación, y, si hay
  GPS, una entidad `location` que pivota a `geo_point`.
- **Límites:** no lee PDF que guarden el Info en flujos comprimidos, ni XMP, IPTC, PNG ni TIFF
  (el adaptador `ext_exiftool` del roadmap cubriría el resto). Lee como mucho 512 KiB al principio
  y 64 KiB al final del fichero y 1 MiB de cada miembro de un zip; rechaza el XML con `DOCTYPE` o
  entidades. Los metadatos revelan quién y con qué creó el fichero: úsalo solo con ficheros
  propios o de los que tengas derecho a analizar.

### `file_hash`
- **Consume:** file. **Produce:** `record` `file_hash:<sha256>`.
- **Datos:** MD5, SHA-1, SHA-256 y tamaño, leídos por bloques de 1 MiB.
- **Límites:** la consulta de reputación por hash (VirusTotal, abuse.ch) no está: el hash es un
  pivote que se puede lanzar a mano. Pendiente en el roadmap (F6.10).

### `geo_point`
- **Consume:** location con forma `lat,lon`. **Produce:** `record` `geo:<lat,lon>`.
- **Datos:** latitud y longitud, grados-minutos-segundos y enlaces a OpenStreetMap y Google Maps.
  Las coordenadas se guardan con 6 decimales (unos 10 cm).

### `image_links`
- **Consume:** url de una imagen (`.jpg`, `.jpeg`, `.png`, `.gif`, `.webp`, `.bmp`).
  **Produce:** `record` `image_links:<url>`.
- **Datos:** enlaces de búsqueda inversa de Google Lens, Yandex, TinEye y Bing con la URL
  codificada. Solo genera enlaces: no descarga ni sube la imagen.

## Fuentes evaluadas y no incluidas

Entregables del [ROADMAP](../ROADMAP.md) que se evaluaron en el cierre del 07-11-2026 y no se
implementaron. Un módulo que no se puede probar contra su fuente, o cuyos términos de uso no se
han podido leer, no se añade: sus tests solo comprobarían lo que uno mismo supone de la respuesta.

| ID | Fuente | Por qué no |
|---|---|---|
| F4.17 (rangos) | Feeds de rangos de AWS, GCP, Azure y Cloudflare | Cambian a diario y `update-data` fija el SHA-256 de cada fichero; no se han comprobado sus licencias |
| F4.23 `geoip_offline` | GeoLite2 | Exige que cada usuario descargue la base (licencia de MaxMind) y no hay forma de probar el módulo sin ella |
| F4.24 `ext_amass` | Amass | No hay un formato de salida estable verificado (el mismo motivo por el que `import` no lee Amass) |
| F5.6 `--tags`, `--top` | Categorías y popularidad | Sherlock no trae ni lo uno ni lo otro y solo WhatsMyName trae categorías; un filtro que solo afectase a una de las dos fuentes de usernames daría una idea falsa de la cobertura. `--only username_wmn` ya limita a una fuente |
| F5.8 `hudsonrock` | Infostealers | La clave gratuita se pide con un correo corporativo y la API documentada devuelve credenciales; no se han podido verificar ni los términos ni una respuesta que demuestre que solo se guardarían metadatos |
| F6.1 `opensanctions` | Sanciones y PEP | Exige una key y no se ha podido verificar su respuesta |
| F6.3 `librebor`, F6.4 `opencorporates` | Registros mercantiles | API de pago o por solicitud, sin acceso para probarla |
| F6.8 `eth_explorer` | Etherscan | Exige una key y no se ha verificado la versión actual de su API |
| F6.10 (reputación) | VirusTotal, abuse.ch | Exigen keys y sacan el hash del equipo; el hash sigue siendo un pivote que se lanza a mano |
| F6.12 `capture` | Navegador *headless* | Necesita un navegador que los tests no pueden ejecutar; una captura sin probar no sirve como evidencia |
| F6.13 `search_dorks`, F6.14 `doc_harvest` | API de búsqueda y descarga de documentos | Exigen una key y una decisión sobre el proveedor; `doc_harvest` depende de `search_dorks` y descarga ficheros del objetivo |
| F6.15 `github_code` | Búsqueda de código de GitHub | Exige una key y una detección de secretos que no se puede validar sin ver contenido real; el criterio de no guardar nunca el valor no se puede demostrar con datos inventados |
| F6.16 `cloud_storage_refs` | Buckets de S3, GCS y Azure | No se ha verificado cómo responde cada proveedor al sondear un bucket |
| F6.18 `ext_exiftool` | ExifTool | Depende de cómo `file_meta` acepta rutas locales y de la política de lectura de ficheros |
| F11.5 | Internacionalización | Traducir la interfaz y toda la documentación excede el cierre; el proyecto está en español por convención |

Sí se verificaron contra el servicio antes de implementarse: la API pública de LeakCheck (respuesta
con resultados y sin ellos, límites y condiciones de uso), la de DEV Community y la de Codeberg, la
de Bluesky, el listado de HackerTarget y el índice de `keys.openpgp.org` (documentación y 404);
GitLab se descartó porque su API pública de usuarios solo confirma que la cuenta existe.

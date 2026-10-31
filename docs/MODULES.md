# Referencia de módulos

Para cada módulo: qué consume, qué produce, de dónde saca los datos y sus limitaciones.
`osineitor modules` muestra el estado actual (incluido si falta la API key) y `osineitor doctor`
prueba cada uno contra su fuente (valor de prueba: `example.com`, `1.1.1.1` o `test@example.com`;
`whois` usa `google.io`; `username_sites` solo comprueba que `github.com` responde, porque sus ~460
peticiones no son una prueba de salud, y `cve_enrich` consulta la API de EPSS). Todos los módulos pasivos y sin key cachean sus respuestas 6 horas, salvo
`username_sites`.

Hay dos tipos especiales de módulo: los **analizadores** (`analyzer = True`) leen lo ya recogido
en un pase final, sin red (el único por ahora es `saas_footprint`), y los adaptadores de
**herramientas externas** (`ExternalToolModule`, sin ejemplos todavía) ejecutan un binario
instalado por el usuario y quedan `omitido` si falta. Ver [Arquitectura](ARCHITECTURE.md).

Pesan más en la [confianza](ARCHITECTURE.md) de un dato los módulos **autoritativos**, cuya respuesta
viene de quien administra el dato: `dns`, `rdap`, `whois`, `mail_security`, `http_fingerprint` y
`email_validate`. El resto son bases de terceros (`aggregated`).

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

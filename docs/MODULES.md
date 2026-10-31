# Referencia de módulos

Para cada módulo: qué consume, qué produce, de dónde saca los datos y sus limitaciones.
`osineitor modules` muestra el estado actual (incluido si falta la API key) y `osineitor doctor`
prueba cada uno contra su fuente (valor de prueba: `example.com`, `1.1.1.1` o `test@example.com`;
`username_sites` solo comprueba que `github.com` responde, porque sus ~460 peticiones no son una
prueba de salud). Todos los módulos pasivos y sin key cachean sus respuestas 6 horas, salvo
`username_sites`.

Hay dos tipos especiales de módulo, sin ejemplos todavía: los **analizadores** (`analyzer = True`)
leen lo ya recogido en un pase final, sin red, y los adaptadores de **herramientas externas**
(`ExternalToolModule`) ejecutan un binario instalado por el usuario y quedan `omitido` si falta.
Ver [Arquitectura](ARCHITECTURE.md).

Pesan más en la [confianza](ARCHITECTURE.md) de un dato los módulos **autoritativos**, cuya respuesta
viene de quien administra el dato: `dns`, `rdap`, `http_fingerprint` y `email_validate`. El resto
son bases de terceros (`aggregated`).

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
  consulta igualmente. El WHOIS de respaldo llegará con F4.11 del [roadmap](../ROADMAP.md).

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

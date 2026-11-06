# Plan de la fase 4 · Dominio e infraestructura (v0.5.1)

Los cinco entregables *M* (F4.4, F4.11 a F4.14) salieron en la 0.5.0. Este plan cubre los 19 *S* y *C*
de la v0.5.1. Criterios comunes a todo módulo nuevo, de [`CLAUDE.md`](../../CLAUDE.md) y de la fase 4
del [ROADMAP](../../ROADMAP.md):

- Una subclase de `Module` en `src/osineitor/modules/<frente>/`, añadida a `modules/_manifest.py`.
- `canary` o `probe_url` para `osineitor doctor`; `min_interval` si la fuente tiene límite.
- Tests sin red (`respx`, `FakeResolver`); datos de terceros con `try_emit`; todo valor en URL con
  `sanitize.quote_segment`; nada de `httpx` directo.
- README, `docs/MODULES.md` (fuente, datos, límites, términos y licencia) y `CHANGELOG.md`.
- Criterio de salida: `ruff check .`, `ruff format --check .` y `python -m pytest -q` en verde.

## Estado

| ID | P | Módulo | Estado | Decisión |
|---|---|---|---|---|
| F4.5 | S | `web_meta` | ✅ | Hecho en esta rama |
| F4.6 | S | `takeover` | ✅ | Hecho en esta rama |
| F4.7 | S | `ptr` | ✅ | Hecho en esta rama |
| F4.8 | S | `ripestat` | ✅ | Hecho en esta rama |
| F4.9 | S | `dnsbl` | ✅ | Hecho en esta rama |
| F4.16 | S | `asn_netblock` | ✅ | Hecho en esta rama |
| F4.17 | S | `cloud_attribution` | 🟡 | Por CNAME y huella HTTP; faltan los rangos de IP (ver más abajo) |
| F4.1 | S | `urlscan` | ⬜ | Se implementa |
| F4.2 | S | `otx` | ⬜ | Se implementa |
| F4.3 | S | `virustotal` | ⬜ | Se implementa |
| F4.15 | S | `censys` | ⬜ | Se implementa (host); los certificados ya los cubre `cert_details` |
| F4.18 | S | `tech_detect` | ⬜ | Se implementa con firmas propias |
| F4.19 | S | `favicon_pivot` | ⬜ | Se implementa con Shodan; Censys queda fuera |
| F4.20 | S | `lookalike_domains` | ⬜ | Se implementa sin dnstwist |
| F4.10 | C | `abusech` | ⬜ | Se implementa (ThreatFox y URLhaus) |
| F4.24 | C | `ext_subfinder` | ⬜ | Se implementa; `ext_amass` aplazado |
| F4.22 | C | `reverse_ip` | ⛔ | Bloqueado por *spike* |
| F4.23 | C | `geoip_offline` | ⛔ | Bloqueado por *spike* |
| F4.21 | C | `analytics_ids` | ⛔ | Bloqueado por *spike* |

## Orden de trabajo y verificación

Cada paso termina con `pytest` del fichero nuevo en verde; al final, la batería completa.

1. **Cerrar lo ya escrito** (F4.5 a F4.9, F4.16, F4.17): corregir tests rojos, documentar. *Verificación:
   suite completa en verde y `test_docs.py` (README y `MODULES.md` listan exactamente los módulos reales).*
2. **Fuentes con API** (F4.1, F4.2, F4.3, F4.15, F4.10): un fichero por fuente, key en `config`.
   *Verificación: test con la respuesta simulada, test de key inválida (401/403), de cuota (429) y de
   un valor raro de la fuente que no pierde el resto.*
3. **Análisis y pivotes** (F4.20, F4.19, F4.18): F4.20 sin red salvo DNS; F4.19 y F4.18 son activos.
   *Verificación: F4.20 sin ninguna petición HTTP (test que intercepta la red); F4.18 y F4.19 solo corren
   con `--active`.*
4. **Adaptador** (F4.24): `ext_subfinder` sobre `ExternalToolModule`. *Verificación: sin el binario queda
   `omitido`; con una salida NDJSON simulada emite los subdominios del objetivo y descarta los ajenos.*
5. **Cierre**: presets (`domain-recon`, `attack-surface`), ROADMAP (estados y recuentos), CHANGELOG.

## Decisiones por entregable

### F4.1 `urlscan` · urlscan.io
- Endpoint: `GET https://urlscan.io/api/v1/search/?q=domain:<d>&size=100`, cabecera `API-Key` opcional.
  Consume `domain` (raíz) e `ip`. Produce `record`, `ip`, `domain` (subdominios del objetivo) y `url`.
- Límite: sin key la búsqueda tiene cuota baja; 429 → `ModuleQuota`. No se cachea con key.
- Riesgo: los resultados son escaneos públicos hechos por terceros; pueden incluir páginas de otras
  empresas en la misma IP. Solo se aceptan hostnames que sean el objetivo o subdominios suyos.

### F4.2 `otx` · AlienVault OTX
- Endpoints: `/api/v1/indicators/domain/<d>/general` y `/passive_dns`; `/indicators/IPv4|IPv6/<ip>/general`.
  Cabecera `X-OTX-API-KEY` (key `otx`, gratuita).
- Produce `record` (número de pulses, reputación, países), y desde el DNS pasivo `domain` (subdominios del
  objetivo) e `ip`.

### F4.3 `virustotal` · VirusTotal v3
- Endpoints: `/api/v3/domains/<d>`, `/domains/<d>/subdomains?limit=40`, `/ip_addresses/<ip>`; cabecera
  `x-apikey` (key `virustotal`).
- Cuota del plan gratuito: 4 peticiones por minuto y 500 al día → `min_interval = 15` y 429 →
  `ModuleQuota`. Produce `record` (votos de análisis, reputación, categorías) y `domain` (subdominios).

### F4.15 `censys` · Censys Platform
- Endpoint: `GET https://api.platform.censys.io/v3/global/asset/host/<ip>`, `Authorization: Bearer`
  (token personal) y `X-Organization-ID` opcional; `Accept: application/vnd.censys.api.v3.host.v1+json`.
- Produce `record` y `service` (puerto, protocolo, nombre del servicio), ASN y país. Complementa a Shodan.
- **Sin verificar contra la API real** (D1): la forma de la respuesta se ha tomado de la documentación; el
  parseo es tolerante y `doctor` es la comprobación. Términos y créditos del plan gratuito: a revisar.

### F4.10 `abusech` · ThreatFox y URLhaus
- `POST https://threatfox-api.abuse.ch/api/v1/` (`search_ioc`) y `POST https://urlhaus-api.abuse.ch/v1/host/`,
  cabecera `Auth-Key` (key `abusech`; obligatoria desde 2025 [R8]). Consume `domain` e `ip`; produce `record`.
- Solo metadatos del IOC (familia, tipo de amenaza, confianza, fechas y etiquetas); no se descargan muestras.

### F4.20 `lookalike_domains`
- **Sin dependencia de dnstwist** (*spike* resuelto: añadir una dependencia GPL-compatible de mantenimiento
  incierto para generar permutaciones no compensa; las técnicas son pocas y conocidas). Permutaciones:
  omisión, repetición, transposición, sustitución por teclas adyacentes, homógrafos (tabla corta), guion,
  inserción de etiqueta y cambio de TLD, con tope de 300 candidatos.
- Comprueba por DNS (A, MX, NS) y deja un único `record` con los registrados. **No emite `domain`**: un
  dominio parecido puede ser hostil, y como entidad se pivotaría contra él, incluso con módulos activos.
- Solo para dominios propios o autorizados (ver [USO_RESPONSABLE](../USO_RESPONSABLE.md)).

### F4.19 `favicon_pivot` · activo
- Descarga `/favicon.ico` del objetivo (mismo sitio, tope de 256 KiB) y calcula el MurmurHash3 de 32 bits
  de su Base64 con saltos de línea, como Shodan, con una implementación propia (sin dependencia nueva).
- Con key de Shodan con búsqueda, `GET /shodan/host/search?query=http.favicon.hash:<h>`; se emiten hasta
  50 IP. Censys queda fuera por falta de un campo equivalente verificado.

### F4.18 `tech_detect` · activo
- Firmas propias en `modules/domain/data/tech_signatures.json` (cabeceras, cookies, `meta generator`,
  rutas de scripts y patrones del HTML), con versión cuando la firma la captura. Emite `technology`.
- **No** se usa `webappanalyzer` (GPL-3.0 [R20]). Como `update-data` no admite licencias fuera de la lista,
  tampoco hay dataset descargable: la lista de firmas va en el paquete.
- `http_fingerprint` conserva sus 17 firmas: otros módulos (`cloud_attribution`) leen su campo
  `technologies`. Quitarlas es un cambio de contrato que se decidirá aparte.

### F4.24 `ext_subfinder`
- `subfinder -d <dominio> -silent -json` sobre `ExternalToolModule`; se descartan los hosts que no sean el
  dominio o un subdominio suyo. `ext_amass` se aplaza: la salida de Amass cambió entre la v4 y la v5 y no
  hay un formato JSON estable verificado.

## Entregables bloqueados

| ID | Qué falta decidir |
|---|---|
| F4.17 (rangos) | Los feeds de rangos de AWS, GCP, Azure y Cloudflare, su licencia y si encajan en `update-data` |
| F4.22 | *Spike* hecho (06-11-2026, ver abajo); falta decidir si se acepta HackerTarget con sus reservas |
| F4.23 | GeoLite2 exige cuenta y licencia por usuario, y la dependencia `maxminddb` |
| F4.21 | Fuente de dominios relacionados por ID de analítica y sus términos |

### Spike F4.22 `reverse_ip` (06-11-2026)

Qué se verificó y qué no. **Nada de esto está implementado.**

**HackerTarget (candidata)**
- **Endpoint (verificado con una petición real):** `GET https://api.hackertarget.com/reverseiplookup/?q=<ip>`,
  texto plano, un nombre por línea. Con `&apikey=` y `&page=` para miembros.
- **Cuota (de su página):** gratuito 20 consultas al día y 50 resultados por consulta; con
  membresía, de 500 a 20.000 consultas al día y hasta 10 millones de resultados.
- **Origen de los datos (de su página):** rastreos de Alexa Top 1M, Bing, Common Crawl,
  Certificate Transparency y scans.io. Registros A históricos, sin fecha: cada nombre es una pista.
- **Calidad (verificada):** para `1.1.1.1` las primeras líneas son comodines de `invox.ipv64.de`.
  Con el tope de 50 resultados y sin orden de relevancia, una IP compartida o de CDN devuelve una
  muestra arbitraria. Habría que excluir IP de CDN y tratar el resultado como indicio.
- **Términos (de `hackertarget.com/terms`):** no hay una cláusula propia de la API ni de licencia de
  datos. Los términos generales prohíben redistribuir o guardar el contenido «en otro sitio web o
  sistema de recuperación electrónica», limitan la copia al uso personal y no comercial, y excluyen
  a quien ofrezca servicios similares de pago. Su aviso sobre escaneos (solo sistemas propios o con
  permiso) es de sus servicios de escaneo, no de esta consulta. **Es una zona gris para guardar los
  resultados en la base local**; no se ha pedido aclaración a HackerTarget.

**Alternativas, solo por su documentación (sin verificar en este *spike*)**
- Fuentes ya integradas que podrían dar IP → nombres sin fuente nueva: `internetdb`, `shodan` y
  `censys` ya traen `hostnames` como dato suelto; `otx` (DNS pasivo de la IP), `virustotal`
  (resoluciones de la IP) y `urlscan` (escaneos por IP) tienen endpoints oficiales y términos que el
  proyecto ya acepta. Habría que comprobar que existen para IP y qué cuota consumen.
- De pago: WhoisXML Reverse IP (500 créditos gratuitos al registrarse) y DomainTools.

**Recomendación:** no integrar HackerTarget por defecto. Si se quiere `reverse_ip`, empezar por
**promocionar a entidades `domain` los `hostnames` que `internetdb`, `shodan` y `censys` ya
devuelven** (sin fuente nueva ni términos nuevos) y, después, el DNS pasivo de `otx`/`virustotal`
tras verificar sus endpoints. HackerTarget quedaría como módulo opcional, desactivado por defecto,
con aviso de cuota y de términos, solo si se acepta el riesgo anterior.

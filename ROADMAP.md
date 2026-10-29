# Roadmap de OSINEITOR

> **Estado:** vigente · **Versión actual:** 0.1.1 · **Última revisión:** 29 de octubre de 2026
>
> Este documento define la dirección del proyecto después del MVP: qué se construirá, en qué
> orden, por qué y cómo se sabrá que cada fase está terminada. No compromete fechas: el orden,
> las prioridades y los criterios de aceptación sí son vinculantes.

## Índice

1. [Visión y posicionamiento](#1-visión-y-posicionamiento)
2. [Conclusiones de la investigación](#2-conclusiones-de-la-investigación)
3. [Punto de partida y análisis de carencias](#3-punto-de-partida-y-análisis-de-carencias)
4. [Principios de priorización](#4-principios-de-priorización)
5. [Resumen de fases](#5-resumen-de-fases)
6. [Fases en detalle](#6-fases-en-detalle)
7. [Líneas transversales](#7-líneas-transversales)
8. [Fuera de alcance](#8-fuera-de-alcance)
9. [Riesgos](#9-riesgos)
10. [Gobernanza del roadmap](#10-gobernanza-del-roadmap)
11. [Referencias](#11-referencias)

---

## 1. Visión y posicionamiento

**Visión:** ser la herramienta OSINT de línea de comandos **más fiable y verificable** para
investigar dominios, infraestructura, emails, usernames y organizaciones: cada dato con su
fuente, su fecha y su prueba; cada fuente con su estado de salud conocido.

**Posicionamiento.** OSINEITOR no competirá en número de fuentes: Maigret supera los 3.000
sitios, SpiderFoot los 200 módulos y BBOT los 100. Competirá donde el ecosistema es débil:

| Debilidad del ecosistema | Respuesta de OSINEITOR |
|---|---|
| Las fuentes se degradan en silencio: un resultado vacío parece una respuesta | Salud de cada fuente medida y visible; "sin resultados" ≠ "fuente rota" |
| Herramientas abandonadas (Recon-ng sin commits desde 2024, SpiderFoot sin release desde 2022) | Cadencia de releases, tests contra respuestas reales y CI de salud semanal |
| Resultados sin procedencia, difíciles de defender | Procedencia, hash de la evidencia y nivel de confianza por dato |
| Mezcla de recolección pasiva y activa sin control | Pasivo por defecto, alcance declarado y registro de lo que tocó al objetivo |
| Listas de datos crudos sin priorizar | Hallazgos con severidad, evidencia y recomendación sobre los datos recogidos |
| La IA genera conclusiones no verificables | IA opcional, limitada a resumir evidencia guardada y con cita obligatoria |

**Usuarios objetivo** (por orden): el propio autor y analistas individuales en
reconocimiento autorizado (pentest, bug bounty), auditoría de la huella digital propia o de una
organización, e investigación periodística o académica con base legal.

---

## 2. Conclusiones de la investigación

Resumen de la investigación del estado del arte (octubre de 2026) que justifica las prioridades.
Las fuentes están en la [sección 11](#11-referencias).

### 2.1 Mantenimiento por encima de funcionalidades

Las herramientas OSINT son capas finas sobre fuentes de terceros. Cuando una fuente cambia su
API, sus términos o su precio, una herramienta sin mantenimiento **no falla: devuelve menos y
reporta un escaneo limpio** [R1]. Es el modo de fallo más peligroso del sector. Ejemplos
verificados: Recon-ng sin commits desde noviembre de 2024; SpiderFoot sin release etiquetada
desde abril de 2022 y su versión comercial absorbida por Intel 471; holehe con módulos rotos
porque las plataformas endurecieron sus flujos de recuperación de contraseña [R1][R5].

**Consecuencia:** la [fase 1](#fase-1--fiabilidad-seguridad-y-robustez-v020) (fiabilidad) va
antes que cualquier fuente nueva.

### 2.2 El acceso a los datos se está cerrando

- X envió requerimientos legales a Nitter en agosto de 2026; las instancias cayeron [R1].
- Reddit restringió Pushshift en 2023 y no ofrece acceso comercial de autoservicio [R1].
- abuse.ch (URLhaus, ThreatFox) exige ahora `Auth-Key` incluso para la API comunitaria [R8].
- Maltego y Censys miden el acceso en créditos; Shodan limita a 1 petición/s en todos sus planes [R1].
- Microsoft retiró la API de búsqueda de Bing el 11 de agosto de 2025 [R19].

**Consecuencia:** priorizar fuentes con API oficial y términos estables; tratar cada
integración como perecedera (salud monitorizada, desactivación limpia) y respetar cuotas por
diseño. No se integrará scraping de redes sociales ni de buscadores
([sección 8](#8-fuera-de-alcance)).

### 2.3 Verificación y procedencia son el producto

El Protocolo de Berkeley (ONU/UC Berkeley) fija los estándares profesionales de
identificación, recolección, **preservación**, análisis y presentación de información de
fuentes abiertas, incluida la cadena de custodia [R3]. En 2026 el contenido generado por IA
contamina las fuentes que se recolectan, lo que hace la procedencia y la corroboración más
importantes que nunca [R1][R6].

**Consecuencia:** la [fase 2](#fase-2--procedencia-y-confianza-v030) introduce procedencia,
evidencia con hash y puntuación de confianza basada en corroboración entre fuentes.

### 2.4 IA: útil para resumir, peligrosa para concluir

La revisión sistemática más reciente sobre IA agéntica en OSINT identifica la alucinación como
el principal riesgo en más de 20 estudios, pero **solo uno la mide**: un 4 % en condiciones
favorables (RAG con base de conocimiento curada) [R6]. Ningún trabajo propone una cadena de
verificación completa.

**Consecuencia:** la IA llega tarde ([fase 10](#fase-10--asistencia-con-ia-v0110)), es opcional
y desactivada por defecto, y solo puede afirmar lo que esté respaldado por entidades guardadas,
con cita verificada automáticamente.

### 2.5 Interoperabilidad y grafo

Las herramientas de referencia exportan a formatos de análisis: Maigret a grafo HTML, Neo4j,
PDF y XMind [R4]; el ecosistema de inteligencia de amenazas se basa en STIX 2.1 y MISP, con
librerías Python maduras (`stix2`, `misp-stix`) [R9]. Amass mantiene un modelo de grafo de
activos [R1].

**Consecuencia:** las fases [7](#fase-7--hallazgos-análisis-y-casos-v080) y
[8](#fase-8--interoperabilidad-y-extensibilidad-v090) convierten los scans en un grafo
navegable y exportable.

### 2.6 Coberturas con mejor relación valor/coste

| Área | Fuentes gratuitas o con plan gratuito y API oficial |
|---|---|
| Inteligencia de amenazas | AlienVault OTX, abuse.ch (con Auth-Key), urlscan.io, VirusTotal (cuota baja), DNSBL de Spamhaus [R14] |
| Red y ASN | RIPEstat, PTR inverso, Team Cymru |
| Vulnerabilidades | EPSS (API gratuita de FIRST) y catálogo CISA KEV [R17]; NVD para CVSS |
| Certificados | crt.sh y Censys (plan gratuito con créditos) |
| Usernames | WhatsMyName (CC BY-SA 4.0), complementario a Sherlock [R7] |
| Identidades abiertas | Mastodon `accounts/lookup` [R22], registros de paquetes (npm, PyPI, crates.io) |
| Exposición por infostealers | Hudson Rock (API gratuita con key) [R18] |
| Empresas y sanciones | OpenSanctions (gratis para uso no comercial) [R10], GLEIF (LEI), LibreBOR / BORME (España) [R11], OpenCorporates (API desde 2.250 £/año) [R12] |
| Teléfono | `phonenumbers` (offline: país, tipo de línea, operador original) |
| Cripto | Exploradores públicos (mempool.space, Blockchair, Etherscan) |
| Imágenes y ficheros | Metadatos EXIF/XMP en local (sin subir el fichero a terceros) |

### 2.7 Hallazgos adicionales del análisis de carencias

- **Cobertura RDAP incompleta.** El bootstrap oficial de IANA (publicado el 28-10-2026, 1.203
  TLD) **no incluye** `es`, `io`, `de`, `mx`, `it`, `co`, `me`, `cl`, `pt`, `ru` ni `cn`, y sí
  `com`, `fr`, `uk`, `ar` y `br` [R15]. El módulo `rdap` es ciego para esos dominios y hoy lo
  disimula devolviendo "sin resultados". Hace falta WHOIS por puerto 43 como alternativa
  ([F4.11](#fase-4--dominio-e-infraestructura-v050-y-v051)) y distinguir "TLD sin RDAP" de
  "dominio no registrado" (F1.18).
- **Licencias de datos.** `enthec/webappanalyzer`, sucesor de Wappalyzer, es **GPL-3.0** [R20]:
  no puede empaquetarse en un proyecto MIT. WhatsMyName es CC BY-SA 4.0 [R7] y Sherlock MIT
  (fichero separado y con atribución, ya cumplido). Los términos de GeoLite2, NVD y Hudson Rock
  están por verificar en sus *spikes*.
- **APIs de búsqueda.** Bing está retirada [R19]; la API JSON de Google Custom Search solo
  admite clientes existentes y se discontinúa el 1-1-2027 (cita de segunda mano, confirmar en
  el *spike*); Brave Search ofrece una cuota gratuita de entre 1.000 y 2.000 consultas al mes
  según la fuente. El frente de dorks es una evaluación con puerta de decisión, no un
  compromiso.
- **Priorizar vulnerabilidades.** KEV recoge lo ya explotado de forma confirmada; EPSS estima la
  probabilidad de explotación en 30 días [R17]. Se necesitan ambos, y EPSS está pensado para
  consultas puntuales, no masivas.
- **Pivote por favicon.** Shodan indexa el hash MurmurHash3 del favicon (`http.favicon.hash`),
  lo que permite encontrar infraestructura con el mismo icono aunque esté tras un WAF o CDN
  [R16]. Requiere key con acceso a búsqueda.
- **Dominios parecidos.** dnstwist es el referente de permutaciones, homógrafos y comparación
  de contenido [R21]; su licencia y mantenimiento se verifican antes de depender de él.

---

## 3. Punto de partida y análisis de carencias

### 3.1 Disponible en v0.1.0

Núcleo con pivoteo por niveles, 16 módulos (10 sin key, 6 con key), SQLite, informes
JSON/Markdown/HTML, 41 tests sin red y CI en Python 3.11 y 3.13.

### 3.2 Deuda técnica conocida

| ID | Deuda | Impacto | Se resuelve en |
|---|---|---|---|
| D1 | La mayoría de módulos solo se ha probado con respuestas simuladas | Posibles fallos en uso real | Fase 0 |
| D2 | Un módulo sin resultados es indistinguible de un módulo roto | Falsos negativos silenciosos | Fase 1 |
| D3 | La base de datos no tiene sistema de migraciones | Cualquier cambio de esquema rompe datos existentes | Fase 1 |
| D4 | Las entidades solo guardan la primera fuente que las produjo | No hay corroboración medible | Fase 2 |
| D5 | Sin caché ni límites de cuota por fuente | Consumo innecesario de cuotas y bloqueos | Fase 1 |
| D6 | La CLI no tiene tests | Regresiones en la interfaz | Fase 0 |
| D7 | La detección de usernames tiene falsos positivos (WAF, captchas) y no hay línea base medida | Conclusiones erróneas; el criterio "−50 %" de la fase 1 no es comprobable | Fases 0, 1 y 5 |
| D8 | El username se inserta **sin codificar** en las URLs de unos 460 sitios, y el regex de email admite `/ ? #` en la parte local, que luego se reutiliza como username (`username/sites.py`, `email/validate.py`) | Peticiones con ruta o consulta alteradas | F1.11 |
| D9 | Los hostnames que devuelven fuentes externas (p. ej. crt.sh) no se validan y no hay guardia contra IPs privadas, loopback o metadatos cloud | Un módulo activo puede conectar a la red del propio analista | F1.13 |
| D10 | Sin normalización canónica de entidades (IDN/punycode, punto final, IPv6, URL); la clave solo aplica `lower()` | Duplicados y fallos de deduplicación | F1.12 |
| D11 | Sin presupuestos de escaneo: 500 subdominios × módulos × profundidad 2 puede explotar | Consumo de cuota y tiempo sin control | F1.14 |
| D12 | Rutas solo XDG, `chmod 0600` sin efecto en Windows y CI solo en Linux | La herramienta no es fiable fuera de Linux | F1.16 |
| D13 | Solo 10 tipos de entidad | No se pueden modelar ASN, certificados, personas, organizaciones, etc. | F3.1 |
| D14 | `rdap` devuelve vacío ante 404 y muchos TLD no tienen RDAP (ver [2.7](#27-hallazgos-adicionales-del-análisis-de-carencias)) | Dominios `.es`, `.io`, `.de`… sin datos de registro y sin aviso | F1.18 y F4.11 |

### 3.3 Carencias funcionales por frente

| Frente | Carencia | Entregable |
|---|---|---|
| Núcleo | Sin presets de escaneo | F3.2 |
| Núcleo | Sin módulos de análisis offline sobre datos ya recogidos | F3.3 |
| Núcleo | Sin adaptadores para herramientas externas (Subfinder, Amass pasivo, Maigret, ExifTool) | F3.4 |
| Núcleo | Datasets de terceros sin mecanismo de actualización ni registro de licencia | F3.5 |
| Núcleo | Sin barra de progreso, `--quiet`, exit codes ni salida CSV | F1.17, F7.11 |
| Dominio | Sin WHOIS de respaldo | F4.11 |
| Dominio | Certificados reducidos a nombres: sin emisor, validez, SAN ni huella | F4.12 |
| Dominio | Sin inferencia de SaaS desde MX/NS/SPF/TXT | F4.13 |
| Dominio | Solo 17 firmas de tecnología | F4.18 |
| Dominio | Sin detección de dominios parecidos (defensivo) | F4.20 |
| IP / red | Los CVE no se enriquecen (CVSS, EPSS, KEV) | F4.14 |
| IP / red | Sin ASN ni netblocks, sin atribución a nube/CDN, sin segunda base de escaneo (Censys) | F4.15 a F4.17 |
| Infraestructura | Sin pivotes por favicon ni por IDs de analítica | F4.19, F4.21 |
| Email | Sin exposición por infostealers | F5.8 |
| Personas | Sin generadores de variantes de username ni de candidatos de email | F5.9 |
| Usernames | Sin fediverso, Bluesky ni registros de paquetes | F5.10, F5.11 |
| Organizaciones | Sin sanciones, LEI ni registros mercantiles | F6.1 a F6.4 |
| Teléfono, cripto, ficheros | Sin soporte | F6.5 a F6.11 |
| Evidencia | Sin captura de páginas (HTML, WARC, pantallazo) | F6.12 |
| Fugas | Sin búsqueda de menciones del dominio en código público | F6.15 |
| Análisis | Sin capa de hallazgos con severidad y recomendación | F7.8 |
| Análisis | Sin resolución de entidades entre cuentas | F7.10 |

---

## 4. Principios de priorización

1. **Fiabilidad antes que cobertura.** Ninguna fuente nueva hasta que las existentes tengan
   salud medible.
2. **Verificable antes que espectacular.** Cada dato debe poder rastrearse hasta su origen.
3. **Pasivo por defecto.** Lo activo se pide explícitamente y queda registrado.
4. **API oficial antes que scraping.** Una fuente que viola términos de uso es una fuente que
   desaparecerá.
5. **Sin dependencias de pago obligatorias.** Todo frente debe tener al menos una fuente
   gratuita; las de pago son mejoras opcionales.
6. **Cada fase se puede publicar.** Termina en una versión utilizable, con changelog y tests.
7. **Cada fuente nueva empieza con un *spike* documentado:** endpoint real, términos de uso,
   cuota y licencia de los datos. Los entregables marcados *(spike)* no se implementan sin
   haberlo superado.
8. **No se abre la fase N+1 hasta cerrar los entregables *M* de la N.** Los *S* y *C* pueden
   aplazarse sin bloquear.

Prioridades de los entregables: **M** (imprescindible para cerrar la fase), **S** (recomendable,
no bloquea) y **C** (opcional, se hace si hay demanda).

---

## 5. Resumen de fases

| Fase | Versión | Objetivo | Esfuerzo | Depende de |
|---|---|---|---|---|
| [0](#fase-0--validación-en-campo-y-línea-base-v011) | 0.1.1 | Validación en campo y línea base | S | — |
| [1](#fase-1--fiabilidad-seguridad-y-robustez-v020) | 0.2.0 | Fiabilidad, seguridad y robustez | L | 0 |
| [2](#fase-2--procedencia-y-confianza-v030) | 0.3.0 | Procedencia, evidencia y confianza por dato | M | 1 |
| [3](#fase-3--modelo-ampliado-presets-y-adaptadores-v040) | 0.4.0 | Modelo de entidades ampliado, presets, analizadores y adaptadores | M | 2 |
| [4](#fase-4--dominio-e-infraestructura-v050-y-v051) | 0.5.0 y 0.5.1 | Dominio e infraestructura | L | 3 |
| [5](#fase-5--identidades-email-usernames-y-personas-v060) | 0.6.0 | Email, usernames y personas | L | 3 |
| [6](#fase-6--nuevos-frentes-v070) | 0.7.0 | Organizaciones, teléfono, cripto, ficheros, captura y fugas | L | 3 |
| [7](#fase-7--hallazgos-análisis-y-casos-v080) | 0.8.0 | Hallazgos, grafo, casos y comparación de scans | L | 2, 4 |
| [8](#fase-8--interoperabilidad-y-extensibilidad-v090) | 0.9.0 | STIX, MISP, Gephi, librería y plugins externos | M | 7 |
| [9](#fase-9--monitorización-continua-v0100) | 0.10.0 | Vigilancia periódica y alertas de cambios | M | 7 |
| [10](#fase-10--asistencia-con-ia-v0110) | 0.11.0 | Resúmenes con IA verificables y servidor MCP | M | 2, 7 |
| [11](#fase-11--producto-10-v100) | 1.0.0 | Interfaz web local, distribución y API estable | L | 8 |

Esfuerzo: **S** ≈ 1 semana, **M** ≈ 2–4 semanas, **L** ≈ 1–2 meses de dedicación parcial de
una persona. Son estimaciones propias, sin contrastar. Las fases 4, 5 y 6 son independientes
entre sí y pueden reordenarse.

```
0 ──► 1 ──► 2 ──► 3 ──┬──► 4 ──┐
                      ├──► 5   ├──► 7 ──┬──► 8 ──► 11
                      └──► 6   │        ├──► 9
                         2 ────┘        └──► 10
```

### Corte recomendado

**v0.5.0 = fases 0 a 4 con solo los entregables *M*** (30 de los 134 entregables
del roadmap). Es un producto completo y defendible para reconocimiento de dominios e
infraestructura propios: datos validados contra servicios reales, fuentes con salud medible,
entrada y red protegidas, procedencia verificable, WHOIS/RDAP, certificados, correo, SaaS y
CVE priorizados. Todo lo demás es opcional y reordenable.

El roadmap pasó de 80 a 134 entregables tras el análisis de carencias. Para un proyecto de
una persona eso es un riesgo de abandono, y por eso existen las prioridades *M*, *S* y *C*, el
principio 8 y este corte: **se puede parar en cualquier versión y lo hecho sigue siendo útil**.

Recuento por prioridad: 50 *M*, 61 *S* y 23 *C*.

---

## 6. Fases en detalle

Cada entregable tiene un identificador (`F<fase>.<n>`) para enlazarlo desde issues y PRs, y una
prioridad (**P**: M, S o C). Los *spikes* están marcados con *(spike)*.

### Fase 0 · Validación en campo y línea base (v0.1.1)

**Objetivo:** confirmar que lo que ya existe funciona contra los servicios reales y medir el
punto de partida con el que se comparará la fase 1.

| ID | P | Entregable | Detalle |
|---|---|---|---|
| F0.1 | M | Prueba real de cada módulo | Ejecutar cada módulo contra objetivos propios o públicos de prueba (p. ej. `example.com`, `8.8.8.8`) y documentar el resultado |
| F0.2 | M | Fixtures grabadas | Guardar respuestas reales anonimizadas en `tests/fixtures/` y usarlas en los tests en lugar de respuestas inventadas |
| F0.3 | M | Corrección de discrepancias | Ajustar el parseo donde el formato real difiera del documentado |
| F0.4 | M | Tests de la CLI | Cubrir todos los comandos con `typer.testing.CliRunner` |
| F0.5 | M | Línea base de falsos positivos de usernames | Script reproducible que ejecuta `username_sites` con usernames aleatorios inexistentes y publica la tasa en `docs/`; es la referencia del criterio de la fase 1 |
| F0.6 | M | Cobertura RDAP por TLD | Documentar qué TLD tienen RDAP según el bootstrap de IANA [R15] y cuáles quedan ciegos; alimenta F1.18 y F4.11 |

**Estado (29-10-2026, v0.1.1):** F0.4 y F0.6 completados ([`docs/RDAP_COBERTURA.md`](docs/RDAP_COBERTURA.md)).
F0.5 tiene el script listo (`scripts/fp_baseline.py`); la medición está **pendiente** de una red con
acceso a los sitios. F0.1, F0.2 y F0.3 siguen **pendientes** de pruebas en vivo; las cubrirán `osineitor doctor` (F1.2)
y el panel de salud de la aplicación de escritorio.

**Criterios de aceptación**
- Los 16 módulos tienen al menos una ejecución real documentada en el PR.
- Todos los tests de módulo usan fixtures grabadas de respuestas reales.
- Cobertura de la CLI ≥ 80 %.
- La línea base de F0.5 y la tabla de F0.6 están publicadas en `docs/`.

---

### Fase 1 · Fiabilidad, seguridad y robustez (v0.2.0)

**Objetivo:** que el usuario sepa en todo momento qué fuentes funcionan y por qué un resultado
está vacío, y que la herramienta no pueda dañar al propio analista ni explotar en peticiones.

| ID | P | Entregable | Detalle |
|---|---|---|---|
| F1.1 | M | Estado por módulo en cada scan | Cada ejecución registra `ok`, `vacío`, `error`, `omitido` o `cuota agotada`, con duración y número de peticiones |
| F1.2 | M | `osineitor doctor` | Comprueba cada módulo contra un **canario** de resultado conocido y muestra una tabla de salud. Para usernames se usa el campo `username_claimed` que ya incluyen las 481 firmas de Sherlock |
| F1.3 | S | Health check programado en CI | Workflow semanal (no bloqueante) que ejecuta `doctor` y abre un issue si una fuente falla |
| F1.4 | M | Migraciones de esquema | Versionado con `PRAGMA user_version` y migraciones incrementales con tests; requisito previo para la fase 2 |
| F1.5 | M | Caché HTTP | Caché en disco con TTL por fuente (`--no-cache`, `--refresh`) para no repetir consultas ni gastar cuota |
| F1.6 | M | Límites declarativos por fuente | Cada módulo declara su límite (p. ej. Shodan 1 petición/s) y el cliente HTTP lo respeta |
| F1.7 | M | Timeout por módulo y cancelación | Ningún módulo puede bloquear el scan más de su tiempo máximo |
| F1.8 | S | Proxy y Tor | `--proxy socks5://…` aplicado a todas las peticiones salientes |
| F1.9 | S | Registro estructurado | `--verbose` y `--log-file` en JSON, sin incluir nunca API keys |
| F1.10 | M | Reducción de falsos positivos en usernames | Comprobación doble con un username inexistente aleatorio: si el sitio también "lo encuentra", el resultado se descarta |
| F1.11 | M | Codificación y validación de entradas | Todo valor que se inserta en una URL se codifica (`quote(…, safe="")`); cada tipo de entidad valida su juego de caracteres; el username derivado de un email se sanea. Resuelve D8 |
| F1.12 | M | Normalización canónica de entidades | Dominios en minúsculas, punycode (IDNA) y sin punto final; IPv6 comprimida; URLs normalizadas; la clave de identidad usa la forma canónica; migración de los datos existentes. Resuelve D10 |
| F1.13 | M | Guardia de red | Los módulos activos y las redirecciones rechazan loopback, redes privadas, *link-local* y metadatos cloud (`169.254.169.254`) salvo `--allow-private`; los hostnames devueltos por fuentes externas se validan antes de emitirse. Resuelve D9 |
| F1.14 | M | Presupuestos de escaneo | `--max-entities`, `--max-requests`, `--max-time` y límite por módulo; al agotarse, el scan termina de forma ordenada e informa de lo omitido. Resuelve D11 |
| F1.15 | S | Detección de DNS wildcard | Sondeo con etiquetas aleatorias; los subdominios que solo resuelven por wildcard se marcan y no se pivotan |
| F1.16 | S | Multiplataforma | Rutas con `platformdirs`, permisos equivalentes en Windows y CI en Linux, macOS y Windows. Resuelve D12 |
| F1.17 | S | Experiencia de uso | Barra de progreso en `stderr`, `--quiet`, `stdout` limpio con `--json`, y *exit codes* documentados (éxito, error de uso, fuentes con errores, sin resultados) |
| F1.18 | M | `rdap` distingue "TLD sin RDAP" de "no registrado" | Consulta el bootstrap de IANA [R15]; para un TLD sin servidor emite `omitido: TLD sin RDAP` en lugar de un resultado vacío. Resuelve D14 junto con F4.11 |

**Criterios de aceptación**
- `osineitor doctor` informa del estado de los 16 módulos en menos de 2 minutos.
- La salida de un scan distingue visualmente "sin resultados" de "fuente con errores".
- Una base de datos v0.1.0 se migra sin pérdida (test automatizado).
- Repetir el mismo scan en menos de una hora no hace peticiones de red con la caché activa.
- La tasa de falsos positivos de `username_sites` baja al menos un 50 % respecto a la línea base
  de F0.5.
- Un username como `a/../b` o `x?y#z` no altera la ruta ni la consulta de ninguna de las URLs
  construidas (test parametrizado sobre todas las firmas).
- Un módulo activo no conecta con `127.0.0.1`, `10.0.0.0/8` ni `169.254.169.254`, ni sigue
  redirecciones hacia ellos (tests).
- `münchen.de` y `xn--mnchen-3ya.de` resultan en una única entidad.
- Para un dominio `.es` el scan muestra `omitido: TLD sin RDAP`, no "sin resultados".
- Con `--max-entities 50` un scan de 500 subdominios se detiene y lo indica.
- La CI es verde en Linux, macOS y Windows.

---

### Fase 2 · Procedencia y confianza (v0.3.0)

**Objetivo:** que cada dato sea rastreable y defendible, siguiendo los principios de
preservación del Protocolo de Berkeley.

| ID | P | Entregable | Detalle |
|---|---|---|---|
| F2.1 | M | Observaciones múltiples | Una entidad guarda todas las fuentes que la vieron (`observations`: módulo, fecha, consulta realizada) en lugar de solo la primera |
| F2.2 | M | Evidencia con hash | Opción `--evidence` que guarda la respuesta original de cada fuente con su SHA-256, URL consultada y fecha UTC |
| F2.3 | M | Puntuación de confianza | Nivel `bajo/medio/alto` según número de fuentes independientes, tipo de fuente (autoritativa como DNS o RDAP frente a agregada) y antigüedad del dato |
| F2.4 | S | Frescura | Campos `first_seen` y `last_seen` por entidad; los datos de terceros conservan su propia fecha (p. ej. último escaneo de Shodan) |
| F2.5 | M | Alcance declarado | Fichero de alcance (`--scope scope.yml`) con dominios, rangos y exclusiones; el engine no pivota fuera de él (modelo inspirado en BBOT [R2]) |
| F2.6 | S | Propósito del scan | Campo `--purpose` registrado en los metadatos; obligatorio en scans sobre emails o usernames si así se configura |
| F2.7 | S | Informe con anexo de evidencias | El informe HTML incluye una tabla de evidencias con hashes verificables |

**Criterios de aceptación**
- Cualquier entidad de un informe se puede rastrear hasta la consulta exacta que la produjo.
- `osineitor verify <scan>` recalcula los hashes de las evidencias y detecta manipulaciones.
- Un scan con alcance definido no produce entidades fuera de él (test con dominios trampa).

---

### Fase 3 · Modelo ampliado, presets y adaptadores (v0.4.0)

**Objetivo:** preparar el núcleo para las fases 4, 5 y 6: nuevos tipos de datos, perfiles de
escaneo reutilizables, módulos de análisis sin red y una vía segura para usar herramientas
externas.

| ID | P | Entregable | Detalle |
|---|---|---|---|
| F3.1 | M | Nuevos tipos de entidad | `asn`, `netblock`, `certificate`, `technology`, `organization`, `person`, `phone`, `crypto_address`, `file`, `location` y `finding` (este último reservado a F7.8), con su normalización (F1.12) y migración (F1.4). Resuelve D13 |
| F3.2 | M | Presets de escaneo | `--preset` y `osineitor presets`. Definidos en YAML y editables en el directorio de configuración: fijan módulos, profundidad, presupuesto y si admiten módulos activos. Incluidos: `passive`, `quick`, `domain-recon`, `attack-surface`, `person`, `email-audit` y `full` [R2] |
| F3.3 | M | Analizadores offline | Módulos de tipo *analyzer* que consumen entidades ya recogidas (p. ej. el `record` de DNS) sin hacer peticiones; se ejecutan en un pase final y no consumen presupuesto de red |
| F3.4 | S | Adaptadores de herramientas externas | Clase base `ExternalToolModule`: detección con `shutil.which`, ejecución **sin shell**, timeout, versión mínima y parseo de JSON. No se empaquetan binarios; `doctor` informa de cuáles están instalados |
| F3.5 | S | `osineitor update-data` | Descarga y actualiza los datasets de terceros en el directorio de datos del usuario, registrando versión, hash y licencia; los de licencia incompatible con MIT nunca entran en el paquete |
| F3.6 | S | Semillas ampliadas | `scan` reconoce URL (la descompone en dominio y URL), CIDR y ASN (`AS13335`). Teléfono, cripto y ficheros se añaden en la fase 6 junto a sus módulos |
| F3.7 | C | Filtros de salida | `--only-types` y `--exclude` para recortar resultados e informes |

**Criterios de aceptación**
- Los siete presets se listan, se ejecutan y se pueden sobrescribir desde el directorio del
  usuario.
- Un analizador no hace ninguna petición de red (test que intercepta la red).
- Si una herramienta externa no está instalada, su módulo aparece como `omitido`, no como error.
- `update-data` registra versión, hash y licencia de cada dataset y rechaza instalar los que
  figuren como incompatibles.

---

### Fase 4 · Dominio e infraestructura (v0.5.0 y v0.5.1)

**Objetivo:** cubrir los huecos de mayor valor en reconocimiento de dominios y redes,
priorizando fuentes gratuitas con API oficial. **v0.5.0** entrega los *M*; **v0.5.1**, los *S* y
*C*.

**Dominio y correo**

| ID | P | Módulo | Fuente o función | Key | Tipo |
|---|---|---|---|---|---|
| F4.4 | M | `mail_security` | MTA-STS, TLS-RPT, BIMI y selectores DKIM comunes | No | Pasivo (DNS) |
| F4.11 | M | `whois` | WHOIS por puerto 43 para los TLD sin RDAP (`.es`, `.io`, `.de`, `.mx`, `.it`, `.co`, `.me`… [R15]); parseo por TLD, límite de consultas y respeto de la privacidad de los datos | No | Pasivo |
| F4.13 | M | `saas_footprint` | Analizador que deduce proveedores de correo, DNS, identidad y colaboración desde MX, NS, `include:` de SPF y TXT de verificación; tabla de firmas versionada | No | Pasivo (offline) |
| F4.1 | S | `urlscan` | urlscan.io: escaneos históricos, tecnologías, IPs | Opcional | Pasivo |
| F4.2 | S | `otx` | AlienVault OTX: pulses, DNS pasivo, malware asociado | Sí (gratis) | Pasivo |
| F4.3 | S | `virustotal` | VirusTotal: reputación, subdominios, resoluciones | Sí (gratis, cuota baja) | Pasivo |
| F4.5 | S | `web_meta` | `robots.txt`, `sitemap.xml`, `security.txt` | No | **Activo** |
| F4.6 | S | `takeover` | Detección de subdominios con CNAME a servicios no reclamados | No | **Activo** |
| F4.18 | S | `tech_detect` | Detección de tecnologías con un dataset descargable (F3.5). **El de `webappanalyzer` es GPL-3.0 [R20] y no se incluye en el paquete**; alternativa: firmas propias. Sustituye las 17 firmas de `http_fingerprint` | No | **Activo** |

**Certificados y vulnerabilidades**

| ID | P | Módulo | Fuente o función | Key | Tipo |
|---|---|---|---|---|---|
| F4.12 | M | `cert_details` | crt.sh (y Censys si hay key): emisor, validez, SAN y huella SHA-256 como entidad `certificate`; pivote por SAN y huella a otros dominios; aviso de caducidad | No | Pasivo |
| F4.14 | M | `cve_enrich` | Analizador sobre entidades `vulnerability`: CVSS (NVD), probabilidad EPSS y marca KEV [R17]. Límites de NVD *(spike)* | Opcional (NVD) | Pasivo |
| F4.15 | S | `censys` | Censys Platform: hosts y certificados; segunda base de escaneo que complementa a Shodan [R1] | Sí (gratis con créditos) | Pasivo |

**IP y red**

| ID | P | Módulo | Fuente o función | Key | Tipo |
|---|---|---|---|---|---|
| F4.7 | S | `ptr` | DNS inverso | No | Pasivo |
| F4.8 | S | `ripestat` | RIPEstat: ASN, prefijo, país de registro, historial de enrutamiento | No | Pasivo |
| F4.9 | S | `dnsbl` | Listas negras DNS (Spamhaus ZEN y otras de uso gratuito) | No | Pasivo |
| F4.16 | S | `asn_netblock` | De IP a ASN y a los prefijos del AS (con tope); entidades `asn` y `netblock` | No | Pasivo |
| F4.17 | S | `cloud_attribution` | Analizador que etiqueta IPs como AWS, GCP, Azure, Cloudflare… con los rangos que publican esos proveedores (dataset de F3.5; feeds *(spike)*) y detecta CDN por CNAME y cabeceras | No | Pasivo (offline) |
| F4.10 | C | `abusech` | ThreatFox y URLhaus: IOCs asociados [R8] | Sí (gratis) | Pasivo |
| F4.22 | C | `reverse_ip` | Hostnames alojados en la misma IP según fuentes pasivas *(spike)* | Según fuente | Pasivo |
| F4.23 | C | `geoip_offline` | GeoIP con GeoLite2 en local para no enviar IPs a terceros; la licencia exige que cada usuario descargue la base *(spike)* | Cuenta gratuita | Pasivo (offline) |

**Pivotes de infraestructura y defensa**

| ID | P | Módulo | Fuente o función | Key | Tipo |
|---|---|---|---|---|---|
| F4.19 | S | `favicon_pivot` | Hash MurmurHash3 del favicon y búsqueda de otros hosts con el mismo icono en Shodan (`http.favicon.hash`) o Censys [R16] | Sí (Shodan o Censys) | **Activo** (descarga el favicon del objetivo) |
| F4.20 | S | `lookalike_domains` | Permutaciones y homógrafos del dominio **propio** y comprobación DNS (A, MX, NS) de los registrados; se evalúa dnstwist como dependencia opcional [R21] *(spike: licencia y mantenimiento)* | No | Pasivo (DNS) |
| F4.21 | C | `analytics_ids` | IDs de Google Analytics, GTM y AdSense de la página y dominios relacionados donde una fuente lo permita *(spike)* | Según fuente | **Activo** |
| F4.24 | C | `ext_subfinder`, `ext_amass` | Adaptadores (F3.4) de Subfinder y de Amass **solo en modo pasivo**; el binario lo instala el usuario | No | Pasivo |

**Criterios de aceptación**
- Un dominio `.es` obtiene datos de registro por WHOIS, o un aviso explícito de que no están
  disponibles; nunca un vacío silencioso.
- Una CVE de una IP se muestra con CVSS, EPSS y marca KEV.
- `saas_footprint` identifica proveedores a partir de DNS ya recogido sin hacer peticiones
  (test que intercepta la red).
- Cada módulo cumple los requisitos de la fase 1 (canario en `doctor`, límite declarado) y de
  la fase 2 (procedencia).
- Los módulos activos solo se ejecutan con `--active` y respetando el alcance y la guardia de
  red.
- La documentación de cada módulo indica sus términos de uso, su cuota y la licencia de sus
  datos.

---

### Fase 5 · Identidades: email, usernames y personas (v0.6.0)

**Objetivo:** mejorar la fiabilidad y la profundidad de la investigación de identidades en
línea, sin recurrir a scraping de redes sociales.

**Email**

| ID | P | Módulo | Fuente o función | Key | Tipo |
|---|---|---|---|---|---|
| F5.2 | S | `github_email` | Búsqueda de commits públicos por email en la API de GitHub | Opcional | Pasivo |
| F5.8 | S | `hudsonrock` | Exposición del email, username o dominio por infostealers [R18]. **Solo metadatos** (existencia, fecha, equipo comprometido sí o no); nunca credenciales. Términos de uso *(spike)* | Sí (gratis) | Pasivo |
| F5.1 | C | `leakcheck` | LeakCheck API pública: nombres de filtraciones *(spike)* | No | Pasivo |
| F5.12 | C | `pgp_keyserver` | Clave pública asociada al email en keys.openpgp.org (solo identidades verificadas) *(spike)* | No | Pasivo |
| F5.13 | C | `hibp_pastes` | Apariciones del email en *pastes* (mismo endpoint de HIBP y misma key) | Sí (HIBP) | Pasivo |

**Usernames y personas**

| ID | P | Entregable | Detalle |
|---|---|---|---|
| F5.9 | M | Generadores | `username_variants` (permutaciones a partir de nombre o alias) y `email_candidates` (patrones como `{first}.{last}` sobre un dominio). **Solo generan candidatos: nunca se verifican por SMTP.** Introducen la entidad `person` |
| F5.3 | S | Segunda fuente de firmas | Integrar WhatsMyName (CC BY-SA 4.0, fichero de datos separado con atribución [R7]) y marcar como "confirmado" lo que detecten ambas fuentes |
| F5.4 | S | Extracción de perfil | Para los sitios principales, extraer nombre visible, biografía, enlaces y otros usernames de la página pública |
| F5.5 | S | Pivote recursivo de identificadores | Los usernames y enlaces extraídos en F5.4 alimentan el siguiente nivel de pivoteo |
| F5.7 | S | `github_user` | Perfil público de GitHub: nombre, empresa, blog, organizaciones, emails de commits públicos |
| F5.10 | S | `fediverse` | Mastodon `GET /api/v1/accounts/lookup` [R22] y WebFinger en las instancias derivadas de `usuario@instancia`; perfil público de Bluesky *(spike)* |
| F5.11 | S | `dev_registries` | Perfiles y mantenedores en npm, PyPI, crates.io, Docker Hub y Stack Exchange, y metadatos públicos de los paquetes publicados |
| F5.6 | C | Filtros por categoría | `--tags dev,social,gaming` y `--top N` por popularidad |
| F5.14 | C | `discord_snowflake` | Fecha de creación de una cuenta a partir de su ID, en local |
| F5.15 | C | `ext_maigret` | Adaptador (F3.4) de Maigret para extracción de perfil recursiva; el binario lo instala el usuario |

**Criterios de aceptación**
- Los generadores no hacen ninguna petición de red ni de SMTP (test).
- `hudsonrock` nunca almacena contraseñas ni otros secretos (test con una fixture que los
  contiene).
- Los resultados de WhatsMyName y Sherlock coincidentes se marcan como confirmados.
- Cada módulo cumple los criterios de la fase 4 sobre salud, procedencia y términos de uso.

---

### Fase 6 · Nuevos frentes (v0.7.0)

**Objetivo:** abrir los frentes que más demanda tienen en investigaciones profesionales, con
fuentes legales y documentadas.

**Organizaciones** (entidad `organization`)

| ID | P | Módulo | Fuente | Notas |
|---|---|---|---|---|
| F6.1 | S | `opensanctions` | Listas de sanciones y personas políticamente expuestas [R10] | Gratis para uso no comercial con key |
| F6.2 | S | `gleif` | Identificadores LEI y relaciones matriz–filial | API pública gratuita |
| F6.3 | C | `librebor` | Actos del BORME en España: constituciones, cargos, ceses [R11] | API de pago; módulo opcional |
| F6.4 | C | `opencorporates` | Registros mercantiles de más de 140 jurisdicciones [R12] | API de pago; acceso gratuito para periodismo e investigación previa solicitud |

**Teléfono, criptomonedas y ficheros**

| ID | P | Módulo | Fuente | Notas |
|---|---|---|---|---|
| F6.5 | M | `phone_parse` | Librería `phonenumbers`, sin red | País, región, tipo de línea, operador de origen y formatos E.164 |
| F6.6 | M | `crypto_detect` | Validación local de formato (BTC, ETH, LTC, XMR…) | Sin red |
| F6.7 | S | `btc_explorer` | mempool.space: saldo, número de transacciones, primera y última actividad | Gratis |
| F6.8 | C | `eth_explorer` | Etherscan: saldo, transacciones, etiquetas públicas | Key gratuita |
| F6.9 | M | `file_meta` | EXIF, XMP, IPTC y metadatos de documentos (PDF, Office) **en local** | Nunca se suben ficheros a terceros |
| F6.10 | S | `file_hash` | MD5, SHA-1, SHA-256 y pivote a reputación (VirusTotal, abuse.ch) | Solo el hash sale del equipo |
| F6.11 | S | `geo_point` | Coordenadas GPS como entidad `location`, con enlace a mapas | Sin red |

**Evidencia, fugas y búsqueda**

| ID | P | Módulo | Función | Notas |
|---|---|---|---|---|
| F6.12 | S | `capture` | Captura de una URL: HTML, cabeceras, WARC, pantallazo con navegador *headless* y SHA-256; opción de Save Page Now de Wayback. Sigue los principios de preservación [R3] | **Activo**; extra opcional `osineitor[capture]` |
| F6.15 | S | `github_code` | Menciones del dominio en código público de GitHub para detectar fugas (credenciales, endpoints internos). **Solo se guarda repositorio, ruta, tipo de regla y huella; nunca el valor del secreto.** Incluye guía de divulgación responsable | Key de GitHub |
| F6.13 | C | `search_dorks` | Plantillas (`site:`, `filetype:`, `intext:`) lanzadas por una **API oficial de búsqueda** (candidata: Brave Search); sin scraping de buscadores [R19]. Evaluación con puerta de decisión *(spike)* | Cuota gratuita limitada |
| F6.14 | C | `doc_harvest` | Descarga documentos públicos del dominio (de dorks o Wayback) y extrae sus metadatos con `file_meta` (autor, software, rutas internas) | **Activo** |
| F6.16 | C | `cloud_storage_refs` | Detecta referencias a buckets (S3, GCS, Azure) en URLs ya recogidas y comprueba el acceso público de **ese** bucket; **no se adivinan nombres** | Activo |
| F6.17 | C | `image_links` | Genera enlaces de búsqueda inversa de imágenes (Yandex, TinEye, Google) para una URL; no sube ficheros | Sin red |
| F6.18 | C | `ext_exiftool` | Adaptador (F3.4) de ExifTool para formatos que `file_meta` no cubra | Binario del usuario |

**Criterios de aceptación**
- `osineitor scan` detecta automáticamente teléfonos, direcciones cripto y rutas de fichero.
- Ningún módulo de ficheros transmite el contenido del fichero; un test lo verifica
  interceptando la red.
- `github_code` no escribe el valor de un secreto en la base de datos ni en los informes (test
  con una fixture que contiene uno falso).
- Una captura de `capture` puede verificarse con `osineitor verify` (hash coincidente).
- Los módulos de organizaciones documentan la licencia de sus datos y su uso permitido.
- La decisión sobre `search_dorks` (implementar con qué API, o descartar) queda documentada.

---

### Fase 7 · Hallazgos, análisis y casos (v0.8.0)

**Objetivo:** pasar de una lista de resultados a una investigación navegable y priorizada.

| ID | P | Entregable | Detalle |
|---|---|---|---|
| F7.8 | M | Motor de hallazgos | Modelo `Finding` (regla, severidad, entidades afectadas, evidencia, recomendación) y reglas declarativas en YAML. Reglas iniciales (≥ 12): DMARC ausente o `p=none`; SPF con `+all` o `?all`; sin MTA-STS; certificado caducado o a ≤ 30 días; dominio que expira en ≤ 60 días; CVE en KEV; EPSS alto; CNAME colgante; URLs sensibles archivadas (`.env`, `.sql`); IP en lista negra; cabeceras de seguridad ausentes; servicios de administración expuestos |
| F7.1 | M | Grafo interactivo en el informe HTML | Nodos por entidad y aristas por relación de pivoteo, con filtros por tipo y fuente (librería JS local, sin CDN en el informe) |
| F7.3 | M | Comparación de scans | `osineitor diff A B`: entidades y hallazgos nuevos, desaparecidos y modificados |
| F7.11 | M | Exportación CSV | Entidades, relaciones y hallazgos en CSV |
| F7.2 | S | Casos | `osineitor case new/add/show`: agrupa varios scans de una misma investigación con notas y etiquetas |
| F7.4 | S | Línea temporal | Ordena las fechas conocidas (registro de dominio, certificados, capturas de Wayback, filtraciones, primera actividad cripto) |
| F7.5 | S | Búsqueda global | `osineitor search <valor>`: en qué scans y casos aparece un dato |
| F7.6 | S | Correlación entre scans | Avisa cuando una entidad nueva ya apareció en otro caso (p. ej. misma IP o mismo email) |
| F7.7 | S | Informe ejecutivo | Plantilla de informe con resumen, hallazgos clave, nivel de confianza y anexos |
| F7.9 | S | Puntuación de riesgo por activo | Combina severidad de hallazgos, exposición y confianza |
| F7.10 | S | Resolución de entidades | Agrupa cuentas que comparten username, email o avatar con una puntuación. **Siempre se presenta como hipótesis con su evidencia**, nunca como identidad confirmada |
| F7.12 | S | Informe de superficie de ataque | Inventario de dominios, IPs, servicios, tecnologías y certificados con los hallazgos priorizados |

**Criterios de aceptación**
- Al menos 12 reglas con tests positivos y negativos; cada hallazgo enlaza las entidades y
  evidencias que lo justifican.
- El grafo de un scan de 500 entidades se abre y navega con fluidez en un navegador actual.
- `diff` entre dos scans del mismo objetivo identifica correctamente altas y bajas (tests).
- Las coincidencias de F7.10 aparecen etiquetadas como hipótesis en todos los formatos.

---

### Fase 8 · Interoperabilidad y extensibilidad (v0.9.0)

**Objetivo:** que OSINEITOR encaje en flujos de trabajo existentes y que terceros puedan
ampliarlo sin modificar el código.

| ID | P | Entregable | Detalle |
|---|---|---|---|
| F8.4 | M | Streaming NDJSON | `--ndjson` emite entidades en tiempo real para encadenar con otras herramientas |
| F8.5 | M | API de librería estable | `from osineitor import Scanner` con interfaz síncrona y asíncrona documentada |
| F8.6 | M | Plugins externos | Descubrimiento de módulos por *entry points* (`osineitor.modules`), de modo que un paquete de PyPI pueda añadir fuentes |
| F8.1 | S | Exportación STIX 2.1 | Observables de infraestructura (dominios, IPs, URLs, emails, vulnerabilidades) con la librería `stix2` |
| F8.3 | S | Formatos de grafo | GraphML/GEXF (Gephi) y script Cypher (Neo4j) |
| F8.7 | S | Importación | Cargar listas de objetivos (`--targets-file`) y resultados de otras herramientas (Subfinder, Amass, Maigret JSON) como semillas |
| F8.2 | C | Exportación a MISP | Evento MISP con atributos y objetos (`pymisp`) |

**Criterios de aceptación**
- El STIX generado valida con el validador oficial de OASIS.
- Un plugin de ejemplo publicado en un repositorio aparte se instala con `pip` y aparece en
  `osineitor modules` sin tocar el código del proyecto.

---

### Fase 9 · Monitorización continua (v0.10.0)

**Objetivo:** vigilar activos propios y detectar cambios relevantes, el núcleo de la gestión
de la superficie de ataque externa.

| ID | P | Entregable | Detalle |
|---|---|---|---|
| F9.1 | M | `osineitor watch` | Define objetivos vigilados con frecuencia y módulos; se ejecuta desde cron, systemd o GitHub Actions |
| F9.2 | M | Reglas de alerta | Reutilizan el motor de hallazgos (F7.8): nuevo subdominio, nuevo puerto expuesto, nueva CVE, certificado próximo a caducar, dominio próximo a expirar, aparición en una filtración, IP en lista negra |
| F9.3 | M | Notificaciones | Webhook genérico (compatible con Slack, Discord y Teams), email SMTP y salida para sistemas de monitorización |
| F9.4 | S | Supresión de ruido | Umbrales, ventanas de silencio y confirmación en dos ejecuciones antes de alertar |
| F9.5 | S | Retención | Política de conservación configurable (`osineitor purge --older-than 90d`) |
| F9.6 | S | Vigilancia de dominios parecidos | Alerta cuando aparece un dominio nuevo detectado por `lookalike_domains` (F4.20) |
| F9.7 | S | Vigilancia de nuevas filtraciones | Alerta cuando un email o dominio vigilado aparece en una filtración o en infostealers que no figuraba antes |

**Criterios de aceptación**
- Un cambio simulado en las fixtures genera exactamente una alerta, y no se repite en la
  siguiente ejecución.
- Documentación de despliegue con cron y con GitHub Actions.

---

### Fase 10 · Asistencia con IA (v0.11.0)

**Objetivo:** acelerar el análisis sin sacrificar la verificabilidad.

| ID | P | Entregable | Detalle |
|---|---|---|---|
| F10.2 | M | Citas obligatorias y verificadas | Cada afirmación del resumen referencia identificadores de entidad; un validador rechaza las frases sin cita o con citas inexistentes |
| F10.3 | M | Modelos locales y remotos | Soporte para modelos locales (Ollama) por privacidad, y APIs remotas como opción explícita; nunca se envían datos sin consentimiento en la configuración |
| F10.6 | M | Evaluación | Conjunto de pruebas propio para medir la proporción de afirmaciones sin respaldo, publicada en la documentación |
| F10.1 | S | `osineitor summarize <scan>` | Resumen en lenguaje natural generado **solo** a partir de las entidades guardadas |
| F10.4 | S | Servidor MCP | Expone búsqueda, consulta de scans y lanzamiento de módulos pasivos a agentes de IA; los módulos activos quedan excluidos por defecto |
| F10.7 | S | Resúmenes basados en hallazgos | El resumen parte de los hallazgos (F7.8) y sus evidencias, no de las entidades en bruto |
| F10.5 | C | Sugerencia de pivotes | Propone siguientes pasos; nunca los ejecuta sin confirmación del usuario |

**Criterios de aceptación**
- El 100 % de las afirmaciones del resumen tiene una cita válida, comprobado automáticamente.
- La funcionalidad está desactivada por defecto y no añade dependencias a la instalación base
  (extra opcional `osineitor[ai]`).
- La tasa de afirmaciones sin respaldo medida en F10.6 se publica junto a la versión.

---

### Fase 11 · Producto 1.0 (v1.0.0)

**Objetivo:** estabilidad, distribución y una interfaz para quien no usa la terminal.

| ID | P | Entregable | Detalle |
|---|---|---|---|
| F11.2 | M | Publicación en PyPI | Con *trusted publishing* y firma de artefactos (Sigstore) |
| F11.4 | M | Sitio de documentación | MkDocs con guía de usuario, referencia de módulos generada desde el código y tutoriales |
| F11.6 | M | Compromiso de estabilidad | SemVer estricto sobre CLI, formato de exportación y API de librería; política de obsolescencia de dos versiones menores |
| F11.1 | S | Interfaz web local | FastAPI + frontend ligero: lanzar scans, ver el grafo, gestionar casos. Solo escucha en `localhost` por defecto |
| F11.3 | S | Imagen Docker | Imagen oficial mínima y sin privilegios |
| F11.5 | C | Internacionalización | Interfaz y documentación en español e inglés |

**Criterios de aceptación**
- Instalación con `pip install osineitor` y `docker run` documentadas y probadas en CI.
- Guía de migración desde 0.x.

---

## 7. Líneas transversales

Se aplican en todas las fases, no se planifican aparte.

### Calidad

- Cobertura de tests ≥ 85 % en el núcleo y ≥ 70 % global; ningún test depende de la red.
- Tipado estático con `mypy` (estricto en el núcleo) desde la fase 1.
- CI en Linux, macOS y Windows desde F1.16.
- Cada PR que añade un módulo incluye fixture real, canario de salud y documentación.

### Seguridad

- API keys en el llavero del sistema (`keyring`) como alternativa al fichero TOML (fase 1).
- Cifrado opcional de la base de datos (SQLCipher) para investigaciones con datos personales
  (fase 2).
- Informes HTML sin recursos externos y con escape de todo el contenido de terceros.
- Toda entrada del usuario o de una fuente externa se valida y codifica antes de usarse en una
  URL o en un comando (F1.11, F1.13).
- Análisis de dependencias (Dependabot) y de secretos en CI.

### Legal y ética

- Toda fuente nueva documenta sus términos de uso y si permite el acceso automatizado.
- Registro del propósito y del alcance de cada scan (fase 2) como apoyo a la responsabilidad
  proactiva del RGPD.
- Plantilla de evaluación de interés legítimo en `docs/` (fase 2), basada en las directrices
  1/2024 del CEPD [R13].
- Revisión anual de [docs/USO_RESPONSABLE.md](docs/USO_RESPONSABLE.md).

### Licencias de datos

Un dataset de terceros solo entra en el paquete si su licencia es compatible con MIT. El
registro de licencias se mantiene con `update-data` (F3.5).

| Dataset | Licencia | Tratamiento |
|---|---|---|
| Firmas de Sherlock | MIT | Incluido, con atribución |
| WhatsMyName | CC BY-SA 4.0 [R7] | Fichero de datos separado del código, con atribución |
| Firmas de `webappanalyzer` | GPL-3.0 [R20] | **No se incluye**; descarga bajo demanda o firmas propias |
| GeoLite2 | EULA de MaxMind | No se redistribuye; cada usuario lo descarga *(spike)* |
| Catálogo CISA KEV, datos EPSS | Por verificar en el *spike* de F4.14 | Descarga bajo demanda |

### Dependencias previstas

Propuestas que se confirman en el *spike* de cada entregable; las pesadas van en extras
opcionales para no engordar la instalación base.

| Fase | Dependencias |
|---|---|
| 1 | `platformdirs`, `idna`; `keyring` opcional |
| 3 | `pyyaml` |
| 4 | `mmh3`; `maxminddb` opcional |
| 6 | `phonenumbers`, lector de metadatos de imagen; `playwright` y `warcio` en el extra `capture` |
| 8 | `stix2`; `pymisp` opcional |
| 10 | Extra `ai` |
| 11 | `fastapi`, `uvicorn` en un extra |

### Rendimiento

- Un scan de dominio a profundidad 2 sin módulos activos debe completarse en menos de 3 minutos
  con la caché vacía, salvo esperas impuestas por límites de las fuentes.

---

## 8. Fuera de alcance

Decisiones explícitas de **no** construir, con su motivo. Reabrirlas requiere un issue con
justificación.

| Funcionalidad | Motivo |
|---|---|
| Scraping de redes sociales con sesión iniciada (X, Instagram, Facebook, LinkedIn) | Viola sus términos, se aplica activamente contra herramientas abiertas [R1] y obliga a usar cuentas falsas |
| Scraping de buscadores (Google, Bing, DuckDuckGo) | Viola sus términos y se bloquea; solo se usan APIs oficiales (F6.13) |
| Comprobar si un email está registrado mediante flujos de recuperación de contraseña (estilo holehe) | Abusa de funcionalidades no destinadas a ello, rompe con frecuencia [R5] y puede alertar al titular |
| Verificar emails con sondeo SMTP (`RCPT TO`, `VRFY`) | Intrusivo, puede alertar al titular y suele bloquearse; los candidatos de F5.9 solo se generan |
| Saltar captchas, WAF o autenticación | Acceso no autorizado |
| Usar o mostrar contraseñas de filtraciones o de infostealers | Facilita el acceso no autorizado a cuentas; solo se muestran nombres de filtración, fechas y tipos de dato |
| Adivinar nombres de buckets o de recursos cloud | Es fuerza bruta contra terceros; solo se comprueban los que aparecen en datos recogidos (F6.16) |
| Reconocimiento facial | Datos biométricos (categoría especial del RGPD) y alto riesgo de abuso |
| Fuerza bruta de subdominios, escaneo de puertos propio o explotación | Herramientas especializadas (Amass, Nmap, Nuclei) lo hacen mejor; OSINEITOR puede importar sus resultados (F8.7) o invocarlas en modo pasivo (F3.4) |
| Buscadores de personas que agregan datos personales (p. ej. por DNI) | Incompatible con el RGPD en la mayoría de usos |
| Monitorización de la dark web | Requiere infraestructura y riesgos legales desproporcionados para el proyecto |

---

## 9. Riesgos

| Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|
| Una fuente cambia o cierra su API | Alta | Medio | Salud monitorizada (F1.2, F1.3), módulos aislados y desactivables, *spike* previo (principio 7) |
| Cuotas gratuitas insuficientes | Alta | Medio | Caché (F1.5), límites declarativos (F1.6), alternativas gratuitas por frente |
| Uso indebido de la herramienta para acoso | Media | Alto | Fuera de alcance explícito, registro de propósito, sin agregación de datos personales sensibles, entidades resueltas solo como hipótesis (F7.10) |
| Falsos positivos que llevan a conclusiones erróneas | Alta | Alto | Doble comprobación (F1.10), corroboración y confianza (F2.3), avisos en informes |
| Alcance excesivo para un proyecto de una persona (80 → 134 entregables) | Alta | Alto | Prioridades M/S/C, principio 8, corte recomendado en v0.5.0 y fases 4–6 reordenables |
| Contaminación por licencias incompatibles (GPL, CC BY-SA, EULA) | Media | Medio | Registro de licencias, `update-data` (F3.5) que rechaza las incompatibles y datasets separados del código |
| Un módulo activo ataca la red del analista (SSRF desde los resultados de recon) | Media | Alto | Guardia de red (F1.13), validación de hostnames externos, alcance declarado (F2.5) |
| Manejo indebido de secretos hallados en código o en filtraciones | Media | Alto | Política de no almacenar valores (F5.8, F6.15), tests con fixtures de secretos falsos, guía de divulgación responsable |
| Alucinaciones de la IA presentadas como hechos | Media | Alto | IA opcional, citas verificadas (F10.2), evaluación publicada (F10.6) |
| Dependencia de binarios externos que cambian de comportamiento | Media | Bajo | Versión mínima y detección en `doctor` (F3.4); siempre opcionales |

---

## 10. Gobernanza del roadmap

- **Revisión:** al cerrar cada fase y, como mínimo, cada tres meses.
- **Cambios:** mediante PR que modifique este documento, explicando qué cambia y por qué.
- **Cierre de fase:** una fase se cierra cuando todos sus entregables *M* cumplen los criterios
  de aceptación y están publicados con changelog. Los *S* y *C* pendientes pasan a la siguiente
  revisión o se descartan con motivo.
- **Seguimiento:** cada entregable se convierte en un issue con la etiqueta `roadmap` y su
  identificador (`F4.12`) en el título; cada fase, en un *milestone* de GitHub.
- **Versionado:** las fases 0–10 publican versiones 0.x; la API se considera estable desde 1.0.0.
- **Propuestas:** las ideas nuevas entran por la plantilla de issue
  [`Nueva fuente`](.github/ISSUE_TEMPLATE/new_source.md) o
  [`Mejora`](.github/ISSUE_TEMPLATE/feature_request.md), y pasan por un *spike* antes de
  asignarles fase.

### Historial de revisiones

| Fecha | Cambio |
|---|---|
| 28-10-2026 | Versión inicial: fases 0 a 9 |
| 29-10-2026 | Análisis de carencias: deuda D8–D14, fase 3 nueva, las antiguas fases 3 a 9 pasan a 4–11, prioridades M/S/C, corte recomendado y nuevos entregables |

### Correspondencia con la numeración anterior

| Antes (28-10-2026) | Ahora |
|---|---|
| Fase 3 (fuentes en frentes actuales) | Fase 4 (dominio, IP) y fase 5 (email, usernames): F3.1–F3.10 → F4.1–F4.10 y F3.11–F3.17 → F5.1–F5.7 |
| Fase 4 (nuevos frentes) | Fase 6: F4.1–F4.11 → F6.1–F6.11 |
| Fase 5 (análisis, grafo y casos) | Fase 7: F5.1–F5.7 → F7.1–F7.7 |
| Fase 6 (interoperabilidad) | Fase 8: F6.1–F6.7 → F8.1–F8.7 |
| Fase 7 (monitorización) | Fase 9: F7.1–F7.5 → F9.1–F9.5 |
| Fase 8 (IA) | Fase 10: F8.1–F8.6 → F10.1–F10.6 |
| Fase 9 (producto 1.0) | Fase 11: F9.1–F9.6 → F11.1–F11.6 (el orden interno de F11 cambió) |

---

## 11. Referencias

| ID | Fuente |
|---|---|
| R1 | D. Gupta, *Top 6 OSINT Tools for Security Professionals 2026* (verificado el 18-09-2026): estado de mantenimiento, cierres de acceso y precios. <https://guptadeepak.com/tools/top-5-osint-tools-2026/> |
| R2 | Black Lantern Security, *BBOT*: arquitectura recursiva basada en eventos, presets y alcance. <https://github.com/blacklanternsecurity/bbot> |
| R3 | OACNUDH y UC Berkeley, *Protocolo de Berkeley sobre investigaciones digitales de fuentes abiertas* (2022). <https://www.ohchr.org/sites/default/files/2024-01/OHCHR_BerkeleyProtocol.pdf> |
| R4 | soxoj, *Maigret*: búsqueda recursiva, extracción de perfiles y exportaciones. <https://github.com/soxoj/maigret> |
| R5 | *RIP Holehe: Why User-Scanner is the New King of Email OSINT* (2026). <https://dev.to/the_king89/rip-holehe-why-user-scanner-is-the-new-king-of-email-osint-2cff> |
| R6 | *Agentic and Generative AI for Open-Source Intelligence and Cyber Investigations: Taxonomy, Evaluation, Challenges, and Future Directions*, arXiv:2607.03233 (2026). <https://arxiv.org/html/2607.03233v1> |
| R7 | WebBreacher, *WhatsMyName* (CC BY-SA 4.0). <https://github.com/WebBreacher/WhatsMyName> |
| R8 | abuse.ch, *URLhaus* y *ThreatFox Community API*: Auth-Key obligatoria. <https://urlhaus.abuse.ch/api/> · <https://threatfox.abuse.ch/api/> |
| R9 | MISP Project, *misp-stix*: conversión MISP ↔ STIX 1.x/2.x. <https://github.com/MISP/misp-stix> |
| R10 | OpenSanctions, *Free and non-commercial use*. <https://www.opensanctions.org/docs/commercial/exemption/> |
| R11 | LibreBOR, información mercantil del BORME. <https://librebor.me/> |
| R12 | *OSINT Tools by Investigation Task* (precios verificados el 10-10-2026). <https://osint-s.com/osint-tools/> |
| R13 | CEPD, *Directrices 1/2024 sobre el tratamiento basado en el artículo 6.1.f) del RGPD*. <https://www.edpb.europa.eu/system/files/2024-10/edpb_guidelines_202401_legitimateinterest_en.pdf> |
| R14 | Cyware, *Best Threat Intelligence Feeds in 2026*. <https://www.cyware.com/blog/best-threat-intelligence-feeds> |
| R15 | IANA, *RDAP Bootstrap for DNS* (`dns.json`), publicado el 28-10-2026 y consultado el mismo día: 1.203 TLD; sin servidor RDAP `es`, `io`, `de`, `mx`, `it`, `co`, `me`, `cl`, `pt`, `ru`, `cn`; con él `com`, `fr`, `uk`, `ar`, `br`. <https://data.iana.org/rdap/dns.json> |
| R16 | Shodan, *Deep Dive: http.favicon* (hash MurmurHash3 y filtro `http.favicon.hash`). <http://blog.shodan.io/deep-dive-http-favicon/> |
| R17 | FIRST, *EPSS: Get the Data* (API de consulta y CSV diario) y CISA, *Known Exploited Vulnerabilities Catalog*. <https://www.first.org/epss/data> · <https://www.cisa.gov/known-exploited-vulnerabilities-catalog> |
| R18 | Hudson Rock, *Free API Key* (consulta por email, username, IP o familia de stealer). <https://www.hudsonrock.com/free-api-key> |
| R19 | Microsoft, *Bing Search API retirement* (11-08-2025); Google, *Custom Search JSON API* (solo clientes existentes; discontinuación el 1-1-2027, dato de segunda mano); Brave, *Search API*. <https://learn.microsoft.com/en-us/lifecycle/announcements/bing-search-api-retirement> · <https://developers.google.com/custom-search/v1/overview> · <https://brave.com/search/api/> |
| R20 | enthec, *webappanalyzer*: continuación de Wappalyzer bajo GPL-3.0. <https://github.com/enthec/webappanalyzer> |
| R21 | elceef, *dnstwist*: motor de permutación de dominios para detectar typosquatting y suplantación. <https://github.com/elceef/dnstwist> |
| R22 | Mastodon, *accounts API methods* (`GET /api/v1/accounts/lookup`). <https://docs.joinmastodon.org/methods/accounts/> |

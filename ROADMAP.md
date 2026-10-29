# Roadmap de OSINEITOR

> **Estado:** vigente · **Versión actual:** 0.1.0 · **Última revisión:** 28 de octubre de 2026
>
> Este documento define la dirección del proyecto después del MVP: qué se construirá, en qué
> orden, por qué y cómo se sabrá que cada fase está terminada. No compromete fechas: el orden
> y los criterios de aceptación sí son vinculantes.

## Índice

1. [Visión y posicionamiento](#1-visión-y-posicionamiento)
2. [Conclusiones de la investigación](#2-conclusiones-de-la-investigación)
3. [Punto de partida (v0.1.0)](#3-punto-de-partida-v010)
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

**Consecuencia:** la [fase 1](#fase-1--fiabilidad-y-observabilidad-v020) (fiabilidad) va
antes que cualquier fuente nueva.

### 2.2 El acceso a los datos se está cerrando

- X envió requerimientos legales a Nitter en agosto de 2026; las instancias cayeron [R1].
- Reddit restringió Pushshift en 2023 y no ofrece acceso comercial de autoservicio [R1].
- abuse.ch (URLhaus, ThreatFox) exige ahora `Auth-Key` incluso para la API comunitaria [R8].
- Maltego y Censys miden el acceso en créditos; Shodan limita a 1 petición/s en todos sus planes [R1].

**Consecuencia:** priorizar fuentes con API oficial y términos estables; tratar cada
integración como perecedera (salud monitorizada, desactivación limpia) y respetar cuotas por
diseño. No se integrará scraping de redes sociales ([sección 8](#8-fuera-de-alcance)).

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

**Consecuencia:** la IA llega tarde ([fase 8](#fase-8--asistencia-con-ia-v090)), es opcional
y desactivada por defecto, y solo puede afirmar lo que esté respaldado por entidades guardadas,
con cita verificada automáticamente.

### 2.5 Interoperabilidad y grafo

Las herramientas de referencia exportan a formatos de análisis: Maigret a grafo HTML, Neo4j,
PDF y XMind [R4]; el ecosistema de inteligencia de amenazas se basa en STIX 2.1 y MISP, con
librerías Python maduras (`stix2`, `misp-stix`) [R9]. Amass mantiene un modelo de grafo de
activos [R1].

**Consecuencia:** las fases 5 y 6 convierten los scans en un grafo navegable y exportable.

### 2.6 Coberturas con mejor relación valor/coste

| Área | Fuentes gratuitas o con plan gratuito y API oficial |
|---|---|
| Inteligencia de amenazas | AlienVault OTX, abuse.ch (con Auth-Key), urlscan.io, VirusTotal (cuota baja), DNSBL de Spamhaus [R14] |
| Red y ASN | RIPEstat, PTR inverso, Team Cymru |
| Usernames | WhatsMyName (CC BY-SA 4.0), complementario a Sherlock [R7] |
| Empresas y sanciones | OpenSanctions (gratis para uso no comercial) [R10], GLEIF (LEI), LibreBOR / BORME (España) [R11], OpenCorporates (API desde 2.250 £/año) [R12] |
| Teléfono | `phonenumbers` (offline: país, tipo de línea, operador original) |
| Cripto | Exploradores públicos (mempool.space, Blockchair, Etherscan) |
| Imágenes y ficheros | Metadatos EXIF/XMP en local (sin subir el fichero a terceros) |

---

## 3. Punto de partida (v0.1.0)

**Disponible:** núcleo con pivoteo por niveles, 16 módulos (10 sin key, 6 con key), SQLite,
informes JSON/Markdown/HTML, 41 tests sin red y CI en Python 3.11 y 3.13.

**Deuda conocida que condiciona el roadmap:**

| ID | Deuda | Impacto | Se resuelve en |
|---|---|---|---|
| D1 | La mayoría de módulos solo se ha probado con respuestas simuladas | Posibles fallos en uso real | Fase 0 |
| D2 | Un módulo sin resultados es indistinguible de un módulo roto | Falsos negativos silenciosos | Fase 1 |
| D3 | La base de datos no tiene sistema de migraciones | Cualquier cambio de esquema rompe datos existentes | Fase 1 |
| D4 | Las entidades solo guardan la primera fuente que las produjo | No hay corroboración medible | Fase 2 |
| D5 | Sin caché ni límites de cuota por fuente | Consumo innecesario de cuotas y bloqueos | Fase 1 |
| D6 | La CLI no tiene tests | Regresiones en la interfaz | Fase 1 |
| D7 | La detección de usernames tiene falsos positivos (WAF, captchas) | Conclusiones erróneas | Fases 1 y 3 |

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

---

## 5. Resumen de fases

| Fase | Versión | Objetivo | Esfuerzo | Depende de |
|---|---|---|---|---|
| [0](#fase-0--validación-en-campo-v011) | 0.1.1 | Validar el MVP contra servicios reales | S | — |
| [1](#fase-1--fiabilidad-y-observabilidad-v020) | 0.2.0 | Salud de fuentes, caché, cuotas, migraciones | M | 0 |
| [2](#fase-2--procedencia-y-confianza-v030) | 0.3.0 | Procedencia, evidencia y confianza por dato | M | 1 |
| [3](#fase-3--ampliación-de-fuentes-en-frentes-actuales-v040) | 0.4.0 | Más fuentes en dominio, IP, email y username | L | 2 |
| [4](#fase-4--nuevos-frentes-v050) | 0.5.0 | Empresas, teléfono, cripto, ficheros | L | 2 |
| [5](#fase-5--análisis-grafo-y-casos-v060) | 0.6.0 | Grafo, línea temporal, comparación de scans, casos | L | 2 |
| [6](#fase-6--interoperabilidad-y-extensibilidad-v070) | 0.7.0 | STIX, MISP, Gephi, librería y plugins externos | M | 5 |
| [7](#fase-7--monitorización-continua-v080) | 0.8.0 | Vigilancia periódica y alertas de cambios | M | 5 |
| [8](#fase-8--asistencia-con-ia-v090) | 0.9.0 | Resúmenes con IA verificables y servidor MCP | M | 2, 5 |
| [9](#fase-9--producto-v10-v100) | 1.0.0 | Interfaz web local, distribución, API estable | L | 6 |

Esfuerzo: **S** ≈ 1 semana, **M** ≈ 2–4 semanas, **L** ≈ 1–2 meses de dedicación parcial de
una persona. Las fases 3, 4 y 5 son independientes entre sí y pueden reordenarse.

```
0 ──► 1 ──► 2 ──┬──► 3
                ├──► 4
                └──► 5 ──┬──► 6 ──► 9
                         ├──► 7
                         └──► 8
```

---

## 6. Fases en detalle

Cada entregable tiene un identificador (`F<fase>.<n>`) para enlazarlo desde issues y PRs.

### Fase 0 · Validación en campo (v0.1.1)

**Objetivo:** confirmar que lo que ya existe funciona contra los servicios reales.

| ID | Entregable | Detalle |
|---|---|---|
| F0.1 | Prueba real de cada módulo | Ejecutar cada módulo contra objetivos propios o públicos de prueba (p. ej. `example.com`, `8.8.8.8`) y documentar el resultado |
| F0.2 | Fixtures grabadas | Guardar respuestas reales anonimizadas en `tests/fixtures/` y usarlas en los tests en lugar de respuestas inventadas |
| F0.3 | Corrección de discrepancias | Ajustar el parseo donde el formato real difiera del documentado |
| F0.4 | Tests de la CLI | Cubrir todos los comandos con `typer.testing.CliRunner` |

**Criterios de aceptación**
- Los 16 módulos tienen al menos una ejecución real documentada en el PR.
- Todos los tests de módulo usan fixtures grabadas de respuestas reales.
- Cobertura de la CLI ≥ 80 %.

---

### Fase 1 · Fiabilidad y observabilidad (v0.2.0)

**Objetivo:** que el usuario sepa en todo momento qué fuentes funcionan y por qué un
resultado está vacío.

| ID | Entregable | Detalle |
|---|---|---|
| F1.1 | Estado por módulo en cada scan | Cada ejecución registra `ok`, `vacío`, `error`, `omitido` o `cuota agotada`, con duración y número de peticiones |
| F1.2 | `osineitor doctor` | Comprueba cada módulo contra un **canario** de resultado conocido y muestra una tabla de salud. Para usernames se usa el campo `username_claimed` que ya incluyen las 481 firmas de Sherlock |
| F1.3 | Health check programado en CI | Workflow semanal (no bloqueante) que ejecuta `doctor` y abre un issue si una fuente falla |
| F1.4 | Migraciones de esquema | Versionado con `PRAGMA user_version` y migraciones incrementales con tests; requisito previo para la fase 2 |
| F1.5 | Caché HTTP | Caché en disco con TTL por fuente (`--no-cache`, `--refresh`) para no repetir consultas ni gastar cuota |
| F1.6 | Límites declarativos por fuente | Cada módulo declara su límite (p. ej. Shodan 1 petición/s) y el cliente HTTP lo respeta |
| F1.7 | Timeout por módulo y cancelación | Ningún módulo puede bloquear el scan más de su tiempo máximo |
| F1.8 | Proxy y Tor | `--proxy socks5://…` aplicado a todas las peticiones salientes |
| F1.9 | Registro estructurado | `--verbose` y `--log-file` en JSON, sin incluir nunca API keys |
| F1.10 | Reducción de falsos positivos en usernames | Comprobación doble con un username inexistente aleatorio: si el sitio también "lo encuentra", el resultado se descarta |

**Criterios de aceptación**
- `osineitor doctor` informa del estado de los 16 módulos en menos de 2 minutos.
- La salida de un scan distingue visualmente "sin resultados" de "fuente con errores".
- Una base de datos v0.1.0 se migra sin pérdida (test automatizado).
- Repetir el mismo scan en menos de una hora no hace peticiones de red con la caché activa.
- La tasa de falsos positivos de `username_sites` con usernames aleatorios baja al menos un
  50 % respecto a v0.1.0 (medido con el script de evaluación de la fase).

---

### Fase 2 · Procedencia y confianza (v0.3.0)

**Objetivo:** que cada dato sea rastreable y defendible, siguiendo los principios de
preservación del Protocolo de Berkeley.

| ID | Entregable | Detalle |
|---|---|---|
| F2.1 | Observaciones múltiples | Una entidad guarda todas las fuentes que la vieron (`observations`: módulo, fecha, consulta realizada) en lugar de solo la primera |
| F2.2 | Evidencia con hash | Opción `--evidence` que guarda la respuesta original de cada fuente con su SHA-256, URL consultada y fecha UTC |
| F2.3 | Puntuación de confianza | Nivel `bajo/medio/alto` según número de fuentes independientes, tipo de fuente (autoritativa como DNS o RDAP frente a agregada) y antigüedad del dato |
| F2.4 | Frescura | Campos `first_seen` y `last_seen` por entidad; los datos de terceros conservan su propia fecha (p. ej. último escaneo de Shodan) |
| F2.5 | Alcance declarado | Fichero de alcance (`--scope scope.yml`) con dominios, rangos y exclusiones; el engine no pivota fuera de él (modelo inspirado en BBOT [R2]) |
| F2.6 | Propósito del scan | Campo `--purpose` registrado en los metadatos; obligatorio en scans sobre emails o usernames si así se configura |
| F2.7 | Informe con anexo de evidencias | El informe HTML incluye una tabla de evidencias con hashes verificables |

**Criterios de aceptación**
- Cualquier entidad de un informe se puede rastrear hasta la consulta exacta que la produjo.
- `osineitor verify <scan>` recalcula los hashes de las evidencias y detecta manipulaciones.
- Un scan con alcance definido no produce entidades fuera de él (test con dominios trampa).

---

### Fase 3 · Ampliación de fuentes en frentes actuales (v0.4.0)

**Objetivo:** cubrir los huecos de mayor valor en los cuatro frentes existentes, priorizando
fuentes gratuitas con API oficial.

**Dominio e infraestructura**

| ID | Módulo | Fuente | Key | Tipo |
|---|---|---|---|---|
| F3.1 | `urlscan` | urlscan.io: escaneos históricos, tecnologías, IPs | Opcional | Pasivo |
| F3.2 | `otx` | AlienVault OTX: pulses, DNS pasivo, malware asociado | Sí (gratis) | Pasivo |
| F3.3 | `virustotal` | VirusTotal: reputación, subdominios, resoluciones | Sí (gratis, cuota baja) | Pasivo |
| F3.4 | `mail_security` | MTA-STS, TLS-RPT, BIMI y selectores DKIM comunes | No | Pasivo (DNS) |
| F3.5 | `web_meta` | `robots.txt`, `sitemap.xml`, `security.txt` | No | **Activo** |
| F3.6 | `takeover` | Detección de subdominios con CNAME a servicios no reclamados | No | **Activo** |

**IP y red**

| ID | Módulo | Fuente | Key | Tipo |
|---|---|---|---|---|
| F3.7 | `ptr` | DNS inverso | No | Pasivo |
| F3.8 | `ripestat` | RIPEstat: ASN, prefijo, país de registro, historial de enrutamiento | No | Pasivo |
| F3.9 | `dnsbl` | Listas negras DNS (Spamhaus ZEN y otras de uso gratuito) | No | Pasivo |
| F3.10 | `abusech` | ThreatFox y URLhaus: IOCs asociados | Sí (gratis) | Pasivo |

**Email**

| ID | Módulo | Fuente | Key | Tipo |
|---|---|---|---|---|
| F3.11 | `leakcheck` | LeakCheck API pública: nombres de filtraciones | No | Pasivo |
| F3.12 | `github_email` | Búsqueda de commits públicos por email en la API de GitHub | Opcional | Pasivo |

**Usernames**

| ID | Entregable | Detalle |
|---|---|---|
| F3.13 | Segunda fuente de firmas | Integrar WhatsMyName (CC BY-SA 4.0, fichero de datos separado con atribución) y marcar como "confirmado" lo que detecten ambas fuentes |
| F3.14 | Extracción de perfil | Para los sitios principales, extraer nombre visible, biografía, enlaces y otros usernames de la página pública |
| F3.15 | Pivote recursivo de identificadores | Los usernames y enlaces extraídos en F3.14 alimentan el siguiente nivel de pivoteo |
| F3.16 | Filtros por categoría | `--tags dev,social,gaming` y `--top N` por popularidad |
| F3.17 | `github_user` | Perfil público de GitHub: nombre, empresa, blog, organizaciones, emails de commits públicos |

**Criterios de aceptación**
- Cada módulo nuevo cumple los requisitos de la fase 1 (canario en `doctor`, límite declarado)
  y de la fase 2 (procedencia).
- Los módulos activos solo se ejecutan con `--active` y respetando el fichero de alcance.
- La documentación de cada módulo indica sus términos de uso y su cuota.

---

### Fase 4 · Nuevos frentes (v0.5.0)

**Objetivo:** abrir los frentes que más demanda tienen en investigaciones profesionales, con
fuentes legales y documentadas.

**Organizaciones** (nuevo tipo de entidad `organization` y `person_name`)

| ID | Módulo | Fuente | Notas |
|---|---|---|---|
| F4.1 | `opensanctions` | Listas de sanciones y personas políticamente expuestas | Gratis para uso no comercial con key |
| F4.2 | `gleif` | Identificadores LEI y relaciones matriz–filial | API pública gratuita |
| F4.3 | `librebor` | Actos del BORME en España: constituciones, cargos, ceses | API de pago; módulo opcional |
| F4.4 | `opencorporates` | Registros mercantiles de más de 140 jurisdicciones | API de pago; acceso gratuito para periodismo e investigación previa solicitud |

**Teléfono** (nuevo tipo `phone`)

| ID | Módulo | Fuente | Notas |
|---|---|---|---|
| F4.5 | `phone_parse` | Librería `phonenumbers`, sin red | País, región, tipo de línea, operador de origen y formatos E.164 |

**Criptomonedas** (nuevo tipo `crypto_address`)

| ID | Módulo | Fuente | Notas |
|---|---|---|---|
| F4.6 | `crypto_detect` | Validación local de formato (BTC, ETH, LTC, XMR…) | Sin red |
| F4.7 | `btc_explorer` | mempool.space: saldo, número de transacciones, primera y última actividad | Gratis |
| F4.8 | `eth_explorer` | Etherscan: saldo, transacciones, etiquetas públicas | Key gratuita |

**Ficheros e imágenes** (nuevo tipo `file`)

| ID | Módulo | Fuente | Notas |
|---|---|---|---|
| F4.9 | `file_meta` | EXIF, XMP, IPTC y metadatos de documentos (PDF, Office) **en local** | Nunca se suben ficheros a terceros |
| F4.10 | `file_hash` | MD5, SHA-1, SHA-256 y pivote a reputación (VirusTotal, abuse.ch) | Solo el hash sale del equipo |
| F4.11 | `geo_point` | Coordenadas GPS como entidad `location`, con enlace a mapas | Sin red |

**Criterios de aceptación**
- `osineitor scan` detecta automáticamente teléfonos, direcciones cripto y rutas de fichero.
- Ningún módulo de ficheros transmite el contenido del fichero; un test lo verifica
  interceptando la red.
- Los módulos de organizaciones documentan la licencia de sus datos y su uso permitido.

---

### Fase 5 · Análisis, grafo y casos (v0.6.0)

**Objetivo:** pasar de una lista de resultados a una investigación navegable.

| ID | Entregable | Detalle |
|---|---|---|
| F5.1 | Grafo interactivo en el informe HTML | Nodos por entidad y aristas por relación de pivoteo, con filtros por tipo y fuente (librería JS local, sin CDN en el informe) |
| F5.2 | Casos | `osineitor case new|add|show`: agrupa varios scans de una misma investigación con notas y etiquetas |
| F5.3 | Comparación de scans | `osineitor diff A B`: entidades nuevas, desaparecidas y modificadas |
| F5.4 | Línea temporal | Ordena las fechas conocidas (registro de dominio, certificados, capturas de Wayback, filtraciones, primera actividad cripto) |
| F5.5 | Búsqueda global | `osineitor search <valor>`: en qué scans y casos aparece un dato |
| F5.6 | Correlación entre scans | Avisa cuando una entidad nueva ya apareció en otro caso (p. ej. misma IP o mismo email) |
| F5.7 | Informe ejecutivo | Plantilla de informe con resumen, hallazgos clave, nivel de confianza y anexos |

**Criterios de aceptación**
- El grafo de un scan de 500 entidades se abre y navega con fluidez en un navegador actual.
- `diff` entre dos scans del mismo objetivo identifica correctamente altas y bajas (tests).

---

### Fase 6 · Interoperabilidad y extensibilidad (v0.7.0)

**Objetivo:** que OSINEITOR encaje en flujos de trabajo existentes y que terceros puedan
ampliarlo sin modificar el código.

| ID | Entregable | Detalle |
|---|---|---|
| F6.1 | Exportación STIX 2.1 | Observables de infraestructura (dominios, IPs, URLs, emails, vulnerabilidades) con la librería `stix2` |
| F6.2 | Exportación a MISP | Evento MISP con atributos y objetos (`pymisp`) |
| F6.3 | Formatos de grafo | GraphML/GEXF (Gephi), script Cypher (Neo4j) y CSV de entidades y relaciones |
| F6.4 | Streaming NDJSON | `--ndjson` emite entidades en tiempo real para encadenar con otras herramientas |
| F6.5 | API de librería estable | `from osineitor import Scanner` con interfaz síncrona y asíncrona documentada |
| F6.6 | Plugins externos | Descubrimiento de módulos por *entry points* (`osineitor.modules`), de modo que un paquete de PyPI pueda añadir fuentes |
| F6.7 | Importación | Cargar listas de objetivos (`--targets-file`) y resultados de otras herramientas (Subfinder, Amass, Maigret JSON) como semillas |

**Criterios de aceptación**
- El STIX generado valida con el validador oficial de OASIS.
- Un plugin de ejemplo publicado en un repositorio aparte se instala con `pip` y aparece en
  `osineitor modules` sin tocar el código del proyecto.

---

### Fase 7 · Monitorización continua (v0.8.0)

**Objetivo:** vigilar activos propios y detectar cambios relevantes, el núcleo de la gestión
de la superficie de ataque externa.

| ID | Entregable | Detalle |
|---|---|---|
| F7.1 | `osineitor watch` | Define objetivos vigilados con frecuencia y módulos; se ejecuta desde cron, systemd o GitHub Actions |
| F7.2 | Reglas de alerta | Nuevo subdominio, nuevo puerto expuesto, nueva CVE, certificado próximo a caducar, dominio próximo a expirar, aparición en una filtración, IP en lista negra |
| F7.3 | Notificaciones | Webhook genérico (compatible con Slack, Discord y Teams), email SMTP y salida para sistemas de monitorización |
| F7.4 | Supresión de ruido | Umbrales, ventanas de silencio y confirmación en dos ejecuciones antes de alertar |
| F7.5 | Retención | Política de conservación configurable (`osineitor purge --older-than 90d`) |

**Criterios de aceptación**
- Un cambio simulado en las fixtures genera exactamente una alerta, y no se repite en la
  siguiente ejecución.
- Documentación de despliegue con cron y con GitHub Actions.

---

### Fase 8 · Asistencia con IA (v0.9.0)

**Objetivo:** acelerar el análisis sin sacrificar la verificabilidad.

| ID | Entregable | Detalle |
|---|---|---|
| F8.1 | `osineitor summarize <scan>` | Resumen en lenguaje natural generado **solo** a partir de las entidades guardadas |
| F8.2 | Citas obligatorias y verificadas | Cada afirmación del resumen referencia identificadores de entidad; un validador rechaza las frases sin cita o con citas inexistentes |
| F8.3 | Modelos locales y remotos | Soporte para modelos locales (Ollama) por privacidad, y APIs remotas como opción explícita; nunca se envían datos sin consentimiento en la configuración |
| F8.4 | Servidor MCP | Expone búsqueda, consulta de scans y lanzamiento de módulos pasivos a agentes de IA; los módulos activos quedan excluidos por defecto |
| F8.5 | Sugerencia de pivotes | Propone siguientes pasos; nunca los ejecuta sin confirmación del usuario |
| F8.6 | Evaluación | Conjunto de pruebas propio para medir la proporción de afirmaciones sin respaldo, publicada en la documentación |

**Criterios de aceptación**
- El 100 % de las afirmaciones del resumen tiene una cita válida, comprobado automáticamente.
- La funcionalidad está desactivada por defecto y no añade dependencias a la instalación base
  (extra opcional `osineitor[ai]`).
- La tasa de afirmaciones sin respaldo medida en F8.6 se publica junto a la versión.

---

### Fase 9 · Producto v1.0 (v1.0.0)

**Objetivo:** estabilidad, distribución y una interfaz para quien no usa la terminal.

| ID | Entregable | Detalle |
|---|---|---|
| F9.1 | Interfaz web local | FastAPI + frontend ligero: lanzar scans, ver el grafo, gestionar casos. Solo escucha en `localhost` por defecto |
| F9.2 | Publicación en PyPI | Con *trusted publishing* y firma de artefactos (Sigstore) |
| F9.3 | Imagen Docker | Imagen oficial mínima y sin privilegios |
| F9.4 | Sitio de documentación | MkDocs con guía de usuario, referencia de módulos generada desde el código y tutoriales |
| F9.5 | Internacionalización | Interfaz y documentación en español e inglés |
| F9.6 | Compromiso de estabilidad | SemVer estricto sobre CLI, formato de exportación y API de librería; política de obsolescencia de dos versiones menores |

**Criterios de aceptación**
- Instalación con `pip install osineitor` y `docker run` documentadas y probadas en CI.
- Guía de migración desde 0.x.

---

## 7. Líneas transversales

Se aplican en todas las fases, no se planifican aparte.

### Calidad

- Cobertura de tests ≥ 85 % en el núcleo y ≥ 70 % global; ningún test depende de la red.
- Tipado estático con `mypy` (estricto en el núcleo) desde la fase 1.
- Cada PR que añade un módulo incluye fixture real, canario de salud y documentación.

### Seguridad

- API keys en el llavero del sistema (`keyring`) como alternativa al fichero TOML (fase 1).
- Cifrado opcional de la base de datos (SQLCipher) para investigaciones con datos personales
  (fase 2).
- Informes HTML sin recursos externos y con escape de todo el contenido de terceros.
- Análisis de dependencias (Dependabot) y de secretos en CI.

### Legal y ética

- Toda fuente nueva documenta sus términos de uso y si permite el acceso automatizado.
- Registro del propósito y del alcance de cada scan (fase 2) como apoyo a la responsabilidad
  proactiva del RGPD.
- Plantilla de evaluación de interés legítimo en `docs/` (fase 2), basada en las directrices
  1/2024 del CEPD [R13].
- Revisión anual de [docs/USO_RESPONSABLE.md](docs/USO_RESPONSABLE.md).

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
| Comprobar si un email está registrado mediante flujos de recuperación de contraseña (estilo holehe) | Abusa de funcionalidades no destinadas a ello, rompe con frecuencia [R5] y puede alertar al titular |
| Saltar captchas, WAF o autenticación | Acceso no autorizado |
| Usar o mostrar contraseñas de filtraciones | Facilita el acceso no autorizado a cuentas; solo se muestran nombres de filtración y tipos de dato |
| Reconocimiento facial | Datos biométricos (categoría especial del RGPD) y alto riesgo de abuso |
| Fuerza bruta de subdominios, escaneo de puertos propio o explotación | Herramientas especializadas (Amass, Nmap, Nuclei) lo hacen mejor; OSINEITOR puede importar sus resultados (F6.7) |
| Buscadores de personas que agregan datos personales (p. ej. por DNI) | Incompatible con el RGPD en la mayoría de usos |
| Monitorización de la dark web | Requiere infraestructura y riesgos legales desproporcionados para el proyecto |

---

## 9. Riesgos

| Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|
| Una fuente cambia o cierra su API | Alta | Medio | Salud monitorizada (F1.2, F1.3), módulos aislados y desactivables |
| Cuotas gratuitas insuficientes | Alta | Medio | Caché (F1.5), límites declarativos (F1.6), alternativas gratuitas por frente |
| Uso indebido de la herramienta para acoso | Media | Alto | Fuera de alcance explícito, registro de propósito, sin agregación de datos personales sensibles |
| Falsos positivos que llevan a conclusiones erróneas | Alta | Alto | Doble comprobación (F1.10), corroboración y confianza (F2.3), avisos en informes |
| Alcance excesivo para un proyecto de una persona | Alta | Alto | Fases publicables por separado; fases 3–9 reordenables; se prioriza calidad sobre número de fuentes |
| Licencias de datos incompatibles | Baja | Medio | Ficheros de datos de terceros separados y con atribución (Sherlock MIT, WhatsMyName CC BY-SA) |
| Alucinaciones de la IA presentadas como hechos | Media | Alto | IA opcional, citas verificadas (F8.2), evaluación publicada (F8.6) |

---

## 10. Gobernanza del roadmap

- **Revisión:** al cerrar cada fase y, como mínimo, cada tres meses.
- **Cambios:** mediante PR que modifique este documento, explicando qué cambia y por qué.
- **Seguimiento:** cada entregable se convierte en un issue con la etiqueta `roadmap` y su
  identificador (`F3.2`) en el título; cada fase, en un *milestone* de GitHub.
- **Versionado:** las fases 0–8 publican versiones 0.x; la API se considera estable desde 1.0.0.
- **Propuestas:** las ideas nuevas entran por la plantilla de issue
  [`Nueva fuente`](.github/ISSUE_TEMPLATE/new_source.md) o
  [`Mejora`](.github/ISSUE_TEMPLATE/feature_request.md).

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

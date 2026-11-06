# Guía de uso

Referencia de las órdenes y del comportamiento de OSINEITOR. Para instalar y probar rápido, mira
el [README](https://github.com/jmstudio14/OSINEITOR/blob/main/README.md). Los ejemplos usan `example.com` y `1.1.1.1`: dominio e IP reservados
para documentación.

## Índice

- [Órdenes](#órdenes)
- [Qué se investiga y cómo se pivota](#qué-se-investiga-y-cómo-se-pivota)
- [Opciones de los scans](#opciones-de-los-scans)
- [Presets](#presets)
- [Filtros de salida](#filtros-de-salida)
- [Datasets](#datasets)
- [Estado de cada módulo](#estado-de-cada-módulo)
- [Presupuesto](#presupuesto)
- [Caché](#caché)
- [Doctor](#doctor)
- [Red y entradas](#red-y-entradas)
- [Informes e historial](#informes-e-historial)
- [Vigilancia](#vigilancia)
- [Resúmenes con IA](#resúmenes-con-ia)
- [API keys y rutas](#api-keys-y-rutas)
- [Uso desde otros programas](#uso-desde-otros-programas)

## Órdenes

```bash
osineitor scan example.com            # detecta el tipo de la entrada y pivota (profundidad 2)
osineitor domain example.com          # solo el dominio (profundidad 1)
osineitor ip 1.1.1.1
osineitor email alguien@example.com --depth 2
osineitor username johndoe
osineitor person "Ana García López" --domain example.com   # variantes de usuario y emails candidatos
osineitor scan https://example.com/login   # una URL: se investiga su host
osineitor scan 1.1.1.0/24                  # red CIDR (el tipo se reconoce; ningún módulo la consume aún)
osineitor scan AS13335                     # sistema autónomo (asn_netblock lista sus prefijos)
osineitor domain example.com --preset quick   # con un preset (ver Presets)

osineitor history --limit 50          # scans guardados (20 por defecto)
osineitor show 3                      # volver a ver el scan 3
osineitor export 3 -f html            # informe en reports/ (json | md | html | csv | graphml | gexf | cypher)
osineitor export 3 -f md -o informe.md  # en el fichero indicado
osineitor diff 3 7                    # qué cambió entre dos scans (--json para máquinas)
osineitor verify 3                    # comprueba las evidencias del scan 3 (ver Evidencia)
osineitor import nmap scan.xml        # guarda como scan un XML de Nmap (-oX); no ejecuta Nmap

osineitor modules                     # módulos disponibles y estado de sus API keys
osineitor presets                     # perfiles de escaneo disponibles
osineitor update-data                 # descarga los datasets de terceros (ver Datasets)
osineitor doctor                      # prueba cada módulo contra su fuente real
osineitor doctor -m dns --json        # solo esos módulos (-m, repetible); --active y --allow-private como en los scans
osineitor cache info                  # respuestas cacheadas (cache clear las borra)
osineitor summarize 3                 # resumen con IA del scan 3 (desactivado hasta crear ai.yml)
osineitor watch run                   # vigilancia: ejecuta lo que toca y avisa de lo nuevo (ver Vigilancia)
osineitor purge --older-than 90d      # borra scans antiguos (--dry-run solo cuenta)
osineitor config show                 # keys configuradas (se ven solo los 4 primeros caracteres)
osineitor version
```

`scan` deduce el tipo de la entrada. Una cadena como `john.doe` es ambigua (parece un dominio);
en ese caso usa la orden explícita: `osineitor username john.doe`. Lo mismo con un username que
empiece por `AS` y números (`AS1234`), que `scan` toma por un ASN.

`scan` reconoce IP, red CIDR, ASN, URL, email, teléfono (con prefijo `+` o `00`), dirección de
criptomoneda (Bitcoin, Ethereum, Litecoin, Dogecoin y Monero), coordenadas (`40.4168,-3.7038`),
ruta de un fichero local, dominio y username. La ruta debe contener `/` o `\` y existir: un
`foto.jpg` suelto en la carpeta actual se tomaría por un dominio, así que escribe `./foto.jpg`.
Los ficheros se leen **en local**: ni su contenido ni su ruta salen del equipo. De una URL se investiga su host
(dominio o IP); un ASN se acepta como objetivo (`asn_netblock` saca sus prefijos) y una red CIDR
también, pero ningún módulo consume aún una red, así que ese resultado queda vacío.

## Qué se investiga y cómo se pivota

Cada módulo declara qué tipos de entidad consume y cuáles produce. El motor ejecuta, en paralelo,
los módulos que aceptan la entidad inicial y las entidades nuevas pasan al siguiente nivel:

```
email alguien@example.com
├─ email_validate ─► domain example.com ─► dns ─► ip 203.0.113.10
│                 └► username alguien ─► username_sites ─► profile https://…
└─ gravatar ─► profile https://gravatar.com/…
```

### Personas

`osineitor person "Ana García López" [--domain example.com]` parte de un nombre y **solo genera
candidatos**: variantes de username (`ana.garcia`, `agarcia`, `anagarcia`…, hasta 12) y, con
`--domain`, direcciones de email sobre ese dominio. Ninguna se verifica por SMTP ni se consulta
nada para crearlas; los candidatos pasan a los módulos de username y de email como cualquier otra
entidad, así que sus resultados son hipótesis que hay que contrastar. Como el email y el username,
exige `--purpose` si `require_purpose` está activo.

`--depth` controla cuántos niveles se pivota (1 a 4). Con `1` solo se analiza el objetivo; con `2`
también las entidades descubiertas (p. ej. las IPs a las que resuelve un dominio). Cada nivel
multiplica las peticiones: úsalo con criterio. Una entidad ya vista no se vuelve a investigar y los
datos de varias fuentes sobre la misma entidad se fusionan; si discrepan, gana el módulo que va
antes en el orden alfabético. La columna «Fuente» lista todos los módulos que vieron cada entidad;
`--json` y `show --json` añaden en `observations` quién la vio, sobre qué entidad y cuándo, y
`first_seen`/`last_seen` con la primera y la última vez; los informes muestran la última en «Visto».
Las fechas de los terceros (p. ej. `last_update` de Shodan) siguen en los detalles de cada entidad.

La columna «Confianza» (`bajo`, `medio`, `alto`) resume cuánto respalda el dato lo visto: sube con el
número de fuentes distintas y si una es autoritativa (`dns`, `rdap`, `http_fingerprint`,
`email_validate`) y baja un nivel si el dato tiene más de 90 días según el tercero. Sirve para
decidir qué revisar primero, no demuestra que el dato sea cierto.

## Evidencia

Con `--evidence` cada respuesta de las fuentes se guarda tal cual con su **SHA-256**, la URL
consultada (sin API keys), la fecha UTC y el módulo y la entidad que la provocaron. Las consultas DNS
(`dns`, `email_validate`) también constan, incluidas las respuestas negativas (`NXDOMAIN`,
`NOANSWER`). Así un dato del informe se puede rastrear hasta la consulta exacta y comprobar después.
Con `--evidence` no se usa la caché (una copia vieja no es una captura con fecha) y el scan hace más
peticiones; con `--no-save` las evidencias no se guardan.

```bash
osineitor domain example.com --evidence        # al final imprime la huella de evidencias
osineitor verify 3                             # recalcula los hashes: sale con 5 si algo no coincide
osineitor verify 3 --digest HUELLA             # además compara con la huella que anotaste
```

La huella de evidencias resume todas las respuestas. **Anótala fuera de la base de datos**: quien
pueda reescribir a la vez un cuerpo y su hash en la base no se detectaría solo con `verify`, pero sí
con una huella guardada aparte. Los informes HTML y Markdown de un scan con `--evidence` acaban con un
anexo de evidencias (módulo, URL, fecha, estado, tamaño y SHA-256 de cada respuesta, más la huella del
conjunto). Detalles y límites en [EVIDENCIA.md](EVIDENCIA.md).

## Alcance

`--scope scope.yml` (o `OSINEITOR_SCOPE`) limita el scan a lo que tienes autorizado investigar:

```yaml
domains: [example.com]              # el dominio y sus subdominios
ips: [203.0.113.0/24, 198.51.100.7] # IPs sueltas o redes CIDR
exclude: [admin.example.com, 203.0.113.9]
```

Lo que cae fuera no entra en el resultado, no se investiga más y no sale por `--ndjson`; en
`events` consta una línea «fuera de alcance: …» por cada entidad descartada. Un dominio cuenta si es
igual o subdominio de uno declarado (`example.com.evil.test` y `notexample.com` quedan fuera). En
emails se mira el dominio, en URLs el host y en servicios (`IP:puerto`) la IP. `exclude` gana siempre.
Una lista que no declaras no restringe ese tipo: con solo `domains`, las IPs a las que resuelven
siguen entrando; declara `ips` para limitarlas. Hace falta `domains` o `ips`. Un fichero inválido o
un objetivo fuera del alcance es un error de uso (código 2). El alcance queda guardado con el scan y
aparece en `show`, en los informes y en `scan.start`.

El alcance filtra lo que se **descubre**; no controla a dónde redirige un servidor una petición.

```bash
osineitor domain example.com --depth 2 --scope scope.yml
```

## Propósito

`--purpose "TEXTO"` (o `OSINEITOR_PURPOSE`) anota para qué haces el scan: hasta 500 caracteres, sin
saltos de línea. Queda guardado con el scan y aparece en `show`, en los informes y en `scan.start`.

```bash
osineitor email ana@example.com --purpose "Auditoría autorizada de Acme, ticket 42"
```

Para obligarte a indicarlo en los scans sobre personas, activa `require_purpose` en la sección
`[settings]` de `config.toml` (`osineitor config show` muestra la ruta) o define
`OSINEITOR_REQUIRE_PURPOSE=1` (la variable manda sobre el fichero; `0` lo desactiva):

```toml
[settings]
require_purpose = true
```

Con eso, `email`, `username`, `person`, los teléfonos y los `scan` que resulten de uno de ellos sin `--purpose` terminan con
código 2 antes de consultar nada. Los de dominio e IP no se ven afectados. La aplicación de
escritorio aún no pasa `--purpose`: con `require_purpose` activo sus scans de email y username
fallarán.

## Opciones de los scans

Valen para `scan`, `domain`, `ip`, `email`, `username` y `person`.

| Opción | Efecto |
|---|---|
| `--depth`, `-d` | Niveles de pivoteo (1–4) |
| `--module`, `-m` | Ejecuta solo estos módulos (repetible) |
| `--active` | Permite módulos que contactan al objetivo |
| `--max-entities`, `--max-requests`, `--max-time` | [Presupuesto](#presupuesto) (`0` = sin límite) |
| `--no-cache`, `--refresh` | [Caché](#caché) |
| `--allow-private` | Permite conectar con redes privadas (ver [Red y entradas](#red-y-entradas)) |
| `--proxy` | Envía todo el tráfico por un proxy (ver [Proxy y Tor](#proxy-y-tor)); también `OSINEITOR_PROXY` |
| `--evidence` | Guarda la respuesta original de cada fuente con su SHA-256 (ver [Evidencia](#evidencia)) |
| `--scope` | Limita el scan a los dominios y redes de un YAML (ver [Alcance](#alcance)); también `OSINEITOR_SCOPE` |
| `--purpose` | Anota para qué haces el scan; se puede exigir en emails y usernames (ver [Propósito](#propósito)); también `OSINEITOR_PURPOSE` |
| `--preset` | Aplica un perfil de escaneo (ver [Presets](#presets)) |
| `--only-types`, `--exclude` | Recortan los tipos de entidad que se muestran (ver [Filtros de salida](#filtros-de-salida)) |
| `--no-save` | No guarda el scan en el historial |
| `--db` | Ruta de la base de datos SQLite |
| `--json` / `--ndjson` | Salida para otros programas (ver más abajo) |
| `--quiet`, `-q` | Sin salida legible |
| `--control-stdin` | Permite cancelar escribiendo en stdin |

`--no-color`, `--verbose`/`-v` y `--log-file` son globales y van antes de la orden:
`osineitor --no-color scan example.com`.

## Registro

`--verbose` escribe en `stderr` un registro JSON (una línea por registro) con cada petición HTTP
(método, host y ruta, estado, duración, reintentos), cada módulo (estado, duración, peticiones) y
el inicio y fin del scan. `--log-file RUTA` guarda lo mismo en un fichero (añade al final). Se pueden
usar a la vez; con `--verbose` no se dibuja la barra de progreso.

```bash
osineitor --log-file=osineitor.jsonl domain example.com
```

**API keys:** el registro no incluye ni la consulta de las URLs ni cabeceras ni cuerpos, y además
sustituye por `***` cualquier key configurada, también si aparece dentro de un mensaje de error.
**Sí contiene** los objetivos y los hosts que se consultan, así que trata el fichero como parte de la
investigación. No se rota ni se restringen sus permisos.

## Presets

Un preset fija de una vez los módulos, la profundidad y el presupuesto de un tipo de scan.
`osineitor presets` los lista.

| Preset | Qué hace |
|---|---|
| `passive` | Todos los módulos pasivos, 2 niveles |
| `quick` | DNS, RDAP y datos de IP y email, 1 nivel, tope de 100 peticiones y 60 s |
| `domain-recon` | `crtsh`, `dns`, `rdap` y `wayback`, 2 niveles |
| `attack-surface` | Dominio e IP con `http_fingerprint` y los de IP, 3 niveles; admite `--active` |
| `person` | Email y username: perfiles, repositorios públicos y filtraciones, 2 niveles |
| `email-audit` | Email y su dominio de correo (MX, SPF, DMARC), 2 niveles |
| `full` | Todos los módulos, 3 niveles; admite `--active` |

```bash
osineitor domain example.com --preset domain-recon
osineitor domain example.com --preset domain-recon --depth 3   # lo que escribes manda sobre el preset
```

- **Lo que indiques tú manda** sobre el preset (`--depth`, `-m`, `--max-*`).
- **Un preset nunca activa los módulos activos.** `attack-surface` y `full` los *admiten*, pero
  sigue haciendo falta `--active`; con un preset que no los admite, `--active` es un error de uso.
- **Los tuyos** van en `presets/<nombre>.yml` dentro de tu directorio de configuración
  (`%APPDATA%\osineitor` en Windows). Uno con el nombre de un preset incluido lo sustituye. Un
  fichero erróneo no se ignora: `osineitor presets` lo señala (código 2) y `--preset` con ese
  nombre falla.

```yaml
description: Mi reconocimiento
depth: 2                    # 1 a 4
modules: [crtsh, dns, rdap] # sin esta clave, todos
allow_active: false         # true admite los módulos activos (sigue haciendo falta --active)
max_entities: 500           # presupuesto; 0 = sin límite
max_requests: 300
max_time: 120
```

## Filtros de salida

`--only-types` y `--exclude` recortan qué tipos de entidad se muestran. Valen en los scans, en
`show` y en `export`; se repiten o se separan con comas:

```bash
osineitor domain example.com --only-types domain,ip
osineitor show 3 --exclude record
osineitor export 3 -f md --exclude service,vulnerability
```

Solo afectan a lo que se imprime o exporta: el scan se guarda entero, las evidencias no se filtran,
el stream `--ndjson` emite todas las entidades y el código de salida no cambia. Con los dos,
`--exclude` gana.

## Datasets

`osineitor update-data` descarga los datasets de terceros a la carpeta `datasets/` de tu directorio
de datos y anota en `manifest.json` la versión, el SHA-256 y la licencia de cada uno. Hoy solo
hay uno, `sherlock-sites` (las firmas de `username_sites`, licencia MIT): si lo actualizas, el módulo
usa tu copia en lugar de la del paquete, siempre que su hash coincida con el registrado.
Las firmas de WhatsMyName (`username_wmn`, CC BY-SA 4.0) vienen solo en el paquete: esa licencia
no es compatible con el catálogo de `update-data`.

```bash
osineitor update-data
osineitor update-data sherlock-sites --json
```

Solo se instalan datasets con licencia compatible con MIT; los demás se rechazan sin descargarlos
(código de salida `3`). Si una descarga no es válida se conserva la copia anterior.

## Estado de cada módulo

Tras cada scan se muestra una tabla con lo que pasó en cada módulo:

| Estado | Significado |
|---|---|
| `ok` | Respondió con datos |
| `empty` | Respondió, pero sin datos |
| `error` | Falló (respuesta inesperada, caída, tiempo agotado…) |
| `quota` | La fuente rechazó la petición por límite de uso (HTTP 429) |
| `skipped` | No aplica, falta la API key o es un módulo activo sin `--active` |

También se ven las entidades, las peticiones, los aciertos de caché y el tiempo. Así «sin
resultados» deja de confundirse con «la fuente falló». Cada módulo tiene un tiempo máximo por
ejecución (180 s por defecto): si lo supera se anota como error y el resto sigue.

## Presupuesto

Cada scan tiene topes para no dispararse: **2000 entidades, 3000 peticiones y 900 segundos**
(`--max-entities`, `--max-requests`, `--max-time`). Al agotarlos el scan se detiene de forma
ordenada, conserva lo ya encontrado y marca el resultado como **incompleto** (código de salida `4`).
Estos valores por defecto son estimaciones sin medir.

## Caché

Las respuestas GET de las fuentes **pasivas y sin API key** se guardan 6 horas en `cache.db` (en el
directorio de datos) para no repetir consultas ni gastar cuota. Nunca se cachean los módulos con API
key ni los activos, y la base solo guarda un hash de la petición, no la URL. `--refresh` fuerza la
consulta; `--no-cache` desactiva la caché; `osineitor cache clear` la vacía.

## Doctor

`osineitor doctor` lanza cada módulo con un valor de prueba conocido (`example.com`, `1.1.1.1` o
`test@example.com`) y muestra si responde. Los módulos sin valor de prueba seguro (como
`username_sites`, que haría ~460 peticiones) solo comprueban que su fuente es alcanzable. Sale con
código `3` si algún módulo falla. **No valida que los datos sean correctos**, solo que la fuente
contesta y se interpreta sin errores. Es la forma más rápida de ver qué fuentes funcionan desde tu
red.

## Red y entradas

**Red.** Por seguridad, ninguna petición se envía a IPs privadas, loopback ni al servicio de
metadatos de una nube (`169.254.169.254`), tampoco a través de redirecciones: un subdominio
publicado por un tercero podría apuntar ahí. `--allow-private` lo permite si investigas tu propia
red. Queda un riesgo residual de *DNS rebinding* documentado en [SECURITY.md](https://github.com/jmstudio14/OSINEITOR/blob/main/SECURITY.md).

**Entradas.** Los dominios se guardan en minúsculas y en punycode (`münchen.de` →
`xn--mnchen-3ya.de`), así que escrituras distintas del mismo dato son una sola entidad. Un
username admite letras, números, `.`, `_` y `-` (hasta 64); un valor no válido se rechaza antes de
lanzar nada (código de salida `2`).

## Proxy y Tor

`--proxy` (o la variable `OSINEITOR_PROXY`) envía las peticiones de los módulos por un proxy
`socks5://`, `socks5h://`, `http://` o `https://`. Para usar Tor, apunta a su puerto SOCKS:

```bash
osineitor domain example.com --proxy=socks5://127.0.0.1:9050
```

(`9050` es el demonio `tor`; el Navegador Tor usa `9150`.) Con proxy:

- **Los nombres los resuelve el proxy**, no tu equipo. Por eso la guardia de red deja de resolver
  los hostnames en local; las IP privadas, loopback y de metadatos escritas como IP siguen
  bloqueadas.
- **`dns` y `email_validate` se omiten** (`omitido: conexión directa`). Consultan DNS por UDP, que
  un proxy SOCKS no enruta, y harían llegar tus consultas a tu resolvedor local. Pierdes los
  registros DNS y el MX del email mientras uses proxy. Lo mismo vale para cualquier módulo que
  ejecute una herramienta externa.
- Si el proxy no responde, el módulo falla: **nunca se vuelve a conectar sin proxy**.
- Con credenciales en la URL (`socks5://usuario:clave@host:puerto`) mejor usa `OSINEITOR_PROXY`
  para que no queden en la línea de comandos; el registro nunca las incluye.

**Limitaciones.** El tráfico del propio programa (por ejemplo, actualizar el bootstrap RDAP) también va
por el proxy, pero **no se ha probado con una red Tor real**, solo con un servidor SOCKS5 de prueba. Muchos
sitios bloquean las salidas de Tor: los módulos de usernames darán errores o vacíos que sin proxy no
darían. `--proxy` no oculta lo que escribes en el scan a las fuentes consultadas, solo tu IP.

## Informes e historial

Cada scan se guarda en una base SQLite del directorio de datos (salvo con `--no-save`).
`osineitor history` los lista, `osineitor show N` muestra uno y `osineitor export N -f json|md|html`
genera un informe en `reports/`.

### Hallazgos

El analizador `findings` aplica al final de cada scan las reglas de
`src/osineitor/data/rules/default.yml` (DMARC y SPF débiles, certificados y dominios a punto de
caducar, CVE en KEV o con EPSS alto, CNAME colgante, IP en listas negras, servicios de
administración expuestos…) y deja un `finding` por cada coincidencia, con su severidad
(`info`, `low`, `medium`, `high`, `critical`), la entidad afectada, la evidencia y la
recomendación. Un hallazgo es una pista a revisar, no una conclusión: p. ej. un certificado
«caducado» puede ser uno antiguo ya sustituido. Se ven con `show`, `export`
(`-f csv-findings` los saca solos) y el resumen del informe los cuenta por severidad.

### Comparar scans

`osineitor diff A B` compara dos scans guardados por la clave de cada entidad: lista las
nuevas, las desaparecidas y las que cambiaron de datos (campo, antes y después), y aparte los
hallazgos. Avisa si los dos scans son de objetivos distintos.

### Importar un escaneo de Nmap

`osineitor import nmap scan.xml` guarda como un scan el XML que genera `nmap -oX`. OSINEITOR no
escanea puertos ni ejecuta Nmap: solo lee el fichero (hasta 32 MiB, sin `DOCTYPE` ni entidades).
Del XML salen, para cada host `up`, su `ip`, sus nombres de host (`domain`, con `hostname_type`) y
un `service` por cada puerto `open` (`<ip>:<puerto>`, la misma clave que `internetdb`, con
`transport`, `name`, `product`, `version`, `extrainfo`, `tunnel` y `cpe`). El objetivo del scan es un
`record` `nmap:<fichero>` con el SHA-256 del fichero, la versión de Nmap y el número de hosts
activos; todas las entidades llevan la fuente `import_nmap`. La línea de comandos de Nmap (`args`) no
se guarda porque puede llevar credenciales, y las direcciones MAC se ignoran. Lo que no es válido (IP,
nombre de host o puerto) se descarta y se avisa con un evento `skipped`.

El scan importado se ve con `show`, `export` y `diff` como cualquier otro, pero no pivota: ningún
módulo corre sobre él y no lleva confianza. `--no-save` no lo guarda, `--json` imprime el resultado
(el mismo esquema que `show`) y `--db` elige la base de datos. Úsalo solo con resultados de redes
propias o autorizadas.

### Formatos de exportación

| `-f` | Contenido | Fichero |
|---|---|---|
| `json`, `md`, `html` | Informe completo; el HTML lleva un grafo interactivo (sin librerías externas) | `.json`, `.md`, `.html` |
| `csv` | Una fila por entidad: tipo, valor, fuentes, confianza, primera vez, padre y datos | `.entities.csv` |
| `csv-relations` | Una fila por relación de pivoteo (padre → entidad) | `.relations.csv` |
| `csv-findings` | Una fila por hallazgo | `.findings.csv` |
| `graphml`, `gexf` | El grafo (nodos = entidades, aristas = pivoteo) para Gephi y otras herramientas | `.graphml`, `.gexf` |
| `cypher` | Script para `cypher-shell` de Neo4j: `MERGE` de nodos por clave y relaciones `DISCOVERED` | `.cypher` |

Los scripts Cypher no se han probado contra una instancia de Neo4j; GraphML y GEXF se validan
como XML bien formado, no contra Gephi.

En los CSV, un valor que empieza por `=`, `+`, `-` o `@` lleva una comilla delante para que la hoja
de cálculo no lo ejecute como fórmula.

## Vigilancia

`osineitor watch run` repite los scans que declara `watch.yml` y avisa solo de lo nuevo:
subdominios, IPs, servicios, CVE o filtraciones nuevos y hallazgos nuevos, por webhook
(Slack, Discord, Teams o genérico), correo SMTP o un fichero NDJSON. La primera ejecución fija la
línea base y no alerta. Sale con `10` si hay alertas y con `11` si alguna no se pudo entregar.
`watch check` valida el fichero, `watch list` muestra el estado y `purge --older-than 90d` aplica
la retención. Formato, reglas y despliegue con cron, systemd y GitHub Actions:
[VIGILANCIA.md](VIGILANCIA.md).

## Resúmenes con IA

`osineitor summarize <scan>` pide a un modelo un resumen de un scan guardado. Está desactivado
hasta que creas `ai.yml`; con Ollama en tu máquina los datos no salen, y con un proveedor remoto
(OpenAI compatible o Anthropic) hace falta `consent_remote: true`. Cada frase lleva citas
(`[E3]`) a las entidades del scan y solo se muestran las que un validador comprueba (sin cita, cita
inexistente o IP, CVE, correo u host que no figure en lo citado se descartan). Sale con `12` si el
modelo falla. Configuración, límites y evaluación: [IA.md](IA.md).

## API keys y rutas

```bash
osineitor config set shodan TU_KEY      # se guarda en el directorio de configuración
osineitor config show                   # solo muestra las keys enmascaradas
osineitor config unset shodan
export OSINEITOR_SHODAN_KEY=TU_KEY      # alternativa: variable de entorno (tiene prioridad)
```

Para que la key no aparezca en la línea de comandos (la ven otros procesos), pásala por stdin:
`echo TU_KEY | osineitor config set shodan --stdin`.

Nombres de key: `shodan`, `abuseipdb`, `greynoise`, `hibp`, `hunter`, `ipinfo`.

**Dónde se guarda todo** (`OSINEITOR_CONFIG_DIR` y `OSINEITOR_DATA_DIR` lo sobrescriben):

| | Windows | Linux |
|---|---|---|
| Configuración y keys | `%APPDATA%\osineitor\config.toml` | `~/.config/osineitor/config.toml` |
| Historial (SQLite) y cachés | `%LOCALAPPDATA%\osineitor\` | `~/.local/share/osineitor/` |
| Vigilancia (`watch.yml`) y IA (`ai.yml`), si los creas | `%APPDATA%\osineitor\` | `~/.config/osineitor/` |

El fichero de keys **no se cifra**: en Windows hereda los permisos de tu carpeta de usuario.

## Barra de progreso

En una terminal (con `stdout` y `stderr` sin redirigir) el scan muestra una barra en `stderr` con
los módulos completados, las entidades y las peticiones; desaparece al terminar. Con `--json`,
`--ndjson`, `--quiet` o cualquier redirección no se dibuja nada. Los programas que lanzan la CLI
reciben el mismo avance como eventos `progress` con `--ndjson`.

## Uso desde otros programas

`--ndjson` emite un evento JSON por línea (inicio, cada módulo, cada entidad, progreso, fin);
`--json` un único documento (también en `modules`, `presets`, `history`, `show`, `diff`, `verify`,
`export`, `summarize`, `watch run`, `watch list`, `purge`, `update-data`, `doctor`, `config show`,
`config set`, `config unset` y `version`); `--quiet` suprime la salida legible. `--control-stdin` permite cancelar
escribiendo `{"cmd": "cancel"}` en stdin: se guarda lo ya obtenido.

| Código de salida | Significado |
|---|---|
| `0` | Terminó sin incidencias |
| `1` | Error interno |
| `2` | Uso incorrecto o entrada inválida |
| `3` | Terminó, pero algún módulo falló |
| `4` | Resultado incompleto por agotar el presupuesto |
| `5` | Solo `verify`: alguna evidencia no coincide con su huella |
| `10`, `11` | Solo `watch run`: hay alertas nuevas / una alerta no se pudo entregar |
| `12` | Solo `summarize`: el modelo falló o no produjo ninguna frase válida |
| `130` | Cancelado |

El detalle de eventos y esquemas está en [CLI_CONTRACT.md](CLI_CONTRACT.md), con su
[esquema JSON](cli-contract.schema.json).

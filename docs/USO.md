# Guía de uso

Referencia de las órdenes y del comportamiento de OSINEITOR. Para instalar y probar rápido, mira
el [README](../README.md). Los ejemplos usan `example.com` y `1.1.1.1`: dominio e IP reservados
para documentación.

## Índice

- [Órdenes](#órdenes)
- [Qué se investiga y cómo se pivota](#qué-se-investiga-y-cómo-se-pivota)
- [Opciones de los scans](#opciones-de-los-scans)
- [Estado de cada módulo](#estado-de-cada-módulo)
- [Presupuesto](#presupuesto)
- [Caché](#caché)
- [Doctor](#doctor)
- [Red y entradas](#red-y-entradas)
- [Informes e historial](#informes-e-historial)
- [API keys y rutas](#api-keys-y-rutas)
- [Uso desde otros programas](#uso-desde-otros-programas)

## Órdenes

```bash
osineitor scan example.com            # detecta el tipo de la entrada y pivota (profundidad 2)
osineitor domain example.com          # solo el dominio (profundidad 1)
osineitor ip 1.1.1.1
osineitor email alguien@example.com --depth 2
osineitor username johndoe

osineitor history --limit 50          # scans guardados (20 por defecto)
osineitor show 3                      # volver a ver el scan 3
osineitor export 3 -f html            # informe en reports/ (json | md | html)
osineitor export 3 -f md -o informe.md  # en el fichero indicado

osineitor modules                     # módulos disponibles y estado de sus API keys
osineitor doctor                      # prueba cada módulo contra su fuente real
osineitor doctor -m dns --json        # solo esos módulos (-m, repetible); --active y --allow-private como en los scans
osineitor cache info                  # respuestas cacheadas (cache clear las borra)
osineitor config show                 # keys configuradas (se ven solo los 4 primeros caracteres)
osineitor version
```

`scan` deduce el tipo de la entrada. Una cadena como `john.doe` es ambigua (parece un dominio);
en ese caso usa la orden explícita: `osineitor username john.doe`.

## Qué se investiga y cómo se pivota

Cada módulo declara qué tipos de entidad consume y cuáles produce. El motor ejecuta, en paralelo,
los módulos que aceptan la entidad inicial y las entidades nuevas pasan al siguiente nivel:

```
email alguien@example.com
├─ email_validate ─► domain example.com ─► dns ─► ip 203.0.113.10
│                 └► username alguien ─► username_sites ─► profile https://…
└─ gravatar ─► profile https://gravatar.com/…
```

`--depth` controla cuántos niveles se pivota (1 a 4). Con `1` solo se analiza el objetivo; con `2`
también las entidades descubiertas (p. ej. las IPs a las que resuelve un dominio). Cada nivel
multiplica las peticiones: úsalo con criterio. Una entidad ya vista no se vuelve a investigar y los
datos de varias fuentes sobre la misma entidad se fusionan; si discrepan, gana el módulo que va
antes en el orden alfabético. La columna «Fuente» lista todos los módulos que vieron cada entidad;
`--json` y `show --json` añaden en `observations` quién la vio, sobre qué entidad y cuándo.

## Opciones de los scans

Valen para `scan`, `domain`, `ip`, `email` y `username`.

| Opción | Efecto |
|---|---|
| `--depth`, `-d` | Niveles de pivoteo (1–4) |
| `--module`, `-m` | Ejecuta solo estos módulos (repetible) |
| `--active` | Permite módulos que contactan al objetivo |
| `--max-entities`, `--max-requests`, `--max-time` | [Presupuesto](#presupuesto) (`0` = sin límite) |
| `--no-cache`, `--refresh` | [Caché](#caché) |
| `--allow-private` | Permite conectar con redes privadas (ver [Red y entradas](#red-y-entradas)) |
| `--proxy` | Envía todo el tráfico por un proxy (ver [Proxy y Tor](#proxy-y-tor)); también `OSINEITOR_PROXY` |
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
red. Queda un riesgo residual de *DNS rebinding* documentado en [SECURITY.md](../SECURITY.md).

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
- **`dns` y `email_validate` se omiten** (`omitido: consulta DNS directa`). Consultan DNS por UDP, que
  un proxy SOCKS no enruta, y harían llegar tus consultas a tu resolvedor local. Pierdes los
  registros DNS y el MX del email mientras uses proxy.
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

El fichero de keys **no se cifra**: en Windows hereda los permisos de tu carpeta de usuario.

## Barra de progreso

En una terminal (con `stdout` y `stderr` sin redirigir) el scan muestra una barra en `stderr` con
los módulos completados, las entidades y las peticiones; desaparece al terminar. Con `--json`,
`--ndjson`, `--quiet` o cualquier redirección no se dibuja nada. Los programas que lanzan la CLI
reciben el mismo avance como eventos `progress` con `--ndjson`.

## Uso desde otros programas

`--ndjson` emite un evento JSON por línea (inicio, cada módulo, cada entidad, progreso, fin);
`--json` un único documento (también en `modules`, `history`, `show`, `doctor`, `config show`,
`config set`, `config unset`, `version` y `export`); `--quiet` suprime la salida legible. `--control-stdin` permite cancelar
escribiendo `{"cmd": "cancel"}` en stdin: se guarda lo ya obtenido.

| Código de salida | Significado |
|---|---|
| `0` | Terminó sin incidencias |
| `1` | Error interno |
| `2` | Uso incorrecto o entrada inválida |
| `3` | Terminó, pero algún módulo falló |
| `4` | Resultado incompleto por agotar el presupuesto |
| `130` | Cancelado |

El detalle de eventos y esquemas está en [CLI_CONTRACT.md](CLI_CONTRACT.md), con su
[esquema JSON](cli-contract.schema.json).

# Pruebas en Windows pendientes

Estado de lo que **no se ha podido comprobar en vivo** y que se verificará cuando el repositorio
se clone en VS Code y se pruebe desde Windows. Corresponde a los entregables F0.1, F0.2, F0.3 y
F0.5 del [roadmap](../ROADMAP.md).

## Por qué está pendiente

- Todo el desarrollo se hace en un contenedor Linux cuyo proxy **bloquea casi todos los hosts**
  de las fuentes (`403 Forbidden` al abrir el túnel). Los módulos que dependen de ellas no se
  han podido ejecutar contra el servicio real.
- La CI de GitHub (Windows y Linux, Python 3.11 y 3.13) **pasa**, pero no hace peticiones reales
  por diseño: los tests simulan las respuestas. Que estén en verde demuestra que la lógica, las
  rutas y la codificación funcionan en Windows, **no** que las fuentes respondan como se espera.

## Estado de cada módulo

Leyenda: ✅ comprobado en vivo · ⚠️ comprobado solo en parte · ❌ no comprobado en vivo.

| Módulo | Estado | Qué se sabe |
|---|---|---|
| `dns` | ⚠️ | Resolvió registros reales (p. ej. `A` de `github.com`) en el contenedor Linux. Desde mi red en Windows falla, causa sin confirmar (ver [salidas literales](#salidas-literales-2026-10-29)) |
| `email_validate` | ✅ | Validó la sintaxis, los MX y derivó el username |
| `username_sites` | ⚠️ | Solo con los sitios que el proxy dejaba pasar: 6 perfiles para `blue` y 1 falso positivo (`Apple Developer`) con un username aleatorio. La tasa real de falsos positivos **no está medida** (F0.5) |
| `rdap` | ❌ | `rdap.org` bloqueado. El formato de la respuesta sí se comprobó contra una respuesta real de `github.com`; la omisión por TLD sin RDAP se probó con el bootstrap real de IANA |
| `crtsh` | ❌ | `crt.sh` bloqueado; formato sin contrastar con una respuesta real |
| `wayback` | ❌ | `web.archive.org` bloqueado; formato sin contrastar |
| `ipinfo` | ❌ | `ipinfo.io` bloqueado |
| `internetdb` | ❌ | Bloqueado en el entorno; el formato sí se comprobó contra una respuesta real de `1.1.1.1` |
| `gravatar` | ❌ | `gravatar.com` bloqueado |
| `http_fingerprint` | ❌ | Solo se comprobó que la guardia de red bloquea `localhost`; nunca consultó un sitio real |
| `shodan`, `abuseipdb`, `greynoise`, `hibp`, `hunter_verify`, `hunter_domain` | ❌ | Necesitan API key; **nunca se han ejecutado contra su servicio**. Están escritas según su documentación |

## Preparar el entorno en VS Code (Windows)

Requisitos: Git y Python 3.11 o superior (recomendado 3.13). Desde una terminal de VS Code:

```powershell
git clone https://github.com/jmstudio14/OSINEITOR.git
cd OSINEITOR
py -3.13 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

Si PowerShell bloquea la activación del entorno, ejecuta antes
`Set-ExecutionPolicy -Scope Process Bypass` o usa `.venv\Scripts\activate.bat` desde `cmd`.
En VS Code, selecciona el intérprete de `.venv` (`Ctrl+Shift+P` → *Python: Select Interpreter*).

Comprobación base, que debe dar todo en verde:

```powershell
ruff check .
ruff format --check .
python -m pytest -q
osineitor version
```

## Pruebas en vivo

Antes de nada, `osineitor doctor` prueba los 16 módulos de una vez (los de API key y los activos
salen como «omitido» sin su key / sin `--active`). Es la forma más rápida de ver qué fuentes
responden desde tu red; pega su salida en el issue si algo falla.

Cada una usa objetivos públicos y **solo módulos pasivos**, es decir, no tocan el servidor del
objetivo. Para probar con tus propios datos usa tu email y tu username.

```powershell
osineitor modules
osineitor domain example.com --no-save
osineitor domain ejemplo.es --no-save -m rdap
osineitor ip 1.1.1.1 --no-save
osineitor email tu@correo.com --no-save
osineitor username tu_usuario --no-save
osineitor scan example.com --no-save --max-entities 100
```

Qué se espera:

- `domain example.com`: registros DNS, datos de registro (RDAP), subdominios de crt.sh y
  URLs archivadas. Si alguna fuente falla debe salir como `error:` al final, no como un vacío.
- `domain ejemplo.es -m rdap`: `skipped: el TLD .es no tiene servidor RDAP`.
- `ip 1.1.1.1`: geolocalización y puertos abiertos.
- `scan example.com --max-entities 100`: si se alcanza el tope debe avisar de que el resultado
  es incompleto.

Mediciones pendientes (F0.5), desde tu red:

```powershell
python scripts/fp_baseline.py --output reports/fp_baseline.md
python scripts/rdap_coverage.py --output docs/RDAP_COBERTURA.md
```

Con API keys (opcional, una por módulo que quieras comprobar):

```powershell
osineitor config set abuseipdb TU_KEY
osineitor ip 8.8.8.8 --no-save -m abuseipdb
```

Dónde se guarda todo en Windows: configuración en `%APPDATA%\osineitor` y datos en
`%LOCALAPPDATA%\osineitor`.

## Cómo anotar los resultados

Por cada módulo que falle o devuelva algo distinto de lo esperado, abre un issue con:

1. El comando exacto y la versión (`osineitor version`).
2. La salida completa, quitando datos personales y API keys.
3. Lo que esperabas.

Con eso se guardan las respuestas reales como *fixtures* anonimizadas en `tests/fixtures/`
(F0.2), se corrige el parseo donde difiera del formato real (F0.3) y se actualiza la tabla de
este documento. Cuando los 16 módulos tengan una ejecución real documentada, F0.1 queda
cerrado y este fichero deja de ser necesario.

## Registro de resultados

Rellenar al probar desde Windows.

| Módulo | Fecha | Windows / Python | ¿Funciona? | Observaciones |
|---|---|---|---|---|
| `dns` | 2026-10-29 | Windows 11 10.0.26300 / Python 3.14.7 | ❌ Falla desde mi red, causa sin confirmar | `doctor`: «el resolvedor DNS no respondió». Ver [salidas literales](#salidas-literales-2026-10-29) |
| `rdap` | | | | |
| `crtsh` | 2026-10-29 | Windows 11 10.0.26300 / Python 3.14.7 | ❌ Falla desde mi red, causa sin confirmar | `doctor`: «crt.sh respondió 404» tras 61 s; `curl` directo: 502. Ver [salidas literales](#salidas-literales-2026-10-29) |
| `wayback` | | | | |
| `http_fingerprint` | | | | |
| `ipinfo` | | | | |
| `internetdb` | | | | |
| `email_validate` | | | | |
| `gravatar` | | | | |
| `username_sites` | | | | |
| `shodan` | | | | |
| `abuseipdb` | | | | |
| `greynoise` | | | | |
| `hibp` | | | | |
| `hunter_verify` | | | | |
| `hunter_domain` | | | | |

## Salidas literales (2026-10-29)

Windows 11 Home 10.0.26300, Python 3.14.7 (venv), mismo equipo y misma red. `dns` y `crtsh`
**fallan desde mi red y la causa no está confirmada**: no se han probado desde otra red.

`osineitor doctor` (extracto):

```text
│ crtsh            │ FALLO     │ crt.sh respondió 404                │ 61.1 s │
│ dns              │ FALLO     │ el resolvedor DNS no respondió      │  0.4 s │
│                  │           │ (tiempo agotado o sin servidores)   │        │
Fallan: crtsh, dns
```

DNS: `Resolve-DnsName example.com -Type A -DnsOnly -QuickTimeout -Server <X>`:

```text
== Resolve-DnsName example.com A (servidor: sistema)
ERROR: example.com : Se ha rechazado la operación DNS
== Resolve-DnsName example.com A (servidor: 192.168.0.1)
ERROR: example.com : Se ha rechazado la operación DNS
== Resolve-DnsName example.com A (servidor: 1.1.1.1)
ERROR: example.com : Se ha rechazado la operación DNS
== Resolve-DnsName example.com A (servidor: 8.8.8.8)
ERROR: example.com : Se ha rechazado la operación DNS
== nslookup example.com 1.1.1.1
Servidor:  one.one.one.one
Address:  1.1.1.1

nslookup : *** one.one.one.one no encuentra example.com: Query refused
== Test-NetConnection 1.1.1.1 -Port 53
ComputerName     : 1.1.1.1
TcpTestSucceeded : True
```

crt.sh (`curl.exe -s -o NUL -w "http=%{http_code} t=%{time_total}s" -m 40 <url>`):

```text
== https://crt.sh/?q=example.com&output=json
http=502 t=0.712888s
== https://crt.sh/?q=%25.example.com&output=json   (la consulta del módulo)
http=502 t=0.793848s
== https://crt.sh/
http=502 t=0.486813s
```

Comprobaciones posteriores (mismo día, mismo equipo):

```text
GetHostAddresses: example.com FALLO "Host desconocido" | github.com, google.com, wikipedia.org,
                  archive.org, crt.sh, example.org, example.net, iana.org, cloudflare.com OK
                  www.example.com FALLO
dnspython (nameservers ['192.168.0.1']): example.com -> NoNameservers ... answered REFUSED
                                         github.com  -> ['20.250.119.67']
dnspython contra 1.1.1.1, UDP y TCP: example.com -> answered REFUSED (las dos)
Resolve-DnsName example.com -Server 1.1.1.1 -TcpOnly, -Server 9.9.9.9 y tipo NS en 1.1.1.1:
    "Se ha rechazado la operación DNS"
Resolve-DnsName o-o.myaddr.l.google.com TXT -Server 8.8.8.8 -> {212.166.132.197}
DoH (curl a cloudflare-dns.com/dns-query?name=example.com&type=A) -> Status 0,
    104.20.23.154 y 172.66.147.243
fichero hosts: sin entradas
```

Qué descartan y qué no:

- **DNS.** El problema no es un DNS caído: solo se rechaza `example.com` y `www.example.com`
  (`REFUSED`), tanto por UDP como por TCP y desde el router, 1.1.1.1, 8.8.8.8 y 9.9.9.9. El resto
  de nombres probados resuelve y `example.com` sí resuelve por DoH. Descartan un fallo del código
  de OSINEITOR (`Resolve-DnsName`, `nslookup` y dnspython fallan igual), un fallo del router
  concreto y un bloqueo del puerto 53. Explican por qué `dns` falla en `doctor` (su canary es
  `example.com`) y `wayback` e `ipinfo` no. **No** explican por qué cuatro resolvedores de
  operadores distintos rechazan el mismo nombre; apunta a algo en el camino que lo filtra, pero
  no está identificado. Falta probar desde otra red y revisar el panel del router.
- **crt.sh.** Es intermitente, no está bloqueado: diez peticiones espaciadas 30 s a
  `https://crt.sh/?q=example.com&output=json` (2026-10-29, 18:08–18:13) dieron 4 × `200`
  (0,7–8,4 s), 5 × `502` (≈0,3–0,5 s) y 1 × `404` (14 s). Las tres resoluciones (router, 1.1.1.1,
  8.8.8.8) dan la misma IP, 91.199.212.73, y una consulta de `github.com` hecha desde fuera de mi
  red (Firecrawl) devolvió `200` con JSON. Descartan un bloqueo de mi red y un fallo del módulo
  (que ya reintenta los 5xx). No explican por qué falla tanto el servicio ni identifican qué nodo
  responde cada error.

  ```text
  18:08:32 http=404 t=14.132244s   18:11:15 http=200 t=8.424791s
  18:09:02 http=502 t=0.269168s    18:11:45 http=200 t=0.709230s
  18:09:35 http=200 t=3.401130s    18:12:16 http=502 t=0.465469s
  18:10:06 http=502 t=0.445865s    18:12:46 http=502 t=0.491991s
  18:10:36 http=502 t=0.448674s    18:13:21 http=200 t=4.994088s
  ```

### Prueba desde otra red (móvil como punto de acceso, 2026-10-29 18:19)

IP pública de salida 31.4.245.148 (en casa era 212.166.132.197); DNS del Wi-Fi: 10.83.171.171.

```text
GetHostAddresses: example.com FALLO, www.example.com FALLO, github.com OK, example.org OK
Resolve-DnsName example.com (sistema)    ERROR Se ha rechazado la operación DNS
Resolve-DnsName example.com -Server 1.1.1.1  OK 104.20.23.154, 172.66.147.243
Resolve-DnsName example.com -Server 8.8.8.8  OK 172.66.147.243, 104.20.23.154
dnspython (nameservers ['192.168.0.1', '10.83.171.171']): ambos LifetimeTimeout con example.com
osineitor doctor: crtsh FALLO (crt.sh respondió 502, 1.0 s), dns FALLO (el resolvedor DNS no
                  respondió, 79.8 s); ipinfo y wayback ok
```

- **Descartan** que la causa esté en el equipo o en OSINEITOR: con otra red, 1.1.1.1 y 8.8.8.8
  sí resuelven `example.com`. El filtrado de las consultas directas a esos resolvedores ocurre en
  la red doméstica (router o proveedor). Cuál de los dos, **sin confirmar**.
- **No descartan ni explican** que el resolvedor del móvil (el del sistema en esta red) también
  rechace `example.com`, ni por qué `doctor` sigue fallando `dns` aquí.
- **Limitación del mensaje de `doctor`:** `dnspython` toma los servidores de todos los adaptadores,
  también del Ethernet desconectado (192.168.0.1). Con servidores que fallan de formas distintas
  (timeout y `REFUSED`) no sale el mensaje «rechazó la consulta», sino «no respondió».

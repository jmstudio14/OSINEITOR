# Pruebas en Windows pendientes

Estado de lo que **no se ha podido comprobar en vivo** y que se verificará cuando el repositorio
se clone en VS Code y se pruebe desde Windows. Corresponde a los entregables F0.1, F0.2, F0.3 y
F0.5 del [roadmap](https://github.com/jmstudio14/OSINEITOR/blob/main/ROADMAP.md). La lista de comprobación manual de la aplicación de escritorio
está en [GUI.md](GUI.md).

## Por qué está pendiente

- Hasta el 2026-11-05 el desarrollo se hizo en un contenedor Linux cuyo proxy **bloquea casi todos los hosts**
  de las fuentes (`403 Forbidden` al abrir el túnel). Los módulos que dependen de ellas no se
  han podido ejecutar contra el servicio real.
- La CI de GitHub (Windows y Linux, Python 3.11 y 3.13) **pasa**, pero no hace peticiones reales
  por diseño: los tests simulan las respuestas. Que estén en verde demuestra que la lógica, las
  rutas y la codificación funcionan en Windows, **no** que las fuentes respondan como se espera.

## Estado de cada módulo

Leyenda: ✅ comprobado en vivo · ⚠️ comprobado solo en parte · ❌ no comprobado en vivo.

| Módulo | Estado | Qué se sabe |
|---|---|---|
| `dns` | ✅ | Fixture real de `github.com` (A, MX, NS, TXT, CAA, SPF y DMARC). Con `example.com` (el canary de `doctor`) falla en mi red doméstica porque algo intercepta el puerto 53 (ver [salidas literales](#salidas-literales-2026-10-29)) |
| `email_validate` | ✅ | Validó la sintaxis, los MX y derivó el username; fixture real de `octocat@github.com` |
| `username_sites` | ✅ | Fixtures reales de 10 sitios (`octocat` y un username inexistente) y tasa de falsos positivos medida: 0,26 % ([FALSOS_POSITIVOS.md](FALSOS_POSITIVOS.md)) |
| `rdap` | ✅ | Fixture real de `github.com` (bootstrap de IANA y `rdap.org` → Verisign); la omisión por TLD sin RDAP se probó con el bootstrap real de IANA |
| `crtsh` | ⚠️ | Responde, pero es intermitente: 3 de 5 intentos del 2026-11-05 dieron `502` y en `doctor` tardó 61 s. Fixture real de `example.org` grabada al reintentar |
| `wayback` | ✅ | Fixture real de `example.org` (5000 URLs, truncado por el límite; 91 entidades); `doctor`: 25 entidades en 18,5 s |
| `ipinfo` | ✅ | Fixture real de `1.1.1.1` |
| `internetdb` | ✅ | Fixture real de `1.1.1.1` |
| `gravatar` | ✅ | Fixtures reales: sin perfil (`404`) y con perfil (`octocat@github.com`) |
| `http_fingerprint` | ✅ | Fixture real de `example.org`, con las cabeceras de respuesta. Es un módulo activo: `doctor` lo omite sin `--active` |
| `shodan`, `abuseipdb`, `greynoise`, `hibp`, `hunter_verify`, `hunter_domain` | ❌ | Necesitan API key; **nunca se han ejecutado contra su servicio**. Están escritas según su documentación. **Bloqueado** hasta tener una cuenta de cada servicio |

## Resultado de la ejecución en vivo (2026-11-05)

Windows 11 10.0.26300, Python 3.14.10, red doméstica. Los 10 módulos de los 16 originales que no necesitan API key se ejecutaron contra su servicio real y sus respuestas se grabaron con `scripts/record_fixtures.py` en `tests/fixtures/`; `tests/modules/test_recorded.py` las reproduce.

- **Parseo:** sin discrepancias. Cada módulo produce con la respuesta real las mismas entidades que produjo al grabar y los campos esperados (F0.3 no necesitó cambios de código).
- **Hallazgos reales, no fallos de parseo:** `crtsh` devuelve `502` de forma intermitente; `npm` (403, WAF) y `HackerNews` (419) no se pueden evaluar desde esta red y quedan como «desconocido»; `Reddit` responde 200 a usernames inexistentes y la verificación lo descarta.
- **`doctor`:** con los 10 módulos tarda 1 min 23 s (`crtsh` 61 s). Sin `-m` fallaba antes de empezar con `ValidationError: username no válido: 'Banco Santander, S.A.'` (el `canary` de `gleif` se sembraba como username); corregido en `doctor.seed_entity`. `doctor` completo (módulos pasivos y sin key; el resto sale «omitido») tarda 41 s y falla en `crtsh` y `cert_details` (`502` intermitente de crt.sh) y en `dns` y `mail_security` (el filtrado de `example.com` de mi red doméstica).
- **Sin comprobar:** los 6 módulos con API key y las fuentes añadidas en las fases 4 a 11.

Para volver a grabar una fixture (usa solo objetivos públicos):

```powershell
python scripts/record_fixtures.py rdap github.com
python scripts/record_fixtures.py username_sites octocat --sites GitHub,Keybase --name existe
```

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

Medición de falsos positivos (F0.5, ya hecha: [FALSOS_POSITIVOS.md](FALSOS_POSITIVOS.md)); para repetirla desde tu red:

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
| `dns` | 2026-11-05 | Windows 11 10.0.26300 / Python 3.14.10 | ✅ Funciona con `github.com` | Con `example.com` (canary de `doctor`) sigue fallando por el filtrado de la red doméstica: `doctor` ahora lo informa como REFUSED. Ver [salidas literales](#salidas-literales-2026-10-29) |
| `rdap` | 2026-11-05 | Windows 11 10.0.26300 / Python 3.14.10 | ✅ Funciona | `github.com`: bootstrap de IANA y `rdap.org` → Verisign |
| `crtsh` | 2026-11-05 | Windows 11 10.0.26300 / Python 3.14.10 | ⚠️ Intermitente | 3 de 5 intentos con `502`; `doctor` ok en 61 s; fixture de `example.org` grabada al reintentar. Antes (2026-10-29): ver [salidas literales](#salidas-literales-2026-10-29) |
| `wayback` | 2026-11-05 | Windows 11 10.0.26300 / Python 3.14.10 | ✅ Funciona | `example.org`: 5000 URLs (truncado), 91 entidades |
| `http_fingerprint` | 2026-11-05 | Windows 11 10.0.26300 / Python 3.14.10 | ✅ Funciona | `example.org`, con cabeceras de respuesta |
| `ipinfo` | 2026-11-05 | Windows 11 10.0.26300 / Python 3.14.10 | ✅ Funciona | `1.1.1.1` |
| `internetdb` | 2026-11-05 | Windows 11 10.0.26300 / Python 3.14.10 | ✅ Funciona | `1.1.1.1` |
| `email_validate` | 2026-11-05 | Windows 11 10.0.26300 / Python 3.14.10 | ✅ Funciona | `octocat@github.com` |
| `gravatar` | 2026-11-05 | Windows 11 10.0.26300 / Python 3.14.10 | ✅ Funciona | `test@example.com` (sin perfil) y `octocat@github.com` (con perfil) |
| `username_sites` | 2026-11-05 | Windows 11 10.0.26300 / Python 3.14.10 | ✅ Funciona | 10 sitios con `octocat`; tasa de falsos positivos 0,26 % |
| `shodan` | | | ⬜ Bloqueado | Necesita API key; no se ha podido ejecutar |
| `abuseipdb` | | | ⬜ Bloqueado | Necesita API key; no se ha podido ejecutar |
| `greynoise` | | | ⬜ Bloqueado | Necesita API key; no se ha podido ejecutar |
| `hibp` | | | ⬜ Bloqueado | Necesita API key; no se ha podido ejecutar |
| `hunter_verify` | | | ⬜ Bloqueado | Necesita API key; no se ha podido ejecutar |
| `hunter_domain` | | | ⬜ Bloqueado | Necesita API key; no se ha podido ejecutar |

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
- **`doctor` en esta red:** `dnspython` usó dos servidores, `['192.168.0.1', '10.83.171.171']`,
  y con ambos obtuvo tiempo agotado (no `REFUSED`), de ahí el mensaje «no respondió» tras
  79,8 s. Que el resolvedor del móvil conteste `REFUSED` a Windows y no responda a `dnspython`
  queda sin explicar. No se ha reproducido que `dnspython` mezcle timeouts y `REFUSED`, así que no
  hay ningún defecto demostrado en el mensaje de `doctor`.

### Causa del filtrado en la red doméstica (2026-10-29, de vuelta en casa)

Consultas con `dnspython` a servidores DNS que **no existen**:

```text
10.255.255.1 example.com  NoNameservers ... answered REFUSED
10.255.255.1 github.com   ['20.250.119.67']
192.0.2.1    example.com  NoNameservers ... answered REFUSED
192.0.2.1    github.com   ['20.250.119.67']
```

- **Confirma** que algo en la red doméstica intercepta todo el tráfico al puerto 53 (aunque el
  destino no exista), reenvía las consultas y contesta `REFUSED` solo para `example.com`. Por eso
  1.1.1.1, 8.8.8.8 y 9.9.9.9 «rechazaban» ese nombre: nunca contestaron ellos. Con la red del
  móvil esos resolvedores sí responden.
- **Sin confirmar:** si lo hace el router (192.168.0.1) o el proveedor. Las IP de prueba son
  privadas o de documentación, lo que apunta más al router, pero no está demostrado. Tampoco se
  sabe por qué se rechaza ese nombre. Hace falta revisar el panel del router.
- **Efecto en OSINEITOR:** ninguno en el código. `dns` y `doctor` usan `example.com` como canary,
  por eso fallan en esta red; con otros dominios (`github.com`) el módulo funciona.

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
| `dns` | ✅ | Resolvió registros reales (p. ej. `A` de `github.com`) |
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
| `dns` | | | | |
| `rdap` | | | | |
| `crtsh` | | | | |
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

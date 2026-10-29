# OSINEITOR

Herramienta OSINT modular de línea de comandos. Investiga **dominios, IPs, emails y nombres de
usuario** desde fuentes abiertas, **pivota** automáticamente entre ellos (dominio → IPs →
servicios; email → username → perfiles) y guarda cada investigación para exportarla como
informe JSON, Markdown o HTML.

> **Aviso legal.** OSINEITOR solo consulta fuentes abiertas y APIs públicas. Úsalo sobre
> objetivos propios o con autorización expresa. Investigar a personas físicas está sujeto al
> RGPD y a la legislación local; tú eres responsable del uso que hagas de la herramienta.
> Lee el [uso responsable](docs/USO_RESPONSABLE.md).

## Instalación

Requiere Python 3.11+.

```bash
git clone https://github.com/jmstudio14/OSINEITOR.git
cd OSINEITOR
pip install -e .            # o: pip install -e '.[dev]' para desarrollo
```

## Uso

```bash
osineitor scan ejemplo.com          # detecta el tipo y pivota (profundidad 2)
osineitor domain ejemplo.com        # solo el dominio (profundidad 1)
osineitor ip 1.1.1.1
osineitor email alguien@ejemplo.com --depth 2
osineitor username johndoe
osineitor domain ejemplo.com --active          # incluye módulos que contactan al objetivo
osineitor domain ejemplo.com -m dns -m crtsh   # solo ciertos módulos
osineitor ip 1.1.1.1 --json                    # salida JSON por stdout
osineitor scan ejemplo.com --max-entities 200 --max-requests 500 --max-time 120
osineitor domain ejemplo.com --refresh         # ignora la caché y vuelve a consultar
osineitor domain ejemplo.com --no-cache        # ni lee ni guarda la caché

osineitor history                   # scans guardados
osineitor show 3                    # volver a ver el scan 3
osineitor export 3 -f html          # informe en reports/ (json | md | html)
osineitor modules                   # módulos disponibles y estado de sus API keys
osineitor doctor                    # prueba cada módulo contra su fuente real
osineitor domain ejemplo.com --ndjson   # eventos en streaming para otros programas
osineitor cache info                # respuestas cacheadas (cache clear las borra)
```

`--depth` controla cuántos niveles se pivota. Con `1` solo se analiza el objetivo; con `2`
también se analizan las entidades descubiertas (p. ej. las IPs a las que resuelve un dominio).
Cada nivel multiplica las peticiones: úsalo con criterio.

**Presupuesto.** Cada scan tiene topes para no dispararse: 2000 entidades, 3000 peticiones y 900
segundos (`--max-entities`, `--max-requests`, `--max-time`; `0` = sin límite). Al agotarlos el
scan se detiene de forma ordenada, conserva lo ya encontrado y marca el resultado como
incompleto.

**Estado de cada módulo.** Tras cada scan se muestra una tabla con lo que pasó en cada módulo:
`ok`, `empty` (respondió sin datos), `error`, `quota` (la fuente rechazó por límite de uso),
`skipped` (no aplica, falta la API key o es activo), con entidades, peticiones, aciertos de caché
y tiempo. Así «sin resultados» deja de confundirse con «la fuente falló». Cada módulo tiene un
tiempo máximo (180 s por defecto); si lo supera se anota como error y el resto sigue.

**Caché.** Las respuestas GET de las fuentes pasivas y sin API key se guardan 6 horas en
`cache.db` (directorio de datos) para no repetir consultas ni gastar cuota. Nunca se cachean los
módulos con API key ni los activos, y en la base solo se guarda un hash de la petición, no la URL.
`--refresh` fuerza la consulta; `--no-cache` desactiva la caché; `osineitor cache clear` la vacía.

**Doctor.** `osineitor doctor` lanza cada módulo con un valor de prueba conocido (p. ej.
`example.com` o `1.1.1.1`) y muestra si responde. Sale con código 3 si algún módulo falla. No
valida que los datos sean correctos, solo que la fuente contesta y se interpreta sin errores.

**Uso desde otros programas.** `--ndjson` emite un evento JSON por línea (inicio, cada módulo,
cada entidad, progreso, fin), `--json` un único documento (también en `modules`, `history`,
`show`, `doctor`, `config show`, `version` y `export`) y `--quiet` suprime la salida legible.
`--control-stdin` permite cancelar escribiendo `{"cmd": "cancel"}` en stdin: se guarda lo ya
obtenido. Códigos de salida: `0` ok, `1` error interno, `2` uso incorrecto, `3` algún módulo
falló, `4` resultado incompleto por presupuesto, `130` cancelado. Es el contrato en el que se
apoyará la aplicación de escritorio; está en [docs/CLI_CONTRACT.md](docs/CLI_CONTRACT.md) con su
[esquema JSON](docs/cli-contract.schema.json).

**Red.** Por seguridad, ninguna petición se envía a IPs privadas, loopback ni al servicio de
metadatos de una nube (`169.254.169.254`), tampoco a través de redirecciones: un subdominio
publicado por un tercero podría apuntar ahí. `--allow-private` lo permite si investigas tu
propia red.

**Entradas.** Los dominios se guardan en minúsculas y en punycode (`münchen.de` →
`xn--mnchen-3ya.de`). Un username admite letras, números, `.`, `_` y `-` (hasta 64); un valor no
válido se rechaza antes de lanzar nada.

`scan` deduce el tipo de la entrada. Una cadena como `john.doe` es ambigua (parece un dominio);
en ese caso usa el comando explícito: `osineitor username john.doe`.

## Módulos

| Frente | Módulo | Fuente | API key |
|---|---|---|---|
| Dominio | `rdap` | RDAP (rdap.org): registrador, fechas, nameservers | — |
| Dominio | `dns` | A/AAAA/CNAME/MX/NS/TXT/CAA, SPF, DMARC | — |
| Dominio | `crtsh` | Subdominios por Certificate Transparency | — |
| Dominio | `wayback` | URLs archivadas; destaca rutas sensibles (`.env`, `.sql`, `/admin`…) | — |
| Dominio | `http_fingerprint` | Servidor, tecnologías, cabeceras de seguridad (**activo**) | — |
| Dominio | `hunter_domain` | Emails públicos del dominio y su patrón | `hunter` |
| IP | `ipinfo` | Geolocalización, ASN, hostname | opcional `ipinfo` |
| IP | `internetdb` | Puertos, CPEs y CVEs (Shodan InternetDB) | — |
| IP | `shodan` | Servicios con producto/versión, SO, CVEs | `shodan` |
| IP | `abuseipdb` | Puntuación y reportes de abuso | `abuseipdb` |
| IP | `greynoise` | ¿Escáner masivo o servicio legítimo conocido? | `greynoise` |
| Email | `email_validate` | Sintaxis, MX, desechable; pivota a dominio y username | — |
| Email | `gravatar` | Perfil público y cuentas enlazadas | — |
| Email | `hibp` | Brechas de datos (Have I Been Pwned) | `hibp` |
| Email | `hunter_verify` | Entregabilidad y fuentes públicas | `hunter` |
| Username | `username_sites` | Presencia en ~460 sitios (firmas de Sherlock) | — |

Los módulos **pasivos** solo hablan con terceros. Los **activos** envían tráfico al objetivo y
solo se ejecutan con `--active`. Un módulo sin su API key se omite y se indica en la salida.

### API keys

```bash
osineitor config set shodan TU_KEY      # se guarda en el directorio de configuración (abajo)
osineitor config show
export OSINEITOR_SHODAN_KEY=TU_KEY      # alternativa: variable de entorno (tiene prioridad)
```

Nombres: `shodan`, `abuseipdb`, `greynoise`, `hibp`, `hunter`, `ipinfo`.

**Dónde se guarda todo** (`OSINEITOR_CONFIG_DIR` y `OSINEITOR_DATA_DIR` lo sobrescriben):

| | Windows | Linux |
|---|---|---|
| Configuración y keys | `%APPDATA%\osineitor\config.toml` | `~/.config/osineitor/config.toml` |
| Historial (SQLite) y cachés | `%LOCALAPPDATA%\osineitor\` | `~/.local/share/osineitor/` |

En Windows el fichero de keys hereda los permisos de tu carpeta de usuario; no se cifra.

## Limitaciones conocidas

- **Usernames:** la detección se basa en el código de estado o en el texto de la respuesta.
  WAFs, captchas y cambios en los sitios producen falsos positivos y negativos. Cada positivo se
  contrasta con un username inexistente: si el sitio también lo «encuentra» se descarta. Aun así,
  verifica a mano cualquier perfil antes de sacar conclusiones.
- **crt.sh y Wayback** son servicios gratuitos que a menudo responden lento o con errores 5xx;
  el scan continúa y la incidencia aparece al final.
- Las cuotas gratuitas de ipinfo, GreyNoise y Hunter son bajas.

## Añadir un módulo

Crea un fichero en `src/osineitor/modules/<frente>/` con una subclase de `Module`; el registro
lo descubre automáticamente:

```python
from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module


class MiFuente(Module):
    name = "mi_fuente"
    description = "Qué aporta"
    consumes = frozenset({EntityType.DOMAIN})
    produces = frozenset({EntityType.RECORD})
    requires_key = None  # o "nombre_de_la_key"
    passive = True

    async def run(self, entity: Entity) -> list[Entity]:
        r = await self.ctx.http.get(f"https://api.ejemplo/{entity.value}")
        return [self.emit(entity, EntityType.RECORD, f"mi_fuente:{entity.value}", **r.json())]
```

Lanza `ModuleError("mensaje")` para fallos esperados (key inválida) y `ModuleQuota` si la fuente
rechaza por límite de uso; `status_error("servicio", respuesta)` elige entre ambos según el código
HTTP. Cualquier otra excepción también se captura y se registra sin detener el scan. Declara
además `canary` (un valor de prueba seguro para `doctor`) o `probe_url`, y añade el fichero a
`modules/_manifest.py` (un test lo exige: el ejecutable empaquetado no puede buscar módulos en
disco).

## Desarrollo

```bash
pip install -e '.[dev]'
ruff check . && ruff format --check .
python -m pytest
```

Los tests no hacen peticiones reales: las respuestas HTTP se simulan con `respx` y el DNS con un
resolver en memoria.

## Documentación

- [Arquitectura](docs/ARCHITECTURE.md): engine, pivoteo, modelo de datos y persistencia.
- [Contrato CLI para otros programas](docs/CLI_CONTRACT.md): eventos NDJSON, salidas JSON, cancelación
  y códigos de salida.
- [Referencia de módulos](docs/MODULES.md): fuentes, datos que aportan y limitaciones.
- [Pruebas en Windows pendientes](docs/PRUEBAS_WINDOWS.md): qué módulos no se han comprobado en vivo
  y cómo probarlos tras clonar el repositorio.
- [Uso responsable](docs/USO_RESPONSABLE.md): autorización, RGPD y usos no aceptables.
- [Roadmap](ROADMAP.md): fases siguientes, criterios de aceptación y fuera de alcance.
- [Contribuir](CONTRIBUTING.md) · [Seguridad](SECURITY.md) · [Changelog](CHANGELOG.md) ·
  [Código de conducta](CODE_OF_CONDUCT.md)

## Créditos

Las firmas de detección de usernames proceden del proyecto
[Sherlock](https://github.com/sherlock-project/sherlock) (MIT); ver
`src/osineitor/modules/username/data/README.md`.

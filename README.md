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

osineitor history                   # scans guardados
osineitor show 3                    # volver a ver el scan 3
osineitor export 3 -f html          # informe en reports/ (json | md | html)
osineitor modules                   # módulos disponibles y estado de sus API keys
```

`--depth` controla cuántos niveles se pivota. Con `1` solo se analiza el objetivo; con `2`
también se analizan las entidades descubiertas (p. ej. las IPs a las que resuelve un dominio).
Cada nivel multiplica las peticiones: úsalo con criterio.

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
osineitor config set shodan TU_KEY      # se guarda en ~/.config/osineitor/config.toml (0600)
osineitor config show
export OSINEITOR_SHODAN_KEY=TU_KEY      # alternativa: variable de entorno (tiene prioridad)
```

Nombres: `shodan`, `abuseipdb`, `greynoise`, `hibp`, `hunter`, `ipinfo`.

## Limitaciones conocidas

- **Usernames:** la detección se basa en el código de estado o en el texto de la respuesta.
  WAFs, captchas y cambios en los sitios producen falsos positivos y negativos. Verifica a mano
  cualquier perfil antes de sacar conclusiones.
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

Lanza `ModuleError("mensaje")` para fallos esperados (cuota, key inválida). Cualquier otra
excepción también se captura y se registra sin detener el scan.

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
- [Referencia de módulos](docs/MODULES.md): fuentes, datos que aportan y limitaciones.
- [Uso responsable](docs/USO_RESPONSABLE.md): autorización, RGPD y usos no aceptables.
- [Contribuir](CONTRIBUTING.md) · [Seguridad](SECURITY.md) · [Changelog](CHANGELOG.md) ·
  [Código de conducta](CODE_OF_CONDUCT.md)

## Créditos

Las firmas de detección de usernames proceden del proyecto
[Sherlock](https://github.com/sherlock-project/sherlock) (MIT); ver
`src/osineitor/modules/username/data/README.md`.

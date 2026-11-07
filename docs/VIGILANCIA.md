# Vigilancia continua

`osineitor watch` repite scans de unos objetivos propios y avisa **solo de lo que cambió**. No es un
servicio: cada ejecución es un proceso corto que lanza el planificador del sistema (cron, systemd,
GitHub Actions).

> Vigila únicamente activos propios o con autorización expresa. Ver
> [uso responsable](USO_RESPONSABLE.md).

## Fichero `watch.yml`

Por defecto, en la carpeta de configuración (`osineitor config show` muestra la ruta); con
`--file` se indica otro.

```yaml
notifiers:
  slack:
    type: webhook                  # webhook | email | file
    url_env: OSINEITOR_SLACK_URL   # o `url:`; la URL es un secreto, mejor en el entorno
    format: slack                  # generic | slack | discord | teams
    min_severity: medium           # info | low | medium | high | critical
    quiet: "22:00-07:00"           # opcional: sin avisos en esa franja (hora local del equipo)
  correo:
    type: email
    host: smtp.example.com
    port: 587                      # 465 con `ssl: true`; STARTTLS por defecto
    username: osineitor
    password_env: OSINEITOR_SMTP_PASSWORD
    from: osineitor@example.com
    to: [seguridad@example.com]
  registro:
    type: file                     # una línea JSON por alerta (Filebeat, Telegraf, Promtail…)
    path: /var/log/osineitor/alertas.ndjson

targets:
  - target: example.com
    preset: attack-surface         # opcional; también `depth`, `modules`, `active`
    every: 1d                      # 30m, 6h, 1d… (mínimo 5m)
    notify: [slack, registro]      # por defecto, todos los notificadores
    confirm: 2                     # opcional: alertar solo si se ve en 2 ejecuciones seguidas
  - target: 203.0.113.7
    every: 6h
```

`osineitor watch check` valida el fichero sin ejecutar nada; `watch list` muestra cada objetivo,
su frecuencia, su última ejecución y si le toca.

## Cómo decide qué es nuevo

- La vigilancia guarda, por objetivo, las claves de las entidades que **ya conoce** (en la misma
  base SQLite que los scans).
- La **primera ejecución** fija esa línea base y **no alerta**: todo sería «nuevo».
- Una alerta salta por cada entidad nueva que cumple una regla de
  [`alerts.yml`](https://github.com/jmstudio14/OSINEITOR/blob/main/src/osineitor/data/rules/alerts.yml) (subdominio, IP, servicio, CVE o filtración
  nuevos) y por cada **hallazgo** nuevo del analizador `findings` (SPF permisivo, certificado a punto
  de caducar, CVE en KEV, CNAME colgante…), con la severidad de la regla.
- Lo ya conocido no se repite. Si una entidad **desaparece** en un scan completo y sin fallos de
  módulos, se olvida: si vuelve, alerta otra vez (un fallo corregido que reaparece es noticia).
- Un scan truncado, cancelado o con módulos fallidos **no olvida nada**: lo que no vio no se da por
  desaparecido.
- Si **ningún notificador** recibe una alerta, se conserva y se reintenta en la siguiente ejecución.
  Si al menos uno la recibe, se da por entregada (los fallos parciales se informan).
- Un hallazgo y la alerta de la entidad que lo provoca pueden llegar los dos (p. ej. un servicio RDP
  nuevo da «servicio nuevo» y «servicio de administración expuesto»).

## Vigilar filtraciones de un email

Un objetivo de `watch.yml` puede ser un email (`target: ana@example.com`). Los módulos de
filtraciones (`leakcheck`, sin key, y `hibp`, con key) emiten un `breach` por cada una en la que
aparece; la regla `new-breach` (severidad alta) alerta de las que **no figuraban en la ejecución
anterior**. Lo que ya estaba filtrado al fijar la línea base no alerta. Los infostealers no están
cubiertos: ninguna fuente de infostealers se ha podido verificar (ver
[`MODULES.md`](MODULES.md#fuentes-evaluadas-y-no-incluidas)).

Vigilar un email es investigar a una persona: hazlo solo con el consentimiento de su dueño o sobre
direcciones propias ([uso responsable](USO_RESPONSABLE.md)).

## Menos ruido

- **`min_severity`** (por notificador): solo avisa de alertas de esa severidad o mayor.
- **`confirm: N`** (por objetivo, 1 a 5; por defecto 1): una entidad nueva solo alerta si se ve en
  `N` ejecuciones **seguidas**. Si desaparece entre medias, empieza de cero, así que un subdominio que
  parpadea o una fuente inestable no despiertan a nadie. Mientras espera no cuenta como conocida y
  `watch run` informa de cuántas hay en `pending`.
- **`quiet: HH:MM-HH:MM`** (por notificador): ventana de silencio en hora local del equipo; puede
  cruzar la medianoche y el fin es exclusivo. Una alerta que cae dentro **no se pierde**: si ningún
  notificador pudo avisar, se conserva y sale en la primera ejecución fuera de la ventana. Se informa
  en `held` y no cambia el código de salida a `11` (no es un fallo). Si otro notificador sí avisó, la
  alerta se da por entregada y el que estaba en silencio no la recibirá después.

`every` es un mínimo: un cron cada hora no retrasa un `1d` por unos minutos de diferencia (se admite
una holgura del 10 %, máximo 10 minutos). `--force` ejecuta también los que aún no tocan y
`--target X` limita a uno.

## Salida y códigos de salida

`osineitor watch run` imprime un resumen (o JSON con `--json`, ver
[CLI_CONTRACT.md](CLI_CONTRACT.md)) y sale con:

| Código | Significado |
|---|---|
| `0` | Sin alertas nuevas |
| `3` | Sin alertas, pero un objetivo falló o su scan quedó incompleto |
| `10` | Hay alertas nuevas |
| `11` | Alguna alerta no llegó a ningún notificador |
| `2` | Fichero inválido o argumentos incorrectos |

Un monitor puede tratar `10` como aviso y `11` o `3` como fallo del propio sistema.

## Despliegue

### cron

```cron
# Cada hora; cada objetivo decide por su `every` si le toca.
0 * * * * osineitor watch run >> /var/log/osineitor/watch.log 2>&1
```

Las API keys van por variables de entorno (`OSINEITOR_SHODAN_KEY`…) definidas en el propio
crontab o en un fichero que lea el servicio.

### systemd

```ini
# /etc/systemd/system/osineitor-watch.service
[Service]
Type=oneshot
EnvironmentFile=/etc/osineitor.env
ExecStart=/usr/local/bin/osineitor watch run

# /etc/systemd/system/osineitor-watch.timer
[Timer]
OnCalendar=hourly
Persistent=true
[Install]
WantedBy=timers.target
```

`SuccessExitStatus=10` evita que el servicio figure como fallido cuando solo hay alertas.

### GitHub Actions

El estado vive en la base SQLite, así que **hay que conservarla entre ejecuciones**; con la caché de
Actions (o un artefacto) basta:

```yaml
name: vigilancia
on:
  schedule: [{cron: "0 * * * *"}]
  workflow_dispatch:
jobs:
  watch:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4          # donde esté watch.yml
      - uses: actions/setup-python@v5
        with: {python-version: "3.12"}
      - run: pip install osineitor
      - uses: actions/cache@v4
        with:
          path: ~/.local/share/osineitor   # OSINEITOR_DATA_DIR lo cambia
          key: osineitor-db-${{ github.run_id }}
          restore-keys: osineitor-db-
      - run: osineitor watch run --file watch.yml
        env:
          OSINEITOR_SLACK_URL: ${{ secrets.OSINEITOR_SLACK_URL }}
```

Con `workflow_dispatch` y `schedule`, un código `10` marca el trabajo como fallido: es la forma
más simple de que GitHub avise por correo. Si no se quiere, añade `|| [ $? -eq 10 ]`.

> **Sin comprobar:** estos tres ejemplos no se han ejecutado en cron, systemd ni GitHub Actions
> reales; lo probado son los códigos de salida, el estado y los notificadores con simulaciones
> (ver `tests/test_watch.py`). Los formatos `slack`, `discord` y `teams` siguen la forma documentada
> de cada servicio, pero no se han enviado a uno real.

## Notificadores

- **webhook:** `POST` JSON. `slack` y `teams` envían `{"text": …}`; `discord`, `{"content": …}`
  (recortado a 1900 caracteres); `generic`, `text` más `target`, `scan_id` y la lista `alerts`. Sale
  por el mismo cliente HTTP que los módulos (no llega a redes privadas salvo `allow_private: true`).
- **email:** SMTP con STARTTLS (587) o SSL (465). La contraseña solo se lee de `password_env`.
- **file:** una línea JSON por alerta, con `ts`, `target`, `scan_id` y los campos de la alerta.
- Un error de entrega nunca incluye la URL del webhook ni la contraseña.

## Retención

Cada ejecución guarda un scan. `osineitor purge --older-than 90d` borra los scans más antiguos (con
sus evidencias); `--dry-run` solo cuenta. No toca el estado de la vigilancia.

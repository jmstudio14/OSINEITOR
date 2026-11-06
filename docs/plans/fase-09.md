# Plan de la fase 9 · Monitorización continua (v0.10.0)

Sale del [ROADMAP](../../ROADMAP.md) (fase 9). Criterios comunes, de
[`CLAUDE.md`](../../CLAUDE.md) y de las fases anteriores:

- Salida estructurada de la CLI solo con cambios aditivos; el esquema
  `docs/cli-contract.schema.json` se actualiza en el mismo cambio y `tests/test_contract.py` lo
  valida.
- Todo lo que sale a la red lo hace por el cliente HTTP del proyecto (guardia de red).
- README, `docs/` y `CHANGELOG.md` al día.
- Criterio de salida: `ruff check .`, `ruff format --check .` y `python -m pytest -q` en verde.

## Estado

| ID | P | Entregable | Estado | Decisión |
|---|---|---|---|---|
| F9.1 | M | `osineitor watch` | ✅ | `watch.yml`; `run`, `list` y `check`; estado en SQLite (migración 8) |
| F9.2 | M | Reglas de alerta | ✅ | `alerts.yml` con el motor de hallazgos + hallazgos nuevos |
| F9.3 | M | Notificaciones | ✅ | Webhook (generic, Slack, Discord, Teams), correo SMTP y fichero NDJSON |
| F9.5 | S | Retención | ✅ | `osineitor purge --older-than 90d [--dry-run]` |
| F9.4 | S | Supresión de ruido | ⬜ | Aplazado: umbrales por notificador (`min_severity`) ya existen; faltan ventanas de silencio y confirmación en dos ejecuciones |
| F9.6 | S | Dominios parecidos | ⬜ | Aplazado: `lookalike_domains` emite un único `record`, hay que decidir cómo detectar «uno nuevo» dentro de él |
| F9.7 | S | Nuevas filtraciones | ⬜ | Aplazado: la regla `new-breach` cubre `hibp`; faltan infostealers (F5.8, bloqueado) |

## Decisiones

- **«Nuevo» = clave no conocida, no «distinto del scan anterior».** La vigilancia guarda por
  objetivo el conjunto de claves de entidad que ya conoce (`watch_seen`). Comparar con el scan
  anterior daba falsos positivos si ese scan quedó truncado o con módulos caídos; con un conjunto
  acumulado, un scan flojo solo añade menos claves y no inventa novedades después. Además es lo que
  garantiza el criterio de aceptación: una alerta no se repite.
- **Olvidar solo con scans limpios.** Las claves ausentes se borran únicamente si el scan fue
  `complete` y ningún módulo terminó en `error` o `quota`. Así un hallazgo corregido que reaparece
  vuelve a alertar, y un fallo de una fuente no provoca alertas dobles.
- **Primera ejecución = línea base, sin alertas.** Todo sería nuevo. Los hallazgos de esa primera
  vez están en el informe del scan, no en una avalancha de avisos.
- **Entrega con reintento.** Si ningún notificador recibe una alerta, sus claves no se marcan como
  conocidas y se reintentan; si al menos uno la recibe, se da por entregada. Los fallos parciales
  se informan en `deliveries`. Alternativa descartada: reintentar por notificador, que obliga a
  guardar el estado de entrega de cada uno.
- **Reglas de alerta = reglas de hallazgo.** `alerts.yml` usa el formato y el evaluador de
  `findings.py` aplicados a las entidades nuevas; un hallazgo nuevo alerta con su severidad sin
  regla extra. Puede salir una alerta doble (p. ej. servicio RDP nuevo): es deliberado y está
  documentado, fusionarlas añadiría una capa de correlación que nadie pidió.
- **Frecuencia declarativa.** `every` vive en `watch.yml`; quien ejecuta es el planificador del
  sistema, con holgura del 10 % (máximo 10 minutos) para que un cron horario no retrase un `1d`.
- **Secretos fuera del fichero.** `url_env` y `password_env` leen del entorno; un error de entrega
  nunca contiene la URL del webhook (puede llevar el token) ni la contraseña, y se descarta el
  texto de la excepción de red por la misma razón.
- **Códigos de salida.** `10` alertas nuevas y `11` alerta sin entregar (prioridad: `11` > `10` >
  `3`). Son nuevos y solo de `watch run`, por tanto aditivos para el contrato.
- **Notificadores por el cliente HTTP.** El webhook usa `HttpClient` con la guardia de red; un
  webhook en red privada exige `allow_private: true` explícito.

## Verificación

- `tests/test_watch.py` (37): criterio de aceptación (un cambio simulado = exactamente una alerta y
  no se repite), línea base silenciosa, reaparición, scan con módulos caídos, hallazgo nuevo con su
  severidad, frecuencia y holgura, reintento de una alerta no entregada, los cuatro formatos de
  webhook, secretos fuera de los errores, `min_severity`, correo SMTP simulado, 16 ficheros inválidos,
  CLI de extremo a extremo (códigos `0`, `10`, `11`, `2`) y `purge`.
- `tests/test_contract.py`: `watch_output`, `watch_list_output` y `purge_output` validan contra el
  esquema.
- **No comprobado:** envío a Slack, Discord, Teams o un servidor SMTP reales, y los ejemplos de cron,
  systemd y GitHub Actions de `docs/VIGILANCIA.md`. El criterio «documentación de despliegue con
  cron y con GitHub Actions» está cumplido en cuanto a documentación, no en cuanto a haberlos
  ejecutado.

# Contrato CLI ↔ otros programas (versión 1)

Esta es la interfaz estable que usa la aplicación de escritorio (Hito G del
[roadmap](../ROADMAP.md)) para controlar la CLI, y que sirve a cualquier otro programa. El esquema
formal está en [`cli-contract.schema.json`](cli-contract.schema.json) y los tests validan contra él
la salida real de la CLI.

**Estabilidad.** Los cambios son solo aditivos (campos o tipos de evento nuevos). Un cliente debe
**ignorar lo que no conozca**. Un cambio incompatible subiría `v`.

## Lanzar la CLI

- Ejecuta `osineitor` (o `python -m osineitor`) con estas variables en el entorno del hijo:
  `PYTHONUTF8=1` y `PYTHONIOENCODING=utf-8`. En Windows, crea el proceso sin ventana de consola
  (`CREATE_NO_WINDOW`) para evitar el parpadeo.
- La salida de `--ndjson` es ASCII puro (los caracteres no ASCII van escapados como `\uXXXX`):
  no depende de la codificación de la tubería. `--json` sale en UTF-8 sin escapar, por eso hay que
  fijar `PYTHONUTF8` y `PYTHONIOENCODING`. Las líneas pueden acabar en `\n` o `\r\n`; usa
  `splitlines()`.
- stdout es solo para datos. Los errores y diagnósticos humanos van a stderr.

## Scans en streaming: `--ndjson`

Válido en `scan`, `domain`, `ip`, `email` y `username`. Excluyente con `--json`. Una línea JSON
por evento, con `flush` inmediato. Todos llevan `v` (1), `ts` (ISO 8601 UTC) y `type`.

| `type` | Cuándo | Campos |
|---|---|---|
| `notice` | Aviso informativo. Hoy solo el aviso legal, la primera vez que se usa la herramienta | `code` (`legal`), `message` |
| `scan.start` | Antes de ejecutar nada | `target{type,value}`, `depth`, `modules[]`, `skipped[{module,message}]`, `budget{max_entities,max_requests,max_seconds}` (`null` = sin límite) |
| `module.start` | Un módulo empieza sobre una entidad | `module`, `entity` (clave `tipo:valor`) |
| `module.end` | Ese módulo termina | `module`, `entity`, `status`, `entities`, `requests`, `cache_hits`, `duration_ms`, `message` |
| `entity` | Entidad nueva (ya deduplicada y normalizada) | `entity{type,value,data,source,parent,observations[{module,query,at}],first_seen,last_seen,confidence}` |
| `progress` | Tras cada `module.end` | `done`, `total` (ejecuciones conocidas hasta ahora; crece al pivotear), `entities`, `requests` |
| `scan.end` | Siempre el último | `status`, `scan_id` (`null` con `--no-save`), `exit_code`; salvo con `failed`, también `entities` y `finished_at`; con `failed`, en su lugar `message` |

- `module.end.status`: `ok`, `empty` (respondió sin datos), `error`, `quota` (la fuente rechazó
  por límite de uso), `skipped` (no aplica, o cancelado).
- `scan.end.status`: `complete`, `truncated` (se agotó el presupuesto: resultado incompleto),
  `cancelled` o `failed` (error interno).
- Todo `module.start` tiene su `module.end`, también si el módulo se cancela. Los módulos que no
  llegan a arrancar (activos sin `--active`, falta la API key) no emiten `module.*`: constan en
  `scan.start.skipped`.
- `entity.source` es la primera fuente que vio la entidad. `entity.observations` lista cada vez
  que un módulo la vio: `module`, `query` (clave de la entidad sobre la que corrió) y `at` (ISO 8601
  UTC). El evento `entity` se emite al **descubrirla**, así que trae solo la primera observación;
  las que lleguen después de otros módulos constan en la salida `--json` (`entities[]`) y en la BD.
- `scan.end` añade `evidence_digest` si el scan guardó evidencias (`--evidence`).
- `entity.first_seen` y `entity.last_seen` (ISO 8601 UTC, o `null` en datos antiguos) son la primera y
  la última observación de la entidad en el scan, no la fecha del dato de un tercero. En el evento
  `entity` coinciden (solo hay una observación).
- `entity.confidence` (`bajo`, `medio`, `alto` o `null`) se calcula **al terminar el scan**: el evento
  `entity` lo lleva siempre a `null`; el valor está en `--json` y en `show`.
- `scope` (`{"domains": [...], "ips": [...], "exclude": [...]}`, o ausente/`null` sin `--scope`) va en
  `scan.start` y en `scan_result`. Lo que cae fuera del alcance no genera evento `entity`: consta
  como `events[]` con `kind: "skipped"`, `module: "engine"` y `message: "fuera de alcance: <clave>"`.
- `purpose` (texto, o ausente/`null` sin `--purpose`) va en `scan.start` y en `scan_result`. Con
  `require_purpose` activo, un scan de email o username sin `--purpose` termina con código 2 antes de
  empezar (no emite `scan.start`).
- `--quiet` suprime la salida legible (no afecta a `--ndjson` ni a `--json`).

## Cancelar: `--control-stdin`

Con esta opción la CLI lee órdenes de **stdin**, una línea JSON cada una:

```json
{"cmd": "cancel"}
```

Se cancelan los módulos en curso, **se conserva y se guarda lo ya obtenido** y el proceso termina
con `scan.end` (`status: "cancelled"`) y código **130**. Si stdin se **cierra** (el cliente murió),
también se cancela. Las líneas que no son una orden conocida se ignoran. Ctrl+C hace lo mismo.

Es necesario porque en Windows `QProcess.terminate()` no detiene una aplicación de consola y
matarla (`kill()`) perdería el resultado parcial. **Mantén stdin abierto** mientras dure el scan:
una CLI lanzada con `--control-stdin` y sin stdin se cancela al instante.

## Registro de diagnóstico

`--verbose` y `--log-file` (opciones globales, antes de la orden) emiten un registro JSON para
diagnosticar. **No forma parte del contrato**: su contenido puede cambiar entre versiones; para
integrarse usa `--ndjson` y `--json`. `--verbose` escribe en `stderr`, así que `stdout` sigue limpio.

## Códigos de salida

| Código | Significado |
|---|---|
| `0` | Terminó sin incidencias |
| `1` | Error interno (excepción no prevista) |
| `2` | Uso incorrecto o entrada inválida (convención de `click`) |
| `3` | Terminó, pero algún módulo falló (también `doctor` si alguna fuente falla) |
| `4` | Terminó **incompleto** por agotar el presupuesto (`--max-entities/--max-requests/--max-time`) |
| `5` | Solo `verify`: alguna evidencia no coincide con su huella (o con `--digest`) |
| `130` | Cancelado |

Si coinciden varios motivos gana el más grave: `130` > `4` > `3`. Un módulo `skipped` no cuenta
como fallo.

## Salidas `--json`

Un único documento JSON por stdout.

| Orden | Esquema (`$defs`) | Contenido |
|---|---|---|
| `scan`, `domain`, `ip`, `email`, `username`, `show` | `scan_result` | Resultado completo: `target`, `entities`, `events`, `runs` (estado por módulo), `evidence` (metadatos y SHA-256 de cada respuesta guardada con `--evidence`, sin el cuerpo), `evidence_digest` (huella del conjunto o `null`), `truncated`, `status` |
| `modules` | `modules_output` | Módulos: `name`, `description`, `consumes`, `produces`, `passive`, `requires_key`, `key_configured`, `timeout` |
| `history` | `history_output` | Scans guardados |
| `doctor` | `doctor_output` | `module`, `verdict` (`ok`, `empty`, `fail`, `skipped`, `unchecked`), `detail`, `duration_ms`, `requests` |
| `config show` | `config_show_output` | Ruta y **nombres** de las keys configuradas (nunca valores, ni enmascarados) |
| `config set`, `config unset` | `config_key_output` | `name` y `configured`. `config set NOMBRE --stdin` lee el valor de stdin (así la key no aparece en la línea de comandos); también acepta el valor como argumento |
| `version` | `version_output` | `{"version": "0.2.0"}` |
| `export` | `export_output` | `scan_id`, `format`, `path` del informe generado |
| `verify` | `verify_output` | `scan_id`, `checked`, `ok`, `mismatches` (evidencias alteradas), `evidence_digest` recalculada, `digest_match` (`null` si no se pasó `--digest`). Sale con `5` si algo no coincide |

## Ejemplo

```
$ osineitor domain example.com -m dns --ndjson --no-save
{"v": 1, "ts": "…", "type": "scan.start", "target": {"type": "domain", "value": "example.com"}, "depth": 1, "modules": ["dns"], "skipped": [], "budget": {…}}
{"v": 1, "ts": "…", "type": "module.start", "module": "dns", "entity": "domain:example.com"}
{"v": 1, "ts": "…", "type": "entity", "entity": {"type": "record", "value": "dns:example.com", …}}
{"v": 1, "ts": "…", "type": "module.end", "module": "dns", "status": "ok", …}
{"v": 1, "ts": "…", "type": "progress", "done": 1, "total": 1, "entities": 2, "requests": 0}
{"v": 1, "ts": "…", "type": "scan.end", "status": "complete", "scan_id": null, "exit_code": 0, …}
```

## Qué no garantiza

- El orden entre eventos de módulos distintos (corren en paralelo); sí que `scan.start` va primero
  y `scan.end` último, y que `module.start` precede a su `module.end`.
- Que `progress.total` sea definitivo: al pivotear aparecen más ejecuciones.
- La latencia de arranque de la CLI (un proceso nuevo por orden): no está medida en Windows.

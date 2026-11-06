# Migración desde 0.x

Esta guía recoge los cambios que pueden romper algo al actualizar desde una versión 0.x, tomados del
[CHANGELOG](https://github.com/jmstudio14/OSINEITOR/blob/main/CHANGELOG.md). La versión 1.0.0 fija lo que cubre el
[compromiso de estabilidad](ESTABILIDAD.md); si al publicarla hubiera otros cambios incompatibles, se
añadirán aquí.

## Antes de actualizar

1. Haz una copia de la base de datos de scans y de `config.toml`. `osineitor config show` indica las
   rutas.
2. Actualiza: `pip install --upgrade osineitor`.
3. Ejecuta `osineitor doctor`.

La base de datos se **migra sola** la primera vez que se abre (hoy está en la versión 8), sin perder
scans. Es una migración solo hacia delante: una base creada por una versión más nueva se rechaza en
una más antigua. Por eso la copia del paso 1.

## Cambios que pueden afectar a tus scripts

| Desde | Cambio | Qué hacer |
|---|---|---|
| 0.2.0 | Un scan que termina con módulos fallidos sale con código `3` (antes `0`), y uno truncado con `4` | Si un script comprobaba `== 0`, decide si `3` es un error para ti |
| 0.2.0 | `doctor` con fallos sale con `3` (antes `2`) | Igual; `2` queda para uso incorrecto |
| 0.2.0 | En Windows la configuración vive en `%APPDATA%\osineitor` y los datos en `%LOCALAPPDATA%\osineitor` | Comprueba la ruta con `osineitor config show`; se pueden fijar con `OSINEITOR_CONFIG_DIR` y `OSINEITOR_DATA_DIR` |
| 0.2.0 | `dns` falla con error si el resolvedor no responde (antes devolvía un vacío que parecía «sin registros») | Un `error` en `runs` ya no significa «sin datos» |
| 0.4.0 | `scan` interpreta un username con forma `AS1234` como un ASN | Para tratarlo como username usa `osineitor username` |
| 0.4.0 | Con `--proxy`, los módulos de conexión directa quedan omitidos con un mensaje | Si procesabas ese texto, ha cambiado |

## Cambios aditivos que no rompen nada

Se listan para saber qué hay de nuevo, no porque haya que hacer algo:

- Códigos de salida nuevos que solo emiten órdenes nuevas: `5` (`verify`), `10` y `11`
  (`watch run`) y `12` (`summarize`).
- Campos nuevos y opcionales en las salidas `--json` y NDJSON (`observations`, `purpose`, `plugin`…).
  Los consumidores deben ignorar los campos desconocidos.
- Órdenes nuevas: `presets`, `diff`, `verify`, `export` con más formatos, `update-data`, `watch`,
  `purge` y `summarize`.
- Tipos de entidad nuevos (`asn`, `netblock`, `certificate`, `technology`, `phone`, `finding`…): un
  consumidor que filtre por tipo no los verá hasta que los pida.

## Si algo falla

Abre una incidencia con la salida de `osineitor version` y, si procede, la de `osineitor doctor --json`.

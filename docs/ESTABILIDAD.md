# Compromiso de estabilidad

Desde la versión 1.0.0 OSINEITOR sigue [SemVer](https://semver.org/lang/es/) de forma estricta sobre
tres superficies. Lo que no figura aquí puede cambiar en cualquier versión menor.

| Versión | Qué puede cambiar en las superficies cubiertas |
|---|---|
| Parche (`1.0.x`) | Solo correcciones. Nada que obligue a cambiar un script |
| Menor (`1.x.0`) | Solo adiciones compatibles y avisos de obsolescencia |
| Mayor (`x.0.0`) | Eliminaciones y cambios incompatibles, con [guía de migración](MIGRACION.md) |

## Qué está cubierto

### 1. La CLI

- Los **nombres** de las órdenes y de sus opciones, y el significado de sus valores.
- Los **códigos de salida** documentados en [CLI_CONTRACT.md](CLI_CONTRACT.md#códigos-de-salida):
  `0`, `1`, `2`, `3`, `4`, `5`, `10`, `11`, `12` y `130`. Se pueden añadir códigos nuevos para
  órdenes nuevas; no cambia el significado de uno existente.
- La salida estructurada: `--json` y `--ndjson`, descritas por
  [`cli-contract.schema.json`](cli-contract.schema.json). Los cambios son **aditivos**: campos
  nuevos y opcionales. Quien consuma estas salidas debe ignorar los campos que no conozca. La
  versión del flujo NDJSON va en el campo `v` de cada evento.

### 2. Los formatos de exportación

- `json`: es la salida `scan_result` del contrato.
- `csv`, `csv-relations` y `csv-findings`: las columnas existentes conservan nombre y significado; se
  pueden añadir columnas al final.
- `graphml`, `gexf` y `cypher`: tipos de nodo, relaciones y propiedades existentes se mantienen.

Los informes `md` y `html` son para leer: su maquetación puede cambiar en una versión menor.

### 3. La API de librería y de plugins

- Los nombres de `osineitor.__all__` (`Scanner`, `ScanResult`, `Entity`, `EntityType`,
  `ScanInputError` y `__version__`) con la forma descrita en [API.md](API.md).
- El contrato de un módulo de plugin: la clase `Module` con sus atributos, `emit`, `try_emit` y
  `Context`, tal como los documenta [API.md](API.md#plugins).

Todo lo demás de `osineitor.*` (módulos internos, funciones sin documentar) es interno y puede
cambiar sin aviso.

## Qué no está cubierto

- El texto de la salida legible, de los mensajes de error y del registro (`--verbose`).
- Los datos que cada módulo guarda en `Entity.data`, salvo los campos que documente
  [MODULES.md](MODULES.md): dependen de lo que devuelva la fuente de un tercero.
- Qué fuentes consulta un módulo, o que una fuente siga existiendo: una API de terceros puede
  desaparecer. En ese caso el módulo falla con un error claro y se actualiza en una versión menor.
- El esquema interno de la base de datos. Se migra solo hacia delante y de forma automática; una base
  más nueva que el programa se rechaza. No se garantiza abrirla con otras herramientas.
- La lista exacta de módulos y la composición de los presets: se pueden añadir módulos en versiones
  menores (y un preset puede incluirlos).

## Política de obsolescencia

1. Lo que va a desaparecer se **marca como obsoleto** en una versión menor: aparece en la sección
   «Obsoleto» del [CHANGELOG](https://github.com/jmstudio14/OSINEITOR/blob/main/CHANGELOG.md), en la documentación y, si es una opción o una orden,
   con un aviso por stderr (nunca por stdout, para no romper `--json`).
2. Sigue funcionando **al menos dos versiones menores** después del aviso.
3. Se elimina solo en la **siguiente versión mayor**, nunca antes de cumplirse lo anterior.

Una vulnerabilidad de seguridad puede obligar a saltarse este calendario; en ese caso se explica en
el CHANGELOG y en un aviso de seguridad.

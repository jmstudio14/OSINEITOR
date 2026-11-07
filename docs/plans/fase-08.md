# Plan de la fase 8 · Interoperabilidad y extensibilidad (v0.9.0)

Sale del [ROADMAP](../../ROADMAP.md) (fase 8). Criterios comunes, de
[`CLAUDE.md`](../../CLAUDE.md) y de las fases anteriores:

- Salida estructurada de la CLI solo con cambios aditivos; el esquema
  `docs/cli-contract.schema.json` se actualiza en el mismo cambio.
- README, `docs/` y `CHANGELOG.md` al día.
- Criterio de salida: `ruff check .`, `ruff format --check .` y `python -m pytest -q` en verde.

## Estado

| ID | P | Entregable | Estado | Decisión |
|---|---|---|---|---|
| F8.4 | M | Streaming NDJSON | ✅ | Hecho en v0.2.0 |
| F8.5 | M | API de librería | ✅ | `osineitor.Scanner` (`scan`, `ascan`, `cancel`) |
| F8.6 | M | Plugins externos | ✅ | *Entry points* del grupo `osineitor.modules` |
| F8.3 | S | Formatos de grafo | ✅ | GraphML, GEXF y script Cypher, sin dependencias |
| F8.1 | S | Exportación STIX 2.1 | ✅ | Cierre del roadmap: `export -f stix` (extra `osineitor[stix]`). |
| F8.7 | S | Importación | 🟡 | Solo `osineitor import nmap` (XML `-oX`, guardado como un scan, sin pivoteo). Aplazado: `--targets-file` obliga a repetir el scan por objetivo y los formatos de Subfinder, Amass y Maigret no están verificados |
| F8.2 | C | Exportación a MISP | ✅ | Cierre del roadmap: `export -f misp` (extra `osineitor[misp]`); no se ha probado contra un servidor MISP. |

## Decisiones

- **`Scanner` no duplica la CLI, pero tampoco la reemplaza.** La CLI sigue montando su propio
  `Engine` (barra de progreso, señal de interrupción, NDJSON); `Scanner` monta el mismo con
  `HttpClient`, `Budget` y `ResponseCache`. Lo único compartido es `MAX_PURPOSE` y
  `PURPOSE_REQUIRED_FOR`, que ahora viven en `osineitor.scanner` y la CLI importa de allí. Unificar
  los dos caminos queda como mejora, no se pidió.
- **Sin guardado automático.** Un scan de la librería devuelve el `ScanResult` y nada más; guardarlo
  es una línea con `Storage` (documentada). Evita que una librería escriba en la base del usuario
  sin que lo pida.
- **`None` = sin límite** en los parámetros del presupuesto (la CLI usa `0`): es lo idiomático en
  Python y es lo que ya guarda `Budget`.
- **Errores tipados.** Una petición inválida lanza `ScanInputError(ValueError)` antes de abrir
  conexiones, en lugar de dejar escapar `ValidationError` o `InvalidEntityValue`.
- **Importación ligera.** `osineitor/__init__.py` carga los nombres públicos al pedirlos (PEP 562):
  `import osineitor` para leer `__version__` (lo hace la GUI) no arrastra el motor. Un test lo
  comprueba en un proceso aparte.
- **Un solo cancelador seguro entre hilos.** `Scanner.cancel()` usa `call_soon_threadsafe` sobre el
  bucle del scan, porque `asyncio.Event` no es seguro entre hilos.
- **Plugins: aislar, no confiar.** Cada *entry point* se carga dentro de un `try`: un plugin roto,
  mal formado o con un nombre repetido se omite entero y se avisa (`registry.plugin_problems`,
  stderr de `osineitor modules` y registro). Un plugin nunca sustituye a un módulo incluido. El
  descubrimiento no es un límite de seguridad: el código del plugin se ejecuta con los permisos del
  usuario, y la documentación lo dice.
- **Marca `plugin` en `modules --json`**: campo opcional nuevo en `modules_output`; la tabla humana
  añade «· plugin» al tipo.
- **Grafo.** Las tres exportaciones usan las mismas aristas que el informe HTML (padre → hija,
  solo si el padre está en el scan). Los valores son de terceros: los caracteres de control no
  válidos en XML 1.0 se descartan en GraphML y GEXF, y en Cypher se descartan y se escapan comillas,
  barras y saltos de línea.

## Verificación

- `tests/test_scanner.py` (18): scan síncrono y asíncrono, tipo forzado, opciones hasta el motor,
  cancelación desde otro hilo, rechazo de dos scans simultáneos, errores de entrada, propósito
  exigido, nombres públicos perezosos e importación ligera en proceso aparte.
- `tests/test_plugins.py` (12): instalan un paquete real (módulo + `.dist-info` con
  `entry_points.txt`) en un directorio temporal y comprueban que aparece en `modules`, que corre en
  el motor y que cada tipo de fallo se aísla.
- `tests/test_graph_export.py` (5): GraphML y GEXF se parsean como XML con texto hostil, aristas
  sin nodos huérfanos y script Cypher con cadenas escapadas.
- **No comprobado:** el criterio «plugin de ejemplo publicado en un repositorio aparte» (no hay
  repositorio ni `pip install` real), un ejecutable congelado con plugins, Cypher contra Neo4j y
  GraphML/GEXF abiertos en Gephi.

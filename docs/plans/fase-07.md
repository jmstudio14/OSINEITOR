# Plan de la fase 7 · Hallazgos, análisis y casos (v0.8.0)

Sale del [ROADMAP](../../ROADMAP.md) (fase 7). Criterios comunes, de
[`CLAUDE.md`](../../CLAUDE.md) y de las fases anteriores:

- Un módulo nuevo es una subclase de `Module`, añadida a `modules/_manifest.py`, con `canary` o
  `probe_url`.
- Toda salida estructurada de la CLI sigue el contrato (`docs/CLI_CONTRACT.md`): cambios solo
  aditivos y el esquema `docs/cli-contract.schema.json` se actualiza en el mismo cambio.
- README, `docs/MODULES.md` y `CHANGELOG.md` al día.
- Criterio de salida: `ruff check .`, `ruff format --check .` y `python -m pytest -q` en verde.

## Estado

| ID | P | Entregable | Estado | Decisión |
|---|---|---|---|---|
| F7.8 | M | Motor de hallazgos | ✅ | Reglas YAML + analizador `findings`; el hallazgo es una entidad `finding` |
| F7.3 | M | `osineitor diff A B` | ✅ | Compara por clave de entidad; salida `--json` en el contrato |
| F7.11 | M | Exportación CSV | ✅ | Tres formatos (`csv`, `csv-relations`, `csv-findings`) |
| F7.1 | M | Grafo en el informe HTML | ✅ | JS propio en línea con `<canvas>`; sin librería ni CDN |
| F7.2 | S | Casos | ✅ | Cierre del roadmap: `osineitor case new/add/note/show/list`. |
| F7.4 | S | Línea temporal | ✅ | Cierre del roadmap: `osineitor timeline N`. |
| F7.5 | S | Búsqueda global | ✅ | Cierre del roadmap: `osineitor search VALOR`. |
| F7.6 | S | Correlación entre scans | ✅ | Cierre del roadmap: `case add` y `case show` avisan de datos identificadores ya vistos en otro caso. |
| F7.7 | S | Informe ejecutivo | ✅ | Cierre del roadmap: formato de exportación `executive`. |
| F7.9 | S | Puntuación de riesgo | ✅ | Cierre del roadmap: `osineitor risk N`; es una heurística de priorización sin contrastar con scans reales. |
| F7.10 | S | Resolución de entidades | ✅ | Cierre del roadmap: `osineitor resolve N`: hipótesis con señales y puntuación, calculadas al consultar. |
| F7.12 | S | Informe de superficie de ataque | ✅ | Cierre del roadmap: formato de exportación `attack-surface`. |

Los *S* no están bloqueados por nada externo: se dejan por prioridad. Los cuatro *M* cumplen los
criterios de aceptación de la fase salvo el último punto, que depende de F7.10.

## Decisiones

- **Un hallazgo es una entidad.** Tipo `finding` (ya reservado en F3.1), emitido por un analizador
  en la pasada final. Así la base de datos, el JSON, los informes, el `diff` y `show` funcionan sin
  cambiar el esquema. `affected` lleva las claves de las entidades que lo justifican y `evidence`
  los campos que lo prueban. Un `finding` no recibe confianza (`confidence.assess` devuelve `None`).
- **Reglas declarativas.** `src/osineitor/data/rules/default.yml`; cada regla tiene `id`, `title`,
  `severity`, `type`, `value_prefix` opcional, condiciones `when`, `evidence` y `recommendation`.
  Operadores: `eq`, `ne`, `in`, `gt`, `gte`, `lt`, `lte`, `exists`, `missing`, `regex`, `contains`,
  `days_lte` y `root_domain`. Una regla mal formada falla al cargar (`RuleError`), no en mitad de un
  scan. El campo `subject` es lo que sigue al primer `:` del valor de un `record`.
- **Límites aceptados del motor.** `root_domain` solo reconoce `nombre.tld`; no cubre sufijos de
  varias etiquetas (`ejemplo.co.uk`) y prefiere un falso negativo a un falso positivo. Un
  certificado «caducado» puede ser uno antiguo ya sustituido (crt.sh los lista todos): la
  recomendación lo dice.
- **`diff` compara por clave** (`tipo:valor`). «Modificada» es la misma clave con algún campo de
  `data` distinto o presente solo en un lado. Los hallazgos salen también aparte para verlos de
  un vistazo. Dos scans de objetivos distintos se comparan igualmente, con `same_target: false`.
- **CSV.** `FORMATS` admite ahora extensiones compuestas (`entities.csv`, `relations.csv`,
  `findings.csv`), así que un mismo scan se exporta a tres ficheros sin pisarse. Los valores vienen
  de terceros: una celda que empieza por `=`, `+`, `-`, `@`, tabulador o retorno de carro lleva
  una comilla delante (inyección de fórmulas en hojas de cálculo).
- **Grafo.** Un `<canvas>` con diseño de fuerzas propio (~100 líneas de JS) en lugar de una
  librería: el informe sigue siendo un fichero único y no carga nada de Internet. Las aristas son la
  relación padre → entidad (`parent`). Máximo 1500 nodos (la repulsión es cuadrática); el informe
  avisa si recorta. Los datos van en un `<script type="application/json">` con todo `<` escrito
  como `<`, de modo que ni `</script>` ni `<!--` en un valor de terceros rompen la página.
  Las tablas siguen debajo como versión accesible.

## Verificación

- `tests/test_findings.py`: 22 pruebas, un caso positivo y otro negativo por regla, más validación
  del fichero de reglas y la pasada final del motor.
- `tests/test_diff.py`: altas, bajas, cambios, campos que aparecen o desaparecen, hallazgos, el
  comando y el rechazo de un scan inexistente; `diff_output` entra en el test de contrato.
- `tests/test_csv_report.py`: columnas, relaciones, hallazgos, neutralización de fórmulas y
  extensión del fichero exportado.
- `tests/test_graph.py`: datos del grafo, escape de `</script>` y `<!--`, tope de nodos y una
  ejecución del JS real en Node con 500 entidades (converge y dibuja; se omite si no hay Node).
- **No comprobado:** el aspecto y la fluidez en un navegador real. Solo se probó que el programa
  se ejecuta, converge y dibuja con un DOM simulado.

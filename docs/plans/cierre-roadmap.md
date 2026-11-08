# Plan de cierre del roadmap · entregables pendientes y parciales

Sale del [ROADMAP](../../ROADMAP.md) a 06-11-2026 (rama `feat/roadmap-f4-s`). Recoge todo lo que
seguía en ⬜ Pendiente o 🟡 Parcial y fija el orden y las decisiones. Los planes por fase
(`fase-NN.md`) siguen siendo el detalle de cada una; aquí solo va lo que cambia al cerrarlas.

Criterio de salida de cada bloque, común a todo el plan (de [`CLAUDE.md`](../../CLAUDE.md)):
`ruff check .`, `ruff format --check .` y `python -m pytest -q` en verde; README,
`docs/MODULES.md` y `CHANGELOG.md` al día; salida estructurada solo con cambios aditivos y
`docs/cli-contract.schema.json` actualizado en el mismo cambio.

## Lo que no se puede cerrar desde el código

No es pereza: necesita algo que solo tiene el autor. Se deja documentado y no se marca como hecho.

| ID | Motivo |
|---|---|
| G9 | Pruebas manuales en un Windows real (instalar, escanear, desinstalar); la CI no puede |
| F0.1 a F0.3 | Cuentas y API keys de `shodan`, `abuseipdb`, `greynoise`, `hibp`, `hunter_*` |
| F11.2 | Cuenta del mantenedor en PyPI (publicación con *trusted publishing*) |
| Verificación en vivo (D1) | Las fuentes nuevas se prueban con respuestas simuladas; ejecutarlas contra el servicio real queda para el autor |
| macOS | La CI lo incluye pero no se ha ejecutado en GitHub |

## Bloques, en orden de ejecución

El orden va de lo que no depende de nadie ni de ningún servicio externo a lo que exige un *spike*.

| Bloque | Entregables | Depende de |
|---|---|---|
| A · Núcleo y vigilancia | F1.15, F1.6, F9.4, F9.6 | — |
| B · Casos y análisis (fase 7) | F7.2, F7.5, F7.6, F7.4, F7.9, F7.10, F7.7, F7.12 | A (migración) |
| C · Interoperabilidad (fase 8) | F8.7 (resto), F8.1, F8.2 | — |
| D · IA (fase 10) | F10.4, F10.5 | B |
| E · Identidades (fase 5) | F5.6, F5.10, F5.11, F5.4, F5.5, F5.15 | — |
| F · Spikes y fuentes externas | F4.21 a F4.23, F5.1, F5.8, F5.12, F6.1, F6.3, F6.4, F6.8, F6.10, F6.13 a F6.16, F6.18, F4.17, F4.24 | *spike* de cada una |
| G · Cierre | F11.5, F9.7, documentación y recuento del ROADMAP | F |

## Decisiones

- **Comodín DNS (F1.15).** Se marca fusionando (`wildcard: true`) y no se pivota hacia sus IP; un
  sondeo de etiqueta aleatoria por zona y escaneo.
- **Supresión de ruido (F9.4).** `confirm` y `quiet` nunca pierden una alerta retenida: se entrega
  después o se reintenta.
- **Dominios parecidos (F9.6).** Un `record` por dominio parecido (no uno por escaneo), para que
  `watch` alerte de cada uno.
- **Correlación (F7.6).** Solo sobre los tipos que identifican (email, username, teléfono, cripto,
  dominio...), no sobre ruido como tecnologías o puertos.
- **Riesgo (F7.9).** La fórmula es una heurística de priorización y no está validada con scans
  reales; el desglose explica cada punto para que se pueda discutir.
- **Línea temporal (F7.4).** Solo cuentan las fechas que traen los datos, no la hora del scan.
- **Resolución de entidades (F7.10).** Se calcula al consultar, no se guarda como entidades, así que
  CSV y grafo no la llevan. Siempre es una hipótesis con sus señales; el avatar no se compara.
- **Amass.** No se importa ni se adapta: no hay un formato de salida estable que comprobar.
- **`--targets-file`.** Rechaza `--json` (varias salidas JSON mezcladas romperían el contrato).
- **STIX y MISP (F8.1, F8.2).** Extras opcionales; en MISP no se marca nada como indicador de
  detección y la distribución es 0. No se ha probado contra un servidor MISP.
- **MCP (F10.4).** Más estricto que el roadmap: ni siquiera hay un interruptor para módulos activos
  ni se aceptan ficheros locales.
- **Pivotes (F10.5).** Solo proponen; el comando lo ejecuta quien lo lea.
- **Stack Overflow (F5.11).** Solo coincidencia exacta de nombre visible, marcada
  `match: display_name` y sin `verified`.
- **Recursión de perfiles (F5.4, F5.5).** Solo APIs oficiales (DEV Community, Codeberg) y nada de
  HTML de terceros; los usernames declarados se emiten como entidades y los pivota el motor. Es una
  hipótesis: enlazar una cuenta no prueba que el perfil de partida sea de la persona investigada.
- **Maigret (F5.15).** El informe sale a un fichero, no a stdout: el adaptador usa una carpeta
  temporal y desactiva la recursión y la extracción de Maigret.
- **`reverse_ip` (F4.22).** Más de 50 hostnames = alojamiento compartido: se emite un resumen y no
  dominios, para no pivotar sobre terceros.
- **`analytics_ids` (F4.21).** Activo y autoritativo (lee la portada del propio objetivo); no busca
  otros dominios con el mismo ID.
- **Fuentes no incluidas.** Las que exigen una key, un servicio de pago, un binario o un navegador
  que los tests no pueden ejercitar, o cuyos términos no se han podido leer, quedan documentadas en
  `docs/MODULES.md` («Fuentes evaluadas y no incluidas») con su motivo.

## Estado final

Cerrados, con las excepciones de F8.7 (no se importa Amass) y F5.6 (`--tags`/`--top`, evaluado y no
incluido): bloques A, B, C, D y E; del bloque F, F4.21, F4.22, F5.1 y F5.12; del G, F9.7 (con la
regla `new-breach` ya existente y un test de extremo a extremo) y el recuento del ROADMAP.
Evaluados y no incluidos: el resto del bloque F y F11.5. Sin tocar: lo de la tabla «Lo que no se
puede cerrar desde el código».

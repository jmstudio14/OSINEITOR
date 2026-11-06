# Plan de la fase 10 · Asistencia con IA (v0.11.0)

Sale del [ROADMAP](../../ROADMAP.md) (fase 10). Criterios comunes, de
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
| F10.2 | M | Citas obligatorias y verificadas | ✅ | `ai.validate`: sin cita, cita inexistente o dato literal ausente de lo citado |
| F10.3 | M | Modelos locales y remotos | ✅ | Ollama, OpenAI compatible y Anthropic; `consent_remote: true` para todo lo que no sea loopback |
| F10.6 | M | Evaluación | ✅ | `scripts/eval_ai.py` + corpus etiquetado; números en `docs/IA.md` |
| F10.1 | S | `osineitor summarize <scan>` | ✅ | Solo lee scans guardados; muestra únicamente frases validadas |
| F10.7 | S | Resúmenes basados en hallazgos | ✅ | Los hallazgos van primero en los hechos, con evidencia y entidades afectadas |
| F10.4 | S | Servidor MCP | ⬜ | Aplazado: exige un servidor JSON-RPC por stdio (o la dependencia `mcp`) y decidir qué herramientas expone; no es parte de la ayuda al análisis |
| F10.5 | C | Sugerencia de pivotes | ⬜ | Aplazado: es *Could*; además necesita un segundo prompt con su propia validación |

## Decisiones

- **Desactivada por defecto, sin dependencias.** No hay `ai.yml`, no hay IA. Se usa `HttpClient`
  (httpx ya es dependencia), así que **no se crea el extra `osineitor[ai]`** del ROADMAP: un extra
  vacío no instalaría nada. El criterio «no añade dependencias a la instalación base» se cumple.
- **Consentimiento en el fichero, no en un flag.** `consent_remote: true` debe ser un `true` YAML
  (no `"yes"`, no `1`) y sin él el fichero se rechaza al cargar, antes de cualquier petición. El
  criterio de «local» es solo Ollama en loopback; un Ollama en otra máquina de la LAN es remoto. Un
  flag de línea de comandos se tecleará por costumbre; un fichero revisado, no.
- **La clave solo viaja por entorno.** `api_key_env` nombra la variable; `api_key:` en el fichero se
  rechaza como clave desconocida. Con clave, `url` debe ser `https://`.
- **Errores sin secretos.** Un error de red sustituye el texto de la excepción por su nombre (puede
  llevar la URL o la clave), igual que en `notify.py`.
- **Guardia de red.** Los proveedores remotos pasan por `HttpClient` con la guardia activa; solo el
  Ollama en loopback (o un `allow_private: true` explícito) puede ir a una red privada.
- **Hechos numerados, no el JSON del scan.** El modelo ve `[E3] tipo: valor · datos` y debe citar
  `E#`. Identificadores cortos y estables dentro de la petición, imposibles de confundir con un dato.
  Las entidades se ordenan: objetivo, hallazgos (por gravedad), vulnerabilidades, filtraciones,
  servicios, registros, certificados, tecnologías y el resto; el tope son 120 y se informa de las
  omitidas.
- **Los valores de terceros se aplanan.** Un registro DNS con saltos de línea no puede inventar una
  línea `[E99]` ni abrir una instrucción nueva; además el prompt dice que los hechos son datos.
- **Validar la forma y los datos literales, no el sentido.** El validador comprueba (1) que hay cita,
  (2) que existe, y (3) que cada IP, CVE, correo y host de la frase aparece en los hechos que cita.
  La (3) cubre las invenciones más típicas y se puede automatizar sin otro modelo. Comprobar que la
  frase *significa* lo que el hecho exigiría necesitaría un segundo modelo juez, que traería sus
  propios errores; se descarta y el límite se documenta y se mide en vez de ocultarlo.
- **Mostrar solo lo validado.** Las frases rechazadas no se muestran ni se «corrigen»: se cuentan y,
  con `--json`, se listan con su motivo. Si no pasa ninguna, error (código `12`). Alternativa
  descartada: reintentar con el error como realimentación; multiplica el coste y los datos enviados.
- **Un código de salida propio.** `12` solo para `summarize`; reutilizar `3` (módulos fallidos) o `1`
  (excepción) mezclaría significados.
- **Corpus de evaluación propio y adversarial.** Mezcla frases respaldadas con defectos de cada clase.
  Por eso sus porcentajes **no son la tasa de ningún modelo real**: la proporción la fija quien lo
  escribe. Lo que se publica es qué clases detecta el validador y cuáles no. La tasa de un modelo
  concreto la mide `--live`, que el usuario ejecuta con su proveedor.

## Verificación

- `tests/test_ai.py` (53): configuración (10 ficheros inválidos, consentimiento, clave solo por
  entorno, `https` con clave, Ollama remoto), hechos (orden, tope, valores hostiles, recorte),
  validador (cada motivo de rechazo, literales de otro hecho que no cuentan, cita final pegada,
  encabezados), los tres proveedores con la petición exacta que envían, errores sin secretos,
  respuestas mal formadas, guardia de red, CLI de extremo a extremo (códigos `0`, `2`, `12`; nada
  sale sin consentimiento) y evaluación.
- `tests/test_contract.py`: `summary_output` valida contra el esquema.
- `test_published_numbers_match_the_evaluation`: los números de `docs/IA.md` coinciden con los del
  corpus; no pueden quedar desfasados.
- **No comprobado:** ninguna petición a Ollama, OpenAI ni Anthropic reales. Las peticiones y las
  respuestas siguen el formato documentado de cada API pero se probaron con respuestas simuladas; un
  cambio de la API del proveedor no lo detectaría ningún test. Tampoco se ha medido la tasa de un
  modelo real (F10.6 pide publicarla «junto a la versión»: queda pendiente hasta ejecutar `--live`).

# Asistencia con IA

`osineitor summarize <scan>` pide a un modelo de lenguaje un resumen de un scan **guardado** y solo
muestra las frases que superan una validación automática de citas. Está **desactivado por defecto**:
sin el fichero `ai.yml` no se envía nada a ningún modelo, y no añade dependencias a la instalación
(usa el mismo cliente HTTP que los módulos, así que no hace falta ningún extra `osineitor[ai]`).

> Un modelo de lenguaje puede equivocarse con aplomo. El resumen es una ayuda para leer más rápido,
> no una fuente: lo que cuenta son las entidades y las evidencias del scan, a las que cada frase
> remite.

## Activarlo

`ai.yml` va en la carpeta de configuración (`osineitor config show` muestra la ruta) o se indica con
`--config`.

```yaml
enabled: true
provider: ollama              # ollama (local) | openai (compatible) | anthropic
model: llama3.1
url: http://localhost:11434   # opcional; cada proveedor trae el suyo
api_key_env: OPENAI_API_KEY   # openai y anthropic; la clave se lee del entorno, nunca del fichero
consent_remote: true          # obligatorio si los datos salen de tu máquina
allow_private: false          # permite un servidor en red privada que no sea loopback
timeout: 120
```

| Proveedor | Dónde corre | Consentimiento |
|---|---|---|
| `ollama` en `localhost`, `127.0.0.1` o `::1` | Tu máquina: los datos no salen | No hace falta |
| `ollama` en otro servidor | Ese servidor | `consent_remote: true` |
| `openai` (cualquier servidor compatible con `/chat/completions`) | El de la `url` | `consent_remote: true` |
| `anthropic` | La API de Anthropic o la `url` | `consent_remote: true` |

- Sin `consent_remote: true` el fichero **se rechaza** al cargarlo y no se hace ninguna petición; el
  error nombra el servidor al que irían los datos.
- Antes de enviar, `summarize` avisa por stderr de adónde va el scan (`en tu máquina` o
  `a <servidor>`).
- Con clave de API, `url` debe ser `https://`. Las peticiones salen por el cliente HTTP del proyecto:
  un servidor en red privada exige `allow_private: true`.
- Los errores nunca incluyen la clave ni la URL.

**Qué se envía:** hasta 120 «hechos» del scan (el objetivo, los hallazgos, vulnerabilidades,
filtraciones, servicios… con sus datos, recortados a 300 caracteres). Pueden incluir emails, usernames
y otros datos personales: con un proveedor remoto salen de tu máquina. Ver
[uso responsable](USO_RESPONSABLE.md).

## Cómo se garantizan las citas

1. El modelo recibe solo hechos numerados, **los hallazgos primero** con su evidencia y las entidades
   que afectan:

   ```
   [E1] domain: example.com
   [E2] hallazgo high: SPF permisivo · afecta a: record:dns:example.com · evidencia: {"SPF": "v=spf1 +all"}
   ```

2. Se le pide una afirmación por frase y las citas al final: `… permite cualquier origen [E2].`
3. `osineitor.ai.validate` descarta toda frase que:
   - no tiene cita (`sin cita`),
   - cita un hecho que no existe (`cita inexistente: E99`),
   - contiene una IP, un CVE, un correo o un nombre de host que **no figura en los hechos que cita**
     (`dato que no figura en los hechos citados: …`).
4. Solo se muestran las frases que pasan. Las descartadas se cuentan y, con `--json`, se listan en
   `rejected` con su motivo. Si no pasa ninguna, `summarize` sale con el código `12`.

Los valores que vienen de terceros se aplanan a una sola línea antes de entrar en el prompt (un
registro DNS no puede inventar una línea `[E99]`), y el prompt indica al modelo que los hechos son
datos, no instrucciones.

## Límites

- **El validador comprueba la forma, no el sentido.** No sabe si «el SPF está bien configurado
  `[E2]`» contradice al hecho `E2`. Es el límite medido en la evaluación de abajo: una frase con cita
  válida y sin datos literales nuevos pasa aunque sea falsa.
- Una inyección de instrucciones en un dato de un tercero no se puede descartar: la validación limita
  qué puede aparecer (todo debe citar un hecho real), no qué puede afirmar sobre él.
- Un scan truncado o con módulos caídos produce un resumen de lo que hay: «no se vio» no es «no
  existe». El prompt incluye el estado del scan, pero el modelo puede ignorarlo.
- No se ha probado contra un modelo real en esta versión: el comportamiento de cada proveedor se
  verificó con respuestas simuladas, siguiendo el formato documentado de su API.

## Evaluación

`python scripts/eval_ai.py` mide el validador con un corpus propio, etiquetado a mano
(`tests/ai_eval/corpus.json`): un scan de ejemplo y 26 frases, unas respaldadas por los hechos y otras
con un defecto concreto. Los números salen de ese corpus; **no son la tasa de ningún modelo real**,
porque la proporción de cada defecto la fijó quien escribió el corpus.

| Resultado | Valor |
|---|---|
| Frases sin respaldo con defecto estructural (sin cita, cita inexistente, dato inventado) rechazadas | 12 de 12 |
| Frases respaldadas rechazadas por error | 0 de 9 |
| Frases sin respaldo con defecto semántico (cita real, afirmación falsa) rechazadas | 0 de 5 |
| Frases sin respaldo entre las que pasan el validador | 5 de 14 aceptadas |

Es decir: el validador garantiza que el 100 % de lo que se muestra tiene una cita válida y ningún
dato literal inventado, pero no puede asegurar que cada frase diga lo que dice su hecho. Las 5 que
pasan sin respaldo son todas del tipo semántico.

Para medir un modelo concreto, `python scripts/eval_ai.py --live` envía el scan de ejemplo al
proveedor de `ai.yml` y cuenta qué parte de sus frases descarta el validador. **Esa cifra no está
publicada**: no se ha ejecutado contra ningún modelo (ver [plan de la fase 10](https://github.com/jmstudio14/OSINEITOR/blob/main/docs/plans/fase-10.md)).

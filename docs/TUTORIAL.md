# Tutorial: tu primera investigación

Este recorrido investiga un dominio **que sea tuyo** (o que tengas autorización expresa para
analizar), guarda el resultado, lo exporta y detecta qué cambia una semana después. Los ejemplos usan
`example.com`: sustitúyelo por el tuyo.

> Antes de empezar, lee el [uso responsable](USO_RESPONSABLE.md). Los scans consultan fuentes
> abiertas, pero seguirán siendo actividad sobre un objetivo concreto.

## 1. Instalar y comprobar

```bash
pip install -e .
osineitor version
osineitor modules
```

`osineitor modules` lista los módulos y dice cuáles necesitan una API key que aún no has configurado.
Muchos funcionan sin ninguna. Para comprobar que las fuentes responden desde tu red:

```bash
osineitor doctor
```

## 2. Un primer scan

```bash
osineitor domain example.com --preset quick
```

`domain` investiga solo el dominio (profundidad 1); `--preset quick` elige un conjunto de módulos
rápido y pasivo. Verás una tabla con las entidades descubiertas (subdominios, IPs, registros) y, tras
ella, el estado de cada módulo: `ok`, `empty` (sin datos), `skipped` (no aplica) o `error`.

Cada scan se guarda en una base de datos local. Para ver los guardados:

```bash
osineitor history
```

## 3. Pivotar: más profundidad

```bash
osineitor scan example.com --depth 2
```

Con profundidad 2 las entidades nuevas (por ejemplo, las IPs a las que resuelve el dominio) pasan a
los módulos que las aceptan. Cada nivel multiplica las peticiones; si quieres acotar el coste usa
`--max-requests` o `--max-time`. Si el presupuesto se agota, el resultado queda marcado como
incompleto y la orden sale con código `4`.

## 4. Leer el resultado

```bash
osineitor show 1
osineitor show 1 --json
```

El número es el del scan en `history`. La columna «Confianza» orienta sobre qué revisar primero; no
demuestra que un dato sea cierto. Los hallazgos (SPF permisivo, un certificado a punto de caducar,
una vulnerabilidad conocida…) aparecen como entidades de tipo `finding` con su severidad y una
recomendación.

## 5. Exportar un informe

```bash
osineitor export 1 -f html
osineitor export 1 -f md -o informe.md
```

Los informes HTML no cargan nada de Internet. Hay también `json`, `csv`, `graphml`, `gexf` y
`cypher` para llevar el resultado a otras herramientas (hojas de cálculo, Gephi, Neo4j).

## 6. Dejar constancia: evidencias

```bash
osineitor domain example.com --evidence
osineitor verify 2
```

Con `--evidence` se guarda cada respuesta original con su huella SHA-256. `verify` comprueba más
tarde que ninguna se ha alterado. Ver [Evidencias](EVIDENCIA.md).

## 7. Ver qué ha cambiado

Pasado un tiempo, repite el scan y compáralo con el anterior:

```bash
osineitor domain example.com --preset quick
osineitor diff 1 3
```

`diff` lista las entidades y los hallazgos nuevos, los desaparecidos y los modificados.

## 8. Automatizarlo

Para que sea la herramienta quien repita el scan y avise solo de lo nuevo, escribe un `watch.yml` y
ejecuta `osineitor watch run` desde cron, systemd o GitHub Actions. Todo el detalle está en
[vigilancia continua](VIGILANCIA.md). Para pasar un scan a texto con un modelo de lenguaje
(desactivado por defecto) mira [asistencia con IA](IA.md).

## Siguientes pasos

- [Guía de uso](USO.md): todas las opciones, presets, proxy, alcance y propósito.
- [Módulos](MODULES.md): qué hace cada fuente y sus límites.
- [Librería y plugins](API.md): usar OSINEITOR desde Python o añadir módulos propios.

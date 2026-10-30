# Evidencia y verificación

`--evidence` conserva la respuesta original de cada fuente para que un dato de un informe se pueda
rastrear hasta la consulta que lo produjo y comprobar que no se ha tocado después. Sigue la idea de
preservación del Protocolo de Berkeley: guardar lo observado, cuándo y cómo, con una huella.

## Qué se guarda

Por cada respuesta, en la tabla `evidence` de la base de datos del scan:

| Campo | Contenido |
|---|---|
| `module`, `entity` | Módulo que consultó y entidad sobre la que corrió (`domain:example.com`). Son los mismos valores que `module` y `query` de las observaciones de cada entidad: así se une un dato con su evidencia |
| `kind`, `method`, `status` | `http` (método y código HTTP) o `dns` (`DNS`, sin código) |
| `url` | URL consultada con su consulta completa, **sin credenciales ni valores de API key** (`***`). En DNS, `dns://nombre/TIPO` |
| `at` | Fecha y hora UTC de la captura |
| `sha256`, `size`, `truncated` | Huella del cuerpo guardado, tamaño original y si se recortó |
| cuerpo | La respuesta tal cual. **No** sale en `--json` ni en los informes (estos llevan solo los metadatos y el hash), solo en la base |

- Cada salto de una redirección y cada consulta DNS dejan su propia evidencia; los reintentos
  automáticos dejan solo la respuesta definitiva. Las respuestas negativas de DNS (`NXDOMAIN`,
  `NOANSWER`) también constan.
- Un cuerpo de más de 2 MB se guarda recortado (`truncated`) y la huella es la del trozo guardado.
- No se guardan cabeceras. Las respuestas de error de la red (sin respuesta) no dejan evidencia.

## Cómo se comprueba

```bash
osineitor verify 3              # recalcula el SHA-256 de cada cuerpo y lo compara con el guardado
osineitor verify 3 --digest HUELLA
osineitor verify 3 --json       # esquema verify_output (ver CLI_CONTRACT.md)
```

Sale con `0` si todo coincide y con `5` si alguna evidencia o la huella indicada no coincide. Un scan
sin evidencias sale con `0` y avisa. La **huella de evidencias** (`evidence_digest`) es el SHA-256 de
las huellas ordenadas: aparece al final del scan, en `show --json`, en el evento `scan.end` y en
`verify`.

## Anexo en los informes

Los informes HTML y Markdown (`osineitor export N -f html|md`) terminan con una sección
**Evidencias**: una fila por respuesta guardada (módulo, entidad consultada, URL, fecha UTC, estado
HTTP, bytes y SHA-256 completo; «recortada» si pasó de 2 MB) y la huella del conjunto. El anexo
trae los hashes, no los cuerpos: quien reciba el informe puede cotejarlos con la base del scan
(`osineitor verify N`) o comprobar que la huella coincide con la que anotaste al escanear. Un scan
sin `--evidence` lo indica en una línea en vez de mostrar una tabla vacía.

## Límites

- `verify` detecta cuerpos cambiados sin tocar su hash. Si alguien puede reescribir en la base el
  cuerpo **y** su hash, solo lo detecta la huella de evidencias anotada fuera de la base
  (`--digest`). No hay firma criptográfica.
- Las evidencias son una captura fresca: `--evidence` desactiva la caché de respuestas.
- Ocupan espacio: una búsqueda de usernames guarda cientos de respuestas.
- Una evidencia demuestra lo que contestó la fuente, no que el dato sea cierto.

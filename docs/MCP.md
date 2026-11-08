# Servidor MCP

`osineitor mcp` arranca un servidor del [Model Context Protocol](https://modelcontextprotocol.io)
por la entrada y la salida estándar, para que un agente de IA (Claude Desktop, Claude Code u otro
cliente MCP) consulte tus scans guardados y lance scans pasivos. No tiene dependencias: implementa
lo mínimo del protocolo (`initialize`, `ping`, `tools/list` y `tools/call`).

## Configurarlo en un cliente

```json
{
  "mcpServers": {
    "osineitor": {
      "command": "osineitor",
      "args": ["mcp"]
    }
  }
}
```

`--db RUTA` elige otra base de datos. El servidor solo escribe en la salida estándar mensajes del
protocolo; nada más.

## Herramientas

| Herramienta | Qué hace | Escribe |
|---|---|---|
| `list_scans` | Últimos scans guardados | no |
| `get_scan` | Estado, recuento por tipo y entidades de un scan (sin detalle; admite `types` y `limit`) | no |
| `get_entity` | Detalle de una entidad por su clave (`tipo:valor`) | no |
| `get_findings` | Hallazgos de un scan, de mayor a menor severidad | no |
| `search` | En qué scans y casos aparece un dato (igualdad o `contains`) | no |
| `suggest_pivots` | Qué investigar a continuación; solo propone (ver `osineitor suggest`) | no |
| `run_passive_scan` | Lanza un scan pasivo y lo guarda | guarda el scan |

## Qué no puede hacer un agente

- **Pedir módulos activos.** `run_passive_scan` no tiene parámetro `active`, rechaza cualquier
  argumento que no declare y crea siempre el `Scanner` con `active=False`. Los módulos activos
  (los que contactan con el objetivo) no se pueden activar por MCP. A diferencia de lo que
  contemplaba el [ROADMAP](https://github.com/jmstudio14/OSINEITOR/blob/main/ROADMAP.md) («excluidos por defecto»), tampoco hay un interruptor
  para activarlos: si los necesitas, usa la CLI y confirma tú.
- **Investigar ficheros locales.** Un objetivo que sea la ruta de un fichero se rechaza: un agente
  no debe poder hacer leer los metadatos de ficheros de tu equipo.
- **Salirse de los límites.** Profundidad máxima 2, 500 entidades, 300 peticiones y 120 segundos
  por scan. Las redes privadas siguen bloqueadas por la guardia de red.
- **Ejecutar pivotes.** `suggest_pivots` devuelve comandos para que decidas tú.

## Riesgos que sí quedan

- **Inyección de instrucciones.** Todo lo que devuelven las herramientas procede de terceros
  (páginas, registros, perfiles) y puede llevar texto escrito para engañar al agente. El servidor
  lo advierte en sus instrucciones y recorta el texto largo (300 caracteres), pero no puede
  impedir que el agente lo obedezca. Usa un cliente que te pida confirmar las llamadas a
  herramientas, sobre todo `run_passive_scan`.
- **Lo que investiga el agente.** `run_passive_scan` sobre un email, un username o un teléfono es
  investigar a una persona. El parámetro `purpose` existe para declarar para qué y, con
  `require_purpose` activo en la configuración, es obligatorio. Respeta
  [el uso responsable](USO_RESPONSABLE.md).
- **Un cliente a la vez.** Un scan bloquea el servidor hasta terminar (como máximo 120 s) y no
  atiende cancelaciones durante ese tiempo.

## Verificación

`tests/test_mcp_server.py` cubre el protocolo, cada herramienta, los argumentos inválidos, que no
haya forma de pedir módulos activos y el rechazo de ficheros locales; `tests/test_mcp_cli.py`
lanza `osineitor mcp` como un proceso real y le habla por stdio. No se ha probado con un cliente
MCP concreto (Claude Desktop u otro).

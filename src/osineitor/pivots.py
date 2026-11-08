"""Sugerencia de pivotes (F10.5): qué investigar a continuación en un scan guardado.

**Propone, nunca ejecuta**: el resultado es una lista de datos que ningún módulo llegó a mirar y el
comando que los investigaría; lanzarlo es decisión de quien lo lee. Se sugieren solo módulos
pasivos que pueden correr en este equipo (con su API key y su herramienta). Los activos salen
aparte, como información, y nunca forman parte del comando propuesto. Es una aproximación: usa
`consumes` de cada módulo y alguno puede decidir después que no aplica.
"""

from __future__ import annotations

import os
import re
import shlex
from typing import Any

from osineitor.config import Config
from osineitor.models import Entity, EntityType, ScanResult

PIVOTABLE = (
    EntityType.DOMAIN,
    EntityType.IP,
    EntityType.EMAIL,
    EntityType.USERNAME,
    EntityType.PHONE,
    EntityType.URL,
    EntityType.CRYPTO_ADDRESS,
    EntityType.ASN,
    EntityType.NETBLOCK,
)
SENSITIVE = (EntityType.EMAIL, EntityType.USERNAME, EntityType.PHONE, EntityType.PERSON)
MAX_SUGGESTIONS = 50


def _quote(value: str) -> str | None:
    """`value` para pegarlo en la terminal de este sistema, o `None` si no hay forma segura.

    El valor es de terceros y quien lee el comando lo copia y lo pega. `shlex.quote` es para
    shells POSIX: en cmd.exe un `&` de una URL lanzaría un segundo comando. En Windows, entre
    comillas dobles `&|<>^;()` son literales en cmd y en PowerShell; `"%$`!` no lo son en ambos.
    """
    if re.fullmatch(r"[\w@+=:,./-]+", value, re.ASCII):
        return value
    if os.name != "nt":
        return shlex.quote(value)
    return None if re.search(r'["%$`!\r\n]', value) else f'"{value}"'


def _command(entity: Entity, modules: list[str]) -> str | None:
    if (value := _quote(entity.value)) is None:
        return None
    parts = ["osineitor", "scan", value, "--depth", "1"]
    for name in modules:
        parts += ["--module", name]
    if entity.type in SENSITIVE:
        placeholder = "<para qué lo investigas>"
        parts += ["--purpose", f'"{placeholder}"' if os.name == "nt" else f"'{placeholder}'"]
    return " ".join(parts)


def suggest(result: ScanResult, classes: list[type], config: Config) -> list[dict[str, Any]]:
    """Datos del scan que ningún módulo investigó, con los módulos pasivos que podrían hacerlo."""
    ran = {(run.module, run.entity) for run in result.runs if run.entity}
    usable = [
        cls
        for cls in classes
        if not cls.analyzer
        and cls.unavailable() is None
        and (cls.requires_key is None or config.key(cls.requires_key))
    ]
    out = []
    for entity in result.entities:
        if entity.type not in PIVOTABLE:
            continue
        todo = [c for c in usable if entity.type in c.consumes and (c.name, entity.key) not in ran]
        passive = sorted(c.name for c in todo if c.passive)
        if not passive or (command := _command(entity, passive)) is None:
            continue
        out.append(
            {
                "entity": entity.key,
                "type": entity.type.value,
                "value": entity.value,
                "modules": passive,
                "active_modules": sorted(c.name for c in todo if not c.passive),
                "sensitive": entity.type in SENSITIVE,
                "command": command,
            }
        )
    out.sort(key=lambda s: (-len(s["modules"]), s["entity"]))
    return out[:MAX_SUGGESTIONS]

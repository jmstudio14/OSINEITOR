"""Hook de MkDocs: añade al sitio la referencia de módulos generada desde el propio código.

Así la tabla no puede quedar desfasada de lo que `osineitor modules` muestra. Solo cuenta los
módulos del paquete, no los de plugins que haya instalados en el equipo que construye el sitio.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from osineitor import registry
from osineitor.modules.base import Module

PAGE = "referencia-modulos.md"


def _types(values: frozenset) -> str:
    return ", ".join(sorted(f"`{v.value}`" for v in values)) or "—"


def _row(cls: type[Module]) -> str:
    kind = "analizador" if cls.analyzer else ("pasivo" if cls.passive else "activo")
    key = f"`{cls.requires_key}`" if cls.requires_key else "—"
    description = cls.description.replace("|", "\\|")
    cells = [
        f"`{cls.name}`",
        description,
        _types(cls.consumes),
        _types(cls.produces),
        kind,
        cls.authority,
        key,
    ]
    return "| " + " | ".join(cells) + " |"


def modules_reference() -> str:
    """Markdown con una tabla por frente (dominio, ip, email…) de los módulos incluidos."""
    groups: dict[str, list[type[Module]]] = defaultdict(list)
    for cls in registry.discover():
        if not registry.is_plugin(cls):
            groups[cls.__module__.split(".")[2]].append(cls)
    total = sum(len(v) for v in groups.values())
    lines = [
        "# Referencia generada de módulos",
        "",
        f"Generada desde el código: {total} módulos. El detalle de cada fuente, sus límites y su "
        "licencia está en la [referencia escrita](MODULES.md).",
        "",
    ]
    for front in sorted(groups):
        lines += [
            f"## {front}",
            "",
            "| Módulo | Descripción | Consume | Produce | Tipo | Autoridad | API key |",
            "|---|---|---|---|---|---|---|",
        ]
        lines += [_row(cls) for cls in sorted(groups[front], key=lambda c: c.name)]
        lines.append("")
    return "\n".join(lines)


def on_files(files: Any, config: Any) -> Any:
    from mkdocs.structure.files import File

    files.append(File.generated(config, PAGE, content=modules_reference()))
    return files

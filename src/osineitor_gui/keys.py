"""API keys agrupadas por nombre: varios módulos pueden compartir la misma key."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class KeyRow:
    name: str
    modules: tuple[str, ...]
    configured: bool


def group_keys(modules: list[dict[str, Any]]) -> list[KeyRow]:
    """Una fila por key (`requires_key`), ordenada por nombre. Configurada = todos la tienen."""
    by_key: dict[str, list[dict[str, Any]]] = {}
    for module in modules:
        if module.get("requires_key"):
            by_key.setdefault(module["requires_key"], []).append(module)
    return [
        KeyRow(
            name,
            tuple(sorted(m["name"] for m in members)),
            all(m.get("key_configured") for m in members),
        )
        for name, members in sorted(by_key.items())
    ]

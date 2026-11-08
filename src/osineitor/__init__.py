"""OSINEITOR: herramienta OSINT modular."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

__version__ = "0.5.0"

if TYPE_CHECKING:
    from osineitor.models import Entity, EntityType, ScanResult
    from osineitor.scanner import ScanInputError, Scanner

# API pública. Se carga al pedirla (PEP 562): importar `osineitor` solo para leer `__version__`
# no arrastra el motor.
_PUBLIC = {
    "Scanner": "osineitor.scanner",
    "ScanInputError": "osineitor.scanner",
    "ScanResult": "osineitor.models",
    "Entity": "osineitor.models",
    "EntityType": "osineitor.models",
}
__all__ = ["Entity", "EntityType", "ScanInputError", "ScanResult", "Scanner", "__version__"]


def __getattr__(name: str) -> Any:
    if name in _PUBLIC:
        from importlib import import_module

        return getattr(import_module(_PUBLIC[name]), name)
    raise AttributeError(f"module 'osineitor' has no attribute {name!r}")

"""Descubrimiento de módulos en `osineitor.modules`."""

from __future__ import annotations

import importlib
import inspect
import pkgutil
import sys

from osineitor import modules as modules_pkg
from osineitor.modules._manifest import MODULES
from osineitor.modules.base import Module


def module_files() -> list[str]:
    """Ficheros de módulos: del manifiesto si está empaquetado; si no, buscados en disco."""
    if getattr(sys, "frozen", False):
        return list(MODULES)
    return sorted(
        info.name
        for info in pkgutil.walk_packages(modules_pkg.__path__, prefix=f"{modules_pkg.__name__}.")
        if not info.ispkg
        and not info.name.rsplit(".", 1)[-1].startswith("_")
        and info.name != f"{modules_pkg.__name__}.base"
    )


def discover() -> list[type[Module]]:
    found: dict[str, type[Module]] = {}
    for name in module_files():
        module = importlib.import_module(name)
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if issubclass(obj, Module) and not inspect.isabstract(obj) and obj.__module__ == name:
                if obj.name in found:
                    raise RuntimeError(f"Nombre de módulo duplicado: {obj.name}")
                found[obj.name] = obj
    return sorted(found.values(), key=lambda m: m.name)

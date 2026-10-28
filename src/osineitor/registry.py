"""Descubrimiento automático de módulos en `osineitor.modules`."""

from __future__ import annotations

import importlib
import inspect
import pkgutil

from osineitor import modules as modules_pkg
from osineitor.modules.base import Module


def discover() -> list[type[Module]]:
    found: dict[str, type[Module]] = {}
    for info in pkgutil.walk_packages(modules_pkg.__path__, prefix=f"{modules_pkg.__name__}."):
        module = importlib.import_module(info.name)
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(obj, Module)
                and not inspect.isabstract(obj)
                and obj.__module__ == info.name
            ):
                if obj.name in found:
                    raise RuntimeError(f"Nombre de módulo duplicado: {obj.name}")
                found[obj.name] = obj
    return sorted(found.values(), key=lambda m: m.name)

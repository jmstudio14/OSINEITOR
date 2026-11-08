"""Descubrimiento de módulos: los incluidos en `osineitor.modules` y los de plugins externos."""

from __future__ import annotations

import importlib
import inspect
import pkgutil
import sys
from importlib.metadata import entry_points

from osineitor import logs
from osineitor import modules as modules_pkg
from osineitor.modules._manifest import MODULES
from osineitor.modules.base import Module

log = logs.get("registry")

# Grupo de *entry points* en el que un paquete de terceros declara sus módulos:
#   [project.entry-points."osineitor.modules"]
#   mi_fuente = "mi_paquete.fuente:MiFuente"      # una clase `Module`
#   otras = "mi_paquete.otras"                    # o un módulo: se toman todas sus clases
PLUGIN_GROUP = "osineitor.modules"
REQUIRED = ("name", "description", "consumes")

# Plugins que no se cargaron en el último `discover()`, con el motivo. Un plugin roto no debe
# tumbar la herramienta, pero tampoco desaparecer sin decir nada.
plugin_problems: list[str] = []


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


def is_plugin(cls: type[Module]) -> bool:
    """Un módulo que no es del propio paquete: viene de un plugin instalado."""
    return not cls.__module__.startswith(f"{modules_pkg.__name__}.")


def _is_module_class(obj: object) -> bool:
    return inspect.isclass(obj) and issubclass(obj, Module) and not inspect.isabstract(obj)


def _plugin_classes(loaded: object) -> list[type[Module]]:
    """Las clases de módulo que declara un *entry point* (una clase o un módulo con varias)."""
    if inspect.ismodule(loaded):
        found = [
            obj
            for _, obj in inspect.getmembers(loaded, _is_module_class)
            if obj.__module__ == loaded.__name__
        ]
        if not found:
            raise ValueError("el módulo no define ninguna clase Module")
        return found
    if not _is_module_class(loaded):
        raise ValueError("no es una subclase concreta de osineitor.modules.base.Module")
    return [loaded]  # type: ignore[list-item]


def _load_plugins(taken: set[str]) -> list[type[Module]]:
    plugin_problems.clear()
    found: list[type[Module]] = []
    for ep in sorted(entry_points(group=PLUGIN_GROUP), key=lambda e: (e.name, e.value)):
        origin = f"{ep.name} ({ep.value})"
        try:
            classes = _plugin_classes(ep.load())
            names: set[str] = set()
            for cls in classes:
                if missing := [attr for attr in REQUIRED if not hasattr(cls, attr)]:
                    raise ValueError(f"{cls.__name__} no define {', '.join(missing)}")
                if cls.name in taken | names:
                    raise ValueError(f"el nombre de módulo «{cls.name}» ya existe")
                names.add(cls.name)
        except Exception as exc:  # código de un tercero: cualquier fallo se aísla
            plugin_problems.append(f"plugin {origin}: {type(exc).__name__}: {exc}")
            log.warning("plugin.skipped", extra={"fields": {"plugin": origin, "error": str(exc)}})
            continue
        for cls in classes:
            taken.add(cls.name)
            found.append(cls)
    return found


def discover() -> list[type[Module]]:
    found: dict[str, type[Module]] = {}
    for name in module_files():
        module = importlib.import_module(name)
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if issubclass(obj, Module) and not inspect.isabstract(obj) and obj.__module__ == name:
                if obj.name in found:
                    raise RuntimeError(f"Nombre de módulo duplicado: {obj.name}")
                found[obj.name] = obj
    for cls in _load_plugins(set(found)):
        found[cls.name] = cls
    return sorted(found.values(), key=lambda m: m.name)

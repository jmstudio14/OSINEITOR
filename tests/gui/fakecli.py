"""CLI real de OSINEITOR con módulos falsos, para probar la capa de la GUI sin red."""

from __future__ import annotations

import os
import sys
import textwrap

DRIVER = textwrap.dedent(
    """
    import asyncio, os
    from osineitor import registry
    from osineitor.errors import ModuleError
    from osineitor.models import EntityType
    from osineitor.modules.base import Module

    class Fast(Module):
        name = "fast"; description = "rápido"
        consumes = frozenset({EntityType.DOMAIN}); produces = frozenset({EntityType.IP})
        async def run(self, entity):
            return [self.emit(entity, EntityType.IP, "9.9.9.9", org="ACMÉ ñ")]

    class Bad(Module):
        name = "bad"; description = "falla"
        consumes = frozenset({EntityType.DOMAIN})
        async def run(self, entity):
            raise ModuleError("se rompió")

    class Hang(Module):
        name = "hang"; description = "se cuelga"; consumes = frozenset({EntityType.DOMAIN})
        async def run(self, entity):
            await asyncio.sleep(120)
            return []

    mods = {"fast": Fast, "bad": Bad, "hang": Hang}
    registry.discover = lambda: [mods[m] for m in os.environ["DRIVER_MODULES"].split(",")]
    from osineitor.cli import app
    app()
    """
)

CLI = [sys.executable, "-c", DRIVER]
# Un hijo que ignora stdin y no termina: para probar la escalada a terminate/kill.
DEAF = [sys.executable, "-c", "import time; time.sleep(120)"]


def driver_env(modules: str) -> dict[str, str]:
    return {"DRIVER_MODULES": modules}


def use_modules(monkeypatch, modules: str) -> None:
    monkeypatch.setenv("DRIVER_MODULES", modules)
    assert os.environ["DRIVER_MODULES"] == modules

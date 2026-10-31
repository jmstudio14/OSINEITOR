"""Base para módulos que ejecutan una herramienta externa instalada por el usuario.

No se empaquetan binarios. La herramienta se ejecuta **sin shell**, con timeout, sin las API keys
de OSINEITOR en el entorno y su salida JSON se interpreta con `parse`. Su tráfico no pasa por
`ctx.http`: no cuenta en el presupuesto de peticiones, no pasa por la guardia de red ni deja
evidencia, y con `--proxy` el módulo se omite.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
from abc import ABC, abstractmethod
from functools import cache
from typing import Any, ClassVar

from osineitor.errors import ModuleError, ModuleSkipped
from osineitor.models import Entity
from osineitor.modules.base import Module

VERSION_RE = re.compile(r"\d+(?:\.\d+)+")
VERSION_TIMEOUT = 10


@cache
def _version(path: str, args: tuple[str, ...]) -> tuple[int, ...] | None:
    """Versión que declara el ejecutable (`--version`), o `None` si no se puede leer."""
    try:
        done = subprocess.run(
            [path, *args], capture_output=True, text=True, timeout=VERSION_TIMEOUT, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    found = VERSION_RE.search(done.stdout + done.stderr)
    return tuple(int(n) for n in found[0].split(".")) if found else None


def _show(version: tuple[int, ...]) -> str:
    return ".".join(map(str, version))


def json_documents(text: str) -> list[Any]:
    """Un documento JSON, o varios uno por línea (NDJSON, como emiten Subfinder y similares)."""
    try:
        return [json.loads(text)]
    except json.JSONDecodeError:
        pass
    try:
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    except json.JSONDecodeError as exc:
        raise ModuleError("la herramienta no devolvió JSON válido") from exc


class ExternalToolModule(Module, ABC):
    binary: ClassVar[str]  # nombre (o ruta) del ejecutable
    # Versión mínima, p. ej. `(2, 6)`. Con `None` no se comprueba.
    min_version: ClassVar[tuple[int, ...] | None] = None
    version_args: ClassVar[tuple[str, ...]] = ("--version",)
    direct_dns = True  # su tráfico no pasa por --proxy
    timeout = 300.0  # el motor cancela y se mata el proceso al agotarse

    @classmethod
    def unavailable(cls) -> str | None:
        path = shutil.which(cls.binary)
        if path is None:
            return f"{cls.binary} no está instalado"
        if cls.min_version is None:
            return None
        version = _version(path, cls.version_args)
        if version is None:
            return f"no se pudo leer la versión de {cls.binary}"
        if version < cls.min_version:
            return f"{cls.binary} {_show(version)} es anterior a la mínima {_show(cls.min_version)}"
        return None

    @abstractmethod
    def args(self, entity: Entity) -> list[str]:
        """Argumentos tras el ejecutable. Pasa el objetivo como valor de una opción o tras `--`."""

    @abstractmethod
    def parse(self, entity: Entity, documents: list[Any]) -> list[Entity]:
        """Entidades a partir de los documentos JSON que imprimió la herramienta."""

    async def run(self, entity: Entity) -> list[Entity]:
        if entity.value.startswith("-"):
            raise ModuleSkipped("el valor empieza por «-» y la herramienta lo leería como opción")
        if reason := self.unavailable():
            raise ModuleSkipped(reason)
        path = shutil.which(self.binary)
        if path is None:
            raise ModuleSkipped(f"{self.binary} no está instalado")
        stdout = await self._exec([path, *self.args(entity)])
        return self.parse(entity, json_documents(stdout))

    async def _exec(self, argv: list[str]) -> str:
        env = {k: v for k, v in os.environ.items() if not k.startswith("OSINEITOR_")}
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        try:
            out, err = await proc.communicate()
        except BaseException:  # timeout o cancelación del motor: no dejar el proceso huérfano
            proc.kill()
            await proc.wait()
            raise
        if proc.returncode:
            detail = err.decode("utf-8", "replace").strip().splitlines()
            raise ModuleError(
                f"{self.binary} terminó con código {proc.returncode}"
                + (f": {detail[-1][:200]}" if detail else "")
            )
        return out.decode("utf-8", "replace")

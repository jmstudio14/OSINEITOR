"""Localiza el ejecutable de la CLI desde la aplicación."""

from __future__ import annotations

import importlib.util
import os
import shutil
import sys
from pathlib import Path


class CliNotFound(Exception):
    """No se encontró la CLI de OSINEITOR."""


def locate_cli(
    *, frozen: bool | None = None, executable: str | None = None, which=shutil.which
) -> list[str]:
    """Comando para lanzar la CLI.

    Empaquetada (PyInstaller): `osineitor.exe` junto al ejecutable de la aplicación. En
    desarrollo: `python -m osineitor` si el paquete está instalado. En último caso, el PATH.
    """
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    executable = executable or sys.executable
    if frozen:
        name = "osineitor.exe" if os.name == "nt" else "osineitor"
        sibling = Path(executable).parent / name
        if sibling.exists():
            return [str(sibling)]
    elif importlib.util.find_spec("osineitor") is not None:
        return [executable, "-m", "osineitor"]
    if found := which("osineitor"):
        return [found]
    raise CliNotFound(
        "No se encuentra la CLI de OSINEITOR (osineitor). Reinstala la aplicación o instala el "
        "paquete con «pip install osineitor»."
    )

"""Localiza el ejecutable de la CLI desde la aplicación."""

from __future__ import annotations

import importlib.util
import os
import shutil
import sys
from pathlib import Path


class CliNotFound(Exception):
    """No se encontró la CLI de OSINEITOR."""


def which_on_path(name: str) -> str | None:
    """`shutil.which` solo en las carpetas absolutas del PATH.

    En Windows, `shutil.which` mira antes la carpeta actual: un `osineitor.exe` plantado ahí se
    ejecutaría con los argumentos (y las API keys por stdin) de la aplicación.
    """
    for folder in os.environ.get("PATH", "").split(os.pathsep):
        if os.path.isabs(folder) and (found := shutil.which(os.path.join(folder, name))):
            return found
    return None


def locate_cli(
    *, frozen: bool | None = None, executable: str | None = None, which=which_on_path
) -> list[str]:
    """Comando para lanzar la CLI.

    Empaquetada (PyInstaller): `osineitor.exe` junto al ejecutable de la aplicación. En
    desarrollo: `python -m osineitor` si el paquete está instalado. En último caso, el PATH.
    """
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    executable = executable or sys.executable
    # En Windows, el `.exe` exacto: un `osineitor.bat` pasaría los argumentos por cmd.exe.
    name = "osineitor.exe" if os.name == "nt" else "osineitor"
    if frozen:
        sibling = Path(executable).parent / name
        if sibling.exists():
            return [str(sibling)]
    elif importlib.util.find_spec("osineitor") is not None:
        # `-P`: sin la carpeta actual en `sys.path`, que no se cargue un `osineitor/` plantado.
        return [executable, "-P", "-m", "osineitor"]
    if found := which(name):
        return [found]
    raise CliNotFound(
        "No se encuentra la CLI de OSINEITOR (osineitor). Reinstala la aplicación o instala el "
        "paquete con «pip install osineitor»."
    )

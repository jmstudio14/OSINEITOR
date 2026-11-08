# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller: dos ejecutables (CLI con consola y GUI sin ella) en una sola carpeta.

Uso: `pyinstaller packaging/windows/osineitor.spec` (lo hace build.ps1). Salida: dist/OSINEITOR/.
Los nombres no pueden diferir solo en mayúsculas: NTFS no las distingue.
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

from osineitor.modules._manifest import MODULES

CLI_NAME = "osineitor"  # `osineitor_gui.cli_locator.locate_cli` busca «osineitor.exe»
GUI_NAME = "osineitor-gui"

here = Path(SPECPATH)

# Los módulos se importan por nombre en tiempo de ejecución: PyInstaller no los ve solo.
cli_hidden = list(MODULES) + collect_submodules("osineitor")
datas = collect_data_files("osineitor")

cli_a = Analysis(
    [str(here / "entry_cli.py")],
    pathex=[],
    datas=datas,
    hiddenimports=cli_hidden,
    excludes=["PySide6", "osineitor_gui"],
)
gui_a = Analysis(
    [str(here / "entry_gui.py")],
    pathex=[],
    datas=collect_data_files("osineitor_gui"),
    hiddenimports=collect_submodules("osineitor_gui"),
)

cli_exe = EXE(
    PYZ(cli_a.pure),
    cli_a.scripts,
    [],
    exclude_binaries=True,
    name=CLI_NAME,
    console=True,
)
gui_exe = EXE(
    PYZ(gui_a.pure),
    gui_a.scripts,
    [],
    exclude_binaries=True,
    name=GUI_NAME,
    console=False,
)

COLLECT(
    cli_exe,
    cli_a.binaries,
    cli_a.datas,
    gui_exe,
    gui_a.binaries,
    gui_a.datas,
    name="OSINEITOR",
)

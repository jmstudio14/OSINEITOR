"""Arranque de la aplicación de escritorio (`osineitor-gui`)."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from osineitor_gui.cli_locator import CliNotFound, locate_cli
from osineitor_gui.settings import GuiSettings
from osineitor_gui.ui.main_window import MainWindow
from osineitor_gui.ui.theme import apply_theme

APP_ID = "OSINEITOR.Desktop"


def _set_windows_app_id() -> None:
    """Agrupa la ventana bajo su propio icono en la barra de tareas de Windows."""
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)


def main(argv: list[str] | None = None) -> int:
    _set_windows_app_id()
    qapp = QApplication.instance() or QApplication(argv if argv is not None else sys.argv)
    qapp.setApplicationName("OSINEITOR")
    settings = GuiSettings.load()
    apply_theme(settings.theme)

    cli: list[str] | None = None
    cli_error: str | None = None
    try:
        cli = locate_cli()
    except CliNotFound as exc:
        cli_error = str(exc)
        QMessageBox.critical(None, "OSINEITOR", cli_error)

    window = MainWindow(settings, cli, cli_error)
    window.show()
    return QApplication.exec()

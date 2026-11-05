"""Tema claro, oscuro o el del sistema."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication

SCHEMES = {
    "light": Qt.ColorScheme.Light,
    "dark": Qt.ColorScheme.Dark,
    "system": Qt.ColorScheme.Unknown,  # sigue el esquema del sistema
}


def apply_theme(theme: str) -> None:
    """Aplica uno de `settings.THEMES` a toda la aplicación."""
    QGuiApplication.styleHints().setColorScheme(SCHEMES[theme])

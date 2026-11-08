"""Iconos Lucide (ISC) incluidos en `assets/icons`, tintados con los tokens del tema activo."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from osineitor_gui.ui import theme

ICONS = Path(__file__).parent / "assets" / "icons"
RENDER_SIZE = 48  # px: QIcon reduce al tamaño pedido, y a 150 % de escala sigue nítido
ICON_SIZE = QSize(16, 16)


def pixmap(name: str, color: str, size: int = RENDER_SIZE) -> QPixmap:
    svg = (ICONS / f"{name}.svg").read_bytes().replace(b"currentColor", color.encode("ascii"))
    renderer = QSvgRenderer(QByteArray(svg))
    if not renderer.isValid():
        raise ValueError(f"icono no válido: {name}")
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return QPixmap.fromImage(image)


def icon(name: str, tone: str = "muted") -> QIcon:
    """`tone` es un token de `theme.Tokens`; deshabilitado siempre usa el token `disabled`."""
    tokens = theme.current()
    result = QIcon(pixmap(name, QColor(getattr(tokens, tone)).name()))
    result.addPixmap(pixmap(name, tokens.disabled), QIcon.Mode.Disabled)
    return result

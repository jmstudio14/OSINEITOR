"""Piezas comunes de la interfaz: roles de estilo, tarjeta, estado vacío, aviso y texto seguro."""

from __future__ import annotations

import html

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtGui import QAccessible, QAccessibleEvent
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout, QWidget

from osineitor_gui.ui import icons

TOOLTIP_LIMIT = 500


def safe_tooltip(text: object) -> str:
    """Tooltip con datos de terceros: Qt interpreta HTML si lo detecta, así que nunca se le deja.

    `<qt>` fuerza texto enriquecido y `escape` lo deja inerte: se ve lo que hay, tal cual.
    """
    value = str(text)
    if len(value) > TOOLTIP_LIMIT:
        value = value[:TOOLTIP_LIMIT] + "…"
    return f"<qt>{html.escape(value)}</qt>" if value else ""


def set_style(widget: QWidget, **properties: str) -> None:
    """Fija propiedades de estilo (`role`, `kind`, `tone`) y repinta el widget con ellas."""
    for name, value in properties.items():
        widget.setProperty(name, value)
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


def label(text: str = "", role: str = "", *, wrap: bool = False) -> QLabel:
    """Etiqueta en texto plano: puede acabar mostrando datos de terceros o el stderr de la CLI."""
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(wrap)
    if role:
        widget.setProperty("role", role)
    return widget


def button(text: str, kind: str = "") -> QPushButton:
    widget = QPushButton(text)
    if kind:
        widget.setProperty("kind", kind)
    return widget


class Card(QFrame):
    """Panel con título opcional; el contenido se añade a `body`."""

    def __init__(self, title: str = "", hint: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("role", "card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(14, 12, 14, 12)
        self.body.setSpacing(8)
        if title:
            self.body.addWidget(label(title, "cardTitle"))
        if hint:
            self.body.addWidget(label(hint, "kpiHint", wrap=True))


class EmptyState(QWidget):
    """Sección sin datos: qué pasa, por qué y, si tiene sentido, qué hacer."""

    def __init__(self, icon: str, title: str, text: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self._icon = icon
        self.picture = QLabel()
        self.picture.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title = label(title, "emptyTitle", wrap=True)
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.text = label(text, "muted", wrap=True)
        self.text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout_ = QVBoxLayout(self)
        self.layout_.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout_.setSpacing(8)
        self.layout_.addWidget(self.picture)
        self.layout_.addWidget(self.title)
        self.layout_.addWidget(self.text)
        self._paint_icon()

    def _paint_icon(self) -> None:
        self.picture.setPixmap(icons.icon(self._icon).pixmap(32, 32))

    def set_message(self, title: str, text: str = "") -> None:
        self.title.setText(title)
        self.text.setText(text)
        self.text.setVisible(bool(text))

    def add_action(self, widget: QWidget) -> None:
        self.layout_.addWidget(widget, 0, Qt.AlignmentFlag.AlignCenter)

    def changeEvent(self, event: QEvent) -> None:
        if event.type() == QEvent.Type.ApplicationPaletteChange:
            self._paint_icon()
        super().changeEvent(event)


class Toast(QLabel):
    """Confirmación breve sobre la ventana: éxito o error, sin robar el foco."""

    DURATION_MS = 4000
    MARGIN = 16

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setWordWrap(True)
        self.setMaximumWidth(420)
        self.setProperty("role", "toast")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.hide()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)
        parent.installEventFilter(self)

    def show_message(self, text: str, tone: str = "safe") -> None:
        self.setText(text)
        self.setAccessibleName(text)
        set_style(self, tone=tone)
        self.adjustSize()
        self._place()
        self.show()
        self.raise_()
        QAccessible.updateAccessibility(QAccessibleEvent(self, QAccessible.Event.Alert))
        self._timer.start(self.DURATION_MS)

    def _place(self) -> None:
        parent = self.parentWidget()
        self.move(
            parent.width() - self.width() - self.MARGIN,
            parent.height() - self.height() - self.MARGIN,
        )

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Resize and self.isVisible():
            self._place()
        return super().eventFilter(watched, event)

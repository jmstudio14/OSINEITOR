"""Gráficos pintados con QPainter: columnas (simples o apiladas) y lista de barras.

Marcas finas, cuadrícula discreta, una sola escala y leyenda con dos o más series. El color nunca
va solo: cada valor se lee también en texto (etiquetas, tooltip y descripción accesible).
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QEvent, QPoint, QRectF, Qt
from PySide6.QtGui import (
    QAccessible,
    QAccessibleEvent,
    QColor,
    QFocusEvent,
    QFont,
    QFontMetrics,
    QKeyEvent,
    QMouseEvent,
    QPainter,
)
from PySide6.QtWidgets import QSizePolicy, QToolTip, QWidget

from osineitor_gui.ui import theme
from osineitor_gui.ui.widgets import safe_tooltip

GAP = 2.0  # separación entre segmentos apilados
RADIUS = 3.0
AXIS_WIDTH = 28
AXIS_HEIGHT = 18
LEGEND_HEIGHT = 20


@dataclass
class Column:
    label: str
    segments: list[tuple[str, int]]  # (tono, valor)
    tooltip: str = ""

    @property
    def total(self) -> int:
        return sum(value for _tone, value in self.segments)


@dataclass
class BarRow:
    label: str
    value: int
    tone: str = "accent"
    mono: bool = False


def _ticks(maximum: int) -> list[int]:
    """Hasta tres marcas enteras: en un eje de recuentos no tiene sentido «0,5 scans»."""
    if maximum <= 0:
        return [0, 1]
    step = max(1, round(maximum / 2))
    ticks = list(range(0, maximum + 1, step))
    if ticks[-1] < maximum:
        ticks.append(ticks[-1] + step)
    return ticks


class _Chart(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.loading = False
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    def set_loading(self, loading: bool) -> None:
        self.loading = loading
        self.update()

    def _paint_skeleton(self, painter: QPainter) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(theme.current().raised))
        width, height = self.width(), self.height()
        for i, share in enumerate((0.5, 0.8, 0.35, 0.65, 0.45, 0.9)):
            bar = height * share * 0.8
            x = width * (i + 0.2) / 6
            painter.drawRoundedRect(QRectF(x, height - bar, width / 10, bar), RADIUS, RADIUS)

    def _small_font(self) -> QFont:
        font = QFont(self.font())
        font.setPointSize(9)
        return font

    def leaveEvent(self, event: QEvent) -> None:
        QToolTip.hideText()
        self._hover_changed(None)
        super().leaveEvent(event)

    def _hover_changed(self, _index: int | None) -> None:
        self.update()


class ColumnChart(_Chart):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.columns: list[Column] = []
        self.legend: list[tuple[str, str]] = []  # (tono, etiqueta)
        self.label_every = 1
        self._hover: int | None = None
        self.setMinimumHeight(170)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)  # flechas: valor a valor sin ratón

    def set_data(self, columns: list[Column], legend: list[tuple[str, str]] | None = None) -> None:
        self.columns = columns
        self.legend = legend or []
        self.loading = False
        parts = [f"{c.label}: {c.total}" for c in columns if c.total]
        self.setAccessibleDescription("; ".join(parts) or self.tr("Sin datos"))
        self.update()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        steps = {Qt.Key.Key_Left: -1, Qt.Key.Key_Right: 1}
        step = steps.get(event.key())
        if step is None or not self.columns:
            super().keyPressEvent(event)
            return
        current = self._hover if self._hover is not None else -step
        self._select(max(min(current + step, len(self.columns) - 1), 0))

    def focusInEvent(self, event: QFocusEvent) -> None:
        super().focusInEvent(event)
        if self.columns and self._hover is None:
            self._select(len(self.columns) - 1)  # lo más reciente
        self.update()

    def focusOutEvent(self, event: QFocusEvent) -> None:
        super().focusOutEvent(event)
        QToolTip.hideText()
        self._hover_changed(None)

    def _select(self, index: int) -> None:
        self._hover_changed(index)
        column = self.columns[index]
        text = column.tooltip or f"{column.label}: {column.total}"
        plot = self._plot()
        point = QPoint(int(plot.left() + self._slot() * (index + 0.5)), int(plot.top()))
        QToolTip.showText(self.mapToGlobal(point), safe_tooltip(text), self)
        self.setAccessibleDescription(text)
        QAccessible.updateAccessibility(
            QAccessibleEvent(self, QAccessible.Event.DescriptionChanged)
        )

    def _plot(self) -> QRectF:
        top = LEGEND_HEIGHT if self.legend else 4
        return QRectF(
            AXIS_WIDTH, top, self.width() - AXIS_WIDTH - 4, self.height() - top - AXIS_HEIGHT
        )

    def _slot(self) -> float:
        return self._plot().width() / max(len(self.columns), 1)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.loading:
            self._paint_skeleton(painter)
            return
        tokens = theme.current()
        plot = self._plot()
        if self.hasFocus():
            painter.setPen(QColor(tokens.accent))
            painter.drawRoundedRect(
                QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), RADIUS, RADIUS
            )
        painter.setFont(self._small_font())
        metrics = QFontMetrics(painter.font())
        self._paint_legend(painter, metrics)
        maximum = max((c.total for c in self.columns), default=0)
        ticks = _ticks(maximum)
        scale = plot.height() / max(ticks[-1], 1)
        for tick in ticks:
            y = plot.bottom() - tick * scale
            painter.setPen(QColor(tokens.border))
            painter.drawLine(int(plot.left()), int(y), int(plot.right()), int(y))
            painter.setPen(QColor(tokens.muted))
            painter.drawText(
                QRectF(0, y - 8, AXIS_WIDTH - 6, 16),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                str(tick),
            )
        slot = self._slot()
        width = max(min(slot * 0.5, 16.0), 3.0)
        for i, column in enumerate(self.columns):
            x = plot.left() + slot * i + (slot - width) / 2
            if i == self._hover:
                painter.fillRect(
                    QRectF(plot.left() + slot * i, plot.top(), slot, plot.height()),
                    QColor(tokens.hover),
                )
            self._paint_column(painter, column, x, width, plot.bottom(), scale)
            if i % max(self.label_every, 1) == 0:
                painter.setPen(QColor(tokens.muted))
                text = metrics.elidedText(column.label, Qt.TextElideMode.ElideRight, int(slot * 2))
                painter.drawText(
                    QRectF(plot.left() + slot * i - slot / 2, plot.bottom() + 2, slot * 2, 16),
                    Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                    text,
                )

    def _paint_column(
        self, painter: QPainter, column: Column, x: float, width: float, base: float, scale: float
    ) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        y = base
        drawn = [(tone, value) for tone, value in column.segments if value]
        for position, (tone, value) in enumerate(drawn):
            height = value * scale
            is_top = position == len(drawn) - 1
            inner = height - (0 if is_top else GAP)
            rect = QRectF(x, y - height + (0 if is_top else GAP), width, max(inner, 1.0))
            painter.setBrush(theme.tone_color(tone))
            if is_top:  # solo el extremo superior va redondeado: la base apoya en el eje
                painter.save()
                painter.setClipRect(rect)
                painter.drawRoundedRect(rect.adjusted(0, 0, 0, RADIUS), RADIUS, RADIUS)
                painter.restore()
            else:
                painter.drawRect(rect)
            y -= height

    def _paint_legend(self, painter: QPainter, metrics: QFontMetrics) -> None:
        x = float(AXIS_WIDTH)
        for tone, text in self.legend:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(theme.tone_color(tone))
            painter.drawEllipse(QRectF(x, 5, 8, 8))
            painter.setPen(QColor(theme.current().muted))
            painter.drawText(QRectF(x + 12, 0, 200, 18), Qt.AlignmentFlag.AlignVCenter, text)
            x += 12 + metrics.horizontalAdvance(text) + 14

    def _index_at(self, position: QPoint) -> int | None:
        plot = self._plot()
        if not self.columns or not plot.contains(position.toPointF()):
            return None
        index = int((position.x() - plot.left()) / self._slot())
        return index if 0 <= index < len(self.columns) else None

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        index = self._index_at(event.position().toPoint())
        if index != self._hover:
            self._hover_changed(index)
        if index is not None and self.columns[index].tooltip:
            QToolTip.showText(
                event.globalPosition().toPoint(),
                safe_tooltip(self.columns[index].tooltip),
                self,
            )
        else:
            QToolTip.hideText()

    def _hover_changed(self, index: int | None) -> None:
        self._hover = index
        self.update()


class BarList(_Chart):
    """Una fila por categoría: punto opcional, etiqueta, barra fina y valor."""

    ROW = 24
    LABEL_WIDTH = 110
    VALUE_WIDTH = 42

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.rows: list[BarRow] = []
        self.setMinimumHeight(self.ROW * 3)

    def set_data(self, rows: list[BarRow]) -> None:
        self.rows = rows
        self.loading = False
        self.setMinimumHeight(max(self.ROW * len(rows), self.ROW * 3))
        self.setAccessibleDescription(
            "; ".join(f"{r.label}: {r.value}" for r in rows) or self.tr("Sin datos")
        )
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        tokens = theme.current()
        if self.loading:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(tokens.raised))
            for i in range(4):
                painter.drawRoundedRect(
                    QRectF(0, i * self.ROW + 6, self.width() * (0.9 - i * 0.15), 10), RADIUS, RADIUS
                )
            return
        maximum = max((row.value for row in self.rows), default=0) or 1
        track = max(self.width() - self.LABEL_WIDTH - self.VALUE_WIDTH, 10)
        for i, row in enumerate(self.rows):
            y = i * self.ROW
            label_x = 0
            if row.tone != "accent":
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(theme.tone_color(row.tone))
                painter.drawEllipse(QRectF(0, y + 8, 8, 8))
                label_x = 14
            painter.setFont(theme.mono_font() if row.mono else self.font())
            painter.setPen(QColor(tokens.text))
            text = QFontMetrics(painter.font()).elidedText(
                row.label, Qt.TextElideMode.ElideRight, self.LABEL_WIDTH - label_x - 6
            )
            painter.drawText(
                QRectF(label_x, y, self.LABEL_WIDTH - label_x, self.ROW),
                Qt.AlignmentFlag.AlignVCenter,
                text,
            )
            painter.setFont(self.font())
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(tokens.raised))
            painter.drawRoundedRect(QRectF(self.LABEL_WIDTH, y + 9, track, 6), RADIUS, RADIUS)
            if row.value:
                painter.setBrush(theme.tone_color(row.tone))
                share = max(track * row.value / maximum, 6.0)
                painter.drawRoundedRect(QRectF(self.LABEL_WIDTH, y + 9, share, 6), RADIUS, RADIUS)
            painter.setPen(QColor(tokens.text))
            painter.drawText(
                QRectF(self.width() - self.VALUE_WIDTH, y, self.VALUE_WIDTH, self.ROW),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                str(row.value),
            )

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        index = int(event.position().y() // self.ROW)
        if 0 <= index < len(self.rows):
            row = self.rows[index]
            QToolTip.showText(
                event.globalPosition().toPoint(), safe_tooltip(f"{row.label}: {row.value}"), self
            )
        else:
            QToolTip.hideText()

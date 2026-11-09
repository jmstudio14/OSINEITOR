"""Tablas de la aplicación: orden con proxy, insignias de estado y copia al portapapeles."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import (
    QAbstractItemModel,
    QAbstractTableModel,
    QEvent,
    QModelIndex,
    QObject,
    QPoint,
    QRectF,
    QSize,
    QSortFilterProxyModel,
    Qt,
)
from PySide6.QtGui import QAction, QBrush, QColor, QGuiApplication, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QHeaderView,
    QMenu,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableView,
    QWidget,
)

from osineitor_gui.ui import icons, theme
from osineitor_gui.ui.widgets import safe_tooltip

_ROOT = QModelIndex()
HOVER_ROW = "hover_row"
SORT_ROLE = Qt.ItemDataRole.UserRole + 10  # valor crudo para ordenar: «10.0 s» va tras «2.0 s»
ROW_HEIGHT = 30
DOT = 8.0
BADGE_INDENT = 23  # margen + punto + separación


@dataclass(frozen=True)
class ColumnSpec:
    """Una columna de `RowsModel`; las funciones reciben la fila entera."""

    title: str
    value: Callable[[Any], object]
    mono: bool = False
    tooltip: bool = False
    tone: Callable[[Any], str] | None = None
    sort: Callable[[Any], object] | None = None


class RowsModel(QAbstractTableModel):
    """Tabla de solo lectura sobre una lista de filas, descrita por sus columnas."""

    def __init__(self, columns: tuple[ColumnSpec, ...], parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._columns = columns
        self._rows: list[Any] = []

    def set_rows(self, rows: list[Any]) -> None:
        self.beginResetModel()
        self._rows = list(rows)
        self.endResetModel()

    def row(self, row: int) -> Any:
        return self._rows[row]

    def rowCount(self, parent: QModelIndex = _ROOT) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex = _ROOT) -> int:
        return 0 if parent.isValid() else len(self._columns)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.tr(self._columns[section].title)
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row, column = self._rows[index.row()], self._columns[index.column()]
        if role == Qt.ItemDataRole.DisplayRole:
            return column.value(row)
        if role == SORT_ROLE:
            return column.sort(row) if column.sort else column.value(row)
        if role == Qt.ItemDataRole.FontRole and column.mono:
            return theme.mono_font()
        if role == Qt.ItemDataRole.ToolTipRole and column.tooltip:
            return safe_tooltip(column.value(row))
        if role == Qt.ItemDataRole.ForegroundRole and column.tone:
            return QBrush(theme.tone_color(column.tone(row)))
        return None


class HoverDelegate(QStyledItemDelegate):
    """Resalta la fila bajo el ratón; `::item:hover` de la hoja de estilo solo marca la celda."""

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        paint_hover(painter, option, index)
        super().paint(painter, option, index)


class _RowHover(QObject):
    """Sigue la fila bajo el ratón y repinta solo la que deja y la que entra."""

    def __init__(self, table: QTableView) -> None:
        super().__init__(table)
        self._table = table
        table.viewport().setMouseTracking(True)
        table.viewport().installEventFilter(self)

    def _set(self, row: int) -> None:
        table = self._table
        previous = table.property(HOVER_ROW)
        if previous == row:
            return
        table.setProperty(HOVER_ROW, row)
        width = table.viewport().width()
        for changed in (previous, row):
            if changed is not None and changed >= 0:
                top = table.rowViewportPosition(changed)
                table.viewport().update(0, top, width, table.rowHeight(changed))

    def eventFilter(self, _watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.MouseMove:
            self._set(self._table.rowAt(event.position().toPoint().y()))
        elif event.type() == QEvent.Type.Leave:
            self._set(-1)
        return False


def paint_hover(painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
    selected = option.state & QStyle.StateFlag.State_Selected
    if not selected and option.widget and option.widget.property(HOVER_ROW) == index.row():
        painter.fillRect(option.rect, QColor(theme.current().hover))


class BadgeDelegate(QStyledItemDelegate):
    """Punto de color + etiqueta: la gravedad nunca se comunica solo con el color.

    El color lo da el `ForegroundRole` del modelo; el texto usa siempre la tinta normal.
    """

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        size = super().sizeHint(option, index)
        return QSize(size.width() + BADGE_INDENT + 8, size.height())

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        paint_hover(painter, option, index)
        item = QStyleOptionViewItem(option)
        self.initStyleOption(item, index)
        text = item.text
        item.text = ""
        style = item.widget.style() if item.widget else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, item, painter, item.widget)
        if not text:
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        brush = index.data(Qt.ItemDataRole.ForegroundRole)
        color = brush.color() if isinstance(brush, QBrush) else QColor(theme.current().neutral)
        rect = option.rect
        top = rect.top() + (rect.height() - DOT) / 2
        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRectF(rect.left() + 8, top, DOT, DOT))
        tokens = theme.current()
        painter.setPen(QColor(tokens.text))
        text_rect = rect.adjusted(BADGE_INDENT, 0, -4, 0)
        elided = option.fontMetrics.elidedText(text, Qt.TextElideMode.ElideRight, text_rect.width())
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter, elided)
        painter.restore()


def style_table(table: QTableView) -> None:
    """Aspecto y comportamiento comunes de una tabla de datos."""
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setShowGrid(False)
    table.setWordWrap(False)
    table.setTextElideMode(Qt.TextElideMode.ElideMiddle)  # hashes y URL: se ven principio y fin
    table.setItemDelegate(HoverDelegate(table))
    _RowHover(table)
    table.verticalHeader().hide()
    table.verticalHeader().setDefaultSectionSize(ROW_HEIGHT)
    header = table.horizontalHeader()
    header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    header.setHighlightSections(False)
    header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    header.setStretchLastSection(False)


def make_table(
    model: QAbstractItemModel, proxy: QSortFilterProxyModel | None = None
) -> tuple[QTableView, QSortFilterProxyModel]:
    """Tabla ordenable; sin orden inicial: mantiene el de la fuente hasta pulsar una cabecera."""
    proxy = proxy or QSortFilterProxyModel()
    proxy.setSourceModel(model)
    proxy.setSortRole(SORT_ROLE)
    proxy.setDynamicSortFilter(True)
    table = QTableView()
    proxy.setParent(table)
    table.setModel(proxy)
    style_table(table)
    # Sin esto, activar el orden ordena al instante por la primera columna.
    table.horizontalHeader().setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
    table.setSortingEnabled(True)
    return table, proxy


def set_widths(table: QTableView, widths: dict[int, int]) -> None:
    for column, width in widths.items():
        table.setColumnWidth(column, width)


def source_row(table: QTableView, index: QModelIndex) -> int:
    """Fila en el modelo fuente de un índice de la tabla: la del proxy cambia al ordenar."""
    model = table.model()
    return (
        model.mapToSource(index).row() if isinstance(model, QSortFilterProxyModel) else index.row()
    )


def row_text(table: QTableView, row: int) -> str:
    """Las celdas visibles de una fila, separadas por tabuladores."""
    model = table.model()
    cells = (model.index(row, c).data() for c in range(model.columnCount()))
    return "\t".join("" if cell is None else str(cell) for cell in cells)


def show_copy_menu(
    table: QTableView,
    position: QPoint,
    value_column: int,
    extra: tuple[tuple[str, str, object], ...] = (),
) -> None:
    """Menú contextual: copiar el valor o la fila, más `extra` = (texto, icono, función(fila))."""
    index = table.indexAt(position)
    if not index.isValid():
        return
    clipboard = QGuiApplication.clipboard()
    model = table.model()
    menu = QMenu(table)
    copy_value = QAction(icons.icon("copy"), table.tr("Copiar valor"), menu)
    value = model.index(index.row(), value_column).data()
    copy_value.triggered.connect(lambda: clipboard.setText("" if value is None else str(value)))
    copy_row = QAction(icons.icon("copy"), table.tr("Copiar fila"), menu)
    copy_row.triggered.connect(lambda: clipboard.setText(row_text(table, index.row())))
    menu.addActions([copy_value, copy_row])
    if extra:
        menu.addSeparator()
    for text, icon_name, callback in extra:
        action = QAction(icons.icon(icon_name), text, menu)
        action.triggered.connect(lambda _checked=False, fn=callback, i=index: fn(i))
        menu.addAction(action)
    menu.popup(table.viewport().mapToGlobal(position))


def install_badges(table: QTableView, column: int, parent: QWidget | None = None) -> None:
    table.setItemDelegateForColumn(column, BadgeDelegate(parent or table))

"""Tablas de la aplicación: orden con proxy, insignias de estado y copia al portapapeles."""

from __future__ import annotations

from PySide6.QtCore import (
    QAbstractItemModel,
    QModelIndex,
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

SORT_ROLE = Qt.ItemDataRole.UserRole + 10  # valor crudo para ordenar: «10.0 s» va tras «2.0 s»
ROW_HEIGHT = 30
DOT = 8.0
BADGE_INDENT = 23  # margen + punto + separación


class BadgeDelegate(QStyledItemDelegate):
    """Punto de color + etiqueta: la gravedad nunca se comunica solo con el color.

    El color lo da el `ForegroundRole` del modelo; el texto usa siempre la tinta normal.
    """

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        size = super().sizeHint(option, index)
        return QSize(size.width() + BADGE_INDENT + 8, size.height())

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
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

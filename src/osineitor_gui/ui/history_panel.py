"""Página Historial: scans guardados (`CliApi.history`); doble clic o Intro abren uno."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QObject,
    QPoint,
    QSortFilterProxyModel,
    Qt,
    Signal,
)
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from osineitor_gui.api import CliApi
from osineitor_gui.dashboard import HISTORY_LIMIT
from osineitor_gui.ui import theme
from osineitor_gui.ui.tables import SORT_ROLE, make_table, set_widths, show_copy_menu, source_row
from osineitor_gui.ui.widgets import EmptyState, label, safe_tooltip
from osineitor_gui.ui.worker import run_in_thread

_ROOT = QModelIndex()


class HistoryModel(QAbstractTableModel):
    HEADERS = ("Id", "Objetivo", "Tipo", "Entidades", "Fecha")
    MONO_COLUMNS = (0, 1, 4)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._rows: list[dict[str, Any]] = []

    def set_rows(self, rows: list[dict[str, Any]]) -> None:
        self.beginResetModel()
        self._rows = list(rows)
        self.endResetModel()

    def rows(self) -> list[dict[str, Any]]:
        return list(self._rows)

    def row(self, row: int) -> dict[str, Any]:
        return self._rows[row]

    def scan_id(self, row: int) -> int:
        return self._rows[row]["id"]

    def rowCount(self, parent: QModelIndex = _ROOT) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex = _ROOT) -> int:
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.tr(self.HEADERS[section])
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        scan = self._rows[index.row()]
        column = index.column()
        if role == Qt.ItemDataRole.FontRole and column in self.MONO_COLUMNS:
            return theme.mono_font()
        if role == Qt.ItemDataRole.ToolTipRole and column == 1:
            return safe_tooltip(scan["target"])
        if role not in (Qt.ItemDataRole.DisplayRole, SORT_ROLE):
            return None
        started = str(scan.get("started_at", "")).replace("T", " ")[:19]
        return (scan["id"], scan["target"], scan["target_type"], scan["entities"], started)[column]


class HistoryFilter(QSortFilterProxyModel):
    """Filtra por tipo de objetivo y por texto en objetivo o id."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._kind: str | None = None
        self._text = ""

    def set_filter(self, kind: str | None, text: str) -> None:
        # `beginFilterChange` llega con Qt 6.10, que deja obsoleta la otra; el mínimo es 6.8.
        if hasattr(self, "beginFilterChange"):
            self.beginFilterChange()
            self._kind, self._text = kind, text.strip().lower()
            self.endFilterChange(QSortFilterProxyModel.Direction.Rows)
        else:
            self._kind, self._text = kind, text.strip().lower()
            self.invalidateRowsFilter()

    def filterAcceptsRow(self, row: int, _parent: QModelIndex) -> bool:
        scan = self.sourceModel().row(row)
        if self._kind is not None and scan["target_type"] != self._kind:
            return False
        return not self._text or self._text in f"{scan['id']} {scan['target']}".lower()


class HistoryPanel(QWidget):
    scan_requested = Signal(int)  # id del scan que se quiere abrir
    export_requested = Signal(int)  # id del scan que se quiere exportar
    verify_requested = Signal(int)  # id del scan cuyas evidencias se quieren comprobar
    loaded = Signal()  # terminó una recarga (bien o mal)

    def __init__(self, api: CliApi, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._api = api
        self.error: str | None = None  # motivo si la última carga falló
        self.model = HistoryModel(self)
        self.table, self.proxy = make_table(self.model, HistoryFilter())
        self.table.setAccessibleName(self.tr("Scans guardados"))
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        set_widths(self.table, {0: 60, 2: 110, 3: 90, 4: 170})
        self.table.doubleClicked.connect(self._open)
        self.table.activated.connect(self._open)  # Intro con el teclado
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._menu)

        self.search = QLineEdit()
        self.search.setPlaceholderText(self.tr("Filtrar por objetivo o id"))
        self.search.setAccessibleName(self.tr("Filtrar el historial"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter_changed)
        self.kind_filter = QComboBox()
        self.kind_filter.setAccessibleName(self.tr("Filtrar por tipo de objetivo"))
        self.kind_filter.currentIndexChanged.connect(self._filter_changed)
        self.refresh_button = QPushButton(self.tr("Actualizar"))
        self.refresh_button.clicked.connect(self.reload)
        # Puede mostrar el stderr de la CLI: siempre texto plano.
        self.status = label("", "muted", wrap=True)
        self.empty = EmptyState(
            "inbox",
            self.tr("Todavía no hay scans guardados"),
            self.tr("Lanza un scan y aparecerá aquí en cuanto termine."),
        )
        self.content = QStackedWidget()
        self.content.addWidget(self.table)
        self.content.addWidget(self.empty)

        controls = QHBoxLayout()
        controls.addWidget(self.kind_filter)
        controls.addWidget(self.search, 1)
        controls.addWidget(self.refresh_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(8)
        layout.addLayout(controls)
        layout.addWidget(self.content, 1)
        layout.addWidget(self.status)
        self._fill_kinds()

    def reload(self) -> None:
        self.refresh_button.setEnabled(False)
        self.status.setText(self.tr("Cargando…"))
        self.status.show()
        run_in_thread(
            lambda: self._api.history(limit=HISTORY_LIMIT), self._on_loaded, self._on_failed, self
        )

    def _on_loaded(self, rows: list[dict[str, Any]]) -> None:
        self.error = None
        self.model.set_rows(rows)
        self._fill_kinds()
        self.status.setText("" if rows else self.tr("Todavía no hay scans guardados"))
        self.status.setVisible(False)
        self.content.setCurrentWidget(self.table if rows else self.empty)
        self._finish()

    def _on_failed(self, exc: Exception) -> None:
        self.error = str(exc)
        self.status.setText(f"{self.tr('No se pudo cargar el historial')}: {exc}")
        self.status.show()
        self._finish()

    def _finish(self) -> None:
        self.refresh_button.setEnabled(True)
        self.loaded.emit()

    def _fill_kinds(self) -> None:
        kinds = sorted({scan["target_type"] for scan in self.model.rows()})
        current = self.kind_filter.currentData()
        self.kind_filter.blockSignals(True)
        self.kind_filter.clear()
        self.kind_filter.addItem(self.tr("Todos los tipos"), None)
        for kind in kinds:
            self.kind_filter.addItem(kind, kind)
        self.kind_filter.setCurrentIndex(max(self.kind_filter.findData(current), 0))
        self.kind_filter.blockSignals(False)

    def _filter_changed(self, *_args) -> None:
        self.proxy.set_filter(self.kind_filter.currentData(), self.search.text())

    def _scan_at(self, index: QModelIndex) -> int:
        return self.model.scan_id(source_row(self.table, index))

    def _open(self, index: QModelIndex) -> None:
        self.scan_requested.emit(self._scan_at(index))

    def _menu(self, position: QPoint) -> None:
        show_copy_menu(
            self.table,
            position,
            value_column=1,
            extra=(
                (self.tr("Abrir"), "external-link", self._open),
                (
                    self.tr("Verificar evidencias"),
                    "shield-check",
                    lambda index: self.verify_requested.emit(self._scan_at(index)),
                ),
                (
                    self.tr("Exportar…"),
                    "download",
                    lambda index: self.export_requested.emit(self._scan_at(index)),
                ),
            ),
        )

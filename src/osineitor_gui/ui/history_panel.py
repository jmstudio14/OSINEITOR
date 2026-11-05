"""Panel Historial: scans guardados (`CliApi.history`); el doble clic pide abrir uno."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QObject, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from osineitor_gui.api import CliApi
from osineitor_gui.ui.worker import run_in_thread

_ROOT = QModelIndex()


class HistoryModel(QAbstractTableModel):
    HEADERS = ("Id", "Objetivo", "Tipo", "Entidades", "Fecha")

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._rows: list[dict[str, Any]] = []

    def set_rows(self, rows: list[dict[str, Any]]) -> None:
        self.beginResetModel()
        self._rows = list(rows)
        self.endResetModel()

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
        if not index.isValid() or role != Qt.ItemDataRole.DisplayRole:
            return None
        scan = self._rows[index.row()]
        started = str(scan.get("started_at", "")).replace("T", " ")[:19]
        return (scan["id"], scan["target"], scan["target_type"], scan["entities"], started)[
            index.column()
        ]


class HistoryPanel(QWidget):
    scan_requested = Signal(int)  # id del scan que se quiere abrir
    loaded = Signal()  # terminó una recarga (bien o mal)

    def __init__(self, api: CliApi, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._api = api
        self.model = HistoryModel(self)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.doubleClicked.connect(self._open)
        self.refresh_button = QPushButton(self.tr("Actualizar"))
        self.refresh_button.clicked.connect(self.reload)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.addWidget(self.refresh_button)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.status)

    def reload(self) -> None:
        self.refresh_button.setEnabled(False)
        self.status.setText(self.tr("Cargando…"))
        run_in_thread(self._api.history, self._on_loaded, self._on_failed, self)

    def _on_loaded(self, rows: list[dict[str, Any]]) -> None:
        self.model.set_rows(rows)
        self.status.setText("" if rows else self.tr("Todavía no hay scans guardados"))
        self._finish()

    def _on_failed(self, exc: Exception) -> None:
        self.status.setText(f"{self.tr('No se pudo cargar el historial')}: {exc}")
        self._finish()

    def _finish(self) -> None:
        self.refresh_button.setEnabled(True)
        self.loaded.emit()

    def _open(self, index: QModelIndex) -> None:
        self.scan_requested.emit(self.model.scan_id(index.row()))

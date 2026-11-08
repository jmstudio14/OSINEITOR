"""Página Búsqueda: un dato en todos los scans guardados (`CliApi.search`)."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QObject, QPoint, Qt, Signal
from PySide6.QtWidgets import QHeaderView, QStackedWidget, QVBoxLayout, QWidget

from osineitor_gui.api import CliApi
from osineitor_gui.ui import theme
from osineitor_gui.ui.tables import SORT_ROLE, make_table, set_widths, show_copy_menu, source_row
from osineitor_gui.ui.widgets import EmptyState, label, safe_tooltip
from osineitor_gui.ui.worker import run_in_thread

_ROOT = QModelIndex()


class SearchModel(QAbstractTableModel):
    HEADERS = ("Scan", "Tipo", "Valor", "Fuente", "Confianza", "Objetivo", "Fecha")
    MONO_COLUMNS = (0, 2, 5, 6)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._rows: list[dict[str, Any]] = []

    def set_rows(self, rows: list[dict[str, Any]]) -> None:
        self.beginResetModel()
        self._rows = list(rows)
        self.endResetModel()

    def scan_id(self, row: int) -> int:
        return self._rows[row]["scan_id"]

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
        hit = self._rows[index.row()]
        column = index.column()
        if role == Qt.ItemDataRole.FontRole and column in self.MONO_COLUMNS:
            return theme.mono_font()
        if role == Qt.ItemDataRole.ToolTipRole and column == 2:
            return safe_tooltip(hit.get("value", ""))
        if role not in (Qt.ItemDataRole.DisplayRole, SORT_ROLE):
            return None
        return (
            hit.get("scan_id"),
            hit.get("type", ""),
            hit.get("value", ""),
            hit.get("source") or "",
            hit.get("confidence") or "",
            hit.get("target", ""),
            str(hit.get("started_at", "")).replace("T", " ")[:19],
        )[column]


class SearchPanel(QWidget):
    scan_requested = Signal(int)
    finished = Signal()  # terminó una búsqueda (bien o mal)

    def __init__(self, api: CliApi, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._api = api
        self._generation = 0  # solo vale la respuesta de la última búsqueda
        self.model = SearchModel(self)
        self.table, self.proxy = make_table(self.model)
        self.table.setAccessibleName(self.tr("Resultados de la búsqueda"))
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        set_widths(self.table, {0: 60, 1: 90, 3: 100, 4: 90, 5: 210, 6: 170})
        self.table.doubleClicked.connect(self._open)
        self.table.activated.connect(self._open)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._menu)
        self.summary = label("", "muted", wrap=True)  # puede mostrar la consulta o el stderr
        self.empty = EmptyState(
            "search",
            self.tr("Busca en todos los scans guardados"),
            self.tr("Escribe un dominio, una IP, un email o un hash en la barra superior."),
        )
        self.content = QStackedWidget()
        self.content.addWidget(self.empty)
        self.content.addWidget(self.table)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(8)
        layout.addWidget(self.summary)
        layout.addWidget(self.content, 1)

    def run(self, query: str) -> None:
        query = query.strip()
        self._generation += 1
        generation = self._generation
        if not query:
            self.summary.setText("")
            self.content.setCurrentWidget(self.empty)
            return
        self.summary.setText(self.tr("Buscando…"))
        run_in_thread(
            lambda: self._api.search(query),
            lambda hits: self._on_hits(generation, query, hits),
            lambda exc: self._on_failed(generation, exc),
            self,
        )

    def _on_hits(self, generation: int, query: str, hits: list[dict[str, Any]]) -> None:
        if generation != self._generation:
            return
        self.model.set_rows(hits)
        self.summary.setText(f"{len(hits)} {self.tr('coincidencias para')} «{query}»")
        if not hits:
            self.empty.set_message(
                self.tr("Sin coincidencias"),
                self.tr("Ningún scan guardado contiene ese dato."),
            )
        self.content.setCurrentWidget(self.table if hits else self.empty)
        self.finished.emit()

    def _on_failed(self, generation: int, exc: Exception) -> None:
        if generation != self._generation:
            return
        self.model.set_rows([])
        self.summary.setText(f"{self.tr('No se pudo buscar')}: {exc}")
        self.empty.set_message(self.tr("La búsqueda ha fallado"))
        self.content.setCurrentWidget(self.empty)
        self.finished.emit()

    def _open(self, index: QModelIndex) -> None:
        self.scan_requested.emit(self.model.scan_id(source_row(self.table, index)))

    def _menu(self, position: QPoint) -> None:
        show_copy_menu(
            self.table,
            position,
            value_column=2,
            extra=((self.tr("Abrir scan"), "external-link", self._open),),
        )

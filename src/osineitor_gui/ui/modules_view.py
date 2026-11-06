"""Salud de los módulos (`doctor --json`): tabla con el veredicto de cada fuente."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QObject, Qt
from PySide6.QtGui import QBrush
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from osineitor_gui.api import CliApi
from osineitor_gui.ui import risk_dialog
from osineitor_gui.ui.models import STATUS_COLORS
from osineitor_gui.ui.worker import run_in_thread

_ROOT = QModelIndex()

VERDICT_LABELS = {
    "ok": "ok",
    "empty": "sin resultados",
    "fail": "falla",
    "skipped": "omitido",
    "unchecked": "sin comprobar",
}
# Mismos colores que la actividad de un scan: lo que falla se ve a simple vista.
VERDICT_COLORS = {
    "fail": STATUS_COLORS["error"],
    "empty": STATUS_COLORS["quota"],
    "skipped": STATUS_COLORS["skipped"],
    "unchecked": STATUS_COLORS["skipped"],
}


class HealthModel(QAbstractTableModel):
    HEADERS = ("Módulo", "Veredicto", "Detalle", "Tiempo", "Peticiones")

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._rows: list[dict[str, Any]] = []

    def set_rows(self, rows: list[dict[str, Any]]) -> None:
        self.beginResetModel()
        self._rows = list(rows)
        self.endResetModel()

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
        row = self._rows[index.row()]
        verdict = str(row.get("verdict", ""))
        column = index.column()
        if role == Qt.ItemDataRole.ForegroundRole:
            color = VERDICT_COLORS.get(verdict)
            return QBrush(color) if color and column == 1 else None
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        duration, requests = row.get("duration_ms"), row.get("requests")
        return (
            row.get("module", ""),
            self.tr(VERDICT_LABELS[verdict]) if verdict in VERDICT_LABELS else verdict,
            row.get("detail") or "",
            "" if duration is None else f"{duration} ms",
            "" if requests is None else requests,
        )[column]


class HealthDialog(QDialog):
    """Lanza `doctor` bajo demanda (puede tardar minutos) y muestra el veredicto por módulo."""

    def __init__(self, api: CliApi, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._api = api
        self._running = False
        self.setWindowTitle(self.tr("Salud de los módulos"))
        self.resize(720, 420)
        self.model = HealthModel(self)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.run_button = QPushButton(self.tr("Comprobar"))
        self.run_button.clicked.connect(self.check)
        self.active_box = QCheckBox(self.tr("Incluir módulos activos (contactan con el objetivo)"))
        self.active_box.toggled.connect(self._on_active)
        self.busy = QProgressBar()
        self.busy.setRange(0, 0)  # indeterminado: `doctor` no informa del avance
        self.busy.hide()
        self.status = QLabel(self.tr("Pulsa «Comprobar» para consultar cada fuente."))
        self.status.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.addWidget(self.run_button)
        layout.addWidget(self.active_box)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.busy)
        layout.addWidget(self.status)

    def _on_active(self, checked: bool) -> None:
        if checked and not risk_dialog.confirm_active(self):
            self.active_box.blockSignals(True)  # sin reentrar en `toggled`
            self.active_box.setChecked(False)
            self.active_box.blockSignals(False)

    def check(self) -> None:
        if self._running:
            return
        self._running = True
        self.run_button.setEnabled(False)
        self.busy.show()
        self.status.setText(self.tr("Comprobando… puede tardar unos minutos."))
        active = self.active_box.isChecked()  # solo está marcada tras confirmarla
        run_in_thread(lambda: self._api.doctor(active=active), self._done, self._failed, self)

    def _done(self, rows: list[dict[str, Any]]) -> None:
        self.model.set_rows(rows)
        self.status.setText("" if rows else self.tr("No hay módulos que comprobar."))
        self._finish()

    def _failed(self, exc: Exception) -> None:
        self.status.setText(f"{self.tr('No se pudo comprobar la salud')}: {exc}")
        self._finish()

    def _finish(self) -> None:
        self._running = False
        self.busy.hide()
        self.run_button.setEnabled(True)

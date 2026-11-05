"""Vista de un scan (una pestaña): entidades encontradas y actividad por módulo, en vivo."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from PySide6.QtCore import QModelIndex, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from osineitor_gui.scan_request import ScanRequest
from osineitor_gui.session import (
    CANCELLED,
    COMPLETE,
    FAILED,
    IDLE,
    RUNNING,
    TRUNCATED,
    ScanSession,
)
from osineitor_gui.ui.entity_detail import EntityDetail
from osineitor_gui.ui.models import EntityTableModel, ModuleActivityModel
from osineitor_gui.ui.runner import ScanRunner

REFRESH_MS = 100  # los eventos llegan a ráfagas: se repinta como mucho cada 100 ms


class ScanView(QWidget):
    changed = Signal()  # el estado de la sesión cambió (la ventana actualiza barra y botones)

    def __init__(
        self,
        request: ScanRequest | None = None,
        cli: Sequence[str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """Sin `request` es la vista de un scan guardado (ver `from_result`): no lanza nada."""
        super().__init__(parent)
        self.request = request
        self.session = ScanSession()
        self._runner: ScanRunner | None = None
        if request is not None:
            self._runner = ScanRunner(request.to_args(), cli, self)
            self._runner.event.connect(self._on_event)
            self._runner.finished.connect(self._on_finished)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(REFRESH_MS)
        self._timer.timeout.connect(self.refresh)

        self.entities_model = EntityTableModel(self.session, self)
        self.modules_model = ModuleActivityModel(self.session, self)

        self.type_filter = QComboBox()
        self.type_filter.currentIndexChanged.connect(self._filter_changed)
        self.search = QLineEdit()
        self.search.setPlaceholderText(self.tr("Buscar en valor, fuente y datos"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter_changed)
        self.banner = QLabel()
        self.banner.setWordWrap(True)
        self.banner.setStyleSheet("color: #d93025; font-weight: bold;")
        self.banner.hide()

        self.entities_table = self._table(self.entities_model)
        self.modules_table = self._table(self.modules_model)
        self.entities_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.modules_table.horizontalHeader().setSectionResizeMode(
            6, QHeaderView.ResizeMode.Stretch
        )
        self.detail = EntityDetail()
        self.entities_table.selectionModel().currentRowChanged.connect(self._row_changed)
        self.entities_model.modelReset.connect(lambda: self.detail.show_entity(None))
        upper = QSplitter(Qt.Orientation.Horizontal)
        upper.addWidget(self.entities_table)
        upper.addWidget(self.detail)
        upper.setStretchFactor(0, 3)
        upper.setStretchFactor(1, 2)
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(upper)
        splitter.addWidget(self.modules_table)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        filters = QHBoxLayout()
        filters.addWidget(self.type_filter)
        filters.addWidget(self.search, 1)
        layout = QVBoxLayout(self)
        layout.addLayout(filters)
        layout.addWidget(self.banner)
        layout.addWidget(splitter, 1)
        self._rebuild_type_filter()

    @classmethod
    def from_result(cls, result: dict[str, Any], parent: QWidget | None = None) -> ScanView:
        """Vista de un scan guardado (la salida de `CliApi.show`), con el aspecto de uno en vivo."""
        view = cls(parent=parent)
        view.session.load_result(result)
        view.refresh()
        return view

    @property
    def scan_id(self) -> int | None:
        return self.session.scan_id

    def _row_changed(self, current: QModelIndex, _previous: QModelIndex) -> None:
        self.detail.show_entity(
            self.entities_model.entity(current.row()) if current.isValid() else None
        )

    @staticmethod
    def _table(model) -> QTableView:
        table = QTableView()
        table.setModel(model)
        table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        table.verticalHeader().hide()
        table.horizontalHeader().setStretchLastSection(False)
        return table

    # --- ciclo de vida ----------------------------------------------------------------------

    def start(self) -> None:
        if self._runner is None:
            return
        self.session.begin()
        self._runner.start()
        self.refresh()

    def cancel(self) -> None:
        if self._runner is not None:
            self._runner.cancel()

    def kill(self) -> None:
        if self._runner is not None:
            self._runner.kill()

    def wait(self, timeout: float | None = None) -> int:
        return self._runner.wait(timeout) if self._runner is not None else 0

    @property
    def is_running(self) -> bool:
        return self.session.state == RUNNING

    # --- eventos ----------------------------------------------------------------------------

    def _on_event(self, event) -> None:
        self.session.feed(event)
        if not self._timer.isActive():
            self._timer.start()

    def _on_finished(self, code: int) -> None:
        self.session.process_exited(code, self._runner.stderr_tail)
        self._timer.stop()
        self.refresh()

    # --- pintado ----------------------------------------------------------------------------

    def title(self) -> str:
        if self.request is not None:
            target = self.session.target_value or self.request.target.strip()
        else:
            target = f"{self.session.target_value} #{self.session.scan_id}"
        suffix = {
            IDLE: "",
            RUNNING: self.tr("en curso"),
            COMPLETE: "",
            TRUNCATED: self.tr("incompleto"),
            CANCELLED: self.tr("cancelado"),
            FAILED: self.tr("fallido"),
        }.get(self.session.state, "")
        return f"{target} ({suffix})" if suffix else target

    def status_text(self) -> str:
        names = {
            IDLE: self.tr("sin iniciar"),
            RUNNING: self.tr("en curso"),
            COMPLETE: self.tr("completo"),
            TRUNCATED: self.tr("presupuesto agotado"),
            CANCELLED: self.tr("cancelado"),
            FAILED: self.tr("fallido"),
        }
        return names.get(self.session.state, self.session.state)

    def refresh(self) -> None:
        self._rebuild_type_filter()
        self.entities_model.refresh()
        self.modules_model.refresh()
        self._update_banner()
        self.changed.emit()

    def _update_banner(self) -> None:
        if not self.session.incomplete:
            self.banner.hide()
            return
        text = f"{self.tr('Resultado incompleto')}: {self.status_text()}"
        if self.session.message:
            text += f"\n{self.session.message}"
        self.banner.setText(text)
        self.banner.show()

    def _selected_types(self) -> set[str] | None:
        selected = self.type_filter.currentData()
        return None if selected is None else {selected}

    def _rebuild_type_filter(self) -> None:
        """Una entrada por tipo con su recuento; conserva la elegida."""
        counts = self.session.counts_by_type()
        current = self.type_filter.currentData()
        self.type_filter.blockSignals(True)
        self.type_filter.clear()
        self.type_filter.addItem(f"{self.tr('Todos los tipos')} ({sum(counts.values())})", None)
        for kind, count in counts.items():
            self.type_filter.addItem(f"{kind} ({count})", kind)
        index = self.type_filter.findData(current)
        self.type_filter.setCurrentIndex(max(index, 0))
        self.type_filter.blockSignals(False)

    def _filter_changed(self, *_args) -> None:
        self.entities_model.set_filter(self._selected_types(), self.search.text())

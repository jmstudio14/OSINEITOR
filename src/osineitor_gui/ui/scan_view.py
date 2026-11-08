"""Vista de un scan (una pestaña): entidades encontradas y actividad por módulo, en vivo."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from PySide6.QtCore import QModelIndex, QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from osineitor_gui.events import EXIT_MODULE_ERRORS
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
from osineitor_gui.ui.tables import (
    install_badges,
    make_table,
    set_widths,
    show_copy_menu,
    source_row,
)
from osineitor_gui.ui.widgets import Card, label, set_style

REFRESH_MS = 100  # los eventos llegan a ráfagas: se repinta como mucho cada 100 ms
STACK_WIDTH = 760
STATE_TONES = {
    IDLE: "neutral",
    RUNNING: "info",
    COMPLETE: "safe",
    TRUNCATED: "warning",
    CANCELLED: "warning",
    FAILED: "critical",
}


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

        self.header_target = label("", "monoTitle")
        self.header_state = label("", "chip")
        self.header_counts = label("", "muted")

        self.type_filter = QComboBox()
        self.type_filter.setAccessibleName(self.tr("Filtrar por tipo de entidad"))
        self.type_filter.currentIndexChanged.connect(self._filter_changed)
        self.search = QLineEdit()
        self.search.setPlaceholderText(self.tr("Buscar en valor, fuente y datos"))
        self.search.setAccessibleName(self.tr("Buscar en las entidades"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter_changed)
        # Puede traer el stderr de la CLI: siempre texto plano, nunca HTML.
        self.banner = label("", wrap=True)
        self.banner_box = QFrame()
        self.banner_box.setProperty("role", "banner")
        banner_layout = QHBoxLayout(self.banner_box)
        banner_layout.setContentsMargins(12, 8, 12, 8)
        banner_layout.addWidget(self.banner)
        self.banner_box.setVisible(False)
        self.banner.hide()

        self.entities_table, self.entities_proxy = make_table(self.entities_model)
        self.modules_table, self.modules_proxy = make_table(self.modules_model)
        self.entities_table.setAccessibleName(self.tr("Entidades encontradas"))
        self.modules_table.setAccessibleName(self.tr("Actividad por módulo"))
        self.entities_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.modules_table.horizontalHeader().setSectionResizeMode(
            6, QHeaderView.ResizeMode.Stretch
        )
        set_widths(self.entities_table, {0: 90, 2: 100, 3: 104, 4: 90})
        set_widths(self.modules_table, {0: 150, 1: 130, 2: 80, 3: 80, 4: 60, 5: 70})
        install_badges(self.entities_table, EntityTableModel.SEVERITY)
        install_badges(self.entities_table, EntityTableModel.CONFIDENCE)
        install_badges(self.modules_table, 1)
        self.entities_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.entities_table.customContextMenuRequested.connect(self._entity_menu)
        self.detail = EntityDetail()
        self.entities_table.selectionModel().currentRowChanged.connect(self._row_changed)
        self.entities_model.modelReset.connect(lambda: self.detail.show_entity(None))

        entities_card = Card(self.tr("Entidades"))
        filters = QHBoxLayout()
        filters.addWidget(self.type_filter)
        filters.addWidget(self.search, 1)
        entities_card.body.addLayout(filters)
        entities_card.body.addWidget(self.entities_table, 1)
        detail_card = Card(self.tr("Detalle"))
        detail_card.body.addWidget(self.detail, 1)
        modules_card = Card(self.tr("Actividad por módulo"))
        modules_card.setMinimumHeight(190)
        modules_card.body.addWidget(self.modules_table, 1)

        upper = self.upper = QSplitter(Qt.Orientation.Horizontal)
        upper.addWidget(entities_card)
        upper.addWidget(detail_card)
        upper.setStretchFactor(0, 3)
        upper.setStretchFactor(1, 2)
        upper.setSizes([600, 340])
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(upper)
        splitter.addWidget(modules_card)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)

        heading = QHBoxLayout()
        heading.addWidget(self.header_target)
        heading.addWidget(self.header_state)
        heading.addStretch(1)
        heading.addWidget(self.header_counts)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)
        layout.addLayout(heading)
        layout.addWidget(self.banner_box)
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
            self.entities_model.entity(source_row(self.entities_table, current))
            if current.isValid()
            else None
        )

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        # Sin anchura para dos paneles, el detalle pasa debajo: la tabla manda.
        narrow = self.width() < STACK_WIDTH
        wanted = Qt.Orientation.Vertical if narrow else Qt.Orientation.Horizontal
        if self.upper.orientation() != wanted:
            self.upper.setOrientation(wanted)

    def _entity_menu(self, position: QPoint) -> None:
        show_copy_menu(self.entities_table, position, value_column=1)

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
        if self.session.state == COMPLETE and self.session.exit_code == EXIT_MODULE_ERRORS:
            return self.tr("completo, con errores en módulos")
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
        self._update_heading()
        self.changed.emit()

    def _update_heading(self) -> None:
        session = self.session
        target = session.target_value or (self.request.target.strip() if self.request else "")
        self.header_target.setText(target)
        tone = STATE_TONES.get(session.state, "neutral")
        if session.state == COMPLETE and session.exit_code == EXIT_MODULE_ERRORS:
            tone = "warning"
        self.header_state.setText(self.status_text())
        if self.header_state.property("tone") != tone:
            set_style(self.header_state, tone=tone)
        self.header_counts.setText(
            f"{session.done}/{session.total} {self.tr('tareas')} · "
            f"{len(session.entities)} {self.tr('entidades')} · "
            f"{session.requests} {self.tr('peticiones')}"
        )

    def _update_banner(self) -> None:
        if not self.session.incomplete:
            self.banner.hide()
            self.banner_box.hide()
            return
        text = f"{self.tr('Resultado incompleto')}: {self.status_text()}"
        if self.session.message:
            text += f"\n{self.session.message}"
        self.banner.setText(text)
        tone = "critical" if self.session.state == FAILED else "warning"
        if self.banner_box.property("tone") != tone:
            set_style(self.banner_box, tone=tone)
        self.banner.show()
        self.banner_box.show()

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

"""Página Casos: agrupar scans de una investigación, con notas y correlaciones entre casos."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QModelIndex, Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLineEdit,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from osineitor_gui.api import CliApi
from osineitor_gui.ui.tables import ColumnSpec, RowsModel, make_table, set_widths, source_row
from osineitor_gui.ui.widgets import Card, EmptyState, button, label
from osineitor_gui.ui.worker import run_in_thread


def _date(value: object) -> str:
    return str(value or "").replace("T", " ")[:19]


class CasesPanel(QWidget):
    scan_requested = Signal(int)
    loaded = Signal()  # terminó una recarga o una acción (bien o mal)

    def __init__(self, api: CliApi, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._api = api
        self._selected: str | None = None

        self.cases_model = RowsModel(
            (
                ColumnSpec("Caso", lambda c: c["name"], tooltip=True),
                ColumnSpec("Scans", lambda c: c["scans"]),
                ColumnSpec("Etiquetas", lambda c: ", ".join(c["tags"]), tooltip=True),
            ),
            self,
        )
        self.cases_table, self.cases_proxy = make_table(self.cases_model)
        self.cases_table.setAccessibleName(self.tr("Casos"))
        self.cases_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        set_widths(self.cases_table, {1: 60, 2: 110})
        self.cases_table.selectionModel().currentRowChanged.connect(self._case_changed)

        self.scans_model = RowsModel(
            (
                ColumnSpec("Scan", lambda s: s["id"], mono=True),
                ColumnSpec("Tipo", lambda s: s["target_type"]),
                ColumnSpec("Objetivo", lambda s: s["target"], mono=True, tooltip=True),
                ColumnSpec("Entidades", lambda s: s["entities"]),
                ColumnSpec("Fecha", lambda s: _date(s["started_at"]), mono=True),
            ),
            self,
        )
        self.scans_table, self.scans_proxy = make_table(self.scans_model)
        self.scans_table.setAccessibleName(self.tr("Scans del caso"))
        self.scans_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        set_widths(self.scans_table, {0: 60, 1: 90, 3: 80, 4: 170})
        self.scans_table.doubleClicked.connect(self._open_scan)
        self.scans_table.activated.connect(self._open_scan)

        self.notes_model = RowsModel(
            (
                ColumnSpec("Fecha", lambda n: _date(n["at"]), mono=True),
                ColumnSpec("Nota", lambda n: n["text"], tooltip=True),
            ),
            self,
        )
        self.notes_table, _ = make_table(self.notes_model)
        self.notes_table.setAccessibleName(self.tr("Notas del caso"))
        self.notes_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        set_widths(self.notes_table, {0: 170})

        self.links_model = RowsModel(
            (
                ColumnSpec("Tipo", lambda c: c["type"]),
                ColumnSpec("Dato", lambda c: c["value"], mono=True, tooltip=True),
                ColumnSpec("También en", lambda c: ", ".join(map(str, c["cases"])), tooltip=True),
            ),
            self,
        )
        self.links_table, _ = make_table(self.links_model)
        self.links_table.setAccessibleName(self.tr("Datos compartidos con otros casos"))
        self.links_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        set_widths(self.links_table, {0: 90, 2: 170})

        self.new_button = button(self.tr("Nuevo caso…"), "primary")
        self.new_button.clicked.connect(self._new_case)
        self.add_button = button(self.tr("Añadir scan…"))
        self.add_button.clicked.connect(self._add_scan)
        self.note_button = button(self.tr("Añadir nota…"))
        self.note_button.clicked.connect(self._add_note)
        # Puede mostrar el stderr de la CLI: siempre texto plano.
        self.status = label("", "muted", wrap=True)
        self.description = label("", "muted", wrap=True)

        self.empty = EmptyState(
            "folder-open",
            self.tr("Todavía no hay casos"),
            self.tr("Un caso agrupa los scans de una investigación y avisa de los datos en común."),
        )
        scans_card = Card(self.tr("Scans"))
        scans_card.body.addWidget(self.scans_table, 1)
        notes_card = Card(self.tr("Notas"))
        notes_card.body.addWidget(self.notes_table, 1)
        links_card = Card(self.tr("Datos que también figuran en otros casos"))
        links_card.body.addWidget(self.links_table, 1)
        detail = QWidget()
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.addWidget(self.description)
        detail_layout.addWidget(scans_card, 2)
        detail_layout.addWidget(notes_card, 1)
        detail_layout.addWidget(links_card, 1)
        list_card = Card(self.tr("Casos"))
        list_card.body.addWidget(self.cases_table, 1)
        split = QSplitter(Qt.Orientation.Horizontal)
        split.addWidget(list_card)
        split.addWidget(detail)
        split.setStretchFactor(0, 2)
        split.setStretchFactor(1, 3)
        split.setSizes([400, 600])
        self.content = QStackedWidget()
        self.content.addWidget(self.empty)
        self.content.addWidget(split)

        controls = QHBoxLayout()
        controls.addWidget(self.new_button)
        controls.addWidget(self.add_button)
        controls.addWidget(self.note_button)
        controls.addStretch(1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(8)
        layout.addLayout(controls)
        layout.addWidget(self.content, 1)
        layout.addWidget(self.status)
        self._update_buttons()

    # --- carga ------------------------------------------------------------------------------

    def reload(self) -> None:
        run_in_thread(self._api.case_list, self._on_cases, self._on_failed, self)

    def _on_cases(self, cases: list[dict[str, Any]]) -> None:
        self.cases_model.set_rows(cases)
        self.content.setCurrentIndex(1 if cases else 0)
        names = [case["name"] for case in cases]
        if self._selected in names:
            row = self.cases_proxy.mapFromSource(
                self.cases_model.index(names.index(self._selected), 0)
            ).row()
            self.cases_table.selectRow(row)
        elif cases:
            self.cases_table.selectRow(0)
        else:
            self._selected = None
        self._update_buttons()
        self.loaded.emit()

    def _on_failed(self, exc: Exception) -> None:
        self.status.setText(f"{self.tr('No se pudo completar')}: {exc}")
        self.loaded.emit()

    def _case_changed(self, current: QModelIndex, _previous: QModelIndex) -> None:
        if not current.isValid():
            return
        self._selected = self.cases_model.row(source_row(self.cases_table, current))["name"]
        name = self._selected
        self._update_buttons()
        run_in_thread(lambda: self._api.case_show(name), self._on_case, self._on_failed, self)

    def _on_case(self, case: dict[str, Any]) -> None:
        self.description.setText(case.get("description") or "")
        self.description.setVisible(bool(case.get("description")))
        self.scans_model.set_rows(case.get("scans") or [])
        self.notes_model.set_rows(case.get("notes") or [])
        self.links_model.set_rows(case.get("correlations") or [])
        self.loaded.emit()

    def _update_buttons(self) -> None:
        self.add_button.setEnabled(self._selected is not None)
        self.note_button.setEnabled(self._selected is not None)

    def _open_scan(self, index: QModelIndex) -> None:
        self.scan_requested.emit(self.scans_model.row(source_row(self.scans_table, index))["id"])

    # --- acciones ---------------------------------------------------------------------------

    def _run(self, action, done_text: str) -> None:
        def finished(_result) -> None:
            self.status.setText(done_text)
            self.reload()

        run_in_thread(action, finished, self._on_failed, self)

    def _new_case(self) -> None:
        name, accepted = QInputDialog.getText(
            self, self.tr("Nuevo caso"), self.tr("Nombre del caso:"), QLineEdit.EchoMode.Normal
        )
        name = name.strip()
        if accepted and name:
            self._selected = name
            self._run(lambda: self._api.case_new(name), self.tr("Caso creado."))

    def _add_scan(self) -> None:
        name = self._selected
        if name is None:
            return
        scan_id, accepted = QInputDialog.getInt(
            self, self.tr("Añadir scan"), self.tr("Id del scan guardado:"), 1, 1, 2**31 - 1
        )
        if accepted:
            self._run(lambda: self._api.case_add(name, scan_id), self.tr("Scan añadido."))

    def _add_note(self) -> None:
        name = self._selected
        if name is None:
            return
        text, accepted = QInputDialog.getMultiLineText(
            self, self.tr("Añadir nota"), self.tr("Nota:")
        )
        text = text.strip()
        if accepted and text:
            self._run(lambda: self._api.case_note(name, text), self.tr("Nota añadida."))

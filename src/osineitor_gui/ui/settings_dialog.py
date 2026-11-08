"""Ajustes: API keys de los módulos (se guardan con la CLI, por stdin) y preferencias."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QObject, Qt, Signal
from PySide6.QtGui import QBrush
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QTableView,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from osineitor_gui.api import CliApi, CliError
from osineitor_gui.keys import KeyRow, group_keys
from osineitor_gui.settings import THEMES, GuiSettings
from osineitor_gui.ui import theme
from osineitor_gui.ui.tables import BadgeDelegate, style_table
from osineitor_gui.ui.widgets import button, label
from osineitor_gui.ui.worker import run_in_thread

_ROOT = QModelIndex()


class KeysModel(QAbstractTableModel):
    """Una fila por API key: nombre, módulos que la usan y si está configurada.

    Nunca contiene el valor de una key: la CLI tampoco lo devuelve.
    """

    HEADERS = ("Key", "Módulos", "Estado")

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._rows: list[KeyRow] = []

    def set_rows(self, rows: list[KeyRow]) -> None:
        self.beginResetModel()
        self._rows = list(rows)
        self.endResetModel()

    def key_name(self, row: int) -> str:
        return self._rows[row].name

    def row_of(self, name: str) -> int | None:
        return next((i for i, row in enumerate(self._rows) if row.name == name), None)

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
        if role == Qt.ItemDataRole.ForegroundRole and index.column() == 2:
            return QBrush(theme.tone_color("safe" if row.configured else "warning"))
        if role == Qt.ItemDataRole.FontRole and index.column() == 0:
            return theme.mono_font()
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        state = self.tr("configurada") if row.configured else self.tr("falta")
        return (row.name, ", ".join(row.modules), state)[index.column()]


class SettingsDialog(QDialog):
    theme_changed = Signal(str)  # la ventana principal aplica y guarda el tema

    def __init__(self, api: CliApi, settings: GuiSettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._api = api
        self._busy = False
        self._loaded = False  # `modules()` respondió: hay filas sobre las que actuar
        self.setWindowTitle(self.tr("Ajustes"))
        self.resize(680, 480)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_keys_tab(), self.tr("API keys"))
        self.tabs.addTab(self._build_general_tab(settings), self.tr("General"))
        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs)
        self._update_buttons()

    # --- pestaña «API keys» -----------------------------------------------------------------

    def _build_keys_tab(self) -> QWidget:
        self.model = KeysModel(self)
        self.keys_table = QTableView()
        self.keys_table.setModel(self.model)
        style_table(self.keys_table)
        self.keys_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.keys_table.setAccessibleName(self.tr("API keys de los módulos"))
        self.keys_table.setItemDelegateForColumn(2, BadgeDelegate(self.keys_table))
        self.keys_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.keys_table.selectionModel().selectionChanged.connect(lambda *_: self._update_buttons())

        self.key_input = QLineEdit()
        self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_input.setPlaceholderText(self.tr("Pega la key y pulsa Guardar"))
        self.key_input.setAccessibleName(self.tr("Valor de la API key"))
        self.key_input.returnPressed.connect(self.save)
        self.save_button = button(self.tr("Guardar"), "primary")
        self.save_button.clicked.connect(self.save)
        self.delete_button = button(self.tr("Borrar"))
        self.delete_button.clicked.connect(self.delete)
        self.message = label("", "muted", wrap=True)  # puede mostrar el stderr de la CLI

        row = QHBoxLayout()
        row.addWidget(self.key_input, 1)
        row.addWidget(self.save_button)
        row.addWidget(self.delete_button)
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        layout.addWidget(self.keys_table, 1)
        layout.addLayout(row)
        layout.addWidget(self.message)
        return page

    def reload(self) -> None:
        """Vuelve a pedir los módulos a la CLI: el estado «configurada» sale siempre de ella."""
        self._set_busy(True)
        run_in_thread(self._api.modules, self._on_modules, self._on_modules_failed, self)

    def _on_modules(self, modules: list[dict[str, Any]]) -> None:
        selected = self._selected_name()
        self.model.set_rows(group_keys(modules))
        self._loaded = True
        row = self.model.row_of(selected) if selected else None
        if row is None and self.model.rowCount():
            row = 0
        if row is not None:
            self.keys_table.selectRow(row)
        if not self.model.rowCount():
            self.message.setText(self.tr("Ningún módulo necesita API key."))
        self._set_busy(False)

    def _on_modules_failed(self, exc: Exception) -> None:
        self._loaded = False
        self.model.set_rows([])
        self.message.setText(f"{self.tr('No se pudo cargar la lista de módulos')}: {exc}")
        self._set_busy(False)

    def _selected_name(self) -> str | None:
        rows = self.keys_table.selectionModel().selectedRows()
        return self.model.key_name(rows[0].row()) if rows else None

    def save(self) -> None:
        name = self._selected_name()
        if self._busy or name is None:
            return
        value = self.key_input.text().strip()
        if not value:
            self.message.setText(self.tr("Escribe la key antes de guardar."))
            return
        self._set_busy(True)
        run_in_thread(
            lambda: self._api.config_set(name, value),
            lambda _done: self._after_change(self.tr("Key guardada.")),
            lambda exc: self._change_failed(self.tr("No se pudo guardar la key"), exc),
            self,
        )

    def delete(self) -> None:
        name = self._selected_name()
        if self._busy or name is None:
            return
        self._set_busy(True)
        run_in_thread(
            lambda: self._api.config_unset(name),
            lambda _done: self._after_change(self.tr("Key borrada.")),
            lambda exc: self._change_failed(self.tr("No se pudo borrar la key"), exc),
            self,
        )

    def _after_change(self, text: str) -> None:
        self.key_input.clear()
        self.message.setText(text)
        self.reload()

    def _change_failed(self, text: str, exc: Exception) -> None:
        # Nunca se repite `stderr` ni el valor: podrían llevar la key que se acaba de pegar.
        code = getattr(exc, "exit_code", None) if isinstance(exc, CliError) else None
        self.message.setText(f"{text} ({self.tr('código')} {code})" if code is not None else text)
        self._set_busy(False)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._update_buttons()

    def _update_buttons(self) -> None:
        enabled = self._loaded and not self._busy and self._selected_name() is not None
        self.save_button.setEnabled(enabled)
        self.delete_button.setEnabled(enabled)

    # --- pestaña «General» ------------------------------------------------------------------

    def _build_general_tab(self, settings: GuiSettings) -> QWidget:
        names = {
            "system": self.tr("Sistema"),
            "light": self.tr("Claro"),
            "dark": self.tr("Oscuro"),
        }
        self.theme_box = QComboBox()
        self.theme_box.setAccessibleName(self.tr("Tema"))
        for name in THEMES:
            self.theme_box.addItem(names[name], name)
        self.theme_box.setCurrentIndex(self.theme_box.findData(settings.theme))
        self.theme_box.activated.connect(
            lambda _index: self.theme_changed.emit(self.theme_box.currentData())
        )
        page = QWidget()
        form = QFormLayout(page)
        form.addRow(self.tr("Tema"), self.theme_box)
        return page

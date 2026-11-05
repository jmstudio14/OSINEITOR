"""Modelos de tabla sobre `ScanSession`: entidades encontradas y actividad por módulo."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QObject, Qt
from PySide6.QtGui import QBrush, QColor

from osineitor_gui.session import ScanSession

_ROOT = QModelIndex()  # raíz de un modelo de tabla: sin padre

STATUS_LABELS = {
    "running": "en curso",
    "ok": "ok",
    "empty": "sin resultados",
    "error": "error",
    "quota": "límite de uso",
    "skipped": "omitido",
    "pending": "pendiente",
}
# Legibles en tema claro y oscuro: error y límite de uso se ven a simple vista.
STATUS_COLORS = {
    "running": QColor("#2f80ed"),
    "error": QColor("#d93025"),
    "quota": QColor("#e37400"),
    "skipped": QColor("#8a8a8a"),
    "pending": QColor("#8a8a8a"),
}


class EntityTableModel(QAbstractTableModel):
    HEADERS = ("Tipo", "Valor", "Fuente")

    def __init__(self, session: ScanSession, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._session = session
        self._types: set[str] | None = None
        self._text = ""
        self._rows: list[dict[str, Any]] = []

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
        entity = self._rows[index.row()]
        return (entity["type"], entity.get("value", ""), entity.get("source") or "")[index.column()]

    def entity(self, row: int) -> dict[str, Any]:
        return self._rows[row]

    def set_filter(self, types: set[str] | None, text: str) -> None:
        self._types, self._text = types, text
        self.reload()

    def reload(self) -> None:
        self.beginResetModel()
        self._rows = self._session.filtered(self._types, self._text)
        self.endResetModel()

    def refresh(self) -> None:
        """Recoge lo nuevo de la sesión: las entidades solo se añaden al final de la lista."""
        rows = self._session.filtered(self._types, self._text)
        old = len(self._rows)
        if len(rows) >= old and rows[:old] == self._rows:
            if len(rows) > old:
                self.beginInsertRows(QModelIndex(), old, len(rows) - 1)
                self._rows = rows
                self.endInsertRows()
        else:  # la sesión se reinició o cargó otro resultado
            self.beginResetModel()
            self._rows = rows
            self.endResetModel()


class ModuleActivityModel(QAbstractTableModel):
    HEADERS = ("Módulo", "Estado", "Entidades", "Peticiones", "Caché", "Tiempo", "Mensaje")

    def __init__(self, session: ScanSession, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._session = session
        self._names: list[str] = []

    def rowCount(self, parent: QModelIndex = _ROOT) -> int:
        return 0 if parent.isValid() else len(self._names)

    def columnCount(self, parent: QModelIndex = _ROOT) -> int:
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.tr(self.HEADERS[section])
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        module = self._session.modules[self._names[index.row()]]
        column = index.column()
        if role == Qt.ItemDataRole.ForegroundRole:
            color = STATUS_COLORS.get(module.status)
            return QBrush(color) if color and column == 1 else None
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        return (
            module.name,
            self.tr(STATUS_LABELS[module.status]),
            module.entities,
            module.requests,
            module.cache_hits,
            f"{module.duration_ms / 1000:.1f} s",
            module.message,
        )[column]

    def status_at(self, row: int) -> str:
        return self._session.modules[self._names[row]].status

    def refresh(self) -> None:
        names = list(self._session.modules)
        if names != self._names:
            self.beginResetModel()
            self._names = names
            self.endResetModel()
        elif names:
            self.dataChanged.emit(
                self.index(0, 0), self.index(len(names) - 1, len(self.HEADERS) - 1)
            )

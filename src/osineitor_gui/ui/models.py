"""Modelos de tabla sobre `ScanSession`: entidades encontradas y actividad por módulo."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QObject, Qt
from PySide6.QtGui import QBrush

from osineitor_gui.dashboard import SEVERITY_LABELS
from osineitor_gui.session import ScanSession
from osineitor_gui.ui import theme
from osineitor_gui.ui.tables import SORT_ROLE
from osineitor_gui.ui.widgets import safe_tooltip

_ROOT = QModelIndex()  # raíz de un modelo de tabla: sin padre

STATUS_LABELS = {
    "running": "en curso",
    "ok": "ok",
    "empty": "sin resultados",
    "error": "error",
    "quota": "límite de uso",
    "skipped": "omitido",
    "pending": "pendiente",
    "unused": "sin ejecutar",
}
# Estado de un módulo → token: error y límite de uso se ven a simple vista.
STATUS_TONES = {
    "running": "info",
    "ok": "safe",
    "error": "critical",
    "quota": "high",
    "empty": "neutral",
    "skipped": "neutral",
    "pending": "neutral",
    "unused": "neutral",
}
CONFIDENCE_TONES = {"alto": "safe", "medio": "warning", "bajo": "neutral"}
SEVERITY_ORDER = {name: i for i, name in enumerate(("critical", "high", "medium", "low", "info"))}


class EntityTableModel(QAbstractTableModel):
    HEADERS = ("Tipo", "Valor", "Fuente", "Severidad", "Confianza")
    SEVERITY, CONFIDENCE = 3, 4

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
        if not index.isValid():
            return None
        entity = self._rows[index.row()]
        column = index.column()
        severity = (entity.get("data") or {}).get("severity") if entity["type"] == "finding" else ""
        confidence = entity.get("confidence") or ""
        if role == SORT_ROLE and column == self.SEVERITY:
            return SEVERITY_ORDER.get(severity, len(SEVERITY_ORDER))
        if role in (Qt.ItemDataRole.DisplayRole, SORT_ROLE):
            return (
                entity["type"],
                entity.get("value", ""),
                entity.get("source") or "",
                self.tr(SEVERITY_LABELS.get(severity, "")),
                confidence,
            )[column]
        if role == Qt.ItemDataRole.FontRole and column == 1:
            return theme.mono_font()
        if role == Qt.ItemDataRole.ToolTipRole and column == 1:
            return safe_tooltip(entity.get("value", ""))
        if role == Qt.ItemDataRole.ForegroundRole:
            tone = None
            if column == self.SEVERITY:
                tone = theme.SEVERITY_TONES.get(severity)
            elif column == self.CONFIDENCE:
                tone = CONFIDENCE_TONES.get(confidence)
            return QBrush(theme.tone_color(tone)) if tone else None
        return None

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
        status = self.status_at(index.row())
        if role == Qt.ItemDataRole.ForegroundRole:
            return QBrush(theme.tone_color(STATUS_TONES[status])) if column == 1 else None
        if role == Qt.ItemDataRole.FontRole and column == 0:
            return theme.mono_font()
        if role == Qt.ItemDataRole.ToolTipRole and column == 6:
            return safe_tooltip(module.message)
        if role == SORT_ROLE and column == 5:
            return module.duration_ms
        if role not in (Qt.ItemDataRole.DisplayRole, SORT_ROLE):
            return None
        return (
            module.name,
            self.tr(STATUS_LABELS[status]),
            module.entities,
            module.requests,
            module.cache_hits,
            f"{module.duration_ms / 1000:.1f} s",
            module.message,
        )[column]

    def status_at(self, row: int) -> str:
        status = self._session.modules[self._names[row]].status
        # Con el scan acabado, «pendiente» ya no es esperar: el módulo no llegó a ejecutarse.
        return "unused" if status == "pending" and self._session.finished else status

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

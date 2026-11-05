"""Panel de detalle de la entidad seleccionada: fuente, origen y campos de `data`."""

from __future__ import annotations

import json
from typing import Any

from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


class EntityDetail(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.placeholder = QLabel(self.tr("Selecciona una entidad"))
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels([self.tr("Campo"), self.tr("Valor")])
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        layout = QVBoxLayout(self)
        layout.addWidget(self.placeholder)
        layout.addWidget(self.table)
        self.show_entity(None)

    def show_entity(self, entity: dict[str, Any] | None) -> None:
        self.placeholder.setVisible(entity is None)
        self.table.setVisible(entity is not None)
        self.table.setRowCount(0)
        if entity is None:
            return
        rows = [
            (self.tr("Fuente"), _text(entity.get("source"))),
            (self.tr("Origen"), _text(entity.get("parent"))),
            *((str(key), _text(value)) for key, value in (entity.get("data") or {}).items()),
        ]
        self.table.setRowCount(len(rows))
        for row, (key, value) in enumerate(rows):
            self.table.setItem(row, 0, QTableWidgetItem(key))
            self.table.setItem(row, 1, QTableWidgetItem(value))

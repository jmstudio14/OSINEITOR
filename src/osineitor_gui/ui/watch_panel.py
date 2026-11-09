"""Página Vigilancia: consulta de `watch list`. Lanzar `watch run` se queda en la CLI.

`watch run` envía notificaciones reales, puede usar módulos activos y no se puede cancelar.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QHeaderView, QStackedWidget, QVBoxLayout, QWidget

from osineitor_gui.api import CliApi, CliError
from osineitor_gui.events import EXIT_USAGE
from osineitor_gui.ui.tables import ColumnSpec, RowsModel, install_badges, make_table, set_widths
from osineitor_gui.ui.widgets import EmptyState, button, label
from osineitor_gui.ui.worker import run_in_thread

STATUS_TONES = {"complete": "safe", "truncated": "warning", "cancelled": "warning"}


def _every(seconds: float) -> str:
    hours = seconds / 3600
    return f"{hours / 24:g} d" if hours >= 24 else f"{hours:g} h"


class WatchPanel(QWidget):
    loaded = Signal()  # terminó una recarga (bien o mal)

    def __init__(self, api: CliApi, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._api = api
        self.model = RowsModel(
            (
                ColumnSpec("Objetivo", lambda t: t["target"], mono=True, tooltip=True),
                ColumnSpec("Tipo", lambda t: t["type"]),
                ColumnSpec("Cada", lambda t: _every(t["every"]), sort=lambda t: t["every"]),
                ColumnSpec(
                    "Última ejecución",
                    lambda t: (t["last_run"] or "nunca").replace("T", " ")[:19],
                    mono=True,
                ),
                ColumnSpec(
                    "Estado",
                    lambda t: t["last_status"] or "sin ejecutar",
                    tone=lambda t: STATUS_TONES.get(t["last_status"], "neutral"),
                ),
                ColumnSpec(
                    "Toca",
                    lambda t: "sí" if t["due"] else "no",
                    tone=lambda t: "warning" if t["due"] else "neutral",
                ),
                ColumnSpec("Avisa por", lambda t: ", ".join(t["notify"]), tooltip=True),
            ),
            self,
        )
        self.table, self.proxy = make_table(self.model)
        self.table.setAccessibleName(self.tr("Objetivos vigilados"))
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        set_widths(self.table, {1: 90, 2: 70, 3: 170, 4: 130, 5: 70, 6: 150})
        install_badges(self.table, 4)
        install_badges(self.table, 5)
        self.refresh_button = button(self.tr("Actualizar"))
        self.refresh_button.clicked.connect(self.reload)
        self.note = label(
            self.tr(
                "Esta página solo consulta. Para ejecutar la vigilancia: «osineitor watch run». "
                "Envía avisos reales y puede usar módulos activos."
            ),
            "muted",
            wrap=True,
        )
        self.status = label("", "error", wrap=True)  # puede mostrar el stderr de la CLI
        self.status.hide()
        self.empty = EmptyState(
            "eye",
            self.tr("No hay objetivos vigilados"),
            self.tr(
                "Se definen en el fichero watch.yml de la carpeta de configuración. "
                "Consulta docs/VIGILANCIA.md para crearlo."
            ),
        )
        self.content = QStackedWidget()
        self.content.addWidget(self.empty)
        self.content.addWidget(self.table)
        controls = QHBoxLayout()
        controls.addWidget(self.note, 1)
        controls.addWidget(self.refresh_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(8)
        layout.addLayout(controls)
        layout.addWidget(self.content, 1)
        layout.addWidget(self.status)

    def reload(self) -> None:
        self.refresh_button.setEnabled(False)
        run_in_thread(self._api.watch_list, self._on_rows, self._on_failed, self)

    def _on_rows(self, rows: list[dict[str, Any]]) -> None:
        self.status.hide()
        self.model.set_rows(rows)
        self.content.setCurrentWidget(self.table if rows else self.empty)
        self._finish()

    def _on_failed(self, exc: Exception) -> None:
        self.model.set_rows([])
        self.content.setCurrentWidget(self.empty)
        # Sin watch.yml la CLI sale con código de uso: es el caso normal, no un fallo.
        if not (
            isinstance(exc, CliError) and exc.exit_code == EXIT_USAGE and "no existe" in str(exc)
        ):
            self.status.setText(f"{self.tr('No se pudo leer la vigilancia')}: {exc}")
            self.status.show()
        self._finish()

    def _finish(self) -> None:
        self.refresh_button.setEnabled(True)
        self.loaded.emit()

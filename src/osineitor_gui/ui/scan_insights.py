"""Pestañas de un scan guardado: riesgo por activo (`risk`) y cronología (`timeline`)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtWidgets import QHeaderView, QStackedWidget, QVBoxLayout, QWidget

from osineitor_gui.dashboard import SEVERITY_LABELS
from osineitor_gui.ui import theme
from osineitor_gui.ui.tables import ColumnSpec, RowsModel, install_badges, make_table, set_widths
from osineitor_gui.ui.widgets import EmptyState, label
from osineitor_gui.ui.worker import run_in_thread


class _LazyPanel(QWidget):
    """Tabla que se rellena la primera vez que se muestra, y solo si el scan está guardado."""

    EMPTY_TITLE = ""
    EMPTY_TEXT = ""

    def __init__(
        self,
        fetch: Callable[[int], list[dict[str, Any]]] | None,
        columns: tuple[ColumnSpec, ...],
        stretch: int,
        widths: dict[int, int],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._fetch = fetch
        self._loaded_id: int | None = None
        self.model = RowsModel(columns, self)
        self.table, self.proxy = make_table(self.model)
        self.table.horizontalHeader().setSectionResizeMode(stretch, QHeaderView.ResizeMode.Stretch)
        set_widths(self.table, widths)
        self.status = label("", "muted", wrap=True)  # puede mostrar el stderr de la CLI
        self.status.hide()
        self.empty = EmptyState("inbox", self.tr("Guarda el scan para ver este análisis"))
        self.content = QStackedWidget()
        self.content.addWidget(self.empty)
        self.content.addWidget(self.table)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.addWidget(self.status)
        layout.addWidget(self.content, 1)

    def ensure_loaded(self, scan_id: int | None) -> None:
        """Pide los datos una sola vez por scan."""
        if self._fetch is None or scan_id is None or scan_id == self._loaded_id:
            return
        self._loaded_id = scan_id
        self.status.setText(self.tr("Cargando…"))
        self.status.show()
        fetch = self._fetch
        run_in_thread(lambda: fetch(scan_id), self._on_rows, self._on_failed, self)

    def _on_rows(self, rows: list[dict[str, Any]]) -> None:
        self.status.hide()
        self.model.set_rows(rows)
        self.content.setCurrentWidget(self.table if rows else self.empty)
        if not rows:
            self.empty.set_message(self.EMPTY_TITLE, self.EMPTY_TEXT)

    def _on_failed(self, exc: Exception) -> None:
        self._loaded_id = None  # se puede volver a intentar
        self.status.setText(f"{self.tr('No se pudo cargar')}: {exc}")
        self.status.show()


class RiskPanel(_LazyPanel):
    EMPTY_TITLE = "Sin dominios ni IP que puntuar"

    def __init__(self, api, parent: QWidget | None = None) -> None:
        fetch = (lambda scan_id: api.risk(scan_id)["assets"]) if api is not None else None
        columns = (
            ColumnSpec("Activo", lambda a: a["value"], mono=True, tooltip=True),
            ColumnSpec("Tipo", lambda a: a["type"]),
            ColumnSpec("Puntuación", lambda a: a["score"]),
            ColumnSpec(
                "Nivel",
                lambda a: SEVERITY_LABELS.get(a["level"], a["level"]),
                tone=lambda a: theme.SEVERITY_TONES.get(a["level"], "neutral"),
                sort=lambda a: (
                    list(SEVERITY_LABELS).index(a["level"])
                    if a["level"] in SEVERITY_LABELS
                    else len(SEVERITY_LABELS)
                ),
            ),
            ColumnSpec("Servicios", lambda a: a["exposure"]["services"]),
            ColumnSpec("Vulnerabilidades", lambda a: a["exposure"]["vulnerabilities"]),
            ColumnSpec("Motivos", lambda a: "; ".join(a["reasons"]), tooltip=True),
        )
        super().__init__(fetch, columns, 6, {0: 220, 1: 80, 2: 90, 3: 110, 4: 80, 5: 120}, parent)
        self.table.setAccessibleName(self.tr("Riesgo por activo"))
        install_badges(self.table, 3)


class TimelinePanel(_LazyPanel):
    EMPTY_TITLE = "Sin fechas en los datos de este scan"

    def __init__(self, api, parent: QWidget | None = None) -> None:
        fetch = (lambda scan_id: api.timeline(scan_id)["events"]) if api is not None else None
        columns = (
            ColumnSpec("Fecha", lambda e: e["at"].replace("T", " ")[:19], mono=True),
            ColumnSpec("Suceso", lambda e: e["event"], tooltip=True),
            ColumnSpec("Campo", lambda e: e["field"]),
            ColumnSpec("Tipo", lambda e: e["type"]),
            ColumnSpec("Valor", lambda e: e["value"], mono=True, tooltip=True),
            ColumnSpec("Fuente", lambda e: e["source"] or ""),
            ColumnSpec("Aviso", lambda e: "posterior al scan" if e["future"] else ""),
        )
        super().__init__(fetch, columns, 4, {0: 170, 1: 170, 2: 110, 3: 80, 5: 100, 6: 130}, parent)
        self.table.setAccessibleName(self.tr("Cronología del scan"))

"""Panel principal: estado de la investigación con los datos reales de los scans guardados.

Las cifras salen del `history` del panel Historial. Los títulos de los hallazgos piden un `show`
por scan con hallazgos, en cadena desde la UI y solo mientras el panel está a la vista.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from PySide6.QtCore import QAbstractTableModel, QEvent, QModelIndex, QObject, Qt, Signal
from PySide6.QtGui import QAction, QBrush, QResizeEvent, QShowEvent
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QScrollArea,
    QStackedWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from osineitor_gui.api import CliApi
from osineitor_gui.dashboard import (
    RECENT_SCANS,
    SEVERITIES,
    SEVERITY_LABELS,
    Overview,
    ScanSummary,
    aggregate,
    findings_of,
)
from osineitor_gui.ui import icons, theme
from osineitor_gui.ui.charts import BarList, BarRow, Column, ColumnChart
from osineitor_gui.ui.models import STATUS_LABELS, STATUS_TONES
from osineitor_gui.ui.tables import ROW_HEIGHT, BadgeDelegate, style_table
from osineitor_gui.ui.widgets import Card, EmptyState, button, label, safe_tooltip, set_style
from osineitor_gui.ui.worker import run_in_thread

_ROOT = QModelIndex()
STATE_LABELS = {
    "complete": "completo",
    "truncated": "presupuesto agotado",
    "cancelled": "cancelado",
    "failed": "fallido",
}
STATE_TONES = {
    "complete": "safe",
    "truncated": "warning",
    "cancelled": "warning",
    "failed": "critical",
}
OPEN_COLUMN = 70
VALUE_COLUMN = 320
BREAKPOINTS = ((1400, 6), (900, 3), (0, 2))  # anchura mínima del panel → KPI por fila


def _short_date(value: str) -> str:
    return value.replace("T", " ")[:16]


class KpiCard(QFrame):
    def __init__(self, icon: str, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("role", "card")
        self._icon, self._tone = icon, "muted"
        self.picture = QLabel()
        self.title = label(title, "kpiLabel", wrap=True)
        self.value = label("—", "kpiValue")
        self.hint = label("", "kpiHint", wrap=True)
        heading = QHBoxLayout()
        heading.setSpacing(6)
        heading.addWidget(self.picture)
        heading.addWidget(self.title, 1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)
        layout.addLayout(heading)
        layout.addWidget(self.value)
        layout.addWidget(self.hint)
        layout.addStretch(1)
        self._paint_icon()

    def _paint_icon(self) -> None:
        self.picture.setPixmap(icons.icon(self._icon, self._tone).pixmap(16, 16))

    def set_value(self, value: str, hint: str = "", tone: str = "muted") -> None:
        self.value.setText(value)
        self.hint.setText(hint)
        self.value.show()
        self._tone = tone
        self._paint_icon()
        self.setAccessibleName(f"{self.title.text()}: {value}. {hint}")

    def changeEvent(self, event: QEvent) -> None:
        if event.type() == QEvent.Type.ApplicationPaletteChange:
            self._paint_icon()
        super().changeEvent(event)


class _ListModel(QAbstractTableModel):
    """Tabla de solo lectura para el panel: las filas se dan ya como diccionarios."""

    HEADERS: tuple[str, ...] = ()
    MONO_COLUMNS: tuple[int, ...] = ()
    TOOLTIP_COLUMNS: tuple[int, ...] = ()
    TONE_COLUMN = -1

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.rows: list[Any] = []

    def set_rows(self, rows: list[Any]) -> None:
        self.beginResetModel()
        self.rows = list(rows)
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = _ROOT) -> int:
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent: QModelIndex = _ROOT) -> int:
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.tr(self.HEADERS[section])
        return None

    def cell(self, row: Any, column: int) -> object:
        raise NotImplementedError

    def tone(self, row: Any, column: int) -> str | None:
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row, column = self.rows[index.row()], index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            return self.cell(row, column)
        if role == Qt.ItemDataRole.FontRole and column in self.MONO_COLUMNS:
            return theme.mono_font()
        if role == Qt.ItemDataRole.ToolTipRole and column in self.TOOLTIP_COLUMNS:
            return safe_tooltip(self.cell(row, column))
        if role == Qt.ItemDataRole.ForegroundRole:
            tone = self.tone(row, column)
            return QBrush(theme.tone_color(tone)) if tone else None
        return None


class FindingsModel(_ListModel):
    HEADERS = ("Severidad", "Hallazgo", "Valor", "Objetivo", "Fecha", "")
    MONO_COLUMNS = (2, 3, 4)
    TOOLTIP_COLUMNS = (1, 2, 3)

    def cell(self, row: dict[str, Any], column: int) -> object:
        return (
            self.tr(SEVERITY_LABELS[row["severity"]]),
            row["title"],
            row["value"],
            row["target"],
            _short_date(row["started_at"]),
            "",
        )[column]

    def tone(self, row: dict[str, Any], column: int) -> str | None:
        return theme.SEVERITY_TONES[row["severity"]] if column == 0 else None


class RecentScansModel(_ListModel):
    HEADERS = ("Fecha", "Tipo", "Objetivo", "Entidades", "Peor hallazgo", "Estado", "")
    MONO_COLUMNS = (0, 2)
    TOOLTIP_COLUMNS = (2,)

    def cell(self, row: ScanSummary, column: int) -> object:
        worst = row.worst
        return (
            _short_date(row.started_at),
            row.target_type,
            row.target,
            row.entities,
            self.tr(SEVERITY_LABELS[worst]) if worst else self.tr("sin hallazgos"),
            self.tr(STATE_LABELS.get(row.status, row.status)),
            "",
        )[column]

    def tone(self, row: ScanSummary, column: int) -> str | None:
        if column == 4:
            return theme.SEVERITY_TONES[row.worst] if row.worst else "safe"
        return STATE_TONES.get(row.status, "neutral") if column == 5 else None


class DashboardView(QScrollArea):
    scan_requested = Signal(int)
    loaded = Signal()  # terminó la cadena de `show` en curso (para los tests)

    def __init__(self, api: CliApi, new_scan: QAction, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._api = api
        self._generation = 0  # una recarga invalida la cadena anterior
        self._stopped = False
        self._history: list[dict[str, Any]] = []
        self._history_known = False
        self._catalog: list[dict[str, Any]] | None = None
        self._findings: dict[int, list[dict[str, Any]]] = {}  # un scan guardado no cambia
        self._failed: set[int] = set()
        self._fetching = False
        self._columns = 0
        self.overview = Overview()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.empty = EmptyState(
            "radar",
            self.tr("Aún no hay nada que mostrar"),
            self.tr("Lanza tu primer scan: el panel se rellena con los scans guardados."),
        )
        self.empty_action = button(new_scan.text().replace("&", ""), "primary")
        self.empty_action.setEnabled(new_scan.isEnabled())
        new_scan.enabledChanged.connect(self.empty_action.setEnabled)
        self.empty_action.clicked.connect(new_scan.trigger)
        self.empty.add_action(self.empty_action)

        self.pages = QStackedWidget()
        self.pages.addWidget(self.empty)
        self.pages.addWidget(self._build_content())
        self.setWidget(self.pages)
        self._relayout(force=True)

    # --- construcción -----------------------------------------------------------------------

    def _build_content(self) -> QWidget:
        self.kpi_urgent = KpiCard("triangle-alert", self.tr("Hallazgos críticos y altos"))
        self.kpi_worst = KpiCard("shield-check", self.tr("Peor hallazgo"))
        self.kpi_scans = KpiCard("radar", self.tr("Scans en 7 días"))
        self.kpi_entities = KpiCard("layout-dashboard", self.tr("Entidades descubiertas"))
        self.kpi_failed = KpiCard("circle-x", self.tr("Módulos con fallo"))
        self.kpi_modules = KpiCard("activity", self.tr("Módulos disponibles"))
        self.kpis = [
            self.kpi_urgent,
            self.kpi_worst,
            self.kpi_scans,
            self.kpi_entities,
            self.kpi_failed,
            self.kpi_modules,
        ]
        self.kpi_grid = QGridLayout()
        self.kpi_grid.setSpacing(10)

        self.alert_box = QFrame()
        self.alert_box.setProperty("role", "banner")
        self.alert_box.setProperty("tone", "critical")
        self.alert_text = label("", wrap=True)
        self.alert_open = button(self.tr("Abrir scan"), "link")
        self.alert_open.clicked.connect(self._open_worst)
        alert_layout = QHBoxLayout(self.alert_box)
        alert_layout.setContentsMargins(12, 6, 8, 6)
        alert_layout.addWidget(self.alert_text, 1)
        alert_layout.addWidget(self.alert_open)
        self.alert_box.hide()

        self.chart_daily = ColumnChart()
        self.chart_daily.label_every = 3
        self.chart_daily.setAccessibleName(self.tr("Scans por día, últimos 14 días"))
        self.chart_findings = ColumnChart()
        self.chart_findings.setAccessibleName(self.tr("Hallazgos por scan, por severidad"))
        self.list_severity = BarList()
        self.list_severity.setAccessibleName(self.tr("Hallazgos por severidad"))
        self.list_types = BarList()
        self.list_types.setAccessibleName(self.tr("Entidades por tipo"))
        self.list_modules = BarList()
        self.list_modules.setAccessibleName(self.tr("Estado de los módulos, último scan"))
        analyzed = self.tr("Últimos {n} scans").format(n=RECENT_SCANS)
        self.cards = [
            self._chart_card(
                self.tr("Scans por día"), self.tr("Últimos 14 días"), self.chart_daily
            ),
            self._chart_card(self.tr("Hallazgos por scan"), analyzed, self.chart_findings),
            self._chart_card(self.tr("Severidad de los hallazgos"), analyzed, self.list_severity),
            self._chart_card(self.tr("Tipos de entidad"), analyzed, self.list_types),
            self._chart_card(
                self.tr("Estado de los módulos"), self.tr("Último scan"), self.list_modules
            ),
        ]
        self.chart_grid = QGridLayout()
        self.chart_grid.setSpacing(10)

        self.findings_model = FindingsModel(self)
        self.findings_table = self._list_table(self.findings_model, 1, 0)
        self.findings_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.findings_table.setColumnWidth(2, VALUE_COLUMN)
        self.findings_table.setAccessibleName(self.tr("Hallazgos más graves"))
        self.findings_empty = label(self.tr("Sin hallazgos en los scans analizados."), "muted")
        findings_card = Card(self.tr("Hallazgos más graves"), analyzed)
        findings_card.body.addWidget(self.findings_table)
        self.findings_skeleton = QFrame()
        self.findings_skeleton.setProperty("role", "skeleton")
        self.findings_skeleton.setFixedHeight(ROW_HEIGHT * 3)
        self.findings_skeleton.hide()
        findings_card.body.addWidget(self.findings_skeleton)
        findings_card.body.addWidget(self.findings_empty)

        self.scans_model = RecentScansModel(self)
        self.scans_table = self._list_table(self.scans_model, 2, 4, 5)
        self.scans_table.setAccessibleName(self.tr("Actividad reciente"))
        scans_card = Card(self.tr("Actividad reciente"), analyzed)
        scans_card.body.addWidget(self.scans_table)

        self.failures = label("", "error", wrap=True)
        self.failures.hide()

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(10)
        layout.addWidget(self.alert_box)
        layout.addLayout(self.kpi_grid)
        layout.addLayout(self.chart_grid)
        layout.addWidget(findings_card)
        layout.addWidget(scans_card)
        layout.addWidget(self.failures)
        layout.addStretch(1)
        return content

    @staticmethod
    def _chart_card(title: str, hint: str, chart: QWidget) -> Card:
        card = Card(title, hint)
        card.body.addWidget(chart, 1)
        return card

    def _list_table(self, model: _ListModel, stretch: int, *badges: int) -> QTableView:
        table = QTableView()
        table.setModel(model)
        style_table(table)
        table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(stretch, QHeaderView.ResizeMode.Stretch)
        last = model.columnCount() - 1
        header.setSectionResizeMode(last, QHeaderView.ResizeMode.Fixed)
        table.setColumnWidth(last, OPEN_COLUMN)
        for column in badges:
            table.setItemDelegateForColumn(column, BadgeDelegate(table))
        table.doubleClicked.connect(lambda index: self._open_row(model, index.row()))
        table.activated.connect(lambda index: self._open_row(model, index.row()))
        return table

    def _open_row(self, model: _ListModel, row: int) -> None:
        item = model.rows[row]
        self.scan_requested.emit(item["scan_id"] if isinstance(item, dict) else item.scan_id)

    def _fill_list_table(self, table: QTableView, model: _ListModel, rows: list[Any]) -> None:
        model.set_rows(rows)
        for row in range(len(rows)):
            opener = button(self.tr("Abrir"), "link")
            item = rows[row]
            target = item["target"] if isinstance(item, dict) else item.target
            opener.setAccessibleName(f"{self.tr('Abrir scan de')} {target}")
            opener.clicked.connect(lambda _c=False, r=row: self._open_row(model, r))
            table.setIndexWidget(model.index(row, model.columnCount() - 1), opener)
        header_height = table.horizontalHeader().sizeHint().height()
        table.setFixedHeight(header_height + ROW_HEIGHT * len(rows) + 4)

    # --- datos ------------------------------------------------------------------------------

    def set_catalog(self, modules: list[dict[str, Any]]) -> None:
        self._catalog = modules
        self.render_data()

    def set_history(self, rows: list[dict[str, Any]], error: str | None = None) -> None:
        """Llega al terminar cada recarga del historial."""
        self._generation += 1
        self._fetching = False
        self._history = list(rows)
        self._history_known = True
        self._failed.clear()
        if error:
            self.empty.set_message(self.tr("No se pudo cargar el historial"), error)
        else:
            self.empty.set_message(
                self.tr("Aún no hay nada que mostrar"),
                self.tr("Lanza tu primer scan: el panel se rellena con los scans guardados."),
            )
        self.render_data()
        self._fetch_next(self._generation)

    def stop(self) -> None:
        """La ventana se cierra: no se piden más scans."""
        self._stopped = True
        self._generation += 1

    def _pending(self) -> list[int]:
        return [
            row["id"]
            for row in self._history[:RECENT_SCANS]
            if row.get("severity")
            and row["id"] not in self._findings
            and row["id"] not in self._failed
        ]

    def _fetch_next(self, generation: int) -> None:
        if self._stopped or generation != self._generation or self._fetching:
            return
        if not self.isVisible():
            return  # se retoma en `showEvent`
        pending = self._pending()
        if not pending:
            self.loaded.emit()
            return
        scan_id = pending[0]
        self._fetching = True
        run_in_thread(
            lambda: self._api.show(scan_id),
            lambda result: self._on_scan(generation, scan_id, result),
            lambda exc: self._on_scan_failed(generation, scan_id, exc),
            self,
        )

    def _on_scan(self, generation: int, scan_id: int, result: dict[str, Any]) -> None:
        self._findings[scan_id] = findings_of(result)  # vale aunque la cadena haya caducado
        if generation != self._generation:
            return
        self._fetching = False
        self.render_data()
        self._fetch_next(generation)

    def _on_scan_failed(self, generation: int, scan_id: int, exc: Exception) -> None:
        if generation != self._generation:
            return
        self._fetching = False
        self._failed.add(scan_id)
        self.failures.setText(f"{self.tr('No se pudo analizar el scan')} #{scan_id}: {exc}")
        self.failures.show()
        self._fetch_next(generation)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._relayout()
        self._fetch_next(self._generation)

    # --- pintado ----------------------------------------------------------------------------

    def render_data(self) -> None:
        now = datetime.now().astimezone()
        overview = aggregate(self._history, self._findings, now, self._catalog)
        self.overview = overview
        self.pages.setCurrentIndex(1 if self._history else 0)
        if not self._history:
            return
        self._render_kpis(overview)
        self._render_alert(overview)
        self._render_charts(overview)
        self._fill_list_table(self.findings_table, self.findings_model, overview.findings)
        self.findings_table.setVisible(bool(overview.findings))
        loading = bool(self._pending()) and not overview.findings
        self.findings_skeleton.setVisible(loading)
        self.findings_empty.setVisible(not overview.findings and not loading)
        self._fill_list_table(self.scans_table, self.scans_model, overview.analyzed)

    def _render_kpis(self, overview: Overview) -> None:
        count = len(overview.analyzed)
        analyzed = f"{count} {self.tr('scan analizado' if count == 1 else 'scans analizados')}"
        urgent_tone = "critical" if overview.severity.get("critical") else "high"
        self.kpi_urgent.set_value(
            str(overview.urgent), analyzed, urgent_tone if overview.urgent else "safe"
        )
        worst = overview.worst
        self.kpi_worst.set_value(
            self.tr(SEVERITY_LABELS[worst]).capitalize() if worst else self.tr("Ninguno"),
            analyzed,
            theme.SEVERITY_TONES[worst] if worst else "safe",
        )
        last = overview.analyzed[0].target if overview.analyzed else ""
        self.kpi_failed.set_value(
            str(overview.modules_failed),
            f"{self.tr('Último scan')}: {last}",
            "critical" if overview.modules_failed else "safe",
        )
        delta = overview.scans_delta
        signed = f"+{delta}" if delta > 0 else str(delta)
        self.kpi_scans.set_value(
            str(overview.scans_7d), f"{signed} {self.tr('respecto a los 7 días previos')}", "info"
        )
        self.kpi_entities.set_value(
            str(overview.entities_total),
            f"{self.tr('en')} {overview.scans_total} "
            f"{self.tr('scan guardado' if overview.scans_total == 1 else 'scans guardados')}",
            "info",
        )
        if overview.catalog_total is None:
            self.kpi_modules.set_value("—", self.tr("Catálogo no disponible"), "muted")
        else:
            self.kpi_modules.set_value(
                str(overview.catalog_total),
                self.tr("{k} sin API key · {a} activos").format(
                    k=overview.catalog_missing_key, a=overview.catalog_active
                ),
                "warning" if overview.catalog_missing_key else "safe",
            )

    def _render_alert(self, overview: Overview) -> None:
        critical = overview.severity.get("critical", 0)
        self.alert_box.setVisible(bool(critical))
        if critical:
            self.alert_text.setText(
                self.tr("1 hallazgo de severidad crítica en los scans analizados.")
                if critical == 1
                else self.tr("{n} hallazgos de severidad crítica en los scans analizados.").format(
                    n=critical
                )
            )
            set_style(self.alert_box, tone="critical")

    def _open_worst(self) -> None:
        if self.overview.findings:
            self.scan_requested.emit(self.overview.findings[0]["scan_id"])

    def _render_charts(self, overview: Overview) -> None:
        self.chart_daily.set_data(
            [
                Column(
                    day.strftime("%d/%m"),
                    [("accent", count)],
                    f"{day.strftime('%d/%m/%Y')}: {count} "
                    f"{self.tr('scan' if count == 1 else 'scans')}",
                )
                for day, count in overview.daily
            ]
        )
        self.chart_findings.set_data(
            [
                Column(
                    f"#{summary.scan_id}",
                    [
                        (theme.SEVERITY_TONES[s], summary.by_severity.get(s, 0))
                        for s in reversed(SEVERITIES)
                    ],
                    f"#{summary.scan_id} {summary.target}: "
                    + ", ".join(
                        f"{summary.by_severity[s]} {self.tr(SEVERITY_LABELS[s])}"
                        for s in SEVERITIES
                        if summary.by_severity.get(s)
                    ),
                )
                for summary in reversed(overview.analyzed)
            ],
            [(theme.SEVERITY_TONES[s], self.tr(SEVERITY_LABELS[s])) for s in SEVERITIES],
        )
        self.list_severity.set_data(
            [
                BarRow(
                    self.tr(SEVERITY_LABELS[s]).capitalize(),
                    overview.severity.get(s, 0),
                    theme.SEVERITY_TONES[s],
                )
                for s in SEVERITIES
            ]
        )
        self.list_types.set_data([BarRow(kind, count, mono=True) for kind, count in overview.types])
        self.list_modules.set_data(
            [
                BarRow(
                    self.tr(STATUS_LABELS.get(status, status)),
                    count,
                    STATUS_TONES.get(status, "neutral"),
                )
                for status, count in sorted(overview.modules_last.items(), key=lambda i: -i[1])
            ]
        )

    # --- adaptación a la anchura ------------------------------------------------------------

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._relayout()

    def _relayout(self, force: bool = False) -> None:
        width = self.viewport().width()
        columns = next(count for minimum, count in BREAKPOINTS if width >= minimum)
        if columns == self._columns and not force:
            return
        self._columns = columns
        for i, card in enumerate(self.kpis):
            self.kpi_grid.addWidget(card, i // columns, i % columns)
        for column in range(6):
            self.kpi_grid.setColumnStretch(column, 1 if column < columns else 0)
        # Gráficos: columnas arriba; listas debajo, de tres en tres si hay sitio.
        wide = columns >= 3
        positions = (
            [(0, 0, 1, 3), (0, 3, 1, 3), (1, 0, 1, 2), (1, 2, 1, 2), (1, 4, 1, 2)]
            if wide
            else [(i, 0, 1, 6) for i in range(5)]
        )
        for card, position in zip(self.cards, positions, strict=True):
            self.chart_grid.addWidget(card, *position)
        for column in range(6):
            self.chart_grid.setColumnStretch(column, 1)

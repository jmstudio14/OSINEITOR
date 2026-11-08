"""Panel principal, búsqueda global, navegación y tablas ordenables (sin red)."""

from __future__ import annotations

import os
import sys

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QAction, QTextDocument  # noqa: E402
from PySide6.QtWidgets import QLabel, QMessageBox  # noqa: E402

from osineitor_gui.api import CliApi  # noqa: E402
from osineitor_gui.dashboard import summarize_scan  # noqa: E402
from osineitor_gui.scan_request import ScanRequest  # noqa: E402
from osineitor_gui.settings import GuiSettings  # noqa: E402
from osineitor_gui.ui.charts import BarList, BarRow, Column, ColumnChart  # noqa: E402
from osineitor_gui.ui.dashboard_view import DashboardView  # noqa: E402
from osineitor_gui.ui.history_panel import HistoryPanel  # noqa: E402
from osineitor_gui.ui.main_window import MainWindow  # noqa: E402
from osineitor_gui.ui.modules_view import HealthModel  # noqa: E402
from osineitor_gui.ui.scan_view import ScanView  # noqa: E402
from osineitor_gui.ui.search_panel import SearchPanel  # noqa: E402
from osineitor_gui.ui.sidebar import COLLAPSED_WIDTH, EXPANDED_WIDTH  # noqa: E402
from osineitor_gui.ui.tables import SORT_ROLE, make_table, source_row  # noqa: E402
from osineitor_gui.ui.widgets import Toast  # noqa: E402
from tests.gui.fakecli import CLI as FAKE_CLI  # noqa: E402
from tests.gui.fakecli import save_scan, use_modules  # noqa: E402

TIMEOUT = 30_000
EVIL = '<a href="https://evil.test">pulsa</a><img src="https://evil.test/x.png">'


def history_row(scan_id: int) -> dict:
    return {
        "id": scan_id,
        "target": f"t{scan_id}.test",
        "target_type": "domain",
        "entities": 2,
        "started_at": "2026-11-08T10:00:00+00:00",
    }


def scan_result(scan_id: int, severity: str = "high") -> dict:
    return {
        "scan_id": scan_id,
        "target": {"type": "domain", "value": f"t{scan_id}.test"},
        "started_at": "2026-11-08T10:00:00+00:00",
        "status": "complete",
        "entities": [
            {
                "type": "finding",
                "value": "regla: x",
                "data": {"severity": severity, "title": "Regla"},
            },
            {"type": "ip", "value": "9.9.9.9"},
        ],
        "runs": [{"module": "dns", "status": "ok"}, {"module": "x", "status": "error"}],
    }


class FakeApi:
    """Cuenta los `show`: lo que importa aquí es cuándo se piden y en qué orden."""

    def __init__(self, failing=()):
        self.shown = []
        self.failing = set(failing)

    def show(self, scan_id):
        self.shown.append(scan_id)
        if scan_id in self.failing:
            raise RuntimeError(f"<b>falló</b> {scan_id}")
        return scan_result(scan_id)


def make_dashboard(qtbot, api=None) -> DashboardView:
    view = DashboardView(api or FakeApi(), QAction("&Nuevo scan…"))
    qtbot.addWidget(view)
    return view


def analyzed(view) -> list[int]:
    return [s.scan_id for s in view.overview.analyzed]


# --- panel -------------------------------------------------------------------------------------


def test_no_scans_shows_the_empty_state_and_requests_nothing(qtbot):
    api = FakeApi()
    view = make_dashboard(qtbot, api)
    view.show()
    view.set_history([])
    assert view.pages.currentWidget() is view.empty and api.shown == []
    assert view.empty_action.text() == "Nuevo scan…"


def test_a_history_error_is_shown_as_plain_text_in_the_empty_state(qtbot):
    view = make_dashboard(qtbot)
    view.show()
    view.set_history([], EVIL)
    assert view.empty.text.text() == EVIL
    assert view.empty.text.textFormat() == Qt.TextFormat.PlainText


def test_scans_are_fetched_one_by_one_and_painted_as_they_arrive(qtbot):
    api = FakeApi()
    view = make_dashboard(qtbot, api)
    view.show()
    with qtbot.waitSignal(view.loaded, timeout=TIMEOUT):
        view.set_history([history_row(3), history_row(2), history_row(1)])
    assert api.shown == [3, 2, 1]
    assert analyzed(view) == [3, 2, 1]
    assert view.pages.currentIndex() == 1
    assert view.kpi_urgent.value.text() == "3" and view.kpi_worst.value.text() == "Alta"
    assert view.kpi_failed.value.text() == "1"
    assert view.findings_model.rowCount() == 3 and view.scans_model.rowCount() == 3


def test_only_the_visible_panel_requests_scans(qtbot):
    api = FakeApi()
    view = make_dashboard(qtbot, api)
    view.set_history([history_row(1)])  # sin mostrar
    qtbot.wait(100)
    assert api.shown == []
    with qtbot.waitSignal(view.loaded, timeout=TIMEOUT):
        view.show()
    assert api.shown == [1]


def test_a_reload_does_not_request_cached_scans_again(qtbot):
    api = FakeApi()
    view = make_dashboard(qtbot, api)
    view.show()
    with qtbot.waitSignal(view.loaded, timeout=TIMEOUT):
        view.set_history([history_row(1)])
    with qtbot.waitSignal(view.loaded, timeout=TIMEOUT):
        view.set_history([history_row(2), history_row(1)])
    assert api.shown == [1, 2]
    assert analyzed(view) == [2, 1]


def test_a_stale_chain_does_not_continue_after_a_reload(qtbot):
    api = FakeApi()
    view = make_dashboard(qtbot, api)
    view.show()
    with qtbot.waitSignal(view.loaded, timeout=TIMEOUT):
        view.set_history([history_row(2), history_row(1)])
        view.set_history([history_row(9)])  # invalida la cadena anterior
    qtbot.wait(100)
    assert 1 not in api.shown and 9 in api.shown
    assert analyzed(view)[0] == 9


def test_stop_ends_the_chain(qtbot):
    api = FakeApi()
    view = make_dashboard(qtbot, api)
    view.show()
    view.set_history([history_row(2), history_row(1)])
    view.stop()
    qtbot.wait(200)
    assert api.shown in ([], [2])  # la petición en curso, como mucho
    view.set_history([history_row(3)])
    qtbot.wait(100)
    assert 3 not in api.shown


def test_a_failed_scan_is_reported_as_plain_text_and_the_rest_still_load(qtbot):
    api = FakeApi(failing={2})
    view = make_dashboard(qtbot, api)
    view.show()
    with qtbot.waitSignal(view.loaded, timeout=TIMEOUT):
        view.set_history([history_row(3), history_row(2), history_row(1)])
    assert analyzed(view) == [3, 1]
    assert "<b>falló</b> 2" in view.failures.text()
    assert view.failures.textFormat() == Qt.TextFormat.PlainText


def test_the_alert_appears_only_with_critical_findings_and_opens_the_scan(qtbot):
    class Critical(FakeApi):
        def show(self, scan_id):
            self.shown.append(scan_id)
            return scan_result(scan_id, "critical")

    view = make_dashboard(qtbot, Critical())
    view.show()
    with qtbot.waitSignal(view.loaded, timeout=TIMEOUT):
        view.set_history([history_row(1)])
    assert view.alert_box.isVisible() and view.alert_text.text().startswith("1 hallazgo de")
    with qtbot.waitSignal(view.scan_requested, timeout=1000) as blocker:
        view.alert_open.click()
    assert blocker.args == [1]


def test_no_alert_without_critical_findings(qtbot):
    view = make_dashboard(qtbot)
    view.show()
    with qtbot.waitSignal(view.loaded, timeout=TIMEOUT):
        view.set_history([history_row(1)])
    assert not view.alert_box.isVisible()


def test_row_actions_open_the_scan(qtbot):
    view = make_dashboard(qtbot)
    view.show()
    with qtbot.waitSignal(view.loaded, timeout=TIMEOUT):
        view.set_history([history_row(4)])
    with qtbot.waitSignal(view.scan_requested, timeout=1000) as blocker:
        view.scans_table.activated.emit(view.scans_model.index(0, 0))
    assert blocker.args == [4]
    last = view.findings_model.columnCount() - 1
    opener = view.findings_table.indexWidget(view.findings_model.index(0, last))
    with qtbot.waitSignal(view.scan_requested, timeout=1000) as blocker:
        opener.click()
    assert blocker.args == [4]


def test_the_catalog_kpi_says_when_it_is_not_available(qtbot):
    view = make_dashboard(qtbot)
    view.show()
    with qtbot.waitSignal(view.loaded, timeout=TIMEOUT):
        view.set_history([history_row(1)])
    assert view.kpi_modules.value.text() == "—"
    view.set_catalog([{"name": "a", "requires_key": "k", "key_configured": False}])
    assert view.kpi_modules.value.text() == "1" and "1 sin API key" in view.kpi_modules.hint.text()


def test_kpis_reflow_with_the_width(qtbot):
    view = make_dashboard(qtbot)
    view.show()
    view.resize(1600, 800)
    qtbot.waitUntil(lambda: view._columns == 6, timeout=2000)
    view.resize(1000, 800)
    qtbot.waitUntil(lambda: view._columns == 3, timeout=2000)
    view.resize(600, 800)
    qtbot.waitUntil(lambda: view._columns == 2, timeout=2000)


# --- gráficos ----------------------------------------------------------------------------------


def test_charts_paint_with_data_empty_and_loading_and_describe_themselves(qtbot):
    column_chart = ColumnChart()
    bar_list = BarList()
    for chart in (column_chart, bar_list):
        qtbot.addWidget(chart)
        chart.resize(400, 200)
        chart.grab()
        chart.set_loading(True)
        chart.grab()
    column_chart.set_data(
        [Column("#1", [("critical", 2), ("info", 1)], "x"), Column("#2", [("info", 0)])],
        [("critical", "crítica")],
    )
    column_chart.grab()
    assert column_chart.accessibleDescription() == "#1: 3"
    bar_list.set_data([BarRow("Alta", 3, "high"), BarRow("ip", 0, mono=True)])
    bar_list.grab()
    assert bar_list.accessibleDescription() == "Alta: 3; ip: 0"
    bar_list.set_data([])
    assert bar_list.accessibleDescription() == "Sin datos"


# --- tablas ------------------------------------------------------------------------------------


def test_tables_keep_the_source_order_until_a_header_is_clicked(qtbot):
    model = HealthModel()
    table, proxy = make_table(model)
    qtbot.addWidget(table)
    model.set_rows(
        [
            {"module": "b", "verdict": "ok", "duration_ms": 900},
            {"module": "c", "verdict": "ok", "duration_ms": 10000},
            {"module": "a", "verdict": "ok", "duration_ms": 80},
        ]
    )
    assert [proxy.index(r, 0).data() for r in range(3)] == ["b", "c", "a"]
    proxy.sort(3)  # orden numérico, no el de «10000 ms» como texto
    assert [proxy.index(r, 0).data() for r in range(3)] == ["a", "b", "c"]
    assert proxy.index(0, 3).data(SORT_ROLE) == 80


def test_a_sorted_table_opens_the_right_row(qtbot):
    panel = HistoryPanel(CliApi(FAKE_CLI))
    qtbot.addWidget(panel)
    panel.model.set_rows([history_row(1), history_row(3), history_row(2)])
    panel.table.sortByColumn(0, Qt.SortOrder.DescendingOrder)
    with qtbot.waitSignal(panel.scan_requested, timeout=1000) as blocker:
        panel.table.doubleClicked.emit(panel.proxy.index(0, 0))
    assert blocker.args == [3]
    assert source_row(panel.table, panel.proxy.index(0, 0)) == 1


def test_history_filters_by_type_and_text(qtbot):
    panel = HistoryPanel(CliApi(FAKE_CLI))
    qtbot.addWidget(panel)
    rows = [history_row(1), {**history_row(2), "target_type": "ip", "target": "9.9.9.9"}]
    panel._on_loaded(rows)
    assert panel.kind_filter.count() == 3
    panel.kind_filter.setCurrentIndex(panel.kind_filter.findData("ip"))
    assert panel.proxy.rowCount() == 1
    panel.kind_filter.setCurrentIndex(0)
    panel.search.setText("T1.TEST")
    assert panel.proxy.rowCount() == 1 and panel.proxy.index(0, 1).data() == "t1.test"


def test_sorting_the_entities_keeps_the_detail_on_the_selected_entity(qtbot):
    view = ScanView.from_result(
        {
            "scan_id": 1,
            "target": {"type": "domain", "value": "example.com"},
            "entities": [
                {"type": "ip", "value": "b", "source": "fuente-b"},
                {"type": "ip", "value": "a", "source": "fuente-a"},
            ],
            "runs": [],
            "status": "complete",
        }
    )
    qtbot.addWidget(view)
    view.entities_table.sortByColumn(1, Qt.SortOrder.AscendingOrder)
    view.entities_table.selectRow(0)
    assert view.detail.table.item(0, 1).text() == "fuente-a"


def test_severity_sorts_by_gravity_and_shows_a_label(qtbot):
    entities = [
        {"type": "finding", "value": "x", "data": {"severity": "low"}},
        {"type": "ip", "value": "9.9.9.9"},
        {"type": "finding", "value": "y", "data": {"severity": "critical"}},
    ]
    view = ScanView.from_result(
        {
            "scan_id": 1,
            "target": {"type": "domain", "value": "example.com"},
            "entities": entities,
            "runs": [],
            "status": "complete",
        }
    )
    qtbot.addWidget(view)
    view.entities_proxy.sort(3)
    assert [view.entities_proxy.index(r, 3).data() for r in range(3)] == ["crítica", "baja", ""]


# --- texto de terceros -------------------------------------------------------------------------


def test_third_party_text_never_reaches_a_rich_text_label_or_tooltip(qtbot):
    """Un valor o un stderr con etiquetas se ve tal cual: ni enlaces ni imágenes remotas."""
    view = ScanView.from_result(
        {
            "scan_id": 1,
            "target": {"type": "domain", "value": EVIL},
            "entities": [{"type": "url", "value": EVIL, "source": EVIL, "data": {"k": EVIL}}],
            "runs": [{"module": "m", "status": "error", "message": EVIL}],
            "status": "cancelled",
        }
    )
    qtbot.addWidget(view)
    view.session.message = EVIL
    view.refresh()
    assert EVIL in view.banner.text()
    for widget in view.findChildren(QLabel):
        if "evil.test" in widget.text():
            assert widget.textFormat() == Qt.TextFormat.PlainText
    tooltip = view.entities_model.index(0, 1).data(Qt.ItemDataRole.ToolTipRole)
    assert tooltip.startswith("<qt>") and "<a " not in tooltip
    document = QTextDocument()
    document.setHtml(tooltip)
    assert document.toPlainText() == EVIL  # se lee, pero no hay nada activo


def test_saved_scan_summary_handles_what_show_returns(monkeypatch):
    scan_id = save_scan(monkeypatch)
    summary = summarize_scan(CliApi(FAKE_CLI).show(scan_id))
    assert summary.target == "example.com" and summary.entities >= 1


# --- búsqueda global ---------------------------------------------------------------------------


def test_search_finds_saved_data_and_opens_the_scan(qtbot, monkeypatch):
    scan_id = save_scan(monkeypatch)
    panel = SearchPanel(CliApi(FAKE_CLI))
    qtbot.addWidget(panel)
    with qtbot.waitSignal(panel.finished, timeout=TIMEOUT):
        panel.run("9.9.9")
    assert panel.model.rowCount() >= 1 and panel.model.scan_id(0) == scan_id
    assert panel.content.currentWidget() is panel.table
    with qtbot.waitSignal(panel.scan_requested, timeout=1000) as blocker:
        panel.table.doubleClicked.emit(panel.proxy.index(0, 0))
    assert blocker.args == [scan_id]


def test_search_without_matches_says_so(qtbot, monkeypatch):
    save_scan(monkeypatch)
    panel = SearchPanel(CliApi(FAKE_CLI))
    qtbot.addWidget(panel)
    with qtbot.waitSignal(panel.finished, timeout=TIMEOUT):
        panel.run("no-existe")
    assert panel.content.currentWidget() is panel.empty
    assert panel.empty.title.text() == "Sin coincidencias"


def test_a_query_that_looks_like_an_option_is_only_data(qtbot, monkeypatch):
    use_modules(monkeypatch, "fast")
    panel = SearchPanel(CliApi(FAKE_CLI))
    qtbot.addWidget(panel)
    with qtbot.waitSignal(panel.finished, timeout=TIMEOUT):
        panel.run("--db=C:/otra.db")
    assert "No se pudo buscar" not in panel.summary.text()
    assert panel.summary.text().startswith("0 coincidencias")


def test_a_failing_search_is_shown_as_plain_text(qtbot):
    dead = [sys.executable, "-c", "import sys; sys.stderr.write('<b>boom</b>'); sys.exit(2)"]
    panel = SearchPanel(CliApi(dead))
    qtbot.addWidget(panel)
    with qtbot.waitSignal(panel.finished, timeout=TIMEOUT):
        panel.run("x")
    assert "<b>boom</b>" in panel.summary.text()
    assert panel.summary.textFormat() == Qt.TextFormat.PlainText


def test_an_old_search_answer_is_ignored(qtbot):
    panel = SearchPanel(CliApi(FAKE_CLI))
    qtbot.addWidget(panel)
    panel._generation = 2
    panel._on_hits(1, "vieja", [{"scan_id": 1}])
    assert panel.model.rowCount() == 0


# --- navegación --------------------------------------------------------------------------------


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv("OSINEITOR_GUI_CONFIG_DIR", str(tmp_path / "gui"))
    monkeypatch.setattr(HistoryPanel, "reload", lambda self: None)
    monkeypatch.setattr(MainWindow, "load_catalog", lambda self: None)
    win = MainWindow(GuiSettings(), FAKE_CLI)
    qtbot.addWidget(win)
    return win


def test_it_starts_on_the_dashboard(window):
    assert window.stack.currentWidget() is window.dashboard
    assert window.sidebar.selected() == "dashboard" and window.topbar.title.text() == "Panel"


def test_the_sidebar_reaches_every_page(window):
    for name, page in (("history", window.history), ("search", window.search_panel)):
        window.sidebar._pages[name].click()
        assert window.stack.currentWidget() is page and window.sidebar.selected() == name


def test_the_scans_page_without_tabs_shows_the_empty_state(window):
    window.nav_actions["scans"].trigger()
    assert window.stack.currentWidget() is window.scans_empty
    assert window.sidebar.selected() == "scans"


def test_sidebar_actions_follow_the_enabled_state_of_their_action(window):
    buttons = {text: b for b, _icon, text in window.sidebar._buttons}
    assert buttons["Salud"].isEnabled()
    window.action_health.setEnabled(False)
    assert not buttons["Salud"].isEnabled()


def test_a_running_scan_does_not_pull_the_user_out_of_another_page(qtbot, window, monkeypatch):
    use_modules(monkeypatch, "fast,hang")
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.Yes)
    view = window.open_scan(ScanRequest(target="example.com", kind="domain", no_save=True))
    assert window.stack.currentWidget() is window.tabs
    window.nav_actions["history"].trigger()
    qtbot.waitUntil(lambda: bool(view.session.entities), timeout=TIMEOUT)
    view.refresh()
    qtbot.wait(150)
    assert window.stack.currentWidget() is window.history
    window._stop(view)


def test_the_sidebar_collapses_on_narrow_windows_and_on_request(qtbot, window):
    window.show()
    window.resize(1300, 700)
    qtbot.waitUntil(lambda: window.sidebar.width() == EXPANDED_WIDTH, timeout=2000)
    window.resize(900, 700)
    qtbot.waitUntil(lambda: window.sidebar.width() == COLLAPSED_WIDTH, timeout=2000)
    assert window.sidebar.toggle_button.toolTip() == "Expandir menú"
    window.action_toggle_sidebar.trigger()
    assert window.sidebar.width() == EXPANDED_WIDTH  # lo que elige el usuario manda
    window.resize(1300, 700)
    qtbot.waitUntil(lambda: not window.sidebar.collapsed, timeout=2000)
    assert window.topbar.toolbar.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonTextBesideIcon


def test_collapsed_buttons_keep_a_tooltip_and_an_accessible_name(window):
    window.sidebar.set_collapsed(True)
    for button, _icon, text in window.sidebar._buttons:
        assert button.toolTip() and button.accessibleName()
        assert button.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonIconOnly
        assert text


def test_the_cli_chip_reports_only_what_happened(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv("OSINEITOR_GUI_CONFIG_DIR", str(tmp_path / "gui"))
    monkeypatch.setattr(HistoryPanel, "reload", lambda self: None)
    monkeypatch.setattr(MainWindow, "load_catalog", lambda self: None)
    win = MainWindow(GuiSettings(), FAKE_CLI)
    qtbot.addWidget(win)
    assert win.topbar.chip.text() == "Comprobando CLI…"
    win._catalog_loaded([])
    assert win.topbar.chip.text() == "CLI operativa"
    win._catalog_failed(RuntimeError("x"))
    assert win.topbar.chip.text() == "CLI no responde"
    missing = MainWindow(GuiSettings(), None, "falta")
    qtbot.addWidget(missing)
    assert missing.topbar.chip.text() == "CLI no encontrada"


def test_the_top_search_runs_on_the_search_page(qtbot, window, monkeypatch):
    queries = []
    monkeypatch.setattr(window.search_panel, "run", queries.append)
    window.topbar.search.setText("9.9.9.9")
    window.topbar.search.returnPressed.emit()
    assert queries == ["9.9.9.9"] and window.stack.currentWidget() is window.search_panel


def test_toast_shows_plain_text_and_hides_itself(qtbot, window):
    window.show()
    window._notify(EVIL, "critical")
    toast = window.findChild(Toast)
    assert toast.isVisible() and toast.textFormat() == Qt.TextFormat.PlainText
    assert window.statusBar().currentMessage() == EVIL
    toast._timer.timeout.emit()
    assert not toast.isVisible()


def test_every_navigation_button_is_reachable_with_tab_in_visual_order(window):
    order = window.sidebar.tab_order()
    names = [button.accessibleName() for button in order]
    assert names[:4] == ["Panel", "Scans", "Historial", "Búsqueda"]
    assert order[-1] is window.sidebar.toggle_button
    for first, second in zip(order, order[1:], strict=False):
        assert first.nextInFocusChain() is second
    assert order[-1].nextInFocusChain() is window.topbar.search

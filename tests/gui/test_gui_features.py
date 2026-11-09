"""Instancia única, alcance y evidencias, riesgo, cronología, casos, vigilancia y accesibilidad."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QDialogButtonBox,
    QFileDialog,
    QInputDialog,
    QMessageBox,
)

from osineitor_gui import api as api_module  # noqa: E402
from osineitor_gui.api import CliApi, CliError  # noqa: E402
from osineitor_gui.scan_request import InvalidRequest, ScanRequest  # noqa: E402
from osineitor_gui.settings import GuiSettings  # noqa: E402
from osineitor_gui.ui import theme  # noqa: E402
from osineitor_gui.ui.cases_panel import CasesPanel  # noqa: E402
from osineitor_gui.ui.charts import Column, ColumnChart  # noqa: E402
from osineitor_gui.ui.history_panel import HistoryPanel  # noqa: E402
from osineitor_gui.ui.main_window import MainWindow  # noqa: E402
from osineitor_gui.ui.modules_view import HealthModel  # noqa: E402
from osineitor_gui.ui.new_scan_dialog import NewScanDialog  # noqa: E402
from osineitor_gui.ui.scan_insights import RiskPanel, TimelinePanel  # noqa: E402
from osineitor_gui.ui.scan_view import ScanView  # noqa: E402
from osineitor_gui.ui.sidebar import COLLAPSED_WIDTH, EXPANDED_WIDTH  # noqa: E402
from osineitor_gui.ui.single_instance import SingleInstance  # noqa: E402
from osineitor_gui.ui.tables import HOVER_ROW, make_table  # noqa: E402
from osineitor_gui.ui.watch_panel import WatchPanel  # noqa: E402
from tests.gui.fakecli import CLI as FAKE_CLI  # noqa: E402
from tests.gui.fakecli import save_scan, use_modules  # noqa: E402

TIMEOUT = 30_000
SRC = str(Path(api_module.__file__).parents[1])


# --- instancia única ---------------------------------------------------------------------------

SECOND = textwrap.dedent(
    """
    import sys
    from pathlib import Path
    from PySide6.QtCore import QCoreApplication
    from osineitor_gui.ui.single_instance import SingleInstance
    app = QCoreApplication(sys.argv)
    instance = SingleInstance(Path(sys.argv[1]))
    print("primera" if instance.acquire() else "segunda", flush=True)
    instance.release()
    """
)


def run_second(directory: Path) -> str:
    return subprocess.run(
        [sys.executable, "-c", SECOND, str(directory)],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": SRC},
        timeout=60,
    ).stdout.strip()


def test_a_second_process_activates_the_first_and_exits(qtbot, tmp_path):
    first = SingleInstance(tmp_path)
    assert first.acquire()
    activated = []
    first.activated.connect(lambda: activated.append(1))
    try:
        process = subprocess.Popen(
            [sys.executable, "-c", SECOND, str(tmp_path)],
            stdout=subprocess.PIPE,
            text=True,
            env={**os.environ, "PYTHONPATH": SRC},
        )
        qtbot.waitUntil(lambda: bool(activated), timeout=TIMEOUT)
        output, _ = process.communicate(timeout=30)
    finally:
        first.release()
    assert output.strip() == "segunda"


def test_the_lock_is_free_again_after_release(tmp_path):
    first = SingleInstance(tmp_path)
    assert first.acquire()
    first.release()
    assert run_second(tmp_path) == "primera"


def test_another_settings_folder_is_another_instance(tmp_path):
    first = SingleInstance(tmp_path / "a")
    assert first.acquire()
    try:
        assert run_second(tmp_path / "b") == "primera"  # tests y smoke.py no chocan con el usuario
    finally:
        first.release()


def test_an_unusable_folder_still_opens_the_application(tmp_path):
    blocked = tmp_path / "fichero"
    blocked.write_text("x", encoding="utf-8")
    assert SingleInstance(blocked / "dentro").acquire()


def test_activate_shows_a_minimized_window(qtbot, tmp_path, monkeypatch):
    window = make_window(qtbot, tmp_path, monkeypatch)
    window.showMinimized()
    window.activate()
    assert not window.windowState() & Qt.WindowState.WindowMinimized


# --- alcance y evidencias ----------------------------------------------------------------------


def test_scope_and_evidence_go_before_the_target(tmp_path):
    scope = tmp_path / "alcance.yml"
    scope.write_text("domains: [example.com]\n", encoding="utf-8")
    args = ScanRequest(target="example.com", scope=str(scope), evidence=True).to_args()
    assert args.index("--scope") < args.index("--") and "--evidence" in args
    assert args[args.index("--scope") + 1] == str(scope)
    assert "--scope" not in ScanRequest(target="example.com").to_args()


def test_a_missing_scope_file_is_rejected_before_launching(tmp_path):
    request = ScanRequest(target="example.com", scope=str(tmp_path / "no-existe.yml"))
    with pytest.raises(InvalidRequest):
        request.validate()


def test_the_dialog_passes_scope_and_evidence(qtbot, tmp_path, monkeypatch):
    scope = tmp_path / "alcance.yml"
    scope.write_text("domains: [example.com]\n", encoding="utf-8")
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a: (str(scope), "YAML"))
    dialog = NewScanDialog(None, [])
    qtbot.addWidget(dialog)
    dialog.target.setText("example.com")
    dialog.scope_button.click()
    dialog.evidence.setChecked(True)
    dialog.accept()
    request = dialog.request()
    assert request.scope == str(scope) and request.evidence


def test_the_cli_accepts_scope_and_evidence_end_to_end(tmp_path, monkeypatch):
    from osineitor_gui.process import CliProcess

    use_modules(monkeypatch, "fast")
    scope = tmp_path / "alcance.yml"
    scope.write_text("domains: [example.com]\n", encoding="utf-8")
    args = ScanRequest(target="example.com", kind="domain", scope=str(scope), evidence=True)
    proc = CliProcess(args.to_args(), cli=FAKE_CLI)
    proc.start()
    assert proc.wait(60) == 0
    assert CliApi(FAKE_CLI).verify(1)["ok"]


# --- riesgo y cronología -----------------------------------------------------------------------


def saved_view(qtbot, monkeypatch, api=None) -> ScanView:
    scan_id = save_scan(monkeypatch)
    api = api or CliApi(FAKE_CLI)
    view = ScanView.from_result(api.show(scan_id), api=api)
    qtbot.addWidget(view)
    return view


def test_risk_and_timeline_load_only_when_their_tab_is_opened(qtbot, monkeypatch):
    calls = []

    class Counting(CliApi):
        def risk(self, scan_id):
            calls.append(("risk", scan_id))
            return super().risk(scan_id)

        def timeline(self, scan_id):
            calls.append(("timeline", scan_id))
            return super().timeline(scan_id)

    view = saved_view(qtbot, monkeypatch, Counting(FAKE_CLI))
    assert calls == []
    view.views.setCurrentWidget(view.risk)
    qtbot.waitUntil(lambda: view.risk.status.isHidden(), timeout=TIMEOUT)
    view.views.setCurrentWidget(view.timeline)
    qtbot.waitUntil(lambda: view.timeline.status.isHidden(), timeout=TIMEOUT)
    view.views.setCurrentWidget(view.risk)  # ya cargada: no se vuelve a pedir
    assert calls == [("risk", 1), ("timeline", 1)]


def test_an_open_tab_loads_when_the_live_scan_finishes(qtbot, monkeypatch):
    use_modules(monkeypatch, "fast")
    request = ScanRequest(target="example.com", kind="domain")
    view = ScanView(request, FAKE_CLI, api=CliApi(FAKE_CLI))
    qtbot.addWidget(view)
    view.views.setCurrentWidget(view.risk)
    view.start()
    qtbot.waitUntil(lambda: view.session.finished, timeout=TIMEOUT)
    qtbot.waitUntil(lambda: view.risk._loaded_id == view.scan_id, timeout=TIMEOUT)
    assert view.scan_id is not None


def test_an_unsaved_scan_does_not_ask_for_insights(qtbot):
    view = ScanView(ScanRequest(target="example.com", no_save=True), FAKE_CLI, api=CliApi(FAKE_CLI))
    qtbot.addWidget(view)
    view.views.setCurrentWidget(view.risk)
    qtbot.wait(100)
    assert view.risk.content.currentWidget() is view.risk.empty
    assert view.risk._loaded_id is None


def test_a_failing_panel_shows_plain_text_and_can_retry(qtbot):
    class Failing:
        def __init__(self):
            self.calls = 0

        def timeline(self, _scan_id):
            self.calls += 1
            raise RuntimeError("<b>boom</b>")

    api = Failing()
    panel = TimelinePanel(api)
    qtbot.addWidget(panel)
    panel.ensure_loaded(1)
    qtbot.waitUntil(lambda: "boom" in panel.status.text(), timeout=TIMEOUT)
    assert panel.status.textFormat() == Qt.TextFormat.PlainText
    panel.ensure_loaded(1)
    qtbot.waitUntil(lambda: api.calls == 2, timeout=TIMEOUT)


def test_risk_shows_level_with_label_and_sorts_by_score(qtbot):
    class Api:
        def risk(self, _scan_id):
            return {
                "assets": [
                    {
                        "value": "b",
                        "type": "ip",
                        "score": 9,
                        "level": "low",
                        "exposure": {"services": 1, "vulnerabilities": 0},
                        "reasons": ["x"],
                    },
                    {
                        "value": "a",
                        "type": "ip",
                        "score": 80,
                        "level": "critical",
                        "exposure": {"services": 2, "vulnerabilities": 1},
                        "reasons": [],
                    },
                ]
            }

    panel = RiskPanel(Api())
    qtbot.addWidget(panel)
    panel.ensure_loaded(1)
    qtbot.waitUntil(lambda: panel.model.rowCount() == 2, timeout=TIMEOUT)
    assert panel.proxy.index(0, 3).data() == "baja"
    panel.proxy.sort(2, Qt.SortOrder.DescendingOrder)
    assert panel.proxy.index(0, 0).data() == "a"
    assert panel.proxy.index(0, 3).data() == "crítica"
    panel.proxy.sort(3)
    assert panel.proxy.index(0, 3).data() == "crítica"  # por gravedad, no por orden alfabético


# --- casos -------------------------------------------------------------------------------------


def test_a_case_is_created_filled_and_shown_with_the_real_cli(qtbot, monkeypatch):
    scan_id = save_scan(monkeypatch)
    panel = CasesPanel(CliApi(FAKE_CLI))
    qtbot.addWidget(panel)
    with qtbot.waitSignal(panel.loaded, timeout=TIMEOUT):
        panel.reload()
    assert panel.content.currentWidget() is panel.empty
    assert not panel.add_button.isEnabled()

    monkeypatch.setattr(QInputDialog, "getText", lambda *a: ("--caso raro", True))
    panel.new_button.click()
    qtbot.waitUntil(lambda: panel.cases_model.rowCount() == 1, timeout=TIMEOUT)
    assert panel.cases_model.row(0)["name"] == "--caso raro"  # un nombre no es una opción

    monkeypatch.setattr(QInputDialog, "getInt", lambda *a: (scan_id, True))
    panel.add_button.click()
    qtbot.waitUntil(lambda: panel.scans_model.rowCount() == 1, timeout=TIMEOUT)

    monkeypatch.setattr(QInputDialog, "getMultiLineText", lambda *a: ("<b>nota</b>", True))
    panel.note_button.click()
    qtbot.waitUntil(lambda: panel.notes_model.rowCount() == 1, timeout=TIMEOUT)

    with qtbot.waitSignal(panel.scan_requested, timeout=1000) as blocker:
        panel.scans_table.doubleClicked.emit(panel.scans_proxy.index(0, 0))
    assert blocker.args == [scan_id]


def test_an_invalid_case_action_shows_the_error_as_plain_text(qtbot, monkeypatch):
    use_modules(monkeypatch, "fast")
    panel = CasesPanel(CliApi(FAKE_CLI))
    qtbot.addWidget(panel)
    with qtbot.waitSignal(panel.loaded, timeout=TIMEOUT):
        panel.reload()
    panel._selected = "no-existe"
    monkeypatch.setattr(QInputDialog, "getMultiLineText", lambda *a: ("nota", True))
    with qtbot.waitSignal(panel.loaded, timeout=TIMEOUT):
        panel._add_note()
    assert "No se pudo completar" in panel.status.text()
    assert panel.status.textFormat() == Qt.TextFormat.PlainText


def test_cancelling_the_new_case_dialog_does_nothing(qtbot, monkeypatch):
    panel = CasesPanel(CliApi(FAKE_CLI))
    qtbot.addWidget(panel)
    monkeypatch.setattr(QInputDialog, "getText", lambda *a: ("x", False))
    monkeypatch.setattr(panel, "_run", lambda *a: pytest.fail("no debe lanzar nada"))
    panel.new_button.click()


# --- vigilancia --------------------------------------------------------------------------------


def test_without_a_watch_file_there_is_an_explaining_empty_state(qtbot, monkeypatch):
    use_modules(monkeypatch, "fast")
    panel = WatchPanel(CliApi(FAKE_CLI))
    qtbot.addWidget(panel)
    with qtbot.waitSignal(panel.loaded, timeout=TIMEOUT):
        panel.reload()
    assert panel.content.currentWidget() is panel.empty
    assert panel.status.isHidden()  # no es un fallo: es lo normal
    assert panel.refresh_button.isEnabled()


def test_watch_targets_are_listed_and_nothing_can_be_launched(qtbot):
    class Api:
        def watch_list(self):
            return [
                {
                    "target": "example.com",
                    "type": "domain",
                    "every": 86400.0,
                    "last_run": None,
                    "last_status": None,
                    "due": True,
                    "notify": ["correo"],
                }
            ]

    panel = WatchPanel(Api())
    qtbot.addWidget(panel)
    with qtbot.waitSignal(panel.loaded, timeout=TIMEOUT):
        panel.reload()
    assert panel.proxy.index(0, 2).data() == "1 d" and panel.proxy.index(0, 5).data() == "sí"
    assert not hasattr(panel, "run_button")


def test_another_watch_error_is_reported(qtbot):
    class Api:
        def watch_list(self):
            raise CliError("<b>fichero no válido</b>", 2)

    panel = WatchPanel(Api())
    qtbot.addWidget(panel)
    with qtbot.waitSignal(panel.loaded, timeout=TIMEOUT):
        panel.reload()
    assert not panel.status.isHidden() and "<b>fichero" in panel.status.text()
    assert panel.status.textFormat() == Qt.TextFormat.PlainText


# --- ventana: páginas, verificar y barra lateral -------------------------------------------------


def make_window(qtbot, tmp_path, monkeypatch, settings=None, cli=FAKE_CLI) -> MainWindow:
    monkeypatch.setenv("OSINEITOR_GUI_CONFIG_DIR", str(tmp_path / "gui"))
    monkeypatch.setattr(HistoryPanel, "reload", lambda self: None)
    monkeypatch.setattr(MainWindow, "load_catalog", lambda self: None)
    window = MainWindow(settings or GuiSettings(), cli, None if cli else "falta")
    qtbot.addWidget(window)
    return window


def test_cases_and_watch_are_pages_loaded_on_entry(qtbot, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(CasesPanel, "reload", lambda self: calls.append("cases"))
    monkeypatch.setattr(WatchPanel, "reload", lambda self: calls.append("watch"))
    window = make_window(qtbot, tmp_path, monkeypatch)
    assert calls == []
    window.nav_actions["cases"].trigger()
    assert window.stack.currentWidget() is window.cases and calls == ["cases"]
    window.nav_actions["watch"].trigger()
    assert window.stack.currentWidget() is window.watch and calls == ["cases", "watch"]
    assert window.nav_actions["cases"].shortcut().toString() == "Ctrl+5"
    assert window.nav_actions["watch"].shortcut().toString() == "Ctrl+6"


def test_health_is_disabled_without_the_cli(qtbot, tmp_path, monkeypatch):
    window = make_window(qtbot, tmp_path, monkeypatch, cli=None)
    assert not window.sidebar._pages["health"].isEnabled()
    assert window.sidebar._pages["settings"].isEnabled()


@pytest.mark.parametrize(
    ("result", "fragment", "tone"),
    [
        ({"ok": True, "checked": 3}, "3 evidencias correctas", "safe"),
        ({"ok": True, "checked": 0}, "no guardó evidencias", "warning"),
        ({"ok": False, "checked": 3, "mismatches": [{}, {}]}, "2 evidencias alteradas", "critical"),
    ],
)
def test_verify_says_what_really_happened(qtbot, tmp_path, monkeypatch, result, fragment, tone):
    window = make_window(qtbot, tmp_path, monkeypatch)
    window.show()
    window._verified(7, result)
    assert fragment in window.statusBar().currentMessage()
    assert window.toast.property("tone") == tone


def test_verify_treats_tampering_as_a_result_and_not_an_error(monkeypatch):
    seen = {}

    def fake_run(self, args, **kwargs):
        seen.update(kwargs)
        return {"ok": False}

    monkeypatch.setattr(CliApi, "run", fake_run)
    assert CliApi(["x"]).verify(1) == {"ok": False}
    assert 5 in seen["ok_codes"]


def test_the_sidebar_choice_is_remembered_and_beats_the_width(qtbot, tmp_path, monkeypatch):
    settings = GuiSettings()
    window = make_window(qtbot, tmp_path, monkeypatch, settings)
    window.show()
    window.resize(1300, 700)
    qtbot.waitUntil(lambda: window.sidebar.width() == EXPANDED_WIDTH, timeout=2000)
    window.action_toggle_sidebar.trigger()
    assert window.sidebar.width() == COLLAPSED_WIDTH and settings.sidebar == "collapsed"
    assert GuiSettings.load().sidebar == "collapsed"
    window.resize(900, 700)
    window.resize(1300, 700)
    qtbot.wait(50)
    assert window.sidebar.collapsed  # la anchura ya no decide
    again = make_window(qtbot, tmp_path, monkeypatch, GuiSettings.load())
    assert again.sidebar.collapsed


# --- accesibilidad y aspecto ---------------------------------------------------------------------


def test_chart_values_are_reachable_with_the_keyboard(qtbot):
    chart = ColumnChart()
    qtbot.addWidget(chart)
    chart.resize(400, 200)
    chart.set_data([Column("a", [("info", 1)], "a: 1"), Column("b", [("info", 2)], "b: 2")])
    chart.show()
    assert chart.focusPolicy() == Qt.FocusPolicy.StrongFocus
    QTest.keyClick(chart, Qt.Key.Key_Right)
    assert chart._hover == 0 and chart.accessibleDescription() == "a: 1"
    QTest.keyClick(chart, Qt.Key.Key_Right)
    assert chart._hover == 1 and chart.accessibleDescription() == "b: 2"
    QTest.keyClick(chart, Qt.Key.Key_Right)
    assert chart._hover == 1  # no se sale
    QTest.keyClick(chart, Qt.Key.Key_Left)
    assert chart._hover == 0
    chart.grab()


def test_hovering_marks_the_whole_row(qtbot):
    model = HealthModel()
    table, _proxy = make_table(model)
    qtbot.addWidget(table)
    model.set_rows([{"module": "a", "verdict": "ok"}, {"module": "b", "verdict": "ok"}])
    table.resize(400, 200)
    table.show()
    viewport = table.viewport()
    position = QPointF(10, table.rowViewportPosition(1) + 2)
    move = QMouseEvent(
        QEvent.Type.MouseMove,
        position,
        viewport.mapToGlobal(position),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(viewport, move)
    assert table.property(HOVER_ROW) == 1
    table.grab()
    QApplication.sendEvent(viewport, QEvent(QEvent.Type.Leave))
    assert table.property(HOVER_ROW) == -1


def test_standard_buttons_are_in_spanish(qapp, qtbot):
    theme.install(qapp)
    box = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
    qtbot.addWidget(box)
    assert box.button(QDialogButtonBox.StandardButton.Cancel).text() == "Cancelar"
    message = QMessageBox()
    qtbot.addWidget(message)
    message.setStandardButtons(QMessageBox.StandardButton.Yes)
    assert message.button(QMessageBox.StandardButton.Yes).text().replace("&", "") == "Sí"

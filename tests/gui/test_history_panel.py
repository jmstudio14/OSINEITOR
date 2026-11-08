"""Panel Historial y ejecutor en hilo, contra la CLI real con módulos falsos (sin red)."""

from __future__ import annotations

import os
import sys
import threading

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from osineitor_gui.api import CliApi  # noqa: E402
from osineitor_gui.ui.history_panel import HistoryModel, HistoryPanel  # noqa: E402
from osineitor_gui.ui.worker import run_in_thread  # noqa: E402
from tests.gui.fakecli import CLI, save_scan, use_modules  # noqa: E402

TIMEOUT = 30_000


def make_panel(qtbot, cli=CLI) -> HistoryPanel:
    panel = HistoryPanel(CliApi(cli))
    qtbot.addWidget(panel)
    return panel


def load(qtbot, panel: HistoryPanel) -> None:
    with qtbot.waitSignal(panel.loaded, timeout=TIMEOUT):
        panel.reload()


def test_model_shows_id_target_type_entities_and_date():
    model = HistoryModel()
    model.set_rows(
        [
            {
                "id": 3,
                "target": "example.com",
                "target_type": "domain",
                "entities": 7,
                "started_at": "2026-11-05T19:04:11.123+00:00",
            }
        ]
    )
    cells = [model.data(model.index(0, c)) for c in range(5)]
    assert cells == [3, "example.com", "domain", 7, "2026-11-05 19:04:11"]
    assert model.scan_id(0) == 3
    assert model.rowCount(model.index(0, 0)) == 0  # tabla plana: las celdas no tienen hijos


def test_an_empty_history_says_so(qtbot, monkeypatch):
    use_modules(monkeypatch, "fast")
    panel = make_panel(qtbot)
    load(qtbot, panel)
    assert panel.model.rowCount() == 0 and "no hay scans" in panel.status.text()
    assert panel.refresh_button.isEnabled()


def test_it_lists_saved_scans_and_double_click_requests_one(qtbot, monkeypatch):
    scan_id = save_scan(monkeypatch)
    panel = make_panel(qtbot)
    load(qtbot, panel)
    assert panel.model.rowCount() == 1 and panel.model.scan_id(0) == scan_id
    assert panel.model.data(panel.model.index(0, 1)) == "example.com"
    with qtbot.waitSignal(panel.scan_requested, timeout=1000) as blocker:
        panel.table.doubleClicked.emit(panel.proxy.index(0, 0))
    assert blocker.args == [scan_id]


def test_a_failing_cli_shows_the_error_without_breaking(qtbot):
    dead = [sys.executable, "-c", "import sys; sys.stderr.write('boom\n'); sys.exit(2)"]
    panel = make_panel(qtbot, dead)
    load(qtbot, panel)
    assert "No se pudo cargar el historial" in panel.status.text()
    assert "boom" in panel.status.text() and panel.refresh_button.isEnabled()


def test_worker_callbacks_run_in_the_ui_thread(qtbot):
    main = threading.get_ident()
    done = []
    run_in_thread(
        threading.get_ident,
        lambda value: done.append((value, threading.get_ident())),
        lambda exc: done.append(exc),
    )
    qtbot.waitUntil(lambda: bool(done), timeout=TIMEOUT)
    worker, callback = done[0]
    assert worker != main and callback == main


def test_worker_delivers_exceptions_to_on_error(qtbot):
    errors = []

    def boom():
        raise ValueError("falló")

    run_in_thread(boom, lambda value: errors.append(value), errors.append)
    qtbot.waitUntil(lambda: bool(errors), timeout=TIMEOUT)
    assert isinstance(errors[0], ValueError) and str(errors[0]) == "falló"

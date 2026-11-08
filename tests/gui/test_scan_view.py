"""ScanRunner y ScanView contra la CLI real con módulos falsos (sin red)."""

from __future__ import annotations

import os
import sys

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from osineitor_gui.events import (  # noqa: E402
    EXIT_CANCELLED,
    EXIT_MODULE_ERRORS,
    EXIT_OK,
    ModuleEnd,
    ScanEnd,
)
from osineitor_gui.scan_request import ScanRequest  # noqa: E402
from osineitor_gui.ui.runner import ScanRunner  # noqa: E402
from osineitor_gui.ui.scan_view import ScanView  # noqa: E402
from tests.gui.fakecli import CLI, DEAF, use_modules  # noqa: E402

TIMEOUT = 30_000


def request(**kwargs) -> ScanRequest:
    return ScanRequest(target="example.com", kind="domain", **kwargs)


def make_view(qtbot, monkeypatch, modules: str, cli=CLI, **kwargs) -> ScanView:
    use_modules(monkeypatch, modules)
    view = ScanView(request(**kwargs), cli)
    qtbot.addWidget(view)
    return view


def settled(view: ScanView) -> bool:
    """El scan acabó y la vista ya pintó lo último (no queda un refresco pendiente)."""
    return view.session.finished and not view._timer.isActive()


def run_to_end(qtbot, view: ScanView) -> None:
    view.start()
    qtbot.waitUntil(lambda: settled(view), timeout=TIMEOUT)


def entity_values(view: ScanView) -> list[str]:
    return [view.entities_model.entity(r)["value"] for r in range(view.entities_model.rowCount())]


def test_runner_delivers_events_in_order_and_then_finished(qtbot, monkeypatch):
    use_modules(monkeypatch, "fast")
    runner = ScanRunner(request(no_save=True).to_args(), CLI)
    events = []
    runner.event.connect(events.append)
    with qtbot.waitSignal(runner.finished, timeout=TIMEOUT) as blocker:
        runner.start()
    assert blocker.args == [EXIT_OK]
    assert isinstance(events[-1], ScanEnd) and events[-1].exit_code == 0
    assert any(isinstance(e, ModuleEnd) and e.module == "fast" for e in events)


def test_a_live_scan_fills_the_tables(qtbot, monkeypatch):
    view = make_view(qtbot, monkeypatch, "fast,bad", no_save=True)
    run_to_end(qtbot, view)
    assert view.session.state == "complete"
    assert "9.9.9.9" in entity_values(view)
    statuses = {
        view.modules_model.index(r, 0).data(): view.modules_model.status_at(r)
        for r in range(view.modules_model.rowCount())
    }
    assert statuses["fast"] == "ok" and statuses["bad"] == "error"
    assert view.banner.isHidden()  # un módulo con error no hace incompleto el scan


def test_the_type_filter_shows_counts_and_narrows_the_table(qtbot, monkeypatch):
    view = make_view(qtbot, monkeypatch, "fast", no_save=True)
    run_to_end(qtbot, view)
    items = [view.type_filter.itemText(i) for i in range(view.type_filter.count())]
    assert items[0].startswith("Todos los tipos (") and any(t.startswith("ip (1)") for t in items)
    view.type_filter.setCurrentIndex(view.type_filter.findData("ip"))
    assert entity_values(view) == ["9.9.9.9"]
    view.search.setText("no-existe")
    assert entity_values(view) == []


def test_the_title_and_status_follow_the_scan(qtbot, monkeypatch):
    view = make_view(qtbot, monkeypatch, "fast", no_save=True)
    assert view.title() == "example.com" and not view.is_running
    run_to_end(qtbot, view)
    assert view.title() == "example.com" and view.status_text() == "completo"


def test_a_scan_with_failed_modules_says_so_in_its_status(qtbot, monkeypatch):
    view = make_view(qtbot, monkeypatch, "fast,bad", no_save=True)
    run_to_end(qtbot, view)
    assert view.session.exit_code == EXIT_MODULE_ERRORS
    assert view.status_text() == "completo, con errores en módulos"
    assert view.title() == "example.com" and view.banner.isHidden()


def test_cancelling_marks_the_scan_as_cancelled_and_keeps_what_was_found(qtbot, monkeypatch):
    view = make_view(qtbot, monkeypatch, "fast,hang")
    view.start()
    qtbot.waitUntil(lambda: "9.9.9.9" in entity_values(view), timeout=TIMEOUT)
    assert view.is_running
    view.cancel()
    qtbot.waitUntil(lambda: settled(view), timeout=TIMEOUT)
    assert view.session.state == "cancelled" and view.session.exit_code == EXIT_CANCELLED
    assert "9.9.9.9" in entity_values(view)
    assert not view.banner.isHidden() and "cancelado" in view.banner.text()
    assert view.title() == "example.com (cancelado)"


def test_a_cli_that_dies_without_closing_the_scan_is_shown_as_failed(qtbot, monkeypatch):
    dead = [sys.executable, "-c", "import sys; sys.stderr.write('boom\\n'); sys.exit(1)"]
    view = make_view(qtbot, monkeypatch, "fast", cli=dead, no_save=True)
    run_to_end(qtbot, view)
    assert view.session.state == "failed"
    assert not view.banner.isHidden() and "boom" in view.banner.text()


def test_stop_helpers_end_a_process_that_ignores_stdin(qtbot, monkeypatch):
    view = make_view(qtbot, monkeypatch, "fast", cli=DEAF, no_save=True)
    view.start()
    view.kill()
    view.wait(10)
    qtbot.waitUntil(lambda: settled(view), timeout=TIMEOUT)
    assert view.session.state == "failed"


# --- scans guardados y panel de detalle (G4) ---------------------------------------------------


def saved_result(monkeypatch, modules: str = "fast,bad") -> dict:
    from osineitor_gui.api import CliApi
    from tests.gui.fakecli import save_scan

    scan_id = save_scan(monkeypatch, modules)
    return CliApi(CLI).show(scan_id)


def test_a_saved_scan_looks_like_a_live_one(qtbot, monkeypatch):
    view = ScanView.from_result(saved_result(monkeypatch))
    qtbot.addWidget(view)
    assert view.session.state == "complete" and not view.is_running and view.scan_id == 1
    assert "9.9.9.9" in entity_values(view)
    statuses = {
        view.modules_model.index(r, 0).data(): view.modules_model.status_at(r)
        for r in range(view.modules_model.rowCount())
    }
    assert statuses == {"fast": "ok", "bad": "error"}
    assert view.title() == "example.com #1" and view.banner.isHidden()
    items = [view.type_filter.itemText(i) for i in range(view.type_filter.count())]
    assert any(t.startswith("ip (1)") for t in items)


def test_a_saved_scan_has_no_process_to_control(qtbot, monkeypatch):
    view = ScanView.from_result(saved_result(monkeypatch))
    qtbot.addWidget(view)
    view.start()
    view.cancel()
    view.kill()
    assert view.wait(1) == 0 and view.session.state == "complete" and not view.is_running


def test_a_cancelled_saved_scan_shows_the_incomplete_banner(qtbot, monkeypatch):
    result = saved_result(monkeypatch)
    result["status"] = "cancelled"
    view = ScanView.from_result(result)
    qtbot.addWidget(view)
    assert not view.banner.isHidden() and "cancelado" in view.banner.text()
    assert view.title() == "example.com #1 (cancelado)"


def test_selecting_an_entity_fills_the_detail_and_filtering_clears_it(qtbot, monkeypatch):
    view = ScanView.from_result(saved_result(monkeypatch))
    qtbot.addWidget(view)
    view.show()
    assert view.detail.placeholder.isVisible()
    row = entity_values(view).index("9.9.9.9")
    view.entities_table.selectRow(row)
    table = view.detail.table
    cells = {table.item(r, 0).text(): table.item(r, 1).text() for r in range(table.rowCount())}
    assert cells["org"] == "ACMÉ ñ" and "Fuente" in cells and "Origen" in cells
    view.search.setText("zzz")  # el filtro reinicia el modelo: se limpia el detalle
    assert view.detail.placeholder.isVisible()


def test_a_live_scan_also_fills_the_detail(qtbot, monkeypatch):
    view = make_view(qtbot, monkeypatch, "fast", no_save=True)
    run_to_end(qtbot, view)
    view.entities_table.selectRow(entity_values(view).index("9.9.9.9"))
    assert view.detail.table.rowCount() >= 3

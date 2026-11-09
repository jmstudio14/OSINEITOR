"""Panel de salud de los módulos (G5): modelo de la tabla y diálogo."""

from __future__ import annotations

import os
import threading

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt, QThreadPool  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from osineitor_gui.api import CliApi, CliError  # noqa: E402
from osineitor_gui.ui import risk_dialog  # noqa: E402
from osineitor_gui.ui.modules_view import HealthModel, HealthPanel  # noqa: E402
from tests.gui.fakecli import CLI, use_modules  # noqa: E402

TIMEOUT = 30_000

ROWS = [
    {"module": "dns", "verdict": "ok", "detail": "", "duration_ms": 1234, "requests": 3},
    {"module": "rdap", "verdict": "fail", "detail": "HTTP 500", "duration_ms": 80, "requests": 1},
    {
        "module": "wayback",
        "verdict": "skipped",
        "detail": "sin red",
        "duration_ms": 0,
        "requests": 0,
    },
]


class FakeApi:
    """Sustituye a `CliApi`: devuelve filas fijas, o espera a que el test lo libere."""

    def __init__(self, rows=None, error: Exception | None = None, gate=None) -> None:
        self.rows, self.error, self.gate, self.calls = rows or [], error, gate, 0
        self.active_args: list[bool] = []

    def doctor(self, *args, **kwargs):
        self.calls += 1
        self.active_args.append(kwargs.get("active", False))
        if self.gate is not None:
            self.gate.wait(TIMEOUT / 1000)
        if self.error is not None:
            raise self.error
        return self.rows


def cell(model: HealthModel, row: int, column: int, role=Qt.ItemDataRole.DisplayRole):
    return model.data(model.index(row, column), role)


def make_dialog(qtbot, api) -> HealthPanel:
    dialog = HealthPanel(api)
    qtbot.addWidget(dialog)
    return dialog


def run_check(qtbot, dialog: HealthPanel) -> None:
    dialog.check()
    qtbot.waitUntil(lambda: dialog.run_button.isEnabled(), timeout=TIMEOUT)


# --- modelo -----------------------------------------------------------------------------------


def test_model_shows_one_row_per_module():
    model = HealthModel()
    model.set_rows(ROWS)
    assert model.rowCount() == 3 and model.columnCount() == 5
    assert [cell(model, r, 0) for r in range(3)] == ["dns", "rdap", "wayback"]
    assert model.rowCount(model.index(0, 0)) == 0  # tabla plana


def test_model_translates_known_verdicts():
    model = HealthModel()
    model.set_rows(ROWS)
    assert cell(model, 0, 1) == "ok"
    assert cell(model, 1, 1) == "falla"
    assert cell(model, 2, 1) == "omitido"


def test_unknown_verdict_is_shown_as_is():
    model = HealthModel()
    model.set_rows([{"module": "x", "verdict": "raro"}])
    assert cell(model, 0, 1) == "raro"


def test_missing_fields_are_empty_text():
    model = HealthModel()
    model.set_rows([{"module": "x", "verdict": "ok", "detail": None}])
    assert cell(model, 0, 2) == ""
    assert cell(model, 0, 3) == "" and cell(model, 0, 4) == ""


def test_fail_and_ok_have_distinct_foreground():
    model = HealthModel()
    model.set_rows(ROWS)
    fail = cell(model, 1, 1, Qt.ItemDataRole.ForegroundRole)
    ok = cell(model, 0, 1, Qt.ItemDataRole.ForegroundRole)
    assert fail is not None and fail != ok


def test_duration_is_formatted_in_ms():
    model = HealthModel()
    model.set_rows(ROWS)
    assert cell(model, 0, 3) == "1234 ms"
    assert cell(model, 0, 4) == 3


# --- diálogo ----------------------------------------------------------------------------------


def test_check_fills_the_table(qtbot):
    dialog = make_dialog(qtbot, FakeApi(ROWS))
    run_check(qtbot, dialog)
    assert dialog.model.rowCount() == 3
    assert dialog.run_button.isEnabled() and not dialog.busy.isVisibleTo(dialog)


def test_button_is_disabled_while_running(qtbot):
    gate = threading.Event()
    dialog = make_dialog(qtbot, FakeApi(ROWS, gate=gate))
    dialog.check()
    assert not dialog.run_button.isEnabled() and dialog.busy.isVisibleTo(dialog)
    gate.set()
    qtbot.waitUntil(lambda: dialog.run_button.isEnabled(), timeout=TIMEOUT)


def test_second_check_while_running_is_ignored(qtbot):
    gate = threading.Event()
    api = FakeApi(ROWS, gate=gate)
    dialog = make_dialog(qtbot, api)
    dialog.check()
    dialog.check()
    gate.set()
    qtbot.waitUntil(lambda: dialog.run_button.isEnabled(), timeout=TIMEOUT)
    assert api.calls == 1


def test_cli_error_is_shown_inline(qtbot, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("un QMessageBox modal bloquearía la ventana")

    monkeypatch.setattr(QMessageBox, "critical", forbidden)
    dialog = make_dialog(qtbot, FakeApi(error=CliError("boom", 1, "boom")))
    run_check(qtbot, dialog)
    assert "boom" in dialog.status.text()
    assert dialog.run_button.isEnabled() and dialog.model.rowCount() == 0


def test_empty_result_says_so(qtbot):
    dialog = make_dialog(qtbot, FakeApi([]))
    run_check(qtbot, dialog)
    assert dialog.status.text() and "error" not in dialog.status.text().lower()
    assert dialog.model.rowCount() == 0


def test_a_new_check_replaces_the_previous_rows(qtbot):
    api = FakeApi(ROWS)
    dialog = make_dialog(qtbot, api)
    run_check(qtbot, dialog)
    api.rows = ROWS[:1]
    run_check(qtbot, dialog)
    assert dialog.model.rowCount() == 1


def test_closing_while_running_does_not_crash(qtbot):
    gate = threading.Event()
    dialog = make_dialog(qtbot, FakeApi(ROWS, gate=gate))
    dialog.check()
    dialog.close()
    dialog.deleteLater()
    gate.set()
    QThreadPool.globalInstance().waitForDone(TIMEOUT)
    QApplication.processEvents()  # entrega (o descarta) el resultado del hilo


def test_dialog_against_the_real_cli(qtbot, monkeypatch):
    use_modules(monkeypatch, "fast,bad")
    dialog = make_dialog(qtbot, CliApi(CLI))
    run_check(qtbot, dialog)
    assert {cell(dialog.model, r, 0) for r in range(dialog.model.rowCount())} == {"fast", "bad"}


# --- módulos activos (G7) ---------------------------------------------------------------------


def confirm_with(monkeypatch, answer: bool) -> list[int]:
    asked: list[int] = []

    def confirm(parent=None):
        asked.append(1)
        return answer

    monkeypatch.setattr(risk_dialog, "confirm_active", confirm)
    return asked


def test_by_default_only_passive_modules_are_checked(qtbot):
    api = FakeApi(ROWS)
    dialog = make_dialog(qtbot, api)
    assert not dialog.active_box.isChecked()
    run_check(qtbot, dialog)
    assert api.active_args == [False]


def test_active_check_needs_confirmation(qtbot, monkeypatch):
    asked = confirm_with(monkeypatch, False)
    api = FakeApi(ROWS)
    dialog = make_dialog(qtbot, api)
    dialog.active_box.setChecked(True)
    assert asked == [1] and not dialog.active_box.isChecked()
    run_check(qtbot, dialog)
    assert api.active_args == [False]  # rechazada: nunca se llama con active=True


def test_confirmed_active_check_passes_active_to_doctor(qtbot, monkeypatch):
    confirm_with(monkeypatch, True)
    api = FakeApi(ROWS)
    dialog = make_dialog(qtbot, api)
    dialog.active_box.setChecked(True)
    assert dialog.active_box.isChecked()
    run_check(qtbot, dialog)
    assert api.active_args == [True]
    dialog.active_box.setChecked(False)  # desmarcar no vuelve a preguntar
    run_check(qtbot, dialog)
    assert api.active_args == [True, False]

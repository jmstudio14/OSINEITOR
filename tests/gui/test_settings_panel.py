"""Diálogo de ajustes (G6): API keys y pestaña General."""

from __future__ import annotations

import os
import threading

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QLabel, QLineEdit, QMessageBox  # noqa: E402

from osineitor_gui.api import CliApi, CliError  # noqa: E402
from osineitor_gui.settings import GuiSettings  # noqa: E402
from osineitor_gui.ui.settings_panel import SettingsPanel  # noqa: E402
from tests.gui.fakecli import CLI, use_modules  # noqa: E402

TIMEOUT = 30_000
SECRET = "sk-SECRETO"


def module(name: str, key: str | None, configured: bool = False) -> dict:
    return {"name": name, "requires_key": key, "key_configured": configured}


class FakeApi:
    """Sustituye a `CliApi`: guarda las keys en memoria y registra cada llamada."""

    def __init__(self, error: Exception | None = None, gate=None, modules_error=None) -> None:
        self.keys: set[str] = set()
        self.calls: list[tuple] = []
        self.error, self.gate, self.modules_error = error, gate, modules_error

    def modules(self):
        if self.modules_error is not None:
            raise self.modules_error
        return [
            module("hibp", "hibp", "hibp" in self.keys),
            module("hibp_pastes", "hibp", "hibp" in self.keys),
            module("shodan", "shodan", "shodan" in self.keys),
            module("dns", None),
        ]

    def _change(self, call: tuple, apply) -> dict:
        self.calls.append(call)
        if self.gate is not None:
            self.gate.wait(TIMEOUT / 1000)
        if self.error is not None:
            raise self.error
        apply()
        return {"name": call[1], "configured": call[1] in self.keys}

    def config_set(self, name, value):
        return self._change(("set", name, value), lambda: self.keys.add(name))

    def config_unset(self, name):
        return self._change(("unset", name), lambda: self.keys.discard(name))


def cell(dialog: SettingsPanel, row: int, column: int):
    return dialog.model.data(dialog.model.index(row, column))


def make_dialog(qtbot, api, settings=None) -> SettingsPanel:
    dialog = SettingsPanel(api, settings or GuiSettings())
    qtbot.addWidget(dialog)
    dialog.reload()
    qtbot.waitUntil(lambda: dialog.model.rowCount() > 0 or "No se pudo" in dialog.message.text())
    return dialog


def wait_idle(qtbot, dialog: SettingsPanel) -> None:
    qtbot.waitUntil(lambda: not dialog._busy, timeout=TIMEOUT)


def select(dialog: SettingsPanel, name: str) -> None:
    dialog.keys_table.selectRow(dialog.model.row_of(name))


def type_and_save(qtbot, dialog: SettingsPanel, text: str) -> None:
    dialog.key_input.setText(text)
    dialog.save()
    wait_idle(qtbot, dialog)


# --- pestaña «API keys» -----------------------------------------------------------------------


def test_lists_one_row_per_key_with_state(qtbot):
    dialog = make_dialog(qtbot, FakeApi())
    assert dialog.model.rowCount() == 2
    assert [cell(dialog, r, 0) for r in range(2)] == ["hibp", "shodan"]
    assert cell(dialog, 0, 1) == "hibp, hibp_pastes"
    assert cell(dialog, 0, 2) == "falta"


def test_save_sends_the_stripped_value_and_clears_the_field(qtbot):
    api = FakeApi()
    dialog = make_dialog(qtbot, api)
    select(dialog, "hibp")
    type_and_save(qtbot, dialog, "  abc \n")
    assert api.calls == [("set", "hibp", "abc")]
    assert dialog.key_input.text() == ""
    assert cell(dialog, dialog.model.row_of("hibp"), 2) == "configurada"  # sale de la CLI


def test_the_key_field_hides_what_is_typed(qtbot):
    dialog = make_dialog(qtbot, FakeApi())
    assert dialog.key_input.echoMode() == QLineEdit.EchoMode.Password


def test_empty_key_is_not_sent(qtbot):
    api = FakeApi()
    dialog = make_dialog(qtbot, api)
    select(dialog, "hibp")
    dialog.key_input.setText("   ")
    dialog.save()
    assert api.calls == [] and dialog.message.text()


def test_key_never_appears_in_widgets(qtbot):
    api = FakeApi()
    dialog = make_dialog(qtbot, api)
    select(dialog, "shodan")
    type_and_save(qtbot, dialog, SECRET)
    texts = [label.text() + label.toolTip() for label in dialog.findChildren(QLabel)]
    texts += [
        str(dialog.model.data(dialog.model.index(r, c), role))
        for r in range(dialog.model.rowCount())
        for c in range(dialog.model.columnCount())
        for role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole)
    ]
    texts += [dialog.key_input.text(), dialog.key_input.toolTip(), dialog.message.toolTip()]
    assert not any(SECRET in text for text in texts)


def test_cli_error_does_not_echo_the_key(qtbot, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("un QMessageBox modal bloquearía la ventana")

    monkeypatch.setattr(QMessageBox, "critical", forbidden)
    error = CliError(f"fallo con {SECRET}", 2, f"fallo con {SECRET}")
    dialog = make_dialog(qtbot, FakeApi(error=error))
    select(dialog, "shodan")
    type_and_save(qtbot, dialog, SECRET)
    assert SECRET not in dialog.message.text() and "No se pudo guardar" in dialog.message.text()
    assert "2" in dialog.message.text()
    assert dialog.save_button.isEnabled()


def test_delete_calls_config_unset_and_marks_missing(qtbot):
    api = FakeApi()
    api.keys.add("hibp")
    dialog = make_dialog(qtbot, api)
    select(dialog, "hibp")
    assert cell(dialog, 0, 2) == "configurada"
    dialog.delete()
    wait_idle(qtbot, dialog)
    assert api.calls == [("unset", "hibp")]
    assert cell(dialog, dialog.model.row_of("hibp"), 2) == "falta"


def test_selection_survives_the_reload(qtbot):
    dialog = make_dialog(qtbot, FakeApi())
    select(dialog, "shodan")
    type_and_save(qtbot, dialog, "abc")
    assert dialog._selected_name() == "shodan"


def test_buttons_disabled_while_an_operation_runs(qtbot):
    gate = threading.Event()
    api = FakeApi(gate=gate)
    dialog = make_dialog(qtbot, api)
    select(dialog, "hibp")
    dialog.key_input.setText("abc")
    dialog.save()
    assert not dialog.save_button.isEnabled() and not dialog.delete_button.isEnabled()
    dialog.save()
    dialog.delete()  # ignorados mientras hay una operación en curso
    gate.set()
    wait_idle(qtbot, dialog)
    assert api.calls == [("set", "hibp", "abc")]


def test_modules_error_disables_the_buttons(qtbot):
    dialog = make_dialog(qtbot, FakeApi(modules_error=CliError("no hay CLI")))
    assert "no hay CLI" in dialog.message.text()
    assert not dialog.save_button.isEnabled() and not dialog.delete_button.isEnabled()


def test_without_a_selection_nothing_is_sent(qtbot):
    api = FakeApi()
    dialog = make_dialog(qtbot, api)
    dialog.keys_table.clearSelection()
    dialog.key_input.setText("abc")
    dialog.save()
    dialog.delete()
    assert api.calls == [] and not dialog.save_button.isEnabled()


def test_real_cli_save_and_delete_a_shared_key(qtbot, monkeypatch):
    """Contra la CLI real (config aislado): dos módulos con la misma key son una fila."""
    use_modules(monkeypatch, "fast,keyed,keyed2")
    api = CliApi(CLI)
    dialog = make_dialog(qtbot, api)
    assert dialog.model.rowCount() == 1
    assert cell(dialog, 0, 0) == "demo" and cell(dialog, 0, 1) == "keyed, keyed2"
    assert cell(dialog, 0, 2) == "falta"

    type_and_save(qtbot, dialog, SECRET)
    assert cell(dialog, 0, 2) == "configurada"
    assert "demo" in [key["name"] for key in api.config_show()["keys"]]

    dialog.delete()
    wait_idle(qtbot, dialog)
    assert cell(dialog, 0, 2) == "falta"
    assert "demo" not in [key["name"] for key in api.config_show()["keys"]]


# --- pestaña «General» ------------------------------------------------------------------------


def test_general_tab_starts_on_the_saved_theme(qtbot):
    dialog = make_dialog(qtbot, FakeApi(), GuiSettings(theme="dark"))
    assert dialog.theme_box.currentData() == "dark"


def test_general_tab_announces_the_chosen_theme(qtbot):
    dialog = make_dialog(qtbot, FakeApi())
    with qtbot.waitSignal(dialog.theme_changed, timeout=1000) as blocker:
        dialog.theme_box.setCurrentIndex(dialog.theme_box.findData("light"))
        dialog.theme_box.activated.emit(dialog.theme_box.currentIndex())
    assert blocker.args == ["light"]

"""Confirmaciones de módulos activos y redes privadas (G7)."""

from __future__ import annotations

import os

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QMessageBox  # noqa: E402

from osineitor_gui import legal  # noqa: E402
from osineitor_gui.ui import risk_dialog  # noqa: E402


def press(monkeypatch, which: str) -> list[QMessageBox]:
    """Sustituye `exec` por «el usuario pulsa» el botón `which` (`accept` o `cancel`)."""
    boxes: list[QMessageBox] = []

    def fake_exec(self) -> int:
        boxes.append(self)
        getattr(self, f"{which}_button").click()
        return 0

    monkeypatch.setattr(QMessageBox, "exec", fake_exec)
    return boxes


@pytest.mark.parametrize(
    ("confirm", "text"),
    [
        (risk_dialog.confirm_active, legal.ACTIVE_WARNING),
        (risk_dialog.confirm_private, legal.PRIVATE_WARNING),
    ],
)
def test_true_only_on_the_explicit_button(qtbot, monkeypatch, confirm, text):
    boxes = press(monkeypatch, "accept")
    assert confirm(None) is True
    assert boxes[0].text() == text  # el texto es la constante legal, sin retocar


@pytest.mark.parametrize("confirm", [risk_dialog.confirm_active, risk_dialog.confirm_private])
def test_cancel_is_false(qtbot, monkeypatch, confirm):
    press(monkeypatch, "cancel")
    assert confirm(None) is False


@pytest.mark.parametrize("confirm", [risk_dialog.confirm_active, risk_dialog.confirm_private])
def test_closing_the_box_is_false(qtbot, monkeypatch, confirm):
    """Esc o la X no confirman: sin pulsar nada, `clickedButton()` no es el de aceptar."""
    monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)
    assert confirm(None) is False


@pytest.mark.parametrize("make", [risk_dialog.active_box, risk_dialog.private_box])
def test_enter_and_escape_cancel(qtbot, make):
    box = make(None)
    qtbot.addWidget(box)
    assert box.defaultButton() is box.cancel_button  # Enter no confirma
    assert box.escapeButton() is box.cancel_button
    assert box.accept_button.text() != box.cancel_button.text()

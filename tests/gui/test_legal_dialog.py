"""Aviso legal: modo informativo (menú Ayuda) y modo de aceptación obligatoria (primer arranque)."""

from __future__ import annotations

import os

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QDialog, QDialogButtonBox  # noqa: E402

from osineitor_gui import legal  # noqa: E402
from osineitor_gui.ui.legal_dialog import LegalDialog  # noqa: E402


def required(qtbot) -> LegalDialog:
    dialog = LegalDialog(None, require_acceptance=True)
    qtbot.addWidget(dialog)
    dialog.show()
    return dialog


def test_informative_mode_only_closes(qtbot):
    dialog = LegalDialog()
    qtbot.addWidget(dialog)
    assert len(dialog.findChild(QDialogButtonBox).buttons()) == 1
    assert not hasattr(dialog, "accept_button")
    assert dialog.text.toPlainText() == legal.LEGAL_TEXT


def test_required_mode_has_accept_and_exit_with_exit_as_default(qtbot):
    dialog = required(qtbot)
    assert dialog.accept_button.text() == "Acepto"
    assert dialog.exit_button.text() == "Salir"
    assert dialog.exit_button.isDefault() and not dialog.accept_button.isDefault()
    assert dialog.text.toPlainText() == legal.LEGAL_TEXT


def test_accept_button_accepts(qtbot):
    dialog = required(qtbot)
    dialog.accept_button.click()
    assert dialog.result() == QDialog.DialogCode.Accepted


def test_exit_button_rejects(qtbot):
    dialog = required(qtbot)
    dialog.exit_button.click()
    assert dialog.result() == QDialog.DialogCode.Rejected


def test_enter_does_not_accept(qtbot):
    dialog = required(qtbot)
    dialog.accept_button.setFocus()
    qtbot.keyClick(dialog.exit_button, Qt.Key.Key_Return)
    assert dialog.result() == QDialog.DialogCode.Rejected


def test_escape_is_a_rejection(qtbot):
    dialog = required(qtbot)
    qtbot.keyClick(dialog, Qt.Key.Key_Escape)
    assert dialog.result() == QDialog.DialogCode.Rejected


def test_closing_the_window_is_a_rejection(qtbot):
    dialog = required(qtbot)
    dialog.close()
    assert dialog.result() == QDialog.DialogCode.Rejected

"""Arranque de la aplicación: la puerta del aviso legal."""

from __future__ import annotations

import json
import os

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QDialog, QMessageBox  # noqa: E402

from osineitor_gui import app  # noqa: E402
from osineitor_gui.legal import LEGAL_VERSION  # noqa: E402
from osineitor_gui.settings import GuiSettings, settings_path  # noqa: E402
from osineitor_gui.ui import main_window  # noqa: E402
from osineitor_gui.ui.legal_dialog import LegalDialog  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("OSINEITOR_GUI_CONFIG_DIR", str(tmp_path / "gui"))


def answer(monkeypatch, result: QDialog.DialogCode) -> list[LegalDialog]:
    """Sustituye `exec` del aviso por la respuesta del usuario y recuerda los avisos mostrados."""
    shown: list[LegalDialog] = []

    def fake_exec(self) -> QDialog.DialogCode:
        shown.append(self)
        return result

    monkeypatch.setattr(LegalDialog, "exec", fake_exec)
    return shown


def test_skips_when_already_accepted(qtbot, monkeypatch):
    shown = answer(monkeypatch, QDialog.DialogCode.Rejected)
    settings = GuiSettings(legal_accepted=LEGAL_VERSION)
    assert app.ensure_legal(settings) is True
    assert shown == []


def test_saves_the_acceptance(qtbot, monkeypatch):
    shown = answer(monkeypatch, QDialog.DialogCode.Accepted)
    settings = GuiSettings()
    assert app.ensure_legal(settings) is True
    assert len(shown) == 1
    assert settings.legal_accepted == LEGAL_VERSION
    assert json.loads(settings_path().read_text(encoding="utf-8"))["legal_accepted"] == (
        LEGAL_VERSION
    )


def test_rejection_returns_false_and_saves_nothing(qtbot, monkeypatch):
    answer(monkeypatch, QDialog.DialogCode.Rejected)
    settings = GuiSettings()
    assert app.ensure_legal(settings) is False
    assert settings.legal_accepted == 0 and not settings_path().exists()


def test_a_new_legal_version_asks_again(qtbot, monkeypatch):
    shown = answer(monkeypatch, QDialog.DialogCode.Accepted)
    settings = GuiSettings(legal_accepted=LEGAL_VERSION - 1)
    assert app.ensure_legal(settings) is True
    assert len(shown) == 1 and settings.legal_accepted == LEGAL_VERSION


def test_the_notice_is_the_required_kind(qtbot, monkeypatch):
    shown = answer(monkeypatch, QDialog.DialogCode.Accepted)
    app.ensure_legal(GuiSettings())
    assert hasattr(shown[0], "accept_button")  # modo de aceptación obligatoria


def test_a_failing_save_does_not_block_the_start_but_warns(qtbot, monkeypatch):
    answer(monkeypatch, QDialog.DialogCode.Accepted)
    warned = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warned.append(args))

    def read_only(self, path=None):
        raise OSError("disco de solo lectura")

    monkeypatch.setattr(GuiSettings, "save", read_only)
    assert app.ensure_legal(GuiSettings()) is True
    assert len(warned) == 1 and "disco de solo lectura" in warned[0][2]


def test_main_does_not_create_the_window_or_find_the_cli_when_rejected(qtbot, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("no debía llegar aquí")

    monkeypatch.setattr(app, "ensure_legal", lambda settings: False)
    monkeypatch.setattr(app, "locate_cli", forbidden)
    monkeypatch.setattr(main_window.MainWindow, "__init__", forbidden)
    monkeypatch.setattr(app.QApplication, "exec", forbidden)
    assert app.main(["osineitor-gui"]) == 0

"""`run_in_thread`: el resultado llega a la UI, y se descarta si la aplicación ya se cierra."""

from __future__ import annotations

import os
import threading

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QThreadPool  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from osineitor_gui.ui import worker  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_relay(monkeypatch):
    """Cada test arranca con un relé nuevo: `closing` es estado global del módulo."""
    monkeypatch.setattr(worker, "_relay", None)


def test_the_result_reaches_the_ui_thread(qtbot):
    got = []
    worker.run_in_thread(lambda: 42, got.append, got.append)
    qtbot.waitUntil(lambda: got == [42], timeout=5000)


def test_a_result_that_arrives_after_quit_is_dropped_without_error(qtbot):
    release = threading.Event()
    got, errors = [], []
    worker.run_in_thread(lambda: release.wait(10) and 42, got.append, errors.append)
    QApplication.instance().aboutToQuit.emit()  # la aplicación se cierra con la llamada en curso
    release.set()
    assert QThreadPool.globalInstance().waitForDone(10_000)
    qtbot.wait(200)
    assert got == [] and errors == []
    assert worker._relay.closing

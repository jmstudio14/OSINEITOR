"""`run_in_thread`: el resultado llega a la UI y los hilos nunca tocan objetos de Qt."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import threading
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject  # noqa: E402
from shiboken6 import delete  # noqa: E402

from osineitor_gui.ui import worker  # noqa: E402

SRC = str(Path(worker.__file__).parents[2])
EXIT_WITH_A_CALL_IN_PROGRESS = textwrap.dedent(
    """
    import sys, time
    from PySide6.QtWidgets import QApplication
    from osineitor_gui.ui.worker import run_in_thread

    app = QApplication(sys.argv)
    run_in_thread(lambda: time.sleep(1), print, print)
    """
)


def test_the_result_reaches_the_ui_thread(qtbot):
    got = []
    worker.run_in_thread(lambda: 42, got.append, got.append)
    qtbot.waitUntil(lambda: got == [42], timeout=5000)


def test_leaving_with_a_call_in_progress_does_not_touch_a_deleted_object():
    done = subprocess.run(
        [sys.executable, "-c", EXIT_WITH_A_CALL_IN_PROGRESS],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": SRC},
        timeout=60,
    )
    assert "Signal source has been deleted" not in done.stderr
    assert "Traceback" not in done.stderr


def test_a_worker_thread_only_leaves_the_result_in_the_queue(monkeypatch):
    received = []
    monkeypatch.setattr(worker, "_results", type("Q", (), {"put": received.append})())
    on_result, on_error = print, print
    errors = worker._Task(lambda: 1 / 0, on_result, on_error, None)
    fine = worker._Task(lambda: 42, on_result, on_error, None)
    for task in (fine, errors):
        thread = threading.Thread(target=task.run)  # un hilo sin nada de Qt
        thread.start()
        thread.join()
    assert received[0] == (on_result, 42, None)
    callback, error, parent = received[1]
    assert callback is on_error and isinstance(error, ZeroDivisionError) and parent is None


def test_a_result_for_a_deleted_parent_is_dropped(qtbot):
    release = threading.Event()
    parent = QObject()
    got = []
    done = []
    worker.run_in_thread(lambda: release.wait(10) and 42, got.append, got.append, parent)
    delete(parent)
    release.set()
    worker.run_in_thread(lambda: 1, done.append, done.append)
    qtbot.waitUntil(lambda: done == [1] and worker._pending == 0, timeout=5000)
    assert got == []


def test_a_callback_can_start_another_call(qtbot):
    got = []

    def again(value):
        worker.run_in_thread(lambda: value + 1, got.append, got.append)

    worker.run_in_thread(lambda: 1, again, got.append)
    qtbot.waitUntil(lambda: got == [2], timeout=5000)


def test_the_timer_stops_when_nothing_is_pending(qtbot):
    got = []
    worker.run_in_thread(lambda: 1, got.append, got.append)
    qtbot.waitUntil(lambda: got == [1], timeout=5000)
    qtbot.waitUntil(lambda: not worker._timer.isActive(), timeout=5000)

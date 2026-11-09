"""Ejecuta una llamada bloqueante (p. ej. de `CliApi`) en un hilo y entrega el resultado a la UI.

Los hilos solo dejan el resultado en una cola de Python: un hilo no puede saber si un `QObject`
sigue vivo (al cerrar, Qt puede destruirlo en cualquier momento), así que nunca toca ninguno.
"""

from __future__ import annotations

from collections.abc import Callable
from queue import Empty, SimpleQueue
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer
from shiboken6 import isValid

DRAIN_MS = 10

_results: SimpleQueue = SimpleQueue()
_pending = 0  # llamadas sin entregar; solo se toca desde el hilo de la UI
_timer: QTimer | None = None


class _Task(QRunnable):
    def __init__(self, fn, on_result, on_error, parent) -> None:
        super().__init__()
        self._args = (fn, on_result, on_error, parent)

    def run(self) -> None:
        fn, on_result, on_error, parent = self._args
        try:
            value = fn()
        except Exception as exc:  # se entrega a `on_error`; la UI decide cómo mostrarlo
            _results.put((on_error, exc, parent))
        else:
            _results.put((on_result, value, parent))


def _drain() -> None:
    global _pending
    while True:
        try:
            callback, value, parent = _results.get_nowait()
        except Empty:
            break
        _pending -= 1
        if parent is None or isValid(parent):  # si la ventana ya se cerró, nadie espera el dato
            callback(value)
    if _pending == 0:
        _timer.stop()


def run_in_thread(
    fn: Callable[[], Any],
    on_result: Callable[[Any], None],
    on_error: Callable[[Exception], None],
    parent: QObject | None = None,
) -> None:
    """Llama a `fn()` en el pool de hilos; `on_result`/`on_error` corren en el hilo de la UI.

    Si `parent` ya no existe cuando llega el resultado, se descarta. Debe llamarse desde el hilo
    de la UI.
    """
    global _pending, _timer
    if _timer is None:
        _timer = QTimer()
        _timer.setInterval(DRAIN_MS)
        _timer.timeout.connect(_drain)
    _pending += 1
    _timer.start()
    QThreadPool.globalInstance().start(_Task(fn, on_result, on_error, parent))

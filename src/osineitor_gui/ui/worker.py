"""Ejecuta una llamada bloqueante (p. ej. de `CliApi`) en un hilo y entrega el resultado a la UI."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal
from shiboken6 import isValid


class _Relay(QObject):
    """Un único objeto, del hilo de la UI, que recibe en cola lo que producen los hilos."""

    done = Signal(object, object, object)  # (callback, valor, parent)

    def __init__(self) -> None:
        super().__init__()
        self.done.connect(self._deliver, Qt.ConnectionType.QueuedConnection)

    @staticmethod
    def _deliver(callback: Callable[[Any], None], value: Any, parent: QObject | None) -> None:
        if parent is None or isValid(parent):  # si la ventana ya se cerró, nadie espera el dato
            callback(value)


class _Task(QRunnable):
    def __init__(self, fn, on_result, on_error, parent, relay: _Relay) -> None:
        super().__init__()
        self._args = (fn, on_result, on_error, parent)
        self._relay = relay

    def run(self) -> None:
        fn, on_result, on_error, parent = self._args
        try:
            value = fn()
        except Exception as exc:  # se entrega a `on_error`; la UI decide cómo mostrarlo
            self._relay.done.emit(on_error, exc, parent)
        else:
            self._relay.done.emit(on_result, value, parent)


_relay: _Relay | None = None


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
    global _relay
    if _relay is None:
        _relay = _Relay()
    QThreadPool.globalInstance().start(_Task(fn, on_result, on_error, parent, _relay))

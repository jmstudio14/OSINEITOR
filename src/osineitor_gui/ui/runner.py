"""Adaptador Qt de `CliProcess`: pasa al hilo de la interfaz lo que llega desde hilos de fondo."""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QObject, Signal

from osineitor_gui.process import CliProcess


class ScanRunner(QObject):
    event = Signal(object)  # un osineitor_gui.events.Event
    finished = Signal(int)  # código de salida

    def __init__(self, args: Sequence[str], cli: Sequence[str], parent: QObject | None = None):
        super().__init__(parent)
        # Los callbacks corren en hilos lectores: solo emiten señales (conexión en cola).
        self._proc = CliProcess(args, cli=cli, on_event=self.event.emit, on_exit=self.finished.emit)

    def start(self) -> None:
        self._proc.start()

    def cancel(self) -> None:
        self._proc.cancel()

    def kill(self) -> None:
        self._proc.kill()

    def wait(self, timeout: float | None = None) -> int:
        return self._proc.wait(timeout)

    @property
    def running(self) -> bool:
        return self._proc.running

    @property
    def stderr_tail(self) -> list[str]:
        return self._proc.stderr_tail

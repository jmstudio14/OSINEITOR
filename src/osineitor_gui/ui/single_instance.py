"""Una sola ventana por usuario: la segunda instancia avisa a la primera y termina.

El candado y el nombre del servidor salen de la carpeta de ajustes, así que los tests y `smoke.py`,
que usan su propia carpeta, no chocan con la aplicación que el usuario tenga abierta.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from PySide6.QtCore import QLockFile, QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

CONNECT_TIMEOUT_MS = 1000


class SingleInstance(QObject):
    activated = Signal()  # otra instancia ha pedido que esta se muestre

    def __init__(self, directory: Path, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._directory = directory
        digest = hashlib.sha256(str(directory.resolve()).encode("utf-8")).hexdigest()[:16]
        self._name = f"osineitor-gui-{digest}"
        self._lock: QLockFile | None = None
        self._server: QLocalServer | None = None

    def acquire(self) -> bool:
        """`True` si es la primera instancia, o si no se puede saber: mejor abrir que negarse."""
        try:
            self._directory.mkdir(parents=True, exist_ok=True)
        except OSError:
            return True
        lock = QLockFile(str(self._directory / "instance.lock"))
        lock.setStaleLockTime(0)  # un candado de un proceso que ya no existe no bloquea nunca
        if not lock.tryLock(0):
            if lock.error() == QLockFile.LockError.LockFailedError:
                self._notify_first()
                return False
            return True
        self._lock = lock
        QLocalServer.removeServer(self._name)  # el de una ejecución anterior que acabó mal
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._on_connection)
        self._server.listen(self._name)
        return True

    def _notify_first(self) -> None:
        socket = QLocalSocket()
        socket.connectToServer(self._name)
        if socket.waitForConnected(CONNECT_TIMEOUT_MS):
            socket.disconnectFromServer()

    def _on_connection(self) -> None:
        connection = self._server.nextPendingConnection()
        if connection is not None:
            connection.disconnected.connect(connection.deleteLater)
        self.activated.emit()

    def release(self) -> None:
        if self._server is not None:
            self._server.close()
            self._server = None
        if self._lock is not None:
            self._lock.unlock()
            self._lock = None

"""Canal de control por stdin: permite a otro programa cancelar un scan de forma ordenada.

En Windows, `QProcess.terminate()` no detiene una aplicación de consola, y matarla perdería el
resultado parcial. Por eso el cliente escribe `{"cmd": "cancel"}` en stdin. Si stdin se cierra
(el cliente murió), también se cancela.
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
from collections.abc import Callable


def parse_command(line: bytes) -> str | None:
    """`cmd` de una línea de control, o `None` si no es un comando válido."""
    try:
        message = json.loads(line)
    except ValueError:
        return None
    if isinstance(message, dict) and isinstance(message.get("cmd"), str):
        return message["cmd"]
    return None


def watch_stdin(on_cancel: Callable[[], None], fd: int = 0) -> None:
    """Lanza un hilo que llama a `on_cancel` en el bucle actual al recibir `cancel` o EOF.

    Lee del descriptor con `os.read` y no con `sys.stdin`: un hilo bloqueado en el lector con
    búfer puede abortar el intérprete al salir (`_enter_buffered_busy`), y `os.read` no.
    El hilo es demonio: si el scan acaba sin que el cliente escriba, no impide salir.
    """
    loop = asyncio.get_running_loop()

    def reader() -> None:
        pending = b""
        while True:
            try:
                chunk = os.read(fd, 4096)
            except OSError:
                chunk = b""
            if not chunk:  # EOF: el cliente cerró stdin o murió
                loop.call_soon_threadsafe(on_cancel)
                return
            pending += chunk
            *lines, pending = pending.split(b"\n")
            for line in lines:
                if parse_command(line) == "cancel":
                    loop.call_soon_threadsafe(on_cancel)
                    return

    threading.Thread(target=reader, name="osineitor-control", daemon=True).start()

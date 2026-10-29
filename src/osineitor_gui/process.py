"""Lanza la CLI como proceso hijo y entrega sus eventos NDJSON.

Es Python puro (`subprocess` + hilos) y no `QProcess`: así se prueba entero sin Qt y se comporta
igual en la CI. Los callbacks se invocan **desde hilos lectores**: la interfaz debe pasarlos a su
hilo (en Qt, emitiendo una señal desde el callback).
"""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import threading
from collections import deque
from collections.abc import Callable, Mapping, Sequence

from osineitor_gui.cli_locator import locate_cli
from osineitor_gui.events import Event, parse_event

STDERR_LINES = 200
KILL_AFTER_TERMINATE = 5.0


def child_env(extra: Mapping[str, str] | None = None) -> dict[str, str]:
    """Entorno del hijo: UTF-8 en todas partes (si no, Windows usa cp1252) y sin colores."""
    env = dict(os.environ)
    env.update({"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", "NO_COLOR": "1"})
    if extra:
        env.update(extra)
    return env


def popen_flags() -> int:
    """En Windows, sin ventana de consola (si no, parpadea una al lanzar cada orden)."""
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


class CliProcess:
    def __init__(
        self,
        args: Sequence[str],
        *,
        cli: Sequence[str] | None = None,
        on_event: Callable[[Event], None] | None = None,
        on_stderr: Callable[[str], None] | None = None,
        on_exit: Callable[[int], None] | None = None,
        env: Mapping[str, str] | None = None,
    ) -> None:
        self._command = [*(cli if cli is not None else locate_cli()), *args]
        self._on_event = on_event
        self._on_stderr = on_stderr
        self._on_exit = on_exit
        self._env = child_env(env)
        self._proc: subprocess.Popen[bytes] | None = None
        self._threads: list[threading.Thread] = []
        self._stderr_tail: deque[str] = deque(maxlen=STDERR_LINES)
        self._cancel_requested = threading.Event()
        self._exited = threading.Event()
        self.callback_errors: list[BaseException] = []

    @property
    def command(self) -> list[str]:
        return list(self._command)

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    @property
    def returncode(self) -> int | None:
        return None if self._proc is None else self._proc.returncode

    @property
    def stderr_tail(self) -> list[str]:
        return list(self._stderr_tail)

    def start(self) -> None:
        if self._proc is not None:
            raise RuntimeError("el proceso ya se lanzó")
        self._proc = subprocess.Popen(
            self._command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=self._env,
            creationflags=popen_flags(),
        )
        readers = [
            threading.Thread(target=self._read_stdout, name="osineitor-stdout", daemon=True),
            threading.Thread(target=self._read_stderr, name="osineitor-stderr", daemon=True),
        ]
        for thread in readers:
            thread.start()
        waiter = threading.Thread(
            target=self._wait_and_notify, args=(readers,), name="osineitor-wait", daemon=True
        )
        waiter.start()
        self._threads = [*readers, waiter]

    def _call(self, callback, *args) -> None:
        if callback is None:
            return
        try:
            callback(*args)
        except Exception as exc:  # un fallo de la interfaz no debe matar al lector
            self.callback_errors.append(exc)

    def _read_stdout(self) -> None:
        for raw in self._proc.stdout:
            if (event := parse_event(raw)) is not None:
                self._call(self._on_event, event)

    def _read_stderr(self) -> None:
        for raw in self._proc.stderr:
            text = raw.decode("utf-8", errors="replace").rstrip("\r\n")
            self._stderr_tail.append(text)
            self._call(self._on_stderr, text)

    def _wait_and_notify(self, readers: list[threading.Thread]) -> None:
        code = self._proc.wait()
        for thread in readers:  # todos los eventos se entregan antes de avisar de la salida
            thread.join()
        for stream in (self._proc.stdin, self._proc.stdout, self._proc.stderr):
            with contextlib.suppress(OSError, ValueError):
                stream.close()
        self._exited.set()
        self._call(self._on_exit, code)

    def cancel(self, grace: float = 15.0) -> None:
        """Pide cancelar de forma ordenada (se guarda lo ya obtenido).

        Si el proceso no sale en `grace` segundos se le termina y, si aun así sigue, se mata:
        entonces no se guarda nada. Se puede llamar varias veces.
        """
        if not self.running or self._cancel_requested.is_set():
            return
        self._cancel_requested.set()
        with contextlib.suppress(OSError, ValueError):  # la CLI ya salió o cerró stdin
            self._proc.stdin.write(json.dumps({"cmd": "cancel"}).encode() + b"\n")
            self._proc.stdin.flush()
        threading.Thread(
            target=self._escalate, args=(grace,), name="osineitor-escalate", daemon=True
        ).start()

    def _escalate(self, grace: float) -> None:
        if self._exited.wait(grace):
            return
        self._proc.terminate()
        if not self._exited.wait(KILL_AFTER_TERMINATE):
            self._proc.kill()

    def kill(self) -> None:
        if self.running:
            self._proc.kill()

    def wait(self, timeout: float | None = None) -> int:
        """Espera a que el proceso salga y a que se hayan entregado todos sus eventos."""
        if not self._exited.wait(timeout):
            raise TimeoutError("la CLI no terminó a tiempo")
        return self._proc.returncode

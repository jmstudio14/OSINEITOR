"""CliProcess contra la CLI real (con módulos falsos): eventos, salida, cancelación y escalada."""

from __future__ import annotations

import threading
import time

import pytest

from osineitor_gui.cli_locator import CliNotFound, locate_cli
from osineitor_gui.events import (
    EXIT_CANCELLED,
    EXIT_MODULE_ERRORS,
    EXIT_OK,
    EntityFound,
    ModuleEnd,
    ScanEnd,
)
from osineitor_gui.process import CliProcess, child_env, popen_flags
from osineitor_gui.scan_request import ScanRequest
from osineitor_gui.session import ScanSession
from tests.gui.fakecli import CLI, DEAF, driver_env


class Recorder:
    def __init__(self):
        self.events, self.stderr, self.exits = [], [], []
        self.lock = threading.Lock()

    def on_event(self, event):
        self.events.append(event)

    def on_stderr(self, text):
        self.stderr.append(text)

    def on_exit(self, code):
        # Cuando se avisa de la salida ya se entregaron todos los eventos.
        self.exits.append((code, len(self.events)))


def launch(args, modules="fast", cli=CLI, **kwargs):
    rec = Recorder()
    proc = CliProcess(
        args,
        cli=cli,
        env=driver_env(modules),
        on_event=rec.on_event,
        on_stderr=rec.on_stderr,
        on_exit=rec.on_exit,
        **kwargs,
    )
    proc.start()
    return proc, rec


def wait_for(predicate, timeout=30.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("no ocurrió a tiempo")


def request(**kwargs) -> list[str]:
    return ScanRequest(target="example.com", kind="domain", no_save=True, **kwargs).to_args()


def test_scan_delivers_events_in_order_then_the_exit():
    proc, rec = launch(request())
    assert proc.wait(30) == EXIT_OK
    kinds = [type(e).__name__ for e in rec.events]
    assert kinds[0] in ("Notice", "ScanStart") and kinds[-1] == "ScanEnd"
    assert any(isinstance(e, EntityFound) and e.entity["value"] == "9.9.9.9" for e in rec.events)
    assert rec.events[-1].exit_code == 0
    # on_exit llegó después de todos los eventos, no antes.
    assert rec.exits == [(EXIT_OK, len(rec.events))]
    assert proc.callback_errors == []


def test_non_ascii_survives_the_pipe():
    proc, rec = launch(request())
    proc.wait(30)
    entity = next(e.entity for e in rec.events if isinstance(e, EntityFound))
    assert entity["data"]["org"] == "ACMÉ ñ"


def test_module_errors_exit_code_and_session_state():
    proc, rec = launch(request(), modules="fast,bad")
    session = ScanSession()
    session.begin()
    assert proc.wait(30) == EXIT_MODULE_ERRORS
    for event in rec.events:
        session.feed(event)
    assert session.state == "complete" and session.exit_code == EXIT_MODULE_ERRORS
    assert session.modules["bad"].status == "error"
    assert session.modules["bad"].message == "se rompió"
    assert session.modules["fast"].status == "ok"


def test_cancel_via_stdin_keeps_partial_result_and_exits_130(tmp_path):
    args = ScanRequest(target="example.com", kind="domain").to_args()  # se guarda
    proc, rec = launch(args, modules="fast,hang")
    wait_for(lambda: any(isinstance(e, ModuleEnd) and e.module == "fast" for e in rec.events))
    proc.cancel()
    assert proc.wait(30) == EXIT_CANCELLED
    end = rec.events[-1]
    assert isinstance(end, ScanEnd) and end.status == "cancelled" and end.scan_id == 1
    # Cancelar dos veces no hace nada raro.
    proc.cancel()


def test_cancel_escalates_to_terminate_when_the_child_ignores_it():
    rec = Recorder()
    proc = CliProcess([], cli=DEAF, on_exit=rec.on_exit)
    proc.start()
    assert proc.running
    started = time.monotonic()
    proc.cancel(grace=0.3)  # DEAF ignora stdin: tras la gracia se le termina
    code = proc.wait(30)
    assert time.monotonic() - started < 20
    assert code != 0 and not proc.running


def test_kill():
    proc = CliProcess([], cli=DEAF)
    proc.start()
    proc.kill()
    assert proc.wait(30) != 0


def test_stderr_is_captured_and_usage_error_exits_2():
    proc, rec = launch(["domain", "--depth", "99", "--", "example.com"])
    assert proc.wait(30) == 2
    assert proc.stderr_tail  # el motivo del error, para mostrárselo al usuario
    assert rec.stderr == proc.stderr_tail


def test_stdin_left_open_does_not_hang_a_finished_scan():
    proc, _ = launch(request())
    assert proc.wait(30) == EXIT_OK  # nadie cierra stdin: el proceso termina igualmente


def test_a_failing_callback_does_not_break_the_stream():
    seen = []

    def bad(event):
        seen.append(event)
        raise RuntimeError("la interfaz falló")

    proc = CliProcess(request(), cli=CLI, env=driver_env("fast"), on_event=bad)
    proc.start()
    assert proc.wait(30) == EXIT_OK
    assert isinstance(seen[-1], ScanEnd)  # siguió leyendo tras el primer fallo
    assert len(proc.callback_errors) == len(seen)


def test_cannot_start_twice():
    proc = CliProcess(["version"], cli=CLI, env=driver_env("fast"))
    proc.start()
    with pytest.raises(RuntimeError):
        proc.start()
    proc.wait(30)


def test_child_environment_forces_utf8_and_flags(monkeypatch):
    env = child_env({"X": "1"})
    assert env["PYTHONUTF8"] == "1" and env["PYTHONIOENCODING"] == "utf-8" and env["X"] == "1"
    import subprocess
    import sys

    expected = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    assert popen_flags() == expected


def test_locator_prefers_packaged_exe_then_module_then_path(tmp_path):
    exe = tmp_path / "OSINEITOR.exe"
    sibling = tmp_path / ("osineitor.exe")
    sibling.write_text("x")
    import os

    if os.name != "nt":
        sibling.rename(tmp_path / "osineitor")
    assert locate_cli(frozen=True, executable=str(exe))[0].startswith(str(tmp_path))
    assert locate_cli(frozen=False, executable="/py")[:2] == ["/py", "-m"]
    # Empaquetado pero sin el ejecutable de la CLI junto al de la aplicación: cae al PATH.
    assert locate_cli(
        frozen=True,
        executable=str(tmp_path / "otra" / "x.exe"),
        which=lambda name: "/bin/osineitor",
    ) == ["/bin/osineitor"]
    with pytest.raises(CliNotFound, match="No se encuentra"):
        locate_cli(frozen=True, executable=str(tmp_path / "otra" / "x.exe"), which=lambda n: None)


def test_missing_cli_command_fails_loudly():
    proc = CliProcess([], cli=["/no/existe/osineitor"])
    with pytest.raises(OSError):
        proc.start()

"""Órdenes de la CLI con salida `--json`, para llamar desde un hilo de trabajo (son síncronas)."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Sequence
from typing import Any

from osineitor_gui.cli_locator import locate_cli
from osineitor_gui.events import EXIT_MODULE_ERRORS, EXIT_OK
from osineitor_gui.process import child_env, popen_flags


class CliError(Exception):
    """La CLI terminó con un código inesperado o con una salida que no es JSON."""

    def __init__(self, message: str, exit_code: int | None = None, stderr: str = "") -> None:
        super().__init__(message)
        self.exit_code = exit_code
        self.stderr = stderr


class CliApi:
    def __init__(self, cli: Sequence[str] | None = None, timeout: float = 60.0) -> None:
        self._cli = list(cli) if cli is not None else None
        self.timeout = timeout

    def _command(self) -> list[str]:
        return self._cli if self._cli is not None else locate_cli()

    def run(
        self,
        args: Sequence[str],
        *,
        stdin_text: str | None = None,
        ok_codes: Sequence[int] = (EXIT_OK,),
        timeout: float | None = None,
    ) -> Any:
        """Ejecuta una orden `--json` y devuelve el JSON. Código no admitido → `CliError`."""
        try:
            done = subprocess.run(
                [*self._command(), *args],
                input=None if stdin_text is None else stdin_text.encode("utf-8"),
                capture_output=True,
                env=child_env(),
                creationflags=popen_flags(),
                timeout=timeout or self.timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise CliError(f"la CLI no respondió en {exc.timeout:g} s") from exc
        stderr = done.stderr.decode("utf-8", errors="replace").strip()
        if done.returncode not in ok_codes:
            raise CliError(
                stderr or f"la CLI terminó con código {done.returncode}", done.returncode, stderr
            )
        try:
            return json.loads(done.stdout.decode("utf-8", errors="replace"))
        except ValueError as exc:
            raise CliError("la CLI no devolvió JSON válido", done.returncode, stderr) from exc

    def version(self) -> str:
        return self.run(["version", "--json"])["version"]

    def modules(self) -> list[dict[str, Any]]:
        return self.run(["modules", "--json"])

    def history(self, limit: int = 50) -> list[dict[str, Any]]:
        return self.run(["history", "--json", "--limit", str(limit)])

    def show(self, scan_id: int) -> dict[str, Any]:
        return self.run(["show", str(scan_id), "--json"])

    def doctor(
        self, modules: Sequence[str] = (), *, active: bool = False, timeout: float = 300.0
    ) -> list[dict[str, Any]]:
        """Estado de salud de los módulos. Que alguno falle (código 3) no es un error de la CLI."""
        args = ["doctor", "--json"]
        for name in modules:
            args += ["-m", name]
        if active:
            args.append("--active")
        return self.run(args, ok_codes=(EXIT_OK, EXIT_MODULE_ERRORS), timeout=timeout)

    def config_show(self) -> dict[str, Any]:
        return self.run(["config", "show", "--json"])

    def config_set(self, name: str, value: str) -> dict[str, Any]:
        """Guarda una API key. El valor viaja por stdin, no por la línea de comandos."""
        return self.run(["config", "set", name, "--stdin", "--json"], stdin_text=value)

    def config_unset(self, name: str) -> dict[str, Any]:
        return self.run(["config", "unset", name, "--json"])

    def export(self, scan_id: int, fmt: str, output: str) -> dict[str, Any]:
        return self.run(["export", str(scan_id), "-f", fmt, "-o", output, "--json"])

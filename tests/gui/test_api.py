"""CliApi contra la CLI real (con módulos falsos)."""

from __future__ import annotations

import pytest

from osineitor_gui.api import CliApi, CliError
from osineitor_gui.process import CliProcess
from tests.gui.fakecli import CLI, driver_env, use_modules
from tests.test_contract import validate


@pytest.fixture
def api(monkeypatch):
    use_modules(monkeypatch, "fast,bad")
    return CliApi(cli=CLI)


def test_every_json_command_returns_what_the_schema_describes(api, tmp_path):
    from osineitor import __version__

    assert api.version() == __version__
    modules = api.modules()
    validate("modules_output", modules)
    assert {m["name"] for m in modules} == {"fast", "bad"}

    proc = CliProcess(
        ["domain", "--ndjson", "--", "example.com"], cli=CLI, env=driver_env("fast,bad")
    )
    proc.start()
    proc.wait(30)
    history = api.history()
    validate("history_output", history)
    scan = api.show(history[0]["id"])
    validate("scan_result", scan)
    assert scan["status"] == "complete"

    exported = api.export(history[0]["id"], "json", str(tmp_path / "r.json"))
    validate("export_output", exported)
    assert (tmp_path / "r.json").exists()
    validate("config_show_output", api.config_show())


def test_doctor_failures_are_data_not_errors(api):
    checks = api.doctor()
    validate("doctor_output", checks)
    # `bad` no tiene canario ni probe_url: el módulo falso queda sin prueba, sin error de la CLI.
    assert {c["module"] for c in checks} == {"fast", "bad"}


def test_config_set_goes_through_stdin_not_the_command_line(api, monkeypatch):
    seen = {}
    import subprocess

    real = subprocess.run

    def spy(cmd, **kwargs):
        seen["cmd"], seen["input"] = cmd, kwargs.get("input")
        return real(cmd, **kwargs)

    monkeypatch.setattr(subprocess, "run", spy)
    assert api.config_set("Shodan", "TOP-SECRET-KEY") == {"name": "shodan", "configured": True}
    assert not any("TOP-SECRET-KEY" in part for part in seen["cmd"])  # no sale en argv
    assert seen["input"] == b"TOP-SECRET-KEY"
    assert [k["name"] for k in api.config_show()["keys"]] == ["shodan"]
    assert api.config_unset("shodan") == {"name": "shodan", "configured": False}
    assert api.config_show()["keys"] == []


def test_usage_errors_become_cli_error_with_the_reason(api):
    with pytest.raises(CliError) as err:
        api.show(999)
    assert err.value.exit_code == 2 and "999" in err.value.stderr


def test_non_json_output_is_reported(monkeypatch):
    bad = CliApi(cli=["python", "-c", "print('hola')"])
    import sys

    bad = CliApi(cli=[sys.executable, "-c", "print('hola')"])
    with pytest.raises(CliError, match="JSON"):
        bad.run([])


def test_timeout_is_reported():
    import sys

    slow = CliApi(cli=[sys.executable, "-c", "import time; time.sleep(30)"], timeout=0.3)
    with pytest.raises(CliError, match="no respondió"):
        slow.run([])

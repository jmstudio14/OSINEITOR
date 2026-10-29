"""Registro estructurado (F1.9): formato JSON y, sobre todo, que las API keys no se filtren."""

from __future__ import annotations

import json
import logging
import sys

import httpx
import pytest
import respx
from typer.testing import CliRunner

from osineitor import logs
from osineitor.cli import app
from osineitor.config import Config
from osineitor.http import HttpClient
from osineitor.models import EntityType
from tests.test_cli import fake_module, use_modules

runner = CliRunner()
SECRET = "ZZZ-SECRET-123"


@pytest.fixture(autouse=True)
def clean_logging():
    yield
    logs.close()


def read_log(path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_redact_url_drops_credentials_query_and_fragment():
    assert logs.redact_url("https://u:p@api.test:8443/v1/h?key=S&x=1#frag") == (
        "https://api.test:8443/v1/h"
    )
    assert logs.redact_url("https://api.test?key=S") == "https://api.test"
    assert logs.redact_url("relativa/ruta?key=S") == "relativa/ruta"


def test_formatter_writes_one_json_object_with_fields():
    record = logging.LogRecord("osineitor.http", logging.INFO, "f", 1, "http", None, None)
    record.fields = {"status": 200, "url": "https://x.test/"}
    data = json.loads(logs.JsonFormatter([]).format(record))
    assert data["level"] == "INFO" and data["logger"] == "osineitor.http" and data["msg"] == "http"
    assert data["status"] == 200 and data["ts"].endswith("+00:00")


def test_formatter_masks_secrets_in_message_fields_nested_values_and_exceptions():
    try:
        raise ValueError(f"fallo con {SECRET}")
    except ValueError:
        exc_info = sys.exc_info()
    record = logging.LogRecord("osineitor", logging.ERROR, "f", 1, f"msg {SECRET}", None, exc_info)
    record.fields = {"a": SECRET, "b": {SECRET: [f"x{SECRET}"]}}
    text = logs.JsonFormatter([SECRET]).format(record)
    assert SECRET not in text
    assert text.count(logs.MASK) >= 5


def test_known_secrets_come_from_config_file_and_environment(monkeypatch):
    Config(keys={"shodan": "FILE-KEY-1", "x": "abc"}).save()  # "abc": demasiado corta
    monkeypatch.setenv("OSINEITOR_HUNTER_KEY", "ENV-KEY-22")
    assert logs.known_secrets() == ["ENV-KEY-22", "FILE-KEY-1"]  # largas primero, luego orden fijo


def test_nothing_is_written_without_flags(capfd):
    logs.setup(False, None)
    logging.getLogger("osineitor.http").warning("no debe verse")
    assert capfd.readouterr() == ("", "")


@respx.mock
async def test_http_log_has_host_and_path_but_never_query_or_headers(tmp_path):
    respx.get("https://x.test/p").mock(return_value=httpx.Response(200, text="ok"))
    log_file = tmp_path / "o.jsonl"
    logs.setup(False, log_file)
    async with HttpClient(Config(keys={})) as http:
        await http.get("https://x.test/p", params={"key": SECRET}, headers={"hibp-api-key": SECRET})
        await http.get(f"https://x.test/p?token={SECRET}#{SECRET}")
    logs.close()
    text = log_file.read_text(encoding="utf-8")
    assert SECRET not in text
    entries = [e for e in read_log(log_file) if e["msg"] == "http"]
    assert [e["url"] for e in entries] == ["https://x.test/p", "https://x.test/p"]
    assert entries[0]["status"] == 200 and entries[0]["method"] == "GET"


@respx.mock
async def test_transport_errors_log_only_the_exception_name(tmp_path):
    respx.get("https://x.test/p").mock(side_effect=httpx.ConnectError(f"no conecta {SECRET}"))
    log_file = tmp_path / "o.jsonl"
    logs.setup(False, log_file)
    async with HttpClient(Config(keys={}), retries=1, backoff=0) as http:
        with pytest.raises(httpx.ConnectError):
            await http.get("https://x.test/p")
    logs.close()
    errors = [e for e in read_log(log_file) if e["msg"] == "http.error"]
    assert [e["error"] for e in errors] == ["ConnectError", "ConnectError"]
    assert SECRET not in log_file.read_text(encoding="utf-8")


def test_cli_log_file_records_the_scan_and_masks_keys(monkeypatch, tmp_path):
    Config(keys={"shodan": SECRET}).save()
    mods = [
        fake_module("fake_dns", {EntityType.DOMAIN}, EntityType.IP, "9.9.9.9"),
        fake_module("fake_bad", {EntityType.DOMAIN}, EntityType.IP, "x", error=f"mal {SECRET}"),
    ]
    use_modules(monkeypatch, mods)
    log_file = tmp_path / "scan.jsonl"
    result = runner.invoke(
        app, ["--log-file", str(log_file), "domain", "example.com", "--no-save", "--json"]
    )
    assert result.exit_code == 3  # fake_bad falló
    entries = read_log(log_file)
    assert [e["msg"] for e in entries if e["logger"] == "osineitor.engine"][:1] == ["scan.start"]
    ends = {e["module"]: e for e in entries if e["msg"] == "module.end"}
    assert ends["fake_dns"]["status"] == "ok" and ends["fake_bad"]["status"] == "error"
    assert ends["fake_bad"]["level"] == "WARNING"
    assert entries[-1]["msg"] == "scan.end"
    assert SECRET not in log_file.read_text(encoding="utf-8")
    assert json.loads(result.stdout)["target"]["value"] == "example.com"  # stdout intacto


def test_cli_verbose_logs_json_to_stderr_and_keeps_stdout_clean(monkeypatch):
    use_modules(
        monkeypatch, [fake_module("fake_dns", {EntityType.DOMAIN}, EntityType.IP, "9.9.9.9")]
    )
    result = runner.invoke(app, ["-v", "domain", "example.com", "--no-save", "--json"])
    assert result.exit_code == 0
    json.loads(result.stdout)  # un único documento: los registros no se mezclan
    lines = [json.loads(line) for line in result.stderr.splitlines()]
    assert {"scan.start", "module.end", "scan.end"} <= {e["msg"] for e in lines}


def test_cli_without_flags_adds_nothing_to_stderr(monkeypatch):
    use_modules(
        monkeypatch, [fake_module("fake_dns", {EntityType.DOMAIN}, EntityType.IP, "9.9.9.9")]
    )
    result = runner.invoke(app, ["domain", "example.com", "--no-save", "--json"])
    assert result.stderr == ""


def test_cli_rejects_an_unwritable_log_path(tmp_path):
    result = runner.invoke(
        app, ["--log-file", str(tmp_path / "no" / "existe" / "x.log"), "version"]
    )
    assert result.exit_code == 2
    assert "fichero de registro" in result.output

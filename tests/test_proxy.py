"""`--proxy` (F1.8): todo el tráfico sale por el proxy y no se filtra ningún DNS local."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

import osineitor
from osineitor import cli, logs, netguard
from osineitor.cli import app
from osineitor.config import Config
from osineitor.engine import Engine
from osineitor.errors import NetworkGuardError
from osineitor.http import HttpClient, validate_proxy
from osineitor.models import Entity, EntityType
from osineitor.modules.base import Context
from tests.test_cli import fake_module, use_modules

runner = CliRunner()
PASSWORD = "PWD-12345-XYZ"


@pytest.fixture(autouse=True)
def clean_logging():
    yield
    logs.close()


class FakeSocks5:
    """Proxy SOCKS5 mínimo: anota a qué host (por nombre) se le pide conectar y responde 200."""

    def __init__(self) -> None:
        self.requests: list[tuple[str, int]] = []
        self._server: asyncio.Server | None = None

    async def __aenter__(self) -> FakeSocks5:
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        return self

    async def __aexit__(self, *exc: object) -> None:
        self._server.close()
        await self._server.wait_closed()

    @property
    def url(self) -> str:
        return f"socks5://127.0.0.1:{self._server.sockets[0].getsockname()[1]}"

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            _, count = await reader.readexactly(2)
            await reader.readexactly(count)
            writer.write(b"\x05\x00")  # sin autenticación
            _, _, _, atyp = await reader.readexactly(4)
            assert atyp == 3, "el nombre debe viajar al proxy, no resolverse antes"
            host = (await reader.readexactly((await reader.readexactly(1))[0])).decode()
            port = int.from_bytes(await reader.readexactly(2), "big")
            self.requests.append((host, port))
            writer.write(b"\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00")
            await reader.readuntil(b"\r\n\r\n")
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok")
            await writer.drain()
        finally:
            writer.close()


async def test_requests_go_through_the_proxy_without_resolving_names_locally(monkeypatch):
    async def forbidden(host: str) -> list[str]:
        raise AssertionError(f"DNS local de {host}: fuga con proxy")

    monkeypatch.setattr(netguard, "resolve_host", forbidden)
    async with FakeSocks5() as socks, HttpClient(Config(keys={}), proxy=socks.url) as http:
        response = await http.get("http://objetivo.test/ruta")
    assert (response.status_code, response.text) == (200, "ok")
    assert socks.requests == [("objetivo.test", 80)]


async def test_private_ip_literals_stay_blocked_with_a_proxy():
    async with HttpClient(Config(keys={}), proxy="socks5://127.0.0.1:9") as http:
        with pytest.raises(NetworkGuardError):
            await http.get("http://127.0.0.1/")
        with pytest.raises(NetworkGuardError):
            await http.get("http://169.254.169.254/latest/meta-data")


async def test_without_a_proxy_names_are_still_resolved_by_the_guard(monkeypatch):
    seen: list[str] = []

    async def private(host: str) -> list[str]:
        seen.append(host)
        return ["10.0.0.5"]

    monkeypatch.setattr(netguard, "resolve_host", private)
    async with HttpClient(Config(keys={})) as http:
        with pytest.raises(NetworkGuardError):
            await http.get("http://interno.test/")
    assert seen == ["interno.test"]


@pytest.mark.parametrize(
    "value",
    ["socks5://127.0.0.1:9050", "socks5h://tor:9150", "http://proxy:8080", "socks5://u:p@h:1"],
)
def test_validate_proxy_accepts_supported_schemes(value):
    assert validate_proxy(f"  {value} ") == value


@pytest.mark.parametrize("value", ["ftp://host:1", "127.0.0.1:9050", "socks5://", ""])
def test_validate_proxy_rejects_everything_else(value):
    with pytest.raises(ValueError):
        validate_proxy(value)


def _engine(proxy: str | None) -> Engine:
    plain = fake_module("plain", {EntityType.DOMAIN}, EntityType.IP, "9.9.9.9")
    direct = type(
        "Direct",
        (fake_module("direct", {EntityType.DOMAIN}, EntityType.IP, "8.8.8.8"),),
        {"direct_dns": True},
    )
    http = HttpClient(Config(keys={}), proxy=proxy)
    return Engine(Context(config=Config(keys={}), http=http), [plain, direct])


@pytest.mark.parametrize("proxy, ran", [(None, {"plain", "direct"}), ("socks5://h:9", {"plain"})])
async def test_engine_skips_direct_dns_modules_only_when_there_is_a_proxy(proxy, ran):
    engine = _engine(proxy)
    result = await engine.run(Entity(type=EntityType.DOMAIN, value="example.com"))
    assert {r.module for r in result.runs if r.status == "ok"} == ran
    skipped = {r.module: r.message for r in result.runs if r.status == "skipped"}
    if proxy:
        assert "no se enruta por --proxy" in skipped["direct"]
    else:
        assert not skipped


def test_every_module_using_the_system_resolver_declares_direct_dns():
    root = Path(osineitor.__file__).parent / "modules"
    users = [p for p in root.rglob("*.py") if "self.ctx.resolver" in p.read_text(encoding="utf-8")]
    assert users, "el test debe encontrar al menos dns y email_validate"
    for path in users:
        assert "direct_dns = True" in path.read_text(encoding="utf-8"), path.name


@pytest.fixture
def spy(monkeypatch):
    captured: dict = {}

    class Spy(HttpClient):
        def __init__(self, *args, **kwargs):
            captured.update(kwargs)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(cli, "HttpClient", Spy)
    use_modules(
        monkeypatch, [fake_module("fake_dns", {EntityType.DOMAIN}, EntityType.IP, "9.9.9.9")]
    )
    return captured


def test_cli_passes_the_proxy_to_the_http_client(spy):
    args = ["domain", "example.com", "--no-save", "--json", "--proxy", "socks5://127.0.0.1:9050"]
    assert runner.invoke(app, args).exit_code == 0
    assert spy["proxy"] == "socks5://127.0.0.1:9050"


def test_cli_reads_the_proxy_from_the_environment(spy, monkeypatch):
    monkeypatch.setenv("OSINEITOR_PROXY", "socks5://127.0.0.1:9150")
    assert runner.invoke(app, ["domain", "example.com", "--no-save", "--json"]).exit_code == 0
    assert spy["proxy"] == "socks5://127.0.0.1:9150"


def test_cli_without_proxy_does_not_set_one(spy):
    assert runner.invoke(app, ["domain", "example.com", "--no-save", "--json"]).exit_code == 0
    assert spy["proxy"] is None


@pytest.mark.parametrize("value", ["ftp://x:1", "no-es-una-url", "socks5://"])
def test_cli_rejects_an_invalid_proxy_as_a_usage_error(spy, value):
    result = runner.invoke(app, ["domain", "example.com", "--no-save", "--proxy", value])
    assert result.exit_code == 2


def test_doctor_passes_the_proxy(monkeypatch):
    captured: dict = {}

    async def fake(config, classes, **kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(cli, "run_doctor", fake)
    assert runner.invoke(app, ["doctor", "--proxy", "http://p:8080"]).exit_code == 0
    assert captured["proxy"] == "http://p:8080"


def test_proxy_password_never_reaches_the_log(spy, monkeypatch, tmp_path):
    bad = fake_module("fake_bad", {EntityType.DOMAIN}, EntityType.IP, "x", error=f"mal {PASSWORD}")
    use_modules(monkeypatch, [bad])
    log_file = tmp_path / "o.jsonl"
    args = ["--log-file", str(log_file), "domain", "example.com", "--no-save", "--json"]
    result = runner.invoke(app, [*args, "--proxy", f"socks5://usuario:{PASSWORD}@127.0.0.1:9050"])
    assert result.exit_code == 3
    text = log_file.read_text(encoding="utf-8")
    assert PASSWORD not in text
    start = next(json.loads(line) for line in text.splitlines() if "scan.start" in line)
    assert start["proxy"] == "socks5://127.0.0.1:9050"


def test_proxy_password_from_the_environment_is_masked(monkeypatch):
    monkeypatch.setenv("OSINEITOR_PROXY", f"socks5://u:{PASSWORD}@h:1")
    assert PASSWORD in logs.known_secrets()
    monkeypatch.setenv("OSINEITOR_PROXY", "esto no es una url ::")
    assert logs.known_secrets() == []

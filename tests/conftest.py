from __future__ import annotations

import pytest

from osineitor import netguard
from osineitor.config import Config
from osineitor.http import HttpClient
from osineitor.modules.base import Context
from osineitor.storage import Storage


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    # Estas variables mandan en todos los sistemas (en Windows se ignora XDG).
    monkeypatch.setenv("OSINEITOR_CONFIG_DIR", str(tmp_path / "config" / "osineitor"))
    monkeypatch.setenv("OSINEITOR_DATA_DIR", str(tmp_path / "data" / "osineitor"))
    for name in ("SHODAN", "ABUSEIPDB", "GREYNOISE", "HIBP", "HUNTER", "IPINFO"):
        monkeypatch.delenv(f"OSINEITOR_{name}_KEY", raising=False)


@pytest.fixture(autouse=True)
def public_dns(monkeypatch):
    """Los tests no hacen DNS real: todo host resuelve a una IP pública."""

    async def resolve(host: str) -> list[str]:
        return ["93.184.216.34"]

    monkeypatch.setattr(netguard, "resolve_host", resolve)


@pytest.fixture
def config():
    return Config(keys={})


@pytest.fixture
async def ctx(config):
    http = HttpClient(config, backoff=0)
    yield Context(config=config, http=http)
    await http.aclose()


class FakeRdata:
    def __init__(self, text: str):
        self._text = text
        self.strings = [text.encode()]
        self.exchange = self

    def to_text(self) -> str:
        return self._text


class FakeResolver:
    """Resolver DNS en memoria: {(nombre, tipo): [valores]}."""

    def __init__(self, records: dict[tuple[str, str], list[str]]):
        self.records = records

    async def resolve(self, name, rtype, lifetime=None):
        import dns.resolver

        values = self.records.get((name, rtype))
        if not values:
            raise dns.resolver.NoAnswer()
        return [FakeRdata(v) for v in values]


@pytest.fixture
def storage(tmp_path):
    """Base de datos temporal que se cierra siempre (en Windows un fichero abierto se bloquea)."""
    with Storage(tmp_path / "db.sqlite") as store:
        yield store

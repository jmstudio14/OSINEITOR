from __future__ import annotations

import pytest

from osineitor.config import Config
from osineitor.http import HttpClient
from osineitor.modules.base import Context


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    for name in ("SHODAN", "ABUSEIPDB", "GREYNOISE", "HIBP", "HUNTER", "IPINFO"):
        monkeypatch.delenv(f"OSINEITOR_{name}_KEY", raising=False)


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

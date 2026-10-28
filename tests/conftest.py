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

from __future__ import annotations

import httpx
import respx

from osineitor import registry
from osineitor.config import Config
from osineitor.http import HttpClient
from osineitor.models import Entity, EntityType, ScanEvent, ScanResult
from osineitor.storage import Storage


def test_registry_modules_are_well_formed():
    modules = registry.discover()
    names = [m.name for m in modules]
    assert len(names) == len(set(names))
    for m in modules:
        assert m.description and m.consumes


def test_config_roundtrip_and_env_priority(tmp_path, monkeypatch):
    path = tmp_path / "c.toml"
    Config(keys={"shodan": 'a"b'}).save(path)
    loaded = Config.load(path)
    assert loaded.key("shodan") == 'a"b'
    monkeypatch.setenv("OSINEITOR_SHODAN_KEY", "env")
    assert loaded.key("shodan") == "env"
    assert loaded.key("missing") is None


def test_storage_roundtrip(tmp_path):
    storage = Storage(tmp_path / "db.sqlite")
    seed = Entity(type=EntityType.DOMAIN, value="example.com")
    result = ScanResult(
        target=seed,
        depth=2,
        entities=[
            Entity(
                type=EntityType.IP,
                value="1.2.3.4",
                source="dns",
                parent=seed.key,
                data={"ttl": 300},
            )
        ],
        events=[ScanEvent(kind="error", module="x", message="boom", entity=seed.key)],
    )
    scan_id = storage.save(result)
    loaded = storage.load(scan_id)
    assert loaded.entities == result.entities
    assert loaded.events == result.events
    assert loaded.target.value == "example.com"
    assert storage.list_scans()[0][:4] == (scan_id, "domain", "example.com", 1)
    assert storage.load(999) is None


@respx.mock
async def test_http_retries_on_429():
    route = respx.get("https://api.test/x").mock(
        side_effect=[httpx.Response(429), httpx.Response(200, json={"ok": True})]
    )
    async with HttpClient(Config(), backoff=0) as http:
        response = await http.get("https://api.test/x")
    assert response.json() == {"ok": True}
    assert route.call_count == 2

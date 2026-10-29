from __future__ import annotations

from datetime import UTC, datetime

import httpx
import respx

from osineitor import registry
from osineitor.config import Config
from osineitor.http import HttpClient
from osineitor.models import Entity, EntityType, Observation, ScanEvent, ScanResult
from osineitor.modules.base import Module


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


def test_storage_roundtrip(storage):
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


def test_storage_roundtrip_keeps_every_observation(storage):
    seed = Entity(type=EntityType.DOMAIN, value="example.com")
    at = datetime(2026, 10, 30, 8, 15, tzinfo=UTC)
    seen = Entity(
        type=EntityType.IP,
        value="1.2.3.4",
        source="dns",
        parent=seed.key,
        observations=[
            Observation(module="dns", query=seed.key, at=at),
            Observation(module="crtsh", query="domain:sub.example.com", at=at),
        ],
    )
    loaded = storage.load(storage.save(ScanResult(target=seed, depth=1, entities=[seen])))
    assert loaded.entities[0].observations == seen.observations
    assert loaded.entities[0].sources == ["dns", "crtsh"]


def test_sources_fall_back_to_source_for_data_without_observations():
    assert Entity(type=EntityType.IP, value="1.2.3.4", source="dns").sources == ["dns"]
    assert Entity(type=EntityType.IP, value="1.2.3.4").sources == []


def test_sources_lists_each_module_once_in_arrival_order():
    entity = Entity(
        type=EntityType.IP,
        value="1.2.3.4",
        observations=[
            Observation(module="dns", query="domain:a.example"),
            Observation(module="crtsh", query="domain:a.example"),
            Observation(module="dns", query="domain:b.example"),
        ],
    )
    assert entity.sources == ["dns", "crtsh"]


def test_emit_records_who_saw_it_and_on_what():
    class Probe(Module):
        name = "probe"
        description = "test"
        consumes = frozenset({EntityType.DOMAIN})

        async def run(self, entity):
            return []

    parent = Entity(type=EntityType.DOMAIN, value="example.com")
    before = datetime.now(UTC)
    emitted = Probe(ctx=None).emit(parent, EntityType.IP, "1.2.3.4")  # type: ignore[arg-type]
    (obs,) = emitted.observations
    assert (obs.module, obs.query) == ("probe", "domain:example.com")
    assert emitted.source == "probe" and emitted.parent == "domain:example.com"
    assert before <= obs.at <= datetime.now(UTC)


@respx.mock
async def test_http_retries_on_429():
    route = respx.get("https://api.test/x").mock(
        side_effect=[httpx.Response(429), httpx.Response(200, json={"ok": True})]
    )
    async with HttpClient(Config(), backoff=0) as http:
        response = await http.get("https://api.test/x")
    assert response.json() == {"ok": True}
    assert route.call_count == 2


def test_detect_type():
    from osineitor.models import detect_type

    assert detect_type("8.8.8.8") == EntityType.IP
    assert detect_type("2001:4860:4860::8888") == EntityType.IP
    assert detect_type("Jane@Example.com") == EntityType.EMAIL
    assert detect_type("sub.example.co.uk") == EntityType.DOMAIN
    assert detect_type("john_doe") == EntityType.USERNAME
    # Ambiguo por diseño: parece un dominio. Para forzarlo, `osineitor username john.doe`.
    assert detect_type("john.doe") == EntityType.DOMAIN

from __future__ import annotations

import asyncio

from osineitor.engine import Engine
from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module, ModuleError


class DomainToIp(Module):
    name = "fake_dns"
    description = "test"
    consumes = frozenset({EntityType.DOMAIN})
    produces = frozenset({EntityType.IP})

    async def run(self, entity):
        return [
            self.emit(entity, EntityType.IP, "1.2.3.4"),
            self.emit(entity, EntityType.IP, "1.2.3.4"),
        ]


class IpToDomain(Module):
    name = "fake_reverse"
    description = "test"
    consumes = frozenset({EntityType.IP})
    produces = frozenset({EntityType.DOMAIN})

    async def run(self, entity):
        return [
            self.emit(entity, EntityType.DOMAIN, "EXAMPLE.com"),
            self.emit(entity, EntityType.DOMAIN, "other.example"),
        ]


class Broken(Module):
    name = "broken"
    description = "test"
    consumes = frozenset({EntityType.DOMAIN})

    async def run(self, entity):
        raise ModuleError("cuota agotada")


class Crashing(Module):
    name = "crashing"
    description = "test"
    consumes = frozenset({EntityType.DOMAIN})

    async def run(self, entity):
        raise ValueError("bug")


class NeedsKey(Module):
    name = "needs_key"
    description = "test"
    consumes = frozenset({EntityType.DOMAIN})
    requires_key = "fake"

    async def run(self, entity):
        return [self.emit(entity, EntityType.RECORD, "secret")]


class Active(Module):
    name = "active"
    description = "test"
    consumes = frozenset({EntityType.DOMAIN})
    passive = False

    async def run(self, entity):
        return [self.emit(entity, EntityType.RECORD, "touched")]


SEED = Entity(type=EntityType.DOMAIN, value="example.com")


async def test_depth_one_does_not_pivot(ctx):
    result = await Engine(ctx, [DomainToIp, IpToDomain], depth=1).run(SEED)
    assert [e.key for e in result.entities] == ["ip:1.2.3.4"]


async def test_depth_two_pivots_and_dedupes(ctx):
    result = await Engine(ctx, [DomainToIp, IpToDomain], depth=2).run(SEED)
    keys = [e.key for e in result.entities]
    # el seed (comparado sin mayúsculas) y la IP duplicada no se repiten
    assert keys == ["ip:1.2.3.4", "domain:other.example"]
    assert result.entities[1].parent == "ip:1.2.3.4"
    assert result.entities[1].source == "fake_reverse"


async def test_errors_are_recorded_not_raised(ctx):
    result = await Engine(ctx, [Broken, Crashing, DomainToIp]).run(SEED)
    assert len(result.entities) == 1
    errors = {ev.module: ev.message for ev in result.events if ev.kind == "error"}
    assert errors["broken"] == "cuota agotada"
    assert errors["crashing"].startswith("ValueError")


async def test_missing_key_and_active_modules_are_skipped(ctx):
    result = await Engine(ctx, [NeedsKey, Active]).run(SEED)
    assert result.entities == []
    assert {ev.module for ev in result.events if ev.kind == "skipped"} == {"needs_key", "active"}


async def test_key_and_active_enable_modules(ctx, monkeypatch):
    monkeypatch.setenv("OSINEITOR_FAKE_KEY", "x")
    result = await Engine(ctx, [NeedsKey, Active], active=True).run(SEED)
    assert {e.value for e in result.entities} == {"secret", "touched"}


async def test_on_entity_callback(ctx):
    seen = []
    await Engine(ctx, [DomainToIp], on_entity=seen.append).run(SEED)
    assert [e.value for e in seen] == ["1.2.3.4"]


class ServiceA(Module):
    name = "svc_a"
    description = "test"
    consumes = frozenset({EntityType.IP})

    async def run(self, entity):
        return [self.emit(entity, EntityType.SERVICE, "1.2.3.4:80", port=80, product=None)]


class ServiceB(Module):
    name = "svc_b"
    description = "test"
    consumes = frozenset({EntityType.IP})

    async def run(self, entity):
        return [self.emit(entity, EntityType.SERVICE, "1.2.3.4:80", port=8080, product="nginx")]


async def test_duplicate_entities_merge_missing_data(ctx):
    seed = Entity(type=EntityType.IP, value="1.2.3.4")
    result = await Engine(ctx, [ServiceA, ServiceB]).run(seed)
    assert len(result.entities) == 1
    assert result.entities[0].data == {"port": 80, "product": "nginx"}


async def test_every_source_that_saw_an_entity_is_kept_as_an_observation(ctx):
    seed = Entity(type=EntityType.IP, value="1.2.3.4")
    result = await Engine(ctx, [ServiceA, ServiceB]).run(seed)
    (service,) = result.entities
    assert service.source == "svc_a"  # la primera, como antes
    assert [(o.module, o.query) for o in service.observations] == [
        ("svc_a", "ip:1.2.3.4"),
        ("svc_b", "ip:1.2.3.4"),
    ]
    assert service.sources == ["svc_a", "svc_b"]


class SeesTheSameIp(Module):
    """Ve la misma IP desde cada dominio (y dos veces desde el mismo) y pivota a otro dominio."""

    name = "sees_ip"
    description = "test"
    consumes = frozenset({EntityType.DOMAIN})

    async def run(self, entity):
        found = [self.emit(entity, EntityType.IP, "1.2.3.4") for _ in range(2)]
        if entity.value == "example.com":
            found.append(self.emit(entity, EntityType.DOMAIN, "other.example"))
        return found


async def test_same_module_from_two_parents_counts_twice_but_repeats_do_not(ctx):
    result = await Engine(ctx, [SeesTheSameIp], depth=2).run(SEED)
    ip = next(e for e in result.entities if e.key == "ip:1.2.3.4")
    assert [(o.module, o.query) for o in ip.observations] == [
        ("sees_ip", "domain:example.com"),
        ("sees_ip", "domain:other.example"),
    ]
    assert ip.sources == ["sees_ip"]


async def test_observations_do_not_change_how_data_is_merged(ctx):
    seed = Entity(type=EntityType.IP, value="1.2.3.4")
    result = await Engine(ctx, [ServiceA, ServiceB]).run(seed)
    assert result.entities[0].data == {"port": 80, "product": "nginx"}


class SlowFirst(Module):
    """Va primero en el orden de módulos pero termina el último."""

    name = "a_slow"
    description = "test"
    consumes = frozenset({EntityType.IP})

    async def run(self, entity):
        await asyncio.sleep(0.2)
        return [self.emit(entity, EntityType.SERVICE, "1.2.3.4:80", port=80, product="apache")]


class FastLast(Module):
    name = "z_fast"
    description = "test"
    consumes = frozenset({EntityType.IP})

    async def run(self, entity):
        return [self.emit(entity, EntityType.SERVICE, "1.2.3.4:80", port=8080, product="nginx")]


async def test_conflicting_data_resolves_by_module_order_not_by_arrival(ctx):
    """Si dos fuentes discrepan gana la primera en el orden de módulos, aunque acabe después."""
    seed = Entity(type=EntityType.IP, value="1.2.3.4")
    for classes in ([SlowFirst, FastLast], [FastLast, SlowFirst]):
        result = await Engine(ctx, classes).run(seed)
        winner = "a_slow" if classes[0] is SlowFirst else "z_fast"
        port = 80 if winner == "a_slow" else 8080
        assert result.entities[0].data == {
            "port": port,
            "product": "apache" if port == 80 else "nginx",
        }

"""Confianza de cada entidad: fuentes distintas, autoridad de la fuente y antigüedad del dato."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from osineitor import registry
from osineitor.confidence import MAX_AGE, assess, data_date
from osineitor.engine import Engine
from osineitor.models import Entity, EntityType, Observation, ScanResult
from osineitor.modules.base import Module

NOW = datetime(2026, 10, 30, 12, tzinfo=UTC)
AUTHORITATIVE = {"dns", "rdap"}


def entity(*modules: str, data: dict | None = None, at: datetime = NOW) -> Entity:
    return Entity(
        type=EntityType.IP,
        value="1.2.3.4",
        data=data or {},
        observations=[Observation(module=m, query="domain:example.com", at=at) for m in modules],
    )


@pytest.mark.parametrize(
    ("modules", "expected"),
    [
        (("crtsh",), "bajo"),  # una sola fuente agregada
        (("dns",), "medio"),  # una sola, pero autoritativa
        (("crtsh", "shodan"), "medio"),  # dos agregadas
        (("dns", "crtsh"), "alto"),  # autoritativa corroborada
        (("crtsh", "shodan", "wayback"), "alto"),
        (("dns", "dns"), "medio"),  # el mismo módulo dos veces es una sola fuente
    ],
)
def test_level_from_distinct_sources_and_authority(modules, expected):
    assert assess(entity(*modules), AUTHORITATIVE, NOW) == expected


def test_data_older_than_the_limit_drops_one_level():
    old = (NOW - MAX_AGE - timedelta(days=1)).isoformat()
    recent = (NOW - timedelta(days=5)).isoformat()
    assert (
        assess(entity("dns", "shodan", data={"last_update": recent}), AUTHORITATIVE, NOW) == "alto"
    )
    assert assess(entity("dns", "shodan", data={"last_update": old}), AUTHORITATIVE, NOW) == "medio"
    assert (
        assess(entity("shodan", data={"last_update": old}), AUTHORITATIVE, NOW) == "bajo"
    )  # suelo


def test_the_age_is_the_third_party_date_not_the_time_of_the_scan():
    # Visto ahora por Shodan, pero Shodan dice que el dato es de hace medio año.
    stale = entity("shodan", "greynoise", data={"last_update": "2026-04-01T00:00:00"})
    assert data_date(stale) == datetime(2026, 4, 1, tzinfo=UTC)
    assert assess(stale, AUTHORITATIVE, NOW) == "bajo"
    assert data_date(entity("dns")) == NOW  # sin fecha de tercero vale la última observación


def test_only_last_observed_keys_count_and_odd_formats_are_ignored():
    # `created` (alta del dominio) y `date` (brecha) son antiguas por naturaleza: no penalizan.
    ancient = entity("dns", "crtsh", data={"created": "2001-01-01", "date": "2012-06-05"})
    assert assess(ancient, AUTHORITATIVE, NOW) == "alto"
    wayback = entity("dns", "wayback", data={"last_seen": "20200101000000"})  # formato Wayback
    assert data_date(wayback) == datetime(2020, 1, 1, tzinfo=UTC)
    assert assess(wayback, AUTHORITATIVE, NOW) == "medio"
    assert data_date(entity("dns", data={"last_seen": "no es una fecha"})) == NOW


def test_an_entity_without_observations_has_no_confidence():
    assert assess(Entity(type=EntityType.IP, value="1.2.3.4", source="dns"), {"dns"}, NOW) is None


def test_every_module_declares_a_valid_authority():
    modules = registry.discover()
    assert {m.authority for m in modules} <= {"authoritative", "aggregated"}
    assert {m.name for m in modules if m.authority == "authoritative"} == {
        "dns",
        "rdap",
        "http_fingerprint",
        "email_validate",
        "mail_security",
        "whois",
    }


def fake(name: str, authority: str) -> type[Module]:
    async def run(self, entity):
        return [self.emit(entity, EntityType.IP, "1.2.3.4")]

    return type(
        name,
        (Module,),
        {
            "name": name,
            "description": "test",
            "consumes": frozenset({EntityType.DOMAIN}),
            "authority": authority,
            "run": run,
        },
    )


async def test_the_engine_assigns_the_level_when_the_scan_ends(ctx):
    seed = Entity(type=EntityType.DOMAIN, value="example.com")
    one = await Engine(ctx, [fake("agg_a", "aggregated")]).run(seed)
    assert one.entities[0].confidence == "bajo"
    both = await Engine(ctx, [fake("auth_a", "authoritative"), fake("agg_a", "aggregated")]).run(
        seed
    )
    assert both.entities[0].confidence == "alto"


def test_confidence_survives_the_database(storage):
    seed = Entity(type=EntityType.DOMAIN, value="example.com")
    scored = entity("dns", "crtsh").model_copy(update={"confidence": "alto"})
    loaded = storage.load(storage.save(ScanResult(target=seed, depth=1, entities=[scored])))
    assert loaded.entities[0].confidence == "alto"


def test_migrating_a_v4_database_leaves_old_entities_without_confidence(tmp_path):
    from osineitor.storage import MIGRATIONS, Storage

    path = tmp_path / "v4.db"
    conn = sqlite3.connect(path)
    for statement in ";".join(MIGRATIONS[:4]).split(";"):
        if statement.strip():
            conn.execute(statement)
    conn.execute(
        "INSERT INTO scans VALUES (1, 'domain', 'old.example', 1, '2026-10-01T10:00', NULL)"
    )
    conn.execute(
        "INSERT INTO entities (scan_id, type, value, source, parent, data)"
        " VALUES (1, 'ip', '9.9.9.9', 'dns', 'domain:old.example', '{}')"
    )
    conn.execute("PRAGMA user_version = 4")
    conn.commit()
    conn.close()
    with Storage(path) as store:
        old = store.load(1).entities[0]
        assert (old.confidence, old.sources) == (None, ["dns"])

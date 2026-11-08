"""F4.23: `geoip_offline` geolocaliza una IP con una base GeoLite2 local, sin red."""

from __future__ import annotations

import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from osineitor.engine import Engine
from osineitor.models import Entity, EntityType
from osineitor.modules.base import ModuleError
from osineitor.modules.ip import geoip_offline
from osineitor.modules.ip.geoip_offline import GeoipOffline, database_path

FIXTURES = Path(__file__).parent.parent / "fixtures" / "geoip"
BUILT = datetime(2026, 10, 22, tzinfo=UTC)  # fecha de compilación aproximada de la base de prueba


def install(name: str = "GeoLite2-City-Test.mmdb") -> None:
    database_path().parent.mkdir(parents=True)
    shutil.copy(FIXTURES / name, database_path())


def ip(value: str) -> Entity:
    return Entity(type=EntityType.IP, value=value)


@pytest.fixture
def fresh(monkeypatch):
    monkeypatch.setattr(geoip_offline, "_now", lambda: BUILT + timedelta(days=1))


@pytest.mark.usefixtures("fresh")
async def test_an_ip_in_the_database_gives_its_location(ctx):
    install()
    [record] = await GeoipOffline(ctx).run(ip("81.2.69.142"))
    assert record.type == EntityType.RECORD
    assert record.value == "geoip:81.2.69.142"
    assert record.data["city"] == "London"
    assert record.data["region"] == "England"
    assert record.data["country"] == "GB"
    assert record.data["loc"] == "51.5142,-0.0931"
    assert record.data["timezone"] == "Europe/London"
    assert record.data["accuracy_radius"] == 10
    assert record.data["database_date"] == "2026-10-22"
    assert not record.data.get("stale_database")


@pytest.mark.usefixtures("fresh")
async def test_a_network_without_city_or_region_keeps_the_country(ctx):
    install()
    [record] = await GeoipOffline(ctx).run(ip("67.43.156.1"))
    assert record.data["country"] == "BT"
    assert not record.data.get("city")
    assert not record.data.get("region")


async def test_an_ip_outside_the_database_gives_nothing(ctx):
    install()
    assert await GeoipOffline(ctx).run(ip("8.8.8.8")) == []


async def test_a_database_older_than_30_days_is_flagged(ctx, monkeypatch):
    install()
    monkeypatch.setattr(geoip_offline, "_now", lambda: BUILT + timedelta(days=32))
    [record] = await GeoipOffline(ctx).run(ip("81.2.69.142"))
    assert record.data["stale_database"] is True


def test_without_the_file_the_module_says_where_to_put_it():
    assert str(database_path()) in GeoipOffline.unavailable()


def test_with_the_file_the_module_is_available():
    install()
    assert GeoipOffline.unavailable() is None


async def test_without_the_file_the_engine_skips_the_module(ctx):
    engine = Engine(ctx, [GeoipOffline])
    assert [event.module for event in engine.skipped] == ["geoip_offline"]
    assert str(database_path()) in engine.skipped[0].message


@pytest.mark.parametrize("content", [b"esto no es una base mmdb", b""])
async def test_a_corrupt_file_is_a_module_error(ctx, content):
    database_path().parent.mkdir(parents=True)
    database_path().write_bytes(content)
    with pytest.raises(ModuleError, match="GeoLite2-City.mmdb"):
        await GeoipOffline(ctx).run(ip("81.2.69.142"))


class FakeReader:
    def __init__(self, database_type: str = "GeoLite2-City", found: dict | None = None):
        self.database_type = database_type
        self.found = found

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return None

    def metadata(self):
        return SimpleNamespace(database_type=self.database_type, build_epoch=0)

    def get(self, address):
        return self.found


async def test_another_edition_under_that_name_is_a_module_error(ctx, monkeypatch):
    # Una base sin datos de ciudad daría registros vacíos: se rechaza por su tipo.
    reader = FakeReader("GeoLite2-ASN")
    monkeypatch.setattr(geoip_offline.maxminddb, "open_database", lambda path: reader)
    with pytest.raises(ModuleError, match="GeoLite2-ASN"):
        await GeoipOffline(ctx).run(ip("81.2.69.142"))


async def test_only_the_registered_country_is_not_a_location(ctx, monkeypatch):
    # Lo que la base real de GeoLite2-City devuelve para 1.1.1.1 y otras IP anycast.
    reader = FakeReader(found={"registered_country": {"iso_code": "AU"}})
    monkeypatch.setattr(geoip_offline.maxminddb, "open_database", lambda path: reader)
    assert await GeoipOffline(ctx).run(ip("1.1.1.1")) == []


@pytest.mark.usefixtures("fresh")
async def test_it_runs_in_the_analyzer_pass_without_network(ctx):
    install()
    assert GeoipOffline.analyzer and GeoipOffline.passive
    result = await Engine(ctx, [GeoipOffline]).run(ip("81.2.69.142"))
    assert [e.value for e in result.entities] == ["geoip:81.2.69.142"]
    assert [run.status for run in result.runs if run.entity] == ["ok"]
    assert all(run.requests == 0 for run in result.runs)

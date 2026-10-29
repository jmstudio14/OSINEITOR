"""Estado de cada módulo en un scan (ModuleRun), timeouts, caché por módulo y migraciones."""

from __future__ import annotations

import asyncio
import sqlite3

import httpx
import pytest
import respx

from osineitor import storage as storage_mod
from osineitor.cache import ResponseCache
from osineitor.config import Config
from osineitor.engine import Engine
from osineitor.errors import ModuleQuota, ModuleSkipped
from osineitor.http import HttpClient
from osineitor.models import Entity, EntityType, ModuleRun, ScanResult
from osineitor.modules.base import Context, Module, ModuleError
from osineitor.storage import MIGRATIONS, Storage, StorageError

SEED = Entity(type=EntityType.DOMAIN, value="example.com")


def make(name: str, run, **attrs) -> type[Module]:
    return type(
        name,
        (Module,),
        {
            "name": name,
            "description": "test",
            "consumes": frozenset({EntityType.DOMAIN}),
            "run": run,
            **attrs,
        },
    )


async def ok(self, entity):
    return [self.emit(entity, EntityType.IP, "1.2.3.4")]


async def empty(self, entity):
    return []


async def error(self, entity):
    raise ModuleError("boom")


async def quota(self, entity):
    raise ModuleQuota("sin cuota")


async def skipped(self, entity):
    raise ModuleSkipped("no aplica")


async def crash(self, entity):
    raise ValueError("bug")


async def hang(self, entity):
    await asyncio.sleep(30)


async def run_engine(ctx, classes, **kwargs) -> ScanResult:
    return await Engine(ctx, classes, **kwargs).run(SEED)


async def test_each_module_gets_a_run_with_its_status(ctx):
    classes = [make(n, f) for n, f in [("m_ok", ok), ("m_empty", empty), ("m_err", error)]]
    classes += [make(n, f) for n, f in [("m_quota", quota), ("m_skip", skipped), ("m_bug", crash)]]
    result = await run_engine(ctx, classes)
    runs = {r.module: r for r in result.runs}
    assert {k: v.status for k, v in runs.items()} == {
        "m_ok": "ok",
        "m_empty": "empty",
        "m_err": "error",
        "m_quota": "quota",
        "m_skip": "skipped",
        "m_bug": "error",
    }
    assert runs["m_ok"].entities == 1
    assert runs["m_err"].message == "boom"
    assert runs["m_bug"].message == "ValueError: bug"
    assert all(r.entity == SEED.key for r in runs.values())
    kinds = {e.module: e.kind for e in result.events}
    assert kinds == {
        "m_err": "error",
        "m_quota": "error",
        "m_skip": "skipped",
        "m_bug": "error",
    }


async def test_modules_not_started_are_recorded_as_skipped(ctx):
    active = make("m_active", ok, passive=False)
    keyed = make("m_keyed", ok, requires_key="nokey")
    result = await run_engine(ctx, [active, keyed])
    assert {(r.module, r.status, r.entity) for r in result.runs} == {
        ("m_active", "skipped", None),
        ("m_keyed", "skipped", None),
    }


async def test_module_timeout_is_an_error_not_a_hang(ctx):
    result = await run_engine(ctx, [make("m_hang", hang, timeout=0.05), make("m_ok", ok)])
    runs = {r.module: r for r in result.runs}
    assert runs["m_hang"].status == "error"
    assert "sin respuesta" in runs["m_hang"].message
    assert runs["m_ok"].status == "ok"  # el módulo lento no bloquea al resto
    assert [e.value for e in result.entities] == ["1.2.3.4"]


@respx.mock
async def test_runs_count_requests_per_module(ctx):
    respx.get("https://a.test/").mock(return_value=httpx.Response(200))
    respx.get("https://b.test/").mock(return_value=httpx.Response(200))

    async def one(self, entity):
        await self.ctx.http.get("https://a.test/")
        return []

    async def two(self, entity):
        await self.ctx.http.get("https://b.test/")
        await self.ctx.http.get("https://b.test/")
        return []

    result = await run_engine(ctx, [make("m_one", one), make("m_two", two)])
    assert {r.module: r.requests for r in result.runs} == {"m_one": 1, "m_two": 2}


@respx.mock
async def test_cache_is_per_module_and_off_for_keys_and_active(tmp_path):
    route = respx.get("https://a.test/").mock(return_value=httpx.Response(200, json={}))

    async def fetch(self, entity):
        await self.ctx.http.get("https://a.test/")
        return []

    cache = ResponseCache(tmp_path / "c.db")
    config = Config(keys={"k": "v"})
    async with HttpClient(config, cache=cache) as http:
        ctx = Context(config=config, http=http)
        await run_engine(ctx, [make("cached", fetch)])
        await run_engine(ctx, [make("cached", fetch)])
        assert route.call_count == 1  # la segunda salió de la caché
        await run_engine(ctx, [make("keyed", fetch, requires_key="k")])
        await run_engine(ctx, [make("keyed", fetch, requires_key="k")])
        assert route.call_count == 3  # con API key nunca se cachea
        await run_engine(ctx, [make("act", fetch, passive=False)], active=True)
        await run_engine(ctx, [make("act", fetch, passive=False)], active=True)
        assert route.call_count == 5  # los módulos activos tampoco
        await run_engine(ctx, [make("nocache", fetch, cache_ttl=0)])
        await run_engine(ctx, [make("nocache", fetch, cache_ttl=0)])
        assert route.call_count == 7
        result = await run_engine(ctx, [make("cached", fetch)])
    assert route.call_count == 7
    assert result.runs[0].cache_hits == 1 and result.runs[0].requests == 0


def test_storage_saves_and_loads_runs(storage):
    result = ScanResult(
        target=SEED,
        depth=1,
        runs=[
            ModuleRun(
                module="a",
                status="ok",
                entity=SEED.key,
                entities=3,
                requests=2,
                cache_hits=1,
                duration_ms=120,
                message="",
            ),
            ModuleRun(module="b", status="skipped", message="falta la API key 'x'"),
        ],
    )
    loaded = storage.load(storage.save(result))
    assert loaded.runs == result.runs


V010_SCHEMA = """
CREATE TABLE scans (id INTEGER PRIMARY KEY AUTOINCREMENT, target_type TEXT NOT NULL,
    target TEXT NOT NULL, depth INTEGER NOT NULL, started_at TEXT NOT NULL, finished_at TEXT);
CREATE TABLE entities (scan_id INTEGER NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
    type TEXT NOT NULL, value TEXT NOT NULL, source TEXT, parent TEXT, data TEXT NOT NULL);
CREATE TABLE events (scan_id INTEGER NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
    kind TEXT NOT NULL, module TEXT NOT NULL, entity TEXT, message TEXT NOT NULL);
"""


def test_migrates_a_v010_database_without_losing_data(tmp_path):
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.executescript(V010_SCHEMA)
    conn.execute(
        "INSERT INTO scans VALUES (1, 'domain', 'old.example', 1, '2026-10-01T10:00:00', NULL)"
    )
    conn.execute(
        "INSERT INTO entities VALUES (1, 'ip', '9.9.9.9', 'dns', 'domain:old.example', '{}')"
    )
    conn.execute("INSERT INTO events VALUES (1, 'error', 'rdap', NULL, 'viejo error')")
    conn.commit()
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 0  # así sale una BD de la v0.1.0
    conn.close()

    with Storage(path) as store:
        loaded = store.load(1)
        assert loaded.target.value == "old.example"
        assert [e.value for e in loaded.entities] == ["9.9.9.9"]
        assert loaded.events[0].message == "viejo error"
        assert loaded.runs == []  # el scan antiguo no tiene estado por módulo
        new_id = store.save(
            ScanResult(target=SEED, depth=1, runs=[ModuleRun(module="a", status="ok")])
        )
        assert store.load(new_id).runs[0].module == "a"
    check = sqlite3.connect(path)
    assert check.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS)
    check.close()


def test_reopening_a_migrated_database_is_idempotent(tmp_path):
    path = tmp_path / "db.sqlite"
    with Storage(path) as store:
        store.save(ScanResult(target=SEED, depth=1))
    with Storage(path) as store:
        assert store.list_scans()[0][2] == "example.com"


def test_database_from_a_newer_version_is_refused(tmp_path):
    path = tmp_path / "future.db"
    conn = sqlite3.connect(path)
    conn.execute(f"PRAGMA user_version = {len(MIGRATIONS) + 1}")
    conn.close()
    with pytest.raises(StorageError, match="más nueva"):
        Storage(path)


def test_failed_migration_is_rolled_back(tmp_path, monkeypatch):
    path = tmp_path / "db.sqlite"
    monkeypatch.setattr(
        storage_mod, "MIGRATIONS", [*MIGRATIONS[:1], "CREATE TABLE ok_t (x); CREATE TABLE ok_t (x)"]
    )
    with pytest.raises(sqlite3.OperationalError):
        Storage(path)
    conn = sqlite3.connect(path)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 1  # la 2 no quedó a medias
    assert conn.execute("SELECT name FROM sqlite_master WHERE name='ok_t'").fetchall() == []
    conn.close()

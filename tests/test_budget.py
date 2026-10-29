from __future__ import annotations

import asyncio
import time

import httpx
import pytest
import respx

from osineitor.budget import Budget
from osineitor.config import Config
from osineitor.engine import Engine
from osineitor.errors import BudgetExceeded, ModuleSkipped
from osineitor.http import HttpClient
from osineitor.models import Entity, EntityType
from osineitor.modules.base import Context, Module
from osineitor.storage import Storage

SEED = Entity(type=EntityType.DOMAIN, value="example.com")


def make(name, consumes, produces, run):
    return type(
        f"M_{name}",
        (Module,),
        {
            "name": name,
            "description": "t",
            "consumes": frozenset(consumes),
            "produces": frozenset(produces),
            "run": run,
        },
    )


def test_from_limits_zero_means_unlimited():
    budget = Budget.from_limits(0, 0, 0)
    assert (budget.max_entities, budget.max_requests, budget.max_seconds) == (None, None, None)
    assert budget.exhausted(10**9) is None
    assert budget.remaining_seconds() is None


def test_exhausted_reasons():
    assert "entidades" in Budget(max_entities=2).exhausted(2)
    assert Budget(max_entities=2).exhausted(1) is None
    expired = Budget(max_seconds=0.01)
    expired.start()
    time.sleep(0.03)
    assert "tiempo" in expired.exhausted()
    assert expired.remaining_seconds() == 0.0


def test_requests_are_only_exhausted_after_a_blocked_one():
    budget = Budget(max_requests=1)
    budget.charge_request()  # usa exactamente el tope: aún no está agotado
    assert budget.exhausted() is None
    with pytest.raises(BudgetExceeded):
        budget.charge_request()
    assert "peticiones" in budget.exhausted()


async def test_entity_cap_truncates_the_result(ctx):
    async def run(self, entity):
        return [self.emit(entity, EntityType.IP, f"9.9.9.{i}") for i in range(1, 6)]

    mod = make("many", {EntityType.DOMAIN}, {EntityType.IP}, run)
    result = await Engine(ctx, [mod], budget=Budget(max_entities=3)).run(SEED)
    assert len(result.entities) == 3
    assert result.truncated
    assert [e.kind for e in result.events] == ["budget"]
    assert "entidades" in result.events[0].message


async def test_no_truncation_when_everything_fits(ctx):
    async def run(self, entity):
        return [self.emit(entity, EntityType.IP, "9.9.9.9")]

    mod = make("one", {EntityType.DOMAIN}, {EntityType.IP}, run)
    result = await Engine(ctx, [mod], budget=Budget(max_entities=1)).run(SEED)
    assert not result.truncated
    assert len(result.entities) == 1


@respx.mock
async def test_request_cap_truncates_and_keeps_what_was_found():
    respx.get(url__startswith="https://api.test/").mock(return_value=httpx.Response(200))
    budget = Budget(max_requests=3)
    http = HttpClient(Config(), backoff=0, budget=budget)

    async def run(self, entity):
        found = []
        for i in range(10):
            await self.ctx.http.get(f"https://api.test/{i}")
            found.append(self.emit(entity, EntityType.IP, f"9.9.9.{i + 1}"))
        return found

    mod = make("greedy", {EntityType.DOMAIN}, {EntityType.IP}, run)
    ctx = Context(config=Config(), http=http)
    result = await Engine(ctx, [mod], budget=budget).run(SEED)
    await http.aclose()
    assert result.truncated
    assert "peticiones" in result.events[0].message
    assert budget.requests == 3


async def test_time_cap_cancels_slow_modules(ctx):
    async def slow(self, entity):
        await asyncio.sleep(30)
        return []

    async def quick(self, entity):
        return [self.emit(entity, EntityType.IP, "9.9.9.9")]

    mods = [
        make("slow", {EntityType.DOMAIN}, set(), slow),
        make("quick", {EntityType.DOMAIN}, {EntityType.IP}, quick),
    ]
    started = time.monotonic()
    result = await Engine(ctx, mods, budget=Budget(max_seconds=0.2)).run(SEED)
    assert time.monotonic() - started < 5
    assert result.truncated
    assert [e.value for e in result.entities] == ["9.9.9.9"]  # lo que terminó se conserva
    assert "tiempo" in result.events[-1].message


async def test_skipped_modules_are_events_not_errors(ctx):
    async def run(self, entity):
        raise ModuleSkipped("no aplica")

    result = await Engine(ctx, [make("skip", {EntityType.DOMAIN}, set(), run)]).run(SEED)
    assert [(e.kind, e.module, e.message) for e in result.events] == [
        ("skipped", "skip", "no aplica")
    ]
    assert not result.truncated


async def test_truncation_survives_storage_roundtrip(ctx, tmp_path):
    async def run(self, entity):
        return [self.emit(entity, EntityType.IP, f"9.9.9.{i}") for i in range(1, 4)]

    mod = make("many", {EntityType.DOMAIN}, {EntityType.IP}, run)
    result = await Engine(ctx, [mod], budget=Budget(max_entities=1)).run(SEED)
    storage = Storage(tmp_path / "db.sqlite")
    scan_id = storage.save(result)
    loaded = storage.load(scan_id)
    storage.close()
    assert loaded.truncated
    assert loaded.events == result.events

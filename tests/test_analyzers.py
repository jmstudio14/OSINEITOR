"""F3.3: analizadores offline (leen lo ya recogido, sin red y sin gastar presupuesto)."""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from typer.testing import CliRunner

from osineitor.cli import app
from osineitor.engine import Engine
from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module
from tests.test_cli import fake_module, use_modules

runner = CliRunner()
SEED = Entity(type=EntityType.DOMAIN, value="example.com")


class SpfAnalyzer(Module):
    name = "an_spf"
    description = "deduce la tecnología de correo del registro DNS"
    consumes = frozenset({EntityType.RECORD})
    produces = frozenset({EntityType.TECHNOLOGY})
    analyzer = True

    def accepts(self, entity):
        return super().accepts(entity) and entity.value.startswith("txt:v=spf1")

    async def run(self, entity):
        return [self.emit(entity, EntityType.TECHNOLOGY, "Google Workspace", via="include:_spf")]


class SeedAnalyzer(Module):
    name = "an_seed"
    description = "se ejecuta también sobre la semilla"
    consumes = frozenset({EntityType.DOMAIN})
    produces = frozenset({EntityType.ORGANIZATION})
    analyzer = True

    async def run(self, entity):
        return [self.emit(entity, EntityType.ORGANIZATION, f"Titular de {entity.value}")]


class Greedy(Module):
    name = "an_greedy"
    description = "intenta salir a internet"
    consumes = frozenset({EntityType.DOMAIN})
    analyzer = True

    async def run(self, entity):
        await self.ctx.http.get("https://example.com/")
        return []


class Resolving(Module):
    name = "an_dns"
    description = "intenta resolver DNS"
    consumes = frozenset({EntityType.DOMAIN})
    analyzer = True

    async def run(self, entity):
        await self.ctx.resolver.resolve("example.com", "A")
        return []


class OnTechnology(Module):
    name = "on_tech"
    description = "consume lo que produce el analizador"
    consumes = frozenset({EntityType.TECHNOLOGY})
    produces = frozenset({EntityType.DOMAIN})

    async def run(self, entity):
        return [self.emit(entity, EntityType.DOMAIN, "pivote.test")]


def dns_record():
    return fake_module("fake_dns", {EntityType.DOMAIN}, EntityType.RECORD, "txt:v=spf1 include:x")


async def test_an_analyzer_reads_what_the_other_modules_collected(ctx):
    result = await Engine(ctx, [dns_record(), SpfAnalyzer]).run(SEED)
    assert [(e.type, e.value) for e in result.entities] == [
        (EntityType.RECORD, "txt:v=spf1 include:x"),
        (EntityType.TECHNOLOGY, "Google Workspace"),
    ]
    tech = result.entities[1]
    assert tech.parent == "record:txt:v=spf1 include:x"
    assert tech.sources == ["an_spf"]


async def test_an_analyzer_also_sees_the_seed(ctx):
    result = await Engine(ctx, [SeedAnalyzer]).run(SEED)
    assert [e.value for e in result.entities] == ["Titular de example.com"]


async def test_what_an_analyzer_emits_is_not_pivoted(ctx):
    result = await Engine(ctx, [dns_record(), SpfAnalyzer, OnTechnology], depth=3).run(SEED)
    assert "pivote.test" not in {e.value for e in result.entities}
    assert {r.module for r in result.runs if r.status == "ok"} == {"fake_dns", "an_spf"}


async def test_an_analyzer_does_not_run_in_the_normal_layers(ctx):
    engine = Engine(ctx, [SeedAnalyzer], depth=3)
    result = await engine.run(SEED)
    assert [r.module for r in result.runs] == ["an_seed"]  # una vez, no una por nivel


async def test_an_analyzer_makes_no_network_request(ctx):
    with respx.mock(assert_all_mocked=True) as router:
        result = await Engine(ctx, [Greedy, Resolving]).run(SEED)
    assert not router.calls
    assert {r.module: r.status for r in result.runs} == {"an_greedy": "error", "an_dns": "error"}
    assert {r.message for r in result.runs} == {"un analizador no puede usar la red"}
    assert all(r.requests == 0 for r in result.runs)


async def test_an_analyzer_gets_an_offline_context_even_if_the_http_client_works(ctx):
    with respx.mock(assert_all_called=False) as router:
        router.get("https://example.com/").mock(return_value=httpx.Response(200))
        await Engine(ctx, [Greedy]).run(SEED)
    assert not router.calls  # aunque la ruta existiera, el analizador nunca llega al cliente


async def test_an_analyzer_costs_no_requests(ctx):
    engine = Engine(ctx, [SeedAnalyzer])
    await engine.run(SEED)
    assert engine.budget.requests == 0


async def test_a_cancelled_scan_skips_the_analyzers(ctx):
    engine = Engine(ctx, [dns_record(), SpfAnalyzer])
    engine.cancel()
    result = await engine.run(SEED)
    assert result.cancelled and result.entities == []
    assert "an_spf" not in {r.module for r in result.runs}


async def test_an_analyzer_runs_even_when_the_scan_was_cut_short(ctx):
    from osineitor.budget import Budget

    # Un tope de entidades corta el pivoteo, pero el analizador sigue leyendo lo recogido.
    engine = Engine(ctx, [dns_record(), SeedAnalyzer], budget=Budget.from_limits(1, 0, 0))
    result = await engine.run(SEED)
    assert result.truncated
    assert "an_seed" in {r.module for r in result.runs if r.status == "ok"}


@pytest.fixture
def modules(monkeypatch):
    use_modules(monkeypatch, [dns_record(), SpfAnalyzer])


def test_the_modules_command_marks_analyzers(modules):
    done = runner.invoke(app, ["modules", "--json"])
    flags = {m["name"]: m["analyzer"] for m in json.loads(done.output)}
    assert flags == {"fake_dns": False, "an_spf": True}
    assert "analizador" in runner.invoke(app, ["modules"]).output


def test_a_scan_through_the_cli_includes_the_analysis(modules):
    done = runner.invoke(app, ["domain", "example.com", "--json", "--no-save"])
    assert done.exit_code == 0, done.output
    assert [e["value"] for e in json.loads(done.output)["entities"]] == [
        "txt:v=spf1 include:x",
        "Google Workspace",
    ]

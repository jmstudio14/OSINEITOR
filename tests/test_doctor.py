from __future__ import annotations

import httpx
import respx
from typer.testing import CliRunner

from osineitor import cli, registry
from osineitor.cli import app
from osineitor.config import Config
from osineitor.doctor import check_module, run_doctor
from osineitor.models import EntityType
from osineitor.modules.base import Module, ModuleError

runner = CliRunner()


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


async def broken(self, entity):
    raise ModuleError("formato inesperado")


async def verdicts(classes, **kwargs):
    checks = await run_doctor(Config(), classes, **kwargs)
    return {c.module: c.verdict for c in checks}


async def test_doctor_uses_the_canary_and_reports_verdicts():
    classes = [
        make("d_ok", ok, canary="example.com"),
        make("d_empty", empty, canary="example.com"),
        make("d_fail", broken, canary="example.com"),
        make("d_none", ok),
        make("d_key", ok, canary="example.com", requires_key="nokey"),
        make("d_active", ok, canary="example.com", passive=False),
    ]
    assert await verdicts(classes) == {
        "d_ok": "ok",
        "d_empty": "empty",
        "d_fail": "fail",
        "d_none": "unchecked",
        "d_key": "skipped",
        "d_active": "skipped",
    }
    assert (await verdicts([classes[-1]], active=True)) == {"d_active": "ok"}


async def test_doctor_detail_carries_the_module_error():
    [check] = await run_doctor(Config(), [make("d_fail", broken, canary="example.com")])
    assert check.detail == "formato inesperado"


@respx.mock
async def test_doctor_probe_checks_reachability_when_there_is_no_canary():
    respx.get("https://up.test/").mock(return_value=httpx.Response(200))
    respx.get("https://err.test/").mock(return_value=httpx.Response(503))
    respx.get("https://down.test/").mock(side_effect=httpx.ConnectError("x"))
    classes = [
        make("p_up", ok, probe_url="https://up.test/"),
        make("p_err", ok, probe_url="https://err.test/"),
        make("p_down", ok, probe_url="https://down.test/"),
    ]
    assert await verdicts(classes) == {"p_up": "ok", "p_err": "fail", "p_down": "fail"}


@respx.mock
async def test_doctor_never_uses_the_cache(tmp_path):
    route = respx.get("https://a.test/").mock(return_value=httpx.Response(200, json={}))

    async def fetch(self, entity):
        await self.ctx.http.get("https://a.test/")
        return [self.emit(entity, EntityType.IP, "1.2.3.4")]

    cls = make("d_fetch", fetch, canary="example.com")
    await run_doctor(Config(), [cls])
    await run_doctor(Config(), [cls])
    assert route.call_count == 2


async def test_check_reports_every_bundled_module_has_a_way_to_be_checked():
    """Cada módulo real declara un canario o una URL de prueba (o es explícitamente sin prueba)."""
    for cls in registry.discover():
        assert cls.canary or cls.probe_url, f"{cls.name} no se puede comprobar con doctor"


def test_cli_doctor_prints_table_and_fails_on_error(monkeypatch):
    mods = [make("d_ok", ok, canary="example.com"), make("d_fail", broken, canary="example.com")]
    monkeypatch.setattr(registry, "discover", lambda: mods)
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 2
    assert "d_ok" in result.output and "FALLO" in result.output
    assert "Fallan: d_fail" in result.output
    result = runner.invoke(app, ["doctor", "-m", "d_ok"])
    assert result.exit_code == 0


def test_cli_doctor_unknown_module(monkeypatch):
    monkeypatch.setattr(registry, "discover", lambda: [make("d_ok", ok, canary="example.com")])
    assert runner.invoke(app, ["doctor", "-m", "nope"]).exit_code == 2


async def test_check_module_active_requires_flag():
    cls = make("d_active", ok, canary="example.com", passive=False)
    from osineitor.http import HttpClient

    async with HttpClient(Config()) as http:
        assert (await check_module(cls, Config(), http, active=False)).verdict == "skipped"
        assert cli.run_doctor is run_doctor

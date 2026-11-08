"""F8.6: módulos de plugins externos descubiertos por entry points."""

from __future__ import annotations

import json
import sys
import textwrap

import pytest
from typer.testing import CliRunner

from osineitor import registry
from osineitor.cli import app

runner = CliRunner()

PLUGIN = """
from osineitor.models import EntityType
from osineitor.modules.base import Module


class Demo(Module):
    name = "demo_plugin"
    description = "Módulo de ejemplo de un plugin"
    consumes = frozenset({EntityType.DOMAIN})
    produces = frozenset({EntityType.RECORD})
    canary = "example.com"

    async def run(self, entity):
        return [self.emit(entity, EntityType.RECORD, "demo:" + entity.value)]


class Clash(Module):
    name = "dns"
    description = "Intenta pisar un módulo incluido"
    consumes = frozenset({EntityType.DOMAIN})

    async def run(self, entity):
        return []
"""


def install(tmp_path, monkeypatch, entry_points: str, source: str = PLUGIN) -> None:
    """Instala un paquete mínimo como lo haría pip: un módulo y su `.dist-info`."""
    (tmp_path / "osineitor_demo.py").write_text(textwrap.dedent(source), encoding="utf-8")
    info = tmp_path / "osineitor_demo-1.0.dist-info"
    info.mkdir()
    (info / "METADATA").write_text("Metadata-Version: 2.1\nName: osineitor-demo\nVersion: 1.0\n")
    (info / "entry_points.txt").write_text(
        f"[{registry.PLUGIN_GROUP}]\n{textwrap.dedent(entry_points)}", encoding="utf-8"
    )
    monkeypatch.delitem(sys.modules, "osineitor_demo", raising=False)
    monkeypatch.syspath_prepend(str(tmp_path))


def names() -> set[str]:
    return {m.name for m in registry.discover()}


def test_without_plugins_nothing_changes():
    assert registry.discover()
    assert registry.plugin_problems == []
    assert not any(registry.is_plugin(m) for m in registry.discover())


def test_an_installed_class_shows_up_without_touching_the_project(tmp_path, monkeypatch):
    install(tmp_path, monkeypatch, "demo = osineitor_demo:Demo\n")
    assert "demo_plugin" in names()
    demo = next(m for m in registry.discover() if m.name == "demo_plugin")
    assert registry.is_plugin(demo) and registry.plugin_problems == []


def test_modules_command_lists_the_plugin_and_flags_it(tmp_path, monkeypatch):
    install(tmp_path, monkeypatch, "demo = osineitor_demo:Demo\n")
    result = runner.invoke(app, ["modules", "--json"])
    assert result.exit_code == 0, result.output
    rows = {row["name"]: row for row in json.loads(result.stdout)}
    assert rows["demo_plugin"]["plugin"] is True and rows["dns"]["plugin"] is False
    assert "demo_plugin" in runner.invoke(app, ["modules"]).output


def test_a_module_entry_point_takes_the_concrete_classes_it_defines(tmp_path, monkeypatch):
    install(tmp_path, monkeypatch, "demo = osineitor_demo\n")
    # `Clash` también está en el módulo, pero su nombre choca con `dns`: el plugin entero se omite.
    assert "demo_plugin" not in names()
    assert any("«dns» ya existe" in p for p in registry.plugin_problems)


def test_a_name_that_clashes_with_a_built_in_module_is_rejected_not_fatal(tmp_path, monkeypatch):
    install(tmp_path, monkeypatch, "clash = osineitor_demo:Clash\ndemo = osineitor_demo:Demo\n")
    found = registry.discover()
    assert [m for m in found if m.name == "dns" and registry.is_plugin(m)] == []
    assert "demo_plugin" in {m.name for m in found}
    assert len(registry.plugin_problems) == 1 and "clash" in registry.plugin_problems[0]


@pytest.mark.parametrize(
    ("entry", "source", "reason"),
    [
        ("x = osineitor_demo:Nope", PLUGIN, "AttributeError"),
        ("x = osineitor_demo_missing:Demo", PLUGIN, "ModuleNotFoundError"),
        ("x = osineitor_demo:VALUE", "VALUE = 3\n", "no es una subclase concreta"),
        ("x = osineitor_demo", "VALUE = 3\n", "ninguna clase Module"),
        ("x = osineitor_demo", "raise RuntimeError('roto')\n", "RuntimeError: roto"),
    ],
)
def test_a_broken_plugin_is_skipped_and_reported(tmp_path, monkeypatch, entry, source, reason):
    install(tmp_path, monkeypatch, entry + "\n", source)
    assert names()  # los módulos incluidos siguen ahí
    assert len(registry.plugin_problems) == 1 and reason in registry.plugin_problems[0]


def test_modules_command_warns_about_a_broken_plugin_on_stderr(tmp_path, monkeypatch):
    install(tmp_path, monkeypatch, "x = osineitor_demo:Nope\n")
    result = runner.invoke(app, ["modules", "--json"])
    assert result.exit_code == 0
    json.loads(result.stdout)  # stdout sigue siendo JSON válido
    assert "Aviso: plugin x" in result.stderr


async def test_the_plugin_module_runs_inside_the_engine(tmp_path, monkeypatch, ctx):
    from osineitor.engine import Engine
    from osineitor.models import Entity, EntityType

    install(tmp_path, monkeypatch, "demo = osineitor_demo:Demo\n")
    demo = next(m for m in registry.discover() if m.name == "demo_plugin")
    result = await Engine(ctx, [demo]).run(Entity(type=EntityType.DOMAIN, value="example.com"))
    assert [e.value for e in result.entities] == ["demo:example.com"]

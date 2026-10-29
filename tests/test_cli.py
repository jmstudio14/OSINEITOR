"""Tests de la CLI: todas las órdenes, con módulos falsos y sin red."""

from __future__ import annotations

import json

import pytest
from rich.console import Console
from typer.testing import CliRunner

from osineitor import cli, registry
from osineitor.cli import app
from osineitor.models import EntityType
from osineitor.modules.base import Module, ModuleError

runner = CliRunner()


def fake_module(
    name: str,
    consumes: set[EntityType],
    out_type: EntityType,
    out_value: str,
    *,
    passive: bool = True,
    key: str | None = None,
    error: str | None = None,
    **data: object,
) -> type[Module]:
    async def run(self, entity):
        if error:
            raise ModuleError(error)
        return [self.emit(entity, out_type, out_value, **data)]

    return type(
        f"Fake_{name}",
        (Module,),
        {
            "name": name,
            "description": f"módulo falso {name}",
            "consumes": frozenset(consumes),
            "produces": frozenset({out_type}),
            "requires_key": key,
            "passive": passive,
            "run": run,
        },
    )


def use_modules(monkeypatch, mods: list[type[Module]]) -> None:
    monkeypatch.setattr(registry, "discover", lambda: sorted(mods, key=lambda m: m.name))


@pytest.fixture(autouse=True)
def wide_console(monkeypatch):
    # Evita que Rich parta las tablas a 80 columnas.
    monkeypatch.setattr(cli, "console", Console(width=200))


@pytest.fixture
def modules(monkeypatch):
    mods = [
        fake_module("fake_dns", {EntityType.DOMAIN}, EntityType.IP, "9.9.9.9", via="dns"),
        fake_module("fake_ip", {EntityType.IP}, EntityType.RECORD, "info:9.9.9.9", org="ACME"),
        fake_module("fake_email", {EntityType.EMAIL}, EntityType.USERNAME, "jdoe"),
        fake_module(
            "fake_user", {EntityType.USERNAME}, EntityType.PROFILE, "https://x.test/jdoe", site="X"
        ),
    ]
    use_modules(monkeypatch, mods)
    return mods


@pytest.fixture
def db(tmp_path):
    return str(tmp_path / "scans.db")


def values(data: dict) -> list[str]:
    return [e["value"] for e in data["entities"]]


def test_no_args_shows_help():
    result = runner.invoke(app, [])
    assert "Usage" in result.output
    assert "domain" in result.output


def test_version():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.output.startswith("osineitor ")


@pytest.mark.parametrize(
    ("command", "arg", "etype", "value"),
    [
        ("domain", "Example.COM", "domain", "example.com"),
        ("ip", "8.8.8.8", "ip", "8.8.8.8"),
        ("email", "Jane@Example.com", "email", "jane@example.com"),
        ("username", "JDoe", "username", "JDoe"),
    ],
)
def test_target_commands(modules, command, arg, etype, value):
    result = runner.invoke(app, [command, arg, "--no-save", "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["target"]["type"] == etype
    assert data["target"]["value"] == value


@pytest.mark.parametrize(
    ("arg", "etype", "value"),
    [
        ("EXAMPLE.com", "domain", "example.com"),
        ("8.8.8.8", "ip", "8.8.8.8"),
        ("Jane@Example.com", "email", "jane@example.com"),
        ("jdoe", "username", "jdoe"),
    ],
)
def test_scan_detects_target_type(modules, arg, etype, value):
    result = runner.invoke(app, ["scan", arg, "--no-save", "--json"])
    assert result.exit_code == 0, result.output
    target = json.loads(result.output)["target"]
    assert (target["type"], target["value"]) == (etype, value)


def test_scan_pivots_by_default_depth_two(modules):
    result = runner.invoke(app, ["scan", "example.com", "--no-save", "--json"])
    data = json.loads(result.output)
    assert data["depth"] == 2
    assert values(data) == ["9.9.9.9", "info:9.9.9.9"]


def test_domain_depth_one_does_not_pivot(modules):
    result = runner.invoke(app, ["domain", "example.com", "--no-save", "--json"])
    data = json.loads(result.output)
    assert data["depth"] == 1
    assert values(data) == ["9.9.9.9"]


def test_depth_out_of_range_is_rejected(modules):
    result = runner.invoke(app, ["domain", "example.com", "--depth", "9"])
    assert result.exit_code == 2


def test_module_filter(modules):
    args = ["scan", "example.com", "--no-save", "--json", "-m", "fake_dns"]
    data = json.loads(runner.invoke(app, args).output)
    assert values(data) == ["9.9.9.9"]


def test_unknown_module_is_rejected(modules):
    result = runner.invoke(app, ["domain", "example.com", "-m", "no_existe"])
    assert result.exit_code == 2
    assert "módulos desconocidos" in result.output
    assert "no_existe" in result.output


def test_legal_notice_is_shown_only_once(modules):
    first = runner.invoke(app, ["domain", "example.com", "--no-save"])
    second = runner.invoke(app, ["domain", "example.com", "--no-save"])
    assert "Aviso:" in first.output
    assert "Aviso:" not in second.output


def test_json_mode_prints_only_json(modules):
    result = runner.invoke(app, ["domain", "example.com", "--no-save", "--json"])
    assert "Aviso:" not in result.output
    assert json.loads(result.output)["target"]["value"] == "example.com"


def test_table_output_lists_entities_and_details(modules):
    result = runner.invoke(app, ["scan", "example.com", "--no-save"])
    assert result.exit_code == 0
    assert "Escaneando domain example.com" in result.output
    assert "9.9.9.9" in result.output
    assert "via=dns" in result.output
    assert "org=ACME" in result.output


def test_empty_result_says_so(monkeypatch):
    use_modules(monkeypatch, [])
    result = runner.invoke(app, ["domain", "example.com", "--no-save"])
    assert result.exit_code == 0
    assert "Sin resultados." in result.output


def test_events_are_rendered(monkeypatch):
    use_modules(
        monkeypatch,
        [
            fake_module("fake_boom", {EntityType.DOMAIN}, EntityType.IP, "1.1.1.1", error="cuota"),
            fake_module("fake_keyed", {EntityType.DOMAIN}, EntityType.IP, "2.2.2.2", key="fakekey"),
            fake_module(
                "fake_active", {EntityType.DOMAIN}, EntityType.IP, "3.3.3.3", passive=False
            ),
        ],
    )
    result = runner.invoke(app, ["domain", "example.com", "--no-save"])
    assert "error: fake_boom" in result.output
    assert "cuota" in result.output
    assert "skipped: fake_keyed" in result.output
    assert "fakekey" in result.output
    assert "skipped: fake_active" in result.output


def test_active_flag_enables_active_modules(monkeypatch):
    use_modules(
        monkeypatch,
        [fake_module("fake_active", {EntityType.DOMAIN}, EntityType.IP, "3.3.3.3", passive=False)],
    )
    off = json.loads(runner.invoke(app, ["domain", "example.com", "--no-save", "--json"]).output)
    on_args = ["domain", "example.com", "--no-save", "--json", "--active"]
    on = json.loads(runner.invoke(app, on_args).output)
    assert values(off) == []
    assert values(on) == ["3.3.3.3"]


def test_modules_lists_status_of_keys(monkeypatch):
    use_modules(
        monkeypatch,
        [
            fake_module("fake_free", {EntityType.DOMAIN}, EntityType.IP, "1.1.1.1"),
            fake_module("fake_keyed", {EntityType.IP}, EntityType.RECORD, "r", key="fakekey"),
            fake_module(
                "fake_active", {EntityType.DOMAIN}, EntityType.IP, "3.3.3.3", passive=False
            ),
        ],
    )
    without = runner.invoke(app, ["modules"])
    assert "fake_free" in without.output
    assert "fakekey ✗" in without.output
    assert "activo" in without.output
    monkeypatch.setenv("OSINEITOR_FAKEKEY_KEY", "secreto")
    assert "fakekey ✓" in runner.invoke(app, ["modules"]).output


def test_history_show_and_export_roundtrip(modules, db, tmp_path):
    saved = runner.invoke(app, ["domain", "example.com", "--db", db])
    assert saved.exit_code == 0

    history = runner.invoke(app, ["history", "--db", db])
    assert "example.com" in history.output
    assert "domain" in history.output

    shown = runner.invoke(app, ["show", "1", "--db", db])
    assert shown.exit_code == 0
    assert "9.9.9.9" in shown.output
    assert "scan #1" in shown.output

    out = tmp_path / "informe.md"
    exported = runner.invoke(app, ["export", "1", "-f", "md", "-o", str(out), "--db", db])
    assert exported.exit_code == 0
    assert "Informe guardado" in exported.output
    assert out.read_text(encoding="utf-8").startswith("# OSINEITOR")


@pytest.mark.parametrize(("fmt", "marker"), [("json", '"target"'), ("html", "<!doctype html>")])
def test_export_formats(modules, db, tmp_path, fmt, marker):
    runner.invoke(app, ["domain", "example.com", "--db", db])
    out = tmp_path / f"informe.{fmt}"
    result = runner.invoke(app, ["export", "1", "-f", fmt, "-o", str(out), "--db", db])
    assert result.exit_code == 0
    assert marker in out.read_text(encoding="utf-8")


def test_export_default_path(modules, db, tmp_path, monkeypatch):
    runner.invoke(app, ["domain", "example.com", "--db", db])
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["export", "1", "--db", db])
    assert result.exit_code == 0
    assert (tmp_path / "reports" / "osineitor-1-example.com.html").exists()


def test_export_rejects_unknown_format(modules, db):
    runner.invoke(app, ["domain", "example.com", "--db", db])
    result = runner.invoke(app, ["export", "1", "-f", "pdf", "--db", db])
    assert result.exit_code == 2
    assert "formato no soportado" in result.output


def test_show_and_export_reject_missing_scan(db):
    shown = runner.invoke(app, ["show", "99", "--db", db])
    exported = runner.invoke(app, ["export", "99", "--db", db])
    assert shown.exit_code == exported.exit_code == 2
    assert "no existe el scan 99" in shown.output
    assert "no existe el scan 99" in exported.output


def test_history_when_empty(db):
    result = runner.invoke(app, ["history", "--db", db])
    assert result.exit_code == 0
    assert "ID" in result.output


def test_no_save_does_not_write_history(modules, db):
    runner.invoke(app, ["domain", "example.com", "--no-save", "--db", db])
    assert "example.com" not in runner.invoke(app, ["history", "--db", db]).output


def test_config_set_and_show_masks_values():
    empty = runner.invoke(app, ["config", "show"])
    assert "No hay keys" in empty.output

    setter = runner.invoke(app, ["config", "set", "Shodan", "ABCDEFGHIJ"])
    assert setter.exit_code == 0
    assert "Key 'shodan' guardada" in setter.output

    shown = runner.invoke(app, ["config", "show"])
    assert "shodan = ABCD******" in shown.output
    assert "EFGHIJ" not in shown.output


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ({"a": 1, "b": None, "c": "", "d": [], "e": {}}, "a=1"),
        ({"hosts": [str(i) for i in range(12)]}, "hosts=0, 1, 2, 3, 4, 5, 6, 7 …"),
        ({"x": {"k": "ñ"}}, 'x={"k": "ñ"}'),
    ],
)
def test_summarize(data, expected):
    from osineitor.models import Entity

    entity = Entity(type=EntityType.RECORD, value="r", data=data)
    assert cli._summarize(entity) == expected


def test_summarize_is_capped():
    from osineitor.models import Entity

    entity = Entity(type=EntityType.RECORD, value="r", data={"big": "x" * 1000})
    assert len(cli._summarize(entity)) == 300

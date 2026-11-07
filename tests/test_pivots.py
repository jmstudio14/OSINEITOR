"""F10.5: sugerencia de pivotes. Propone, nunca ejecuta."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from osineitor import pivots
from osineitor.cli import app
from osineitor.config import Config
from osineitor.models import Entity, EntityType, ModuleRun, ScanResult
from osineitor.modules.base import Module
from osineitor.storage import Storage

runner = CliRunner()
SEED = Entity(type=EntityType.DOMAIN, value="example.com")


def make(name, consumes, *, passive=True, key=None, analyzer=False, missing=None):
    attrs = {
        "name": name,
        "description": name,
        "consumes": frozenset(consumes),
        "passive": passive,
        "requires_key": key,
        "analyzer": analyzer,
        "run": lambda self, entity: [],
    }
    if missing:
        attrs["unavailable"] = classmethod(lambda cls: missing)
    return type(name, (Module,), attrs)


DNS = make("dns", [EntityType.DOMAIN])
WHOIS = make("whois", [EntityType.DOMAIN, EntityType.IP])
PROBE = make("probe", [EntityType.DOMAIN], passive=False)
PAID = make("paid", [EntityType.DOMAIN], key="paid")
TOOL = make("tool", [EntityType.DOMAIN], missing="falta la herramienta")
FINDINGS = make("findings", [EntityType.DOMAIN], analyzer=True)
HUNTER = make("mails", [EntityType.EMAIL])
CLASSES = [DNS, WHOIS, PROBE, PAID, TOOL, FINDINGS, HUNTER]


def ent(kind, value) -> Entity:
    return Entity(type=kind, value=value, parent=SEED.key)


def scan(*entities, runs=()) -> ScanResult:
    return ScanResult(target=SEED, depth=1, entities=list(entities), runs=list(runs))


def test_only_what_was_not_investigated_and_can_run_is_suggested():
    sub = ent(EntityType.DOMAIN, "www.example.com")
    ip = ent(EntityType.IP, "203.0.113.7")
    runs = [ModuleRun(module="dns", status="ok", entity=sub.key)]
    found = pivots.suggest(scan(sub, ip, runs=runs), CLASSES, Config())
    by_entity = {s["entity"]: s for s in found}
    assert by_entity[sub.key]["modules"] == ["whois"]  # dns ya corrió; sin key/herramienta/activo
    assert by_entity[ip.key]["modules"] == ["whois"]
    assert by_entity[sub.key]["active_modules"] == ["probe"]


def test_a_module_that_failed_is_not_suggested_again():
    sub = ent(EntityType.DOMAIN, "www.example.com")
    runs = [ModuleRun(module=m, status="error", entity=sub.key) for m in ("dns", "whois")]
    assert pivots.suggest(scan(sub, runs=runs), CLASSES, Config()) == []


def test_a_configured_key_makes_the_module_a_candidate():
    sub = ent(EntityType.DOMAIN, "www.example.com")
    [s] = pivots.suggest(scan(sub), CLASSES, Config(keys={"paid": "k"}))
    assert "paid" in s["modules"]


def test_the_command_never_includes_active_modules_and_quotes_the_value():
    sub = ent(EntityType.DOMAIN, "www.example.com")
    [s] = pivots.suggest(scan(sub), CLASSES, Config())
    assert s["command"].startswith("osineitor scan www.example.com --depth 1")
    assert "--module dns" in s["command"] and "probe" not in s["command"]
    assert "--active" not in s["command"]


def test_personal_data_is_flagged_as_sensitive():
    mail = ent(EntityType.EMAIL, "ana@example.com")
    [s] = pivots.suggest(scan(mail), CLASSES, Config())
    assert s["sensitive"] is True and s["modules"] == ["mails"]
    assert "--purpose" in s["command"]


def test_nothing_to_suggest_on_a_fully_investigated_scan():
    sub = ent(EntityType.DOMAIN, "www.example.com")
    runs = [ModuleRun(module=m, status="ok", entity=sub.key) for m in ("dns", "whois", "paid")]
    assert pivots.suggest(scan(sub, runs=runs), CLASSES, Config(keys={"paid": "k"})) == []


def test_cli_suggest_json_and_table(tmp_path, monkeypatch):
    monkeypatch.setattr("osineitor.cli.registry.discover", lambda: CLASSES)
    db = tmp_path / "p.db"
    with Storage(db) as store:
        store.save(scan(ent(EntityType.DOMAIN, "www.example.com")))
        store.save(scan())
    data = json.loads(runner.invoke(app, ["suggest", "1", "--db", str(db), "--json"]).stdout)
    assert data["scan_id"] == 1 and data["suggestions"][0]["entity"] == "domain:www.example.com"
    assert "osineitor scan" in runner.invoke(app, ["suggest", "1", "--db", str(db)]).stdout
    assert "Nada que sugerir" in runner.invoke(app, ["suggest", "2", "--db", str(db)]).stdout
    assert runner.invoke(app, ["suggest", "9", "--db", str(db)]).exit_code != 0

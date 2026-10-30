"""`--scope`: lo que cae fuera del alcance declarado no entra en el resultado ni se investiga."""

from __future__ import annotations

import json
import sqlite3

import pytest
from typer.testing import CliRunner

from osineitor.cli import app
from osineitor.engine import Engine
from osineitor.models import Entity, EntityType, ScanResult
from osineitor.modules.base import Module
from osineitor.scope import Scope, ScopeError
from tests.test_cli import use_modules

runner = CliRunner()
SEED = Entity(type=EntityType.DOMAIN, value="example.com")

# Dominios que parecen del objetivo y no lo son, y lo que sí es suyo.
TRAPS = ["evil.test", "example.com.evil.test", "notexample.com", "xexample.com"]
INSIDE = ["www.example.com", "a.b.example.com"]


def entity(etype: EntityType, value: str) -> Entity:
    return Entity(type=etype, value=value)


def trap_module() -> type[Module]:
    """Módulo que, desde un dominio, emite entidades dentro y fuera del alcance."""

    async def run(self, entity_):
        out = [self.emit(entity_, EntityType.DOMAIN, d) for d in [*INSIDE, *TRAPS]]
        out += [self.emit(entity_, EntityType.IP, ip) for ip in ("203.0.113.5", "198.51.100.9")]
        out.append(self.emit(entity_, EntityType.EMAIL, "ana@evil.test"))
        out.append(self.emit(entity_, EntityType.URL, "https://evil.test/a"))
        out.append(self.emit(entity_, EntityType.URL, "https://www.example.com/a"))
        out.append(self.emit(entity_, EntityType.SERVICE, "198.51.100.9:443"))
        out.append(self.emit(entity_, EntityType.RECORD, "TXT v=spf1 -all"))
        return out

    return type(
        "Trap",
        (Module,),
        {
            "name": "trap",
            "description": "test",
            "consumes": frozenset({EntityType.DOMAIN}),
            "run": run,
        },
    )


SCOPE = Scope.parse({"domains": ["Example.com"], "ips": ["203.0.113.0/24"]})


# --- Scope.allows ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("etype", "value", "allowed"),
    [
        (EntityType.DOMAIN, "example.com", True),
        (EntityType.DOMAIN, "www.example.com", True),
        (EntityType.DOMAIN, "example.com.evil.test", False),
        (EntityType.DOMAIN, "notexample.com", False),
        (EntityType.DOMAIN, "evil.test", False),
        (EntityType.IP, "203.0.113.200", True),
        (EntityType.IP, "203.0.114.1", False),
        (EntityType.EMAIL, "ana@example.com", True),
        (EntityType.EMAIL, "ana@notexample.com", False),
        (EntityType.URL, "https://www.example.com/x?y=example.com", True),
        (EntityType.URL, "https://evil.test/example.com", False),
        (EntityType.SERVICE, "203.0.113.5:443", True),
        (EntityType.SERVICE, "198.51.100.9:443", False),
        (EntityType.RECORD, "TXT v=spf1 -all", True),  # sin host: hereda
        (EntityType.USERNAME, "ana", True),
    ],
)
def test_allows_by_exact_domain_or_subdomain_and_by_network(etype, value, allowed):
    assert SCOPE.allows(entity(etype, value)) is allowed


def test_exclude_always_wins_over_what_is_included():
    scope = Scope.parse(
        {
            "domains": ["example.com"],
            "ips": ["203.0.113.0/24"],
            "exclude": ["admin.example.com", "203.0.113.9"],
        }
    )
    assert scope.allows(entity(EntityType.DOMAIN, "www.example.com"))
    assert not scope.allows(entity(EntityType.DOMAIN, "admin.example.com"))
    assert not scope.allows(entity(EntityType.DOMAIN, "x.admin.example.com"))
    assert not scope.allows(entity(EntityType.IP, "203.0.113.9"))
    assert scope.allows(entity(EntityType.IP, "203.0.113.10"))


def test_an_absent_list_does_not_restrict_that_kind_of_entity():
    only_domains = Scope.parse({"domains": ["example.com"]})
    assert only_domains.allows(entity(EntityType.IP, "8.8.8.8"))
    only_ips = Scope.parse({"ips": ["203.0.113.0/24"]})
    assert only_ips.allows(entity(EntityType.DOMAIN, "anything.test"))
    assert not only_ips.allows(entity(EntityType.IP, "8.8.8.8"))


def test_domains_are_normalised_and_idn_is_compared_as_punycode():
    scope = Scope.parse({"domains": ["*.Münich.DE."]})
    assert scope.domains == ("xn--mnich-kva.de",)
    assert scope.allows(entity(EntityType.DOMAIN, "www.xn--mnich-kva.de"))


@pytest.mark.parametrize(
    "raw",
    [
        None,
        [],
        "example.com",
        {},
        {"exclude": ["a.example.com"]},  # solo excluir no declara alcance
        {"domains": []},
        {"domains": "example.com"},
        {"domains": ["example.com", 7]},
        {"domains": ["example.com"], "extra": ["x"]},
        {"ips": ["no-es-una-ip/99"]},
        {"domains": ["no es un dominio"]},
        {"domains": ["example.com"], "exclude": ["???"]},
    ],
)
def test_an_invalid_scope_is_rejected(raw):
    with pytest.raises(ScopeError):
        Scope.parse(raw)


def test_from_file_reports_unreadable_and_broken_yaml(tmp_path):
    with pytest.raises(ScopeError, match="no se puede leer"):
        Scope.from_file(tmp_path / "no-existe.yml")
    broken = tmp_path / "roto.yml"
    broken.write_text("domains: [example.com", encoding="utf-8")
    with pytest.raises(ScopeError, match="YAML"):
        Scope.from_file(broken)


# --- motor ----------------------------------------------------------------------------------------


async def test_engine_drops_the_out_of_scope_entities_and_never_pivots_on_them(ctx):
    result = await Engine(ctx, [trap_module()], depth=2, scope=SCOPE).run(SEED)
    values = {e.value for e in result.entities}
    assert values == {
        "www.example.com",
        "a.b.example.com",
        "203.0.113.5",
        "https://www.example.com/a",
        "TXT v=spf1 -all",
    }
    assert not values & set(TRAPS)
    dropped = [ev for ev in result.events if ev.message.startswith("fuera de alcance")]
    assert {ev.entity for ev in dropped} >= {f"domain:{d}" for d in TRAPS}
    assert all(ev.kind == "skipped" and ev.module == "engine" for ev in dropped)
    assert result.scope == {"domains": ["example.com"], "ips": ["203.0.113.0/24"]}


async def test_each_dropped_entity_is_reported_once_even_if_emitted_twice(ctx):
    result = await Engine(ctx, [trap_module()], depth=2, scope=SCOPE).run(SEED)
    keys = [ev.entity for ev in result.events if ev.message.startswith("fuera de alcance")]
    assert len(keys) == len(set(keys))


async def test_without_a_scope_everything_comes_in(ctx):
    result = await Engine(ctx, [trap_module()]).run(SEED)
    assert set(TRAPS) <= {e.value for e in result.entities}
    assert result.scope is None


# --- BD -------------------------------------------------------------------------------------------


def test_the_scope_survives_the_database_roundtrip(storage):
    declared = {"domains": ["example.com"], "exclude": ["admin.example.com"]}
    saved = ScanResult(target=SEED, depth=1, scope=declared)
    assert storage.load(storage.save(saved)).scope == declared
    assert storage.load(storage.save(ScanResult(target=SEED, depth=1))).scope is None


def test_migrating_a_v5_database_adds_the_scope_column(tmp_path):
    from osineitor.storage import MIGRATIONS, Storage

    path = tmp_path / "v5.db"
    conn = sqlite3.connect(path)
    for statement in ";".join(MIGRATIONS[:5]).split(";"):
        if statement.strip():
            conn.execute(statement)
    conn.execute("PRAGMA user_version = 5")
    conn.commit()
    conn.close()
    with Storage(path) as store:
        assert store.load(store.save(ScanResult(target=SEED, depth=1, scope={"ips": ["::1"]})))
        assert store._conn.execute("SELECT scope FROM scans").fetchone() == ('{"ips": ["::1"]}',)


# --- CLI ------------------------------------------------------------------------------------------


@pytest.fixture
def scope_file(tmp_path):
    path = tmp_path / "scope.yml"
    path.write_text(
        "domains: [example.com]\nips: [203.0.113.0/24]\nexclude: [a.b.example.com]\n",
        encoding="utf-8",
    )
    return path


def test_scope_keeps_trap_entities_out_of_json_and_ndjson(monkeypatch, tmp_path, scope_file):
    use_modules(monkeypatch, [trap_module()])
    db = str(tmp_path / "s.db")
    base = ["domain", "example.com", "--scope", str(scope_file), "--db", db]

    run = runner.invoke(app, [*base, "--json"])
    assert run.exit_code == 0, run.output
    scan = json.loads(run.stdout)
    values = {e["value"] for e in scan["entities"]}
    assert values == {
        "www.example.com",
        "203.0.113.5",
        "https://www.example.com/a",
        "TXT v=spf1 -all",
    }
    assert scan["scope"]["exclude"] == ["a.b.example.com"]

    out = runner.invoke(app, [*base, "--ndjson"]).stdout
    lines = [json.loads(line) for line in out.splitlines()]
    seen = {e["entity"]["value"] for e in lines if e["type"] == "entity"}
    assert not seen & set(TRAPS)
    start = next(e for e in lines if e["type"] == "scan.start")
    assert start["scope"]["domains"] == ["example.com"]


def test_a_broken_scope_file_is_a_usage_error(monkeypatch, tmp_path):
    use_modules(monkeypatch, [trap_module()])
    bad = tmp_path / "mal.yml"
    bad.write_text("domains: [example.com\n", encoding="utf-8")
    for path in (bad, tmp_path / "no-existe.yml"):
        run = runner.invoke(app, ["domain", "example.com", "--scope", str(path), "--no-save"])
        assert run.exit_code == 2
    unknown = tmp_path / "clave.yml"
    unknown.write_text("dominios: [example.com]\n", encoding="utf-8")
    run = runner.invoke(app, ["domain", "example.com", "--scope", str(unknown), "--no-save"])
    assert run.exit_code == 2


def test_a_target_outside_the_scope_is_a_usage_error(monkeypatch, scope_file):
    use_modules(monkeypatch, [trap_module()])
    run = runner.invoke(app, ["domain", "evil.test", "--scope", str(scope_file), "--no-save"])
    assert run.exit_code == 2
    assert "fuera del alcance" in run.output

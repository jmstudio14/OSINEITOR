"""`--purpose`: para qué se hace el scan, y `require_purpose` para exigirlo en emails/usernames."""

from __future__ import annotations

import json
import re
import sqlite3

import pytest
from typer.testing import CliRunner

from osineitor.cli import app
from osineitor.config import Config, config_path
from osineitor.models import Entity, EntityType, ScanResult
from osineitor.report import to_html, to_markdown
from tests.test_cli import fake_module, use_modules

runner = CliRunner()
ANSI = re.compile(r"\x1b\[[0-9;]*m")  # en CI Rich colorea el panel de error y parte los textos
SEED = Entity(type=EntityType.DOMAIN, value="example.com")
PURPOSE = "Auditoría autorizada de la web de Acme (ticket 42)"


@pytest.fixture
def modules(monkeypatch):
    use_modules(
        monkeypatch,
        [
            fake_module("fake_dns", {EntityType.DOMAIN}, EntityType.IP, "9.9.9.9"),
            fake_module("fake_mail", {EntityType.EMAIL}, EntityType.DOMAIN, "acme.test"),
            fake_module("fake_user", {EntityType.USERNAME}, EntityType.DOMAIN, "acme.test"),
        ],
    )


def require(monkeypatch, value: str = "1") -> None:
    monkeypatch.setenv("OSINEITOR_REQUIRE_PURPOSE", value)


# --- configuración --------------------------------------------------------------------------------


def test_require_purpose_roundtrips_through_the_config_file():
    config = Config(require_purpose=True)
    config.save()
    assert Config.load().require_purpose is True
    assert "require_purpose = true" in config_path().read_text(encoding="utf-8")
    Config().save()
    assert Config.load().require_purpose is False


def test_an_old_config_without_the_setting_does_not_require_a_purpose():
    config_path().parent.mkdir(parents=True, exist_ok=True)
    config_path().write_text("[settings]\ntimeout = 5.0\n\n[keys]\n", encoding="utf-8")
    assert Config.load().purpose_required() is False


@pytest.mark.parametrize(
    ("env", "in_file", "expected"),
    [
        ("1", False, True),
        ("TRUE", False, True),
        ("0", True, False),  # la variable manda sobre el fichero
        ("no", True, False),
        ("", True, True),
        ("", False, False),
        ("quizá", True, True),  # un valor que no entiende no cambia lo configurado
    ],
)
def test_the_environment_overrides_the_file(monkeypatch, env, in_file, expected):
    monkeypatch.setenv("OSINEITOR_REQUIRE_PURPOSE", env)
    assert Config(require_purpose=in_file).purpose_required() is expected


def test_the_environment_value_is_never_written_to_the_file(monkeypatch):
    require(monkeypatch)
    Config.load().save()
    monkeypatch.delenv("OSINEITOR_REQUIRE_PURPOSE")
    assert Config.load().purpose_required() is False


# --- CLI ------------------------------------------------------------------------------------------


def test_the_purpose_is_saved_shown_and_sent_in_scan_start(modules, tmp_path):
    db = str(tmp_path / "s.db")
    out = runner.invoke(
        app, ["domain", "example.com", "--purpose", f"  {PURPOSE} ", "--ndjson", "--db", db]
    ).stdout
    events = [json.loads(line) for line in out.splitlines()]
    assert next(e for e in events if e["type"] == "scan.start")["purpose"] == PURPOSE

    shown = json.loads(runner.invoke(app, ["show", "1", "--db", db, "--json"]).stdout)
    assert shown["purpose"] == PURPOSE
    human = runner.invoke(app, ["show", "1", "--db", db], terminal_width=200).stdout
    assert PURPOSE in ANSI.sub("", human)


def test_without_the_option_the_purpose_is_empty(modules, tmp_path):
    db = str(tmp_path / "s.db")
    runner.invoke(app, ["domain", "example.com", "--quiet", "--db", db])
    shown = json.loads(runner.invoke(app, ["show", "1", "--db", db, "--json"]).stdout)
    assert shown["purpose"] is None


def test_the_purpose_can_come_from_the_environment(modules, monkeypatch, tmp_path):
    monkeypatch.setenv("OSINEITOR_PURPOSE", PURPOSE)
    db = str(tmp_path / "s.db")
    runner.invoke(app, ["domain", "example.com", "--quiet", "--db", db])
    shown = json.loads(runner.invoke(app, ["show", "1", "--db", db, "--json"]).stdout)
    assert shown["purpose"] == PURPOSE


@pytest.mark.parametrize("bad", ["", "   ", "dos\nlíneas", "x" * 501])
def test_an_invalid_purpose_is_a_usage_error(modules, bad):
    run = runner.invoke(app, ["domain", "example.com", "--purpose", bad, "--no-save"])
    assert run.exit_code == 2


@pytest.mark.parametrize(
    "args",
    [["email", "ana@example.com"], ["username", "ana"], ["scan", "ana@example.com"]],
)
def test_email_and_username_scans_need_a_purpose_when_it_is_required(modules, monkeypatch, args):
    require(monkeypatch)
    run = runner.invoke(app, [*args, "--no-save"])
    assert run.exit_code == 2
    assert "--purpose" in ANSI.sub("", run.output)
    ok = runner.invoke(app, [*args, "--purpose", PURPOSE, "--no-save", "--quiet"])
    assert ok.exit_code == 0, ok.output


def test_the_setting_in_the_file_also_requires_it(modules):
    Config(require_purpose=True).save()
    assert runner.invoke(app, ["email", "ana@example.com", "--no-save"]).exit_code == 2


def test_domain_and_ip_scans_are_never_forced(modules, monkeypatch):
    require(monkeypatch)
    for args in (["domain", "example.com"], ["ip", "9.9.9.9"], ["scan", "example.com"]):
        run = runner.invoke(app, [*args, "--no-save", "--quiet"])
        assert run.exit_code == 0, run.output


def test_without_the_setting_nothing_is_required(modules):
    run = runner.invoke(app, ["email", "ana@example.com", "--no-save", "--quiet"])
    assert run.exit_code == 0, run.output


# --- BD e informes --------------------------------------------------------------------------------


def test_the_purpose_survives_the_database_roundtrip(storage):
    saved = storage.save(ScanResult(target=SEED, depth=1, purpose=PURPOSE))
    assert storage.load(saved).purpose == PURPOSE


def test_migrating_a_v6_database_adds_the_purpose_column(tmp_path):
    from osineitor.storage import MIGRATIONS, Storage

    path = tmp_path / "v6.db"
    conn = sqlite3.connect(path)
    for statement in ";".join(MIGRATIONS[:6]).split(";"):
        if statement.strip():
            conn.execute(statement)
    conn.execute("PRAGMA user_version = 6")
    conn.commit()
    conn.close()
    with Storage(path) as store:
        assert store.load(store.save(ScanResult(target=SEED, depth=1, purpose="x"))).purpose == "x"


def test_the_reports_state_the_purpose_and_escape_it():
    result = ScanResult(target=SEED, depth=1, purpose="<script>alert(1)</script>")
    assert "Propósito" in to_markdown(result)
    html = to_html(result)
    assert "Propósito" in html
    assert "<script>alert" not in html
    assert "&lt;script&gt;" in html

"""F3.7: `--only-types` y `--exclude` recortan lo que se muestra y exporta, no lo que se guarda."""

from __future__ import annotations

import json
import re

import pytest
from typer.testing import CliRunner

from osineitor.cli import app
from osineitor.models import EntityType
from tests.test_cli import fake_module, use_modules

runner = CliRunner()
ANSI = re.compile(r"\x1b\[[0-9;]*m")


@pytest.fixture
def modules(monkeypatch):
    use_modules(
        monkeypatch,
        [
            fake_module("fake_dns", {EntityType.DOMAIN}, EntityType.IP, "9.9.9.9"),
            fake_module("fake_rec", {EntityType.DOMAIN}, EntityType.RECORD, "txt:v=spf1"),
            fake_module("fake_org", {EntityType.DOMAIN}, EntityType.ORGANIZATION, "Acme"),
        ],
    )


def types_of(output: str) -> list[str]:
    return sorted(e["type"] for e in json.loads(output)["entities"])


def scan(*args: str):
    return runner.invoke(app, ["domain", "example.com", "--json", "--no-save", *args])


def test_without_filters_everything_is_shown(modules):
    assert types_of(scan().output) == ["ip", "organization", "record"]


def test_only_types_keeps_just_those(modules):
    assert types_of(scan("--only-types", "ip").output) == ["ip"]


def test_exclude_hides_those(modules):
    assert types_of(scan("--exclude", "record").output) == ["ip", "organization"]


def test_the_options_repeat_and_accept_commas_in_any_case(modules):
    assert types_of(scan("--only-types", "IP,record").output) == ["ip", "record"]
    assert types_of(scan("--only-types", "ip", "--only-types", "organization").output) == [
        "ip",
        "organization",
    ]


def test_exclude_wins_over_only_types(modules):
    assert types_of(scan("--only-types", "ip,record", "--exclude", "record").output) == ["ip"]


def test_an_unknown_type_is_a_usage_error_that_lists_it(modules):
    done = scan("--only-types", "ip,nada")
    assert done.exit_code == 2
    assert "nada" in ANSI.sub("", done.output)


def test_the_human_output_is_filtered_too(modules):
    done = runner.invoke(app, ["domain", "example.com", "--no-save", "--exclude", "ip,record"])
    table = done.output.split("Módulos")[0].split("organization")[-1]
    assert "Acme" in done.output and "9.9.9.9" not in table and "spf1" not in table


def test_the_exit_code_and_the_ndjson_stream_ignore_the_filter(modules):
    done = runner.invoke(
        app, ["domain", "example.com", "--ndjson", "--no-save", "--only-types", "ip"]
    )
    events = [json.loads(line) for line in done.output.splitlines() if line.startswith("{")]
    shown = [e["entity"]["type"] for e in events if e["type"] == "entity"]
    assert sorted(shown) == ["ip", "organization", "record"]


def test_what_is_saved_is_complete_and_show_and_export_can_filter(modules, tmp_path):
    db = str(tmp_path / "scans.db")
    saved = runner.invoke(app, ["domain", "example.com", "--json", "--db", db, "--exclude", "ip"])
    assert types_of(saved.output) == ["organization", "record"]
    whole = runner.invoke(app, ["show", "1", "--json", "--db", db])
    assert types_of(whole.output) == ["ip", "organization", "record"]  # en la BD está todo
    only = runner.invoke(app, ["show", "1", "--json", "--db", db, "--only-types", "ip"])
    assert types_of(only.output) == ["ip"]
    out = tmp_path / "informe.json"
    runner.invoke(
        app, ["export", "1", "-f", "json", "-o", str(out), "--db", db, "--exclude", "ip,record"]
    )
    assert types_of(out.read_text(encoding="utf-8")) == ["organization"]
    bad = runner.invoke(app, ["show", "1", "--db", db, "--exclude", "nada"])
    assert bad.exit_code == 2

"""F8.7: importar resultados de Subfinder (JSONL) y de Maigret (JSON simple y ndjson)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from osineitor.cli import app
from osineitor.models import EntityType
from osineitor.storage import Storage
from osineitor.tool_import import ToolImportError, parse_maigret, parse_subfinder

runner = CliRunner()


def write(path: Path, *lines: object) -> Path:
    path.write_text(
        "\n".join(line if isinstance(line, str) else json.dumps(line) for line in lines),
        encoding="utf-8",
    )
    return path


def values(result, kind: EntityType) -> list[str]:
    return sorted(e.value for e in result.entities if e.type == kind)


def test_subfinder_hosts_ips_and_sources(tmp_path):
    path = write(
        tmp_path / "sub.json",
        {"host": "www.example.com", "input": "example.com", "source": "crtsh"},
        {"host": "API.example.com", "input": "example.com", "sources": ["alienvault", "crtsh"]},
        {"host": "mail.example.com", "ip": "203.0.113.5", "input": "example.com", "source": "x"},
        "",
    )
    result = parse_subfinder(path)
    assert result.target.type == EntityType.RECORD and result.target.value == "subfinder:sub.json"
    assert result.target.data["inputs"] == ["example.com"]
    assert len(result.target.data["sha256"]) == 64
    assert values(result, EntityType.DOMAIN) == [
        "api.example.com",
        "mail.example.com",
        "www.example.com",
    ]
    assert values(result, EntityType.IP) == ["203.0.113.5"]
    api = next(e for e in result.entities if e.value == "api.example.com")
    assert api.data["sources"] == ["alienvault", "crtsh"] and api.data["subdomain"] is True
    assert all(e.source == "import_subfinder" for e in result.entities)
    assert result.runs[0].module == "import_subfinder"


def test_subfinder_discards_invalid_lines_and_says_so(tmp_path):
    path = write(
        tmp_path / "s.json",
        {"host": "ok.example.com", "input": "example.com", "source": "a"},
        "esto no es json",
        {"host": "no es un host", "input": "example.com"},
        {"input": "example.com"},
        ["lista"],
    )
    result = parse_subfinder(path)
    assert values(result, EntityType.DOMAIN) == ["ok.example.com"]
    [event] = result.events
    assert event.kind == "skipped" and "4" in event.message


@pytest.mark.parametrize("content", ["", "esto no es json\notra línea", '{"nada": 1}'])
def test_subfinder_rejects_files_without_a_single_result(tmp_path, content):
    path = tmp_path / "s.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ToolImportError, match="Subfinder"):
        parse_subfinder(path)


def test_oversized_or_missing_files_fail_cleanly(tmp_path, monkeypatch):
    with pytest.raises(ToolImportError, match="no se puede leer"):
        parse_subfinder(tmp_path / "no-existe.json")
    monkeypatch.setattr("osineitor.tool_import.MAX_BYTES", 10)
    big = write(tmp_path / "big.json", {"host": "a.example.com", "input": "example.com"})
    with pytest.raises(ToolImportError, match="demasiado grande"):
        parse_subfinder(big)


SIMPLE = {
    "GitHub": {
        "username": "maria",
        "url_main": "https://github.com/",
        "url_user": "https://github.com/maria",
        "status": {"status": "Claimed", "site_name": "GitHub"},
        "http_status": 200,
    },
    "Gone": {"username": "maria", "url_user": "https://gone.example/maria", "status": "Available"},
    "Roto": {"username": "maria", "url_user": "no es una url", "status": "Claimed"},
}


def test_maigret_simple_report(tmp_path):
    result = parse_maigret(write(tmp_path / "report_maria_simple.json", SIMPLE))
    assert result.target.value == "maigret:report_maria_simple.json"
    assert values(result, EntityType.PROFILE) == ["https://github.com/maria"]
    profile = result.entities[0]
    assert profile.data["site"] == "GitHub" and profile.data["username"] == "maria"
    assert "verified" not in profile.data and profile.source == "import_maigret"
    assert "1" in result.events[0].message  # el de URL rota se cuenta como descartado


def test_maigret_ndjson_report(tmp_path):
    lines = [{**entry, "sitename": name} for name, entry in SIMPLE.items()]
    result = parse_maigret(write(tmp_path / "report.ndjson", *lines))
    assert values(result, EntityType.PROFILE) == ["https://github.com/maria"]


def test_maigret_single_line_ndjson_is_not_mistaken_for_a_simple_report(tmp_path):
    entry = {**SIMPLE["GitHub"], "sitename": "GitHub"}
    result = parse_maigret(write(tmp_path / "one.ndjson", entry))
    assert values(result, EntityType.PROFILE) == ["https://github.com/maria"]


@pytest.mark.parametrize("content", ["", "no es json", "[1, 2]", '{"a": 1}'])
def test_maigret_rejects_other_files(tmp_path, content):
    path = tmp_path / "m.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ToolImportError, match="Maigret"):
        parse_maigret(path)


def test_cli_import_saves_a_scan(tmp_path):
    db = tmp_path / "i.db"
    sub = write(tmp_path / "s.json", {"host": "www.example.com", "input": "example.com"})
    out = runner.invoke(app, ["import", "subfinder", str(sub), "--db", str(db), "--json"])
    assert out.exit_code == 0, out.stdout
    assert json.loads(out.stdout)["target"]["value"] == "subfinder:s.json"
    mai = write(tmp_path / "m.json", SIMPLE)
    assert runner.invoke(app, ["import", "maigret", str(mai), "--db", str(db)]).exit_code == 0
    with Storage(db) as store:
        assert [row[2] for row in store.list_scans(10)] == ["maigret:m.json", "subfinder:s.json"]
    nosave = runner.invoke(app, ["import", "subfinder", str(sub), "--db", str(db), "--no-save"])
    assert nosave.exit_code == 0
    with Storage(db) as store:
        assert len(store.list_scans(10)) == 2


def test_cli_import_reports_a_bad_file_as_a_usage_error(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("nada", encoding="utf-8")
    for tool in ("subfinder", "maigret"):
        res = runner.invoke(app, ["import", tool, str(bad), "--db", str(tmp_path / "x.db")])
        assert res.exit_code != 0 and "Traceback" not in res.output

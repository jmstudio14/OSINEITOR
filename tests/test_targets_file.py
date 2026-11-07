"""F8.7: `scan --targets-file` con una lista de objetivos."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from osineitor import cli
from osineitor.cli import app
from osineitor.models import Entity, ScanResult
from osineitor.storage import Storage
from osineitor.targets import MAX_TARGETS, TargetsError, read_targets

runner = CliRunner()


def listing(tmp_path, text: str):
    path = tmp_path / "objetivos.txt"
    path.write_text(text, encoding="utf-8")
    return path


def test_read_targets_skips_blanks_comments_and_duplicates(tmp_path):
    path = listing(
        tmp_path,
        "﻿# clientes\nexample.com\n\n  203.0.113.7  \nexample.com\n# nada\nmaria@example.com\n",
    )
    assert read_targets(path) == ["example.com", "203.0.113.7", "maria@example.com"]


@pytest.mark.parametrize("text", ["", "\n\n", "# solo comentarios\n"])
def test_read_targets_rejects_empty_lists(tmp_path, text):
    with pytest.raises(TargetsError, match="no tiene ningún objetivo"):
        read_targets(listing(tmp_path, text))


def test_read_targets_limits_the_list(tmp_path):
    many = "\n".join(f"host{i}.example.com" for i in range(MAX_TARGETS + 1))
    with pytest.raises(TargetsError, match="máximo"):
        read_targets(listing(tmp_path, many))


def test_read_targets_fails_cleanly(tmp_path):
    with pytest.raises(TargetsError, match="no se puede leer"):
        read_targets(tmp_path / "no-existe.txt")
    binary = tmp_path / "b.txt"
    binary.write_bytes(b"\xff\xfe\x00\x00")
    with pytest.raises(TargetsError, match="UTF-8"):
        read_targets(binary)


@pytest.fixture
def fake_scan(monkeypatch):
    seen: list[str] = []

    async def scan(seed, opts, live, sink=None):
        seen.append(seed.value)
        return ScanResult(target=Entity(type=seed.type, value=seed.value), depth=opts.depth)

    monkeypatch.setattr(cli, "_scan", scan)
    return seen


def test_batch_runs_one_scan_per_target_and_saves_each(tmp_path, fake_scan):
    db = tmp_path / "b.db"
    path = listing(tmp_path, "example.com\nexample.org\n")
    res = runner.invoke(app, ["scan", "--targets-file", str(path), "--db", str(db), "--quiet"])
    assert res.exit_code == 0, res.output
    assert fake_scan == ["example.com", "example.org"]
    with Storage(db) as store:
        assert sorted(row[2] for row in store.list_scans(10)) == ["example.com", "example.org"]


def test_batch_needs_exactly_one_source_of_targets(tmp_path, fake_scan):
    path = listing(tmp_path, "example.com\n")
    both = runner.invoke(app, ["scan", "example.com", "--targets-file", str(path)])
    neither = runner.invoke(app, ["scan"])
    assert both.exit_code == 2 and neither.exit_code == 2 and fake_scan == []


def test_batch_rejects_json_because_it_would_not_be_one_document(tmp_path, fake_scan):
    path = listing(tmp_path, "example.com\n")
    res = runner.invoke(app, ["scan", "--targets-file", str(path), "--json", "--no-save"])
    assert res.exit_code == 2 and "--ndjson" in res.output and fake_scan == []


def test_one_bad_target_does_not_stop_the_rest_but_sets_the_exit_code(tmp_path, fake_scan):
    scope_file = tmp_path / "scope.yml"
    scope_file.write_text("domains: [example.com]\n", encoding="utf-8")
    path = listing(tmp_path, "fuera.org\nexample.com\n")
    res = runner.invoke(
        app,
        ["scan", "--targets-file", str(path), "--scope", str(scope_file), "--no-save", "--quiet"],
    )
    assert fake_scan == ["example.com"]  # el de fuera de alcance se rechazó, el otro corrió
    assert res.exit_code == 2 and "fuera.org" in res.output


def test_a_missing_targets_file_is_a_usage_error(tmp_path, fake_scan):
    res = runner.invoke(app, ["scan", "--targets-file", str(tmp_path / "no.txt")])
    assert res.exit_code == 2 and fake_scan == []

"""Resumen de scans de `history --json`: estado y recuentos sin cargar cada scan."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime

from typer.testing import CliRunner

from osineitor.cli import app
from osineitor.models import Entity, EntityType, ModuleRun, ScanEvent, ScanResult
from osineitor.storage import MIGRATIONS, Storage


def result(**kwargs) -> ScanResult:
    return ScanResult(
        target=Entity(type=EntityType.DOMAIN, value="example.com"),
        depth=1,
        started_at=datetime(2026, 11, 8, tzinfo=UTC),
        **kwargs,
    )


def finding(severity: str | None) -> Entity:
    data = {"severity": severity} if severity else {}
    return Entity(type=EntityType.FINDING, value=f"regla: {severity}", data=data)


def test_digest_counts_entities_findings_and_modules(tmp_path):
    with Storage(tmp_path / "s.db") as storage:
        scan_id = storage.save(
            result(
                entities=[
                    finding("high"),
                    finding("high"),
                    finding("critical"),
                    finding(None),
                    Entity(type=EntityType.IP, value="9.9.9.9"),
                ],
                runs=[
                    ModuleRun(module="dns", status="ok"),
                    ModuleRun(module="otx", status="error"),
                    ModuleRun(module="otx", status="error"),
                ],
            )
        )
        [digest] = storage.scan_digests()
    assert digest["id"] == scan_id and digest["status"] == "complete"
    assert digest["entities"] == 5 and digest["target"] == "example.com"
    assert digest["severity"] == {"high": 2, "critical": 1, "info": 1}
    assert digest["by_type"] == {"finding": 4, "ip": 1}
    assert digest["modules"] == {"ok": 1, "error": 2}


def test_status_follows_the_same_priority_as_the_scan_result(tmp_path):
    budget = ScanEvent(kind="budget", module="x", message="")
    cancelled = ScanEvent(kind="cancelled", module="x", message="")
    cases = (
        ([], "complete"),
        ([budget], "truncated"),
        ([cancelled], "cancelled"),
        ([cancelled, budget], "cancelled"),
        ([budget, cancelled], "cancelled"),
    )
    with Storage(tmp_path / "s.db") as storage:
        expected = {storage.save(result(events=events)): status for events, status in cases}
        digests = {d["id"]: d["status"] for d in storage.scan_digests(10)}
        for scan_id, status in expected.items():
            assert digests[scan_id] == status
            assert storage.load(scan_id).status == status  # no se separa de `show`


def test_limit_keeps_the_most_recent_and_order(tmp_path):
    with Storage(tmp_path / "s.db") as storage:
        ids = [storage.save(result(entities=[finding("low")])) for _ in range(5)]
        digests = storage.scan_digests(2)
    assert [d["id"] for d in digests] == [ids[4], ids[3]]
    assert all(d["severity"] == {"low": 1} for d in digests)


def test_an_empty_database_has_no_digests(tmp_path):
    with Storage(tmp_path / "s.db") as storage:
        assert storage.scan_digests() == []


def test_a_previous_schema_is_migrated_with_the_new_indexes(tmp_path):
    path = tmp_path / "s.db"
    with Storage(path) as storage:
        scan_id = storage.save(result(entities=[finding("high")]))
    with sqlite3.connect(path) as conn:
        conn.executescript(
            "DROP INDEX idx_entities_scan_type; DROP INDEX idx_events_scan;"
            " DROP INDEX idx_module_runs_scan; PRAGMA user_version = 10;"
        )
    with Storage(path) as storage:
        [digest] = storage.scan_digests()
    assert digest["id"] == scan_id and digest["severity"] == {"high": 1}
    conn = sqlite3.connect(path)
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}
    finally:
        conn.close()
    assert version == len(MIGRATIONS)
    assert {"idx_entities_scan_type", "idx_events_scan", "idx_module_runs_scan"} <= names


def test_the_cli_returns_the_digest_and_the_text_table_is_unchanged(tmp_path):
    db = tmp_path / "s.db"
    with Storage(db) as storage:
        storage.save(result(entities=[finding("medium")]))
    runner = CliRunner()
    out = runner.invoke(app, ["history", "--db", str(db), "--json"])
    assert out.exit_code == 0
    [row] = json.loads(out.stdout)
    assert row["status"] == "complete" and row["severity"] == {"medium": 1}
    text = runner.invoke(app, ["history", "--db", str(db)])
    assert text.exit_code == 0 and "example.com" in text.stdout

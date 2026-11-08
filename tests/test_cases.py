"""F7.2, F7.5 y F7.6: casos, búsqueda global y correlación entre casos."""

from __future__ import annotations

import json
import sqlite3

import pytest
from typer.testing import CliRunner

from osineitor.cli import app
from osineitor.models import Entity, EntityType, ScanResult
from osineitor.storage import MIGRATIONS, Storage, StorageError

runner = CliRunner()


def scan(target: str, *found: tuple[EntityType, str], ttype=EntityType.DOMAIN) -> ScanResult:
    return ScanResult(
        target=Entity(type=ttype, value=target),
        depth=1,
        entities=[Entity(type=t, value=v, source="fake") for t, v in found],
    )


def seed_two_cases(storage: Storage) -> tuple[int, int]:
    """Scan 1 en `caso-a`, scan 2 en `caso-b` (comparten una IP y `nginx`), scan 3 suelto."""
    a1 = storage.save(
        scan(
            "example.com",
            (EntityType.IP, "203.0.113.7"),
            (EntityType.EMAIL, "ana@example.com"),
            (EntityType.TECHNOLOGY, "nginx"),
        )
    )
    b1 = storage.save(
        scan(
            "other.org",
            (EntityType.IP, "203.0.113.7"),
            (EntityType.TECHNOLOGY, "nginx"),
            (EntityType.USERNAME, "ana"),
        )
    )
    storage.save(scan("unrelated.net", (EntityType.IP, "198.51.100.1")))
    ca, cb = storage.case_create("caso-a"), storage.case_create("caso-b")
    storage.case_add_scan(ca, a1)
    storage.case_add_scan(cb, b1)
    return ca, cb


def test_a_case_groups_scans_with_notes_and_tags(storage):
    first = storage.save(scan("example.com", (EntityType.IP, "203.0.113.7")))
    second = storage.save(scan("example.com", (EntityType.IP, "203.0.113.8")))
    case = storage.case_create("Investigación 1", "fraude del CEO", tags=["fraude", "urgente"])
    assert storage.case_add_scan(case, first) is True
    assert storage.case_add_scan(case, second) is True
    assert storage.case_add_scan(case, second) is False  # ya estaba
    storage.case_add_note(case, "El cliente confirma el dominio")
    got = storage.case_get("investigación 1")  # sin distinguir mayúsculas
    assert got["name"] == "Investigación 1" and got["description"] == "fraude del CEO"
    assert got["tags"] == ["fraude", "urgente"]
    assert [s["id"] for s in got["scans"]] == [first, second]
    assert [n["text"] for n in got["notes"]] == ["El cliente confirma el dominio"]


def test_case_names_are_unique_and_scans_must_exist(storage):
    case = storage.case_create("uno")
    with pytest.raises(StorageError, match="ya existe"):
        storage.case_create("UNO")
    with pytest.raises(StorageError, match="no existe el scan 99"):
        storage.case_add_scan(case, 99)
    assert storage.case_get("nada") is None and storage.case_id("nada") is None


def test_purging_a_scan_removes_it_from_its_case(storage):
    scan_id = storage.save(scan("example.com"))
    case = storage.case_create("uno")
    storage.case_add_scan(case, scan_id)
    storage.purge("9999-01-01")
    assert storage.case_get("uno")["scans"] == []


def test_search_finds_a_value_in_scans_and_seeds_with_their_cases(storage):
    seed_two_cases(storage)
    hits = storage.search("203.0.113.7")
    assert [(h["scan_id"], h["type"], h["cases"]) for h in hits] == [
        (2, "ip", ["caso-b"]),
        (1, "ip", ["caso-a"]),
    ]
    seed = storage.search("EXAMPLE.COM")  # la semilla también cuenta; sin distinguir mayúsculas
    assert [(h["scan_id"], h["type"], h["source"]) for h in seed] == [(1, "domain", None)]


def test_search_contains_and_type_filter(storage):
    seed_two_cases(storage)
    assert {h["value"] for h in storage.search("example", contains=True)} == {
        "example.com",
        "ana@example.com",
    }
    assert [h["value"] for h in storage.search("example", contains=True, types=["email"])] == [
        "ana@example.com"
    ]
    assert storage.search("no-existe") == []


def test_search_treats_wildcards_literally(storage):
    storage.save(scan("example.com", (EntityType.USERNAME, "a_b"), (EntityType.USERNAME, "axb")))
    assert [h["value"] for h in storage.search("a_b", contains=True)] == ["a_b"]


def test_correlation_reports_identifiers_shared_with_other_cases_only(storage):
    ca, cb = seed_two_cases(storage)
    found = storage.correlations(ca)
    # `nginx` (technology) es demasiado común y no cuenta; `ana` no es `ana@example.com`.
    assert [(c["type"], c["value"], c["cases"], c["scans"]) for c in found] == [
        ("ip", "203.0.113.7", ["caso-b"], [2])
    ]
    assert [(c["type"], c["value"]) for c in storage.correlations(cb)] == [("ip", "203.0.113.7")]


def test_correlation_ignores_the_same_case_and_includes_seeds(storage):
    one = storage.save(scan("example.com"))
    two = storage.save(scan("example.com"))
    other = storage.save(scan("example.com"))
    ca, cb = storage.case_create("a"), storage.case_create("b")
    storage.case_add_scan(ca, one)
    storage.case_add_scan(ca, two)  # mismo caso: no es una correlación
    assert storage.correlations(ca) == []
    storage.case_add_scan(cb, other)
    [found] = storage.correlations(ca)
    assert found["type"] == "domain" and found["cases"] == ["b"] and found["scans"] == [other]


def test_migration_10_creates_case_tables_on_an_existing_database(tmp_path):
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    for statement in ";".join(MIGRATIONS[:9]).split(";"):
        if statement.strip():
            conn.execute(statement)
    conn.execute("PRAGMA user_version = 9")
    conn.execute(
        "INSERT INTO scans (id, target_type, target, depth, started_at)"
        " VALUES (1, 'domain', 'example.com', 1, '2026-01-01T00:00:00+00:00')"
    )
    conn.commit()
    conn.close()
    with Storage(path) as store:
        assert store.case_list() == []
        assert store.load(1).target.value == "example.com"


# --- CLI ----------------------------------------------------------------------------------------


def cli(db, *args):
    return runner.invoke(app, [*args, "--db", str(db)])


def test_cli_case_workflow(tmp_path):
    db = tmp_path / "c.db"
    with Storage(db) as store:
        a1 = store.save(scan("example.com", (EntityType.IP, "203.0.113.7")))
        b1 = store.save(scan("other.org", (EntityType.IP, "203.0.113.7")))
    assert cli(db, "case", "new", "caso-a", "-d", "uno", "-t", "x", "-t", "y").exit_code == 0
    assert cli(db, "case", "new", "caso-b").exit_code == 0
    assert cli(db, "case", "new", "caso-a").exit_code != 0  # repetido
    assert cli(db, "case", "add", "caso-b", str(b1)).exit_code == 0
    added = cli(db, "case", "add", "caso-a", str(a1))
    assert added.exit_code == 0
    assert "203.0.113.7" in added.stdout and "caso-b" in added.stdout  # avisa de la correlación
    assert cli(db, "case", "note", "caso-a", "Primera pista").exit_code == 0
    data = json.loads(cli(db, "case", "show", "caso-a", "--json").stdout)
    assert data["name"] == "caso-a" and data["tags"] == ["x", "y"]
    assert [s["id"] for s in data["scans"]] == [a1]
    assert data["notes"][0]["text"] == "Primera pista"
    assert [c["value"] for c in data["correlations"]] == ["203.0.113.7"]
    listed = json.loads(cli(db, "case", "list", "--json").stdout)
    assert [(c["name"], c["scans"]) for c in listed] == [("caso-a", 1), ("caso-b", 1)]
    assert cli(db, "case", "show", "nada").exit_code != 0
    assert cli(db, "case", "add", "caso-a", "99").exit_code != 0


def test_cli_search_json_and_text(tmp_path):
    db = tmp_path / "s.db"
    with Storage(db) as store:
        case = store.case_create("caso-a")
        store.case_add_scan(case, store.save(scan("example.com", (EntityType.IP, "203.0.113.7"))))
    hits = json.loads(cli(db, "search", "203.0.113.7", "--json").stdout)
    assert hits[0]["scan_id"] == 1 and hits[0]["cases"] == ["caso-a"]
    text = cli(db, "search", "203.0.113", "--contains")
    assert text.exit_code == 0 and "203.0.113.7" in text.stdout
    none = cli(db, "search", "nada")
    assert none.exit_code == 0 and "Sin coincidencias" in none.stdout
    only = json.loads(cli(db, "search", "example.com", "--type", "domain", "--json").stdout)
    assert [h["type"] for h in only] == ["domain"]
    assert json.loads(cli(db, "search", "example.com", "--type", "ip", "--json").stdout) == []
    assert cli(db, "search", "x", "--type", "invalid").exit_code != 0

"""F7.3: comparación de dos scans."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from osineitor.cli import app
from osineitor.diff import diff_scans
from osineitor.models import Entity, EntityType, ScanResult
from osineitor.storage import Storage

runner = CliRunner()


def scan(*entities: Entity, target: str = "example.com", scan_id: int | None = None) -> ScanResult:
    seed = Entity(type=EntityType.DOMAIN, value=target)
    return ScanResult(target=seed, depth=2, entities=list(entities), scan_id=scan_id)


def ent(kind: EntityType, value: str, **data) -> Entity:
    return Entity(type=kind, value=value, data=data)


def keys(items: list[dict]) -> list[str]:
    return [i["key"] for i in items]


def test_added_removed_and_changed_entities():
    before = scan(
        ent(EntityType.IP, "1.1.1.1"),
        ent(EntityType.IP, "2.2.2.2"),
        ent(EntityType.RECORD, "dns:example.com", SPF="v=spf1 -all", A=["1.1.1.1"]),
    )
    after = scan(
        ent(EntityType.IP, "1.1.1.1"),
        ent(EntityType.IP, "3.3.3.3"),
        ent(EntityType.RECORD, "dns:example.com", SPF="v=spf1 +all", A=["1.1.1.1"]),
    )
    result = diff_scans(before, after)
    assert keys(result["added"]) == ["ip:3.3.3.3"]
    assert keys(result["removed"]) == ["ip:2.2.2.2"]
    assert keys(result["changed"]) == ["record:dns:example.com"]
    assert result["changed"][0]["changes"] == [
        {"field": "SPF", "before": "v=spf1 -all", "after": "v=spf1 +all"}
    ]
    assert result["unchanged"] == 1
    assert result["same_target"] is True


def test_a_field_that_appears_or_disappears_counts_as_a_change():
    before = scan(ent(EntityType.RECORD, "dns:example.com", A=["1.1.1.1"]))
    after = scan(ent(EntityType.RECORD, "dns:example.com", A=["1.1.1.1"], DMARC="v=DMARC1"))
    [item] = diff_scans(before, after)["changed"]
    assert item["changes"] == [{"field": "DMARC", "before": None, "after": "v=DMARC1"}]


def test_findings_are_listed_apart_as_well():
    before = scan(ent(EntityType.FINDING, "spf-permissive: dns:example.com", severity="high"))
    after = scan(
        ent(EntityType.FINDING, "dmarc-missing: dns:example.com", severity="medium"),
        ent(EntityType.IP, "1.1.1.1"),
    )
    result = diff_scans(before, after)
    assert keys(result["findings"]["added"]) == ["finding:dmarc-missing: dns:example.com"]
    assert keys(result["findings"]["removed"]) == ["finding:spf-permissive: dns:example.com"]
    assert keys(result["added"]) == [
        "finding:dmarc-missing: dns:example.com",
        "ip:1.1.1.1",
    ]


def test_identical_scans_have_no_differences_and_other_targets_are_flagged():
    same = scan(ent(EntityType.IP, "1.1.1.1"))
    result = diff_scans(same, scan(ent(EntityType.IP, "1.1.1.1")))
    assert (result["added"], result["removed"], result["changed"]) == ([], [], [])
    assert diff_scans(same, scan(target="other.org"))["same_target"] is False


def test_diff_command_compares_stored_scans(tmp_path):
    db = tmp_path / "s.db"
    with Storage(db) as storage:
        first = storage.save(scan(ent(EntityType.IP, "1.1.1.1")))
        second = storage.save(scan(ent(EntityType.IP, "2.2.2.2")))
    result = runner.invoke(app, ["diff", str(first), str(second), "--db", str(db), "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert keys(data["added"]) == ["ip:2.2.2.2"] and keys(data["removed"]) == ["ip:1.1.1.1"]
    assert (data["from"]["scan_id"], data["to"]["scan_id"]) == (first, second)
    human = runner.invoke(app, ["diff", str(first), str(second), "--db", str(db)])
    assert human.exit_code == 0
    assert "2.2.2.2" in human.output and "1.1.1.1" in human.output


def test_diff_command_rejects_an_unknown_scan(tmp_path):
    db = tmp_path / "s.db"
    with Storage(db) as storage:
        only = storage.save(scan())
    result = runner.invoke(app, ["diff", str(only), "99", "--db", str(db)])
    assert result.exit_code == 2
    assert "99" in result.output

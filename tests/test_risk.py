"""F7.9: puntuación de riesgo por activo."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from osineitor import risk
from osineitor.cli import app
from osineitor.models import Entity, EntityType, ScanResult
from osineitor.storage import Storage

runner = CliRunner()
SEED = Entity(type=EntityType.DOMAIN, value="example.com")


def finding(rule: str, severity: str, affected: Entity, title: str = "t") -> Entity:
    return Entity(
        type=EntityType.FINDING,
        value=f"{rule}: {affected.value}",
        parent=affected.key,
        data={"rule": rule, "title": title, "severity": severity, "affected": [affected.key]},
    )


def ent(kind, value, parent=None, confidence="alto", **data) -> Entity:
    return Entity(type=kind, value=value, parent=parent, confidence=confidence, data=data)


def scan(*entities: Entity) -> ScanResult:
    return ScanResult(target=SEED, depth=2, entities=list(entities))


def test_a_scan_without_findings_or_exposure_has_nothing_to_score():
    assert risk.score(scan(ent(EntityType.TECHNOLOGY, "nginx", SEED.key))) == []


def test_severity_points_with_full_confidence():
    dns = ent(EntityType.RECORD, "dns:example.com", SEED.key)
    [row] = risk.score(scan(dns, finding("spf", "high", dns, "SPF permisivo")))
    assert row["asset"] == "domain:example.com" and row["score"] == 25 and row["level"] == "medium"
    assert row["findings"] == {"high": 1}
    assert "high: SPF permisivo (+25)" in row["reasons"]


def test_low_confidence_weighs_less_and_unknown_confidence_is_in_between():
    weak = ent(EntityType.RECORD, "dns:example.com", SEED.key, confidence="bajo")
    unknown = ent(EntityType.RECORD, "dns:example.com", SEED.key, confidence=None)
    assert risk.score(scan(weak, finding("r", "critical", weak)))[0]["score"] == 20
    assert risk.score(scan(unknown, finding("r", "critical", unknown)))[0]["score"] == 32


def test_findings_go_to_the_nearest_domain_or_ip_up_the_parent_chain():
    ip = ent(EntityType.IP, "203.0.113.7", SEED.key)
    service = ent(EntityType.SERVICE, "203.0.113.7:3389", ip.key, port=3389)
    rdp = finding("rdp", "high", service)
    sub = ent(EntityType.DOMAIN, "dev.example.com", SEED.key, subdomain=True)
    cname = ent(EntityType.RECORD, "dns:dev.example.com", sub.key)
    rows = {
        r["asset"]: r
        for r in risk.score(scan(ip, service, rdp, sub, cname, finding("t", "medium", cname)))
    }
    assert set(rows) == {"ip:203.0.113.7", "domain:dev.example.com"}
    assert rows["ip:203.0.113.7"]["findings"] == {"high": 1}
    assert rows["domain:dev.example.com"]["findings"] == {"medium": 1}


def test_exposure_adds_points_with_a_cap_even_without_findings():
    ip = ent(EntityType.IP, "203.0.113.7", SEED.key)
    services = [ent(EntityType.SERVICE, f"203.0.113.7:{p}", ip.key) for p in range(1, 9)]
    cves = [ent(EntityType.VULNERABILITY, f"CVE-2026-{n}", services[0].key) for n in range(3)]
    [row] = risk.score(scan(ip, *services, *cves))
    assert row["exposure"] == {"services": 8, "vulnerabilities": 3}
    assert row["score"] == 10 + 6  # 8 servicios × 2 con tope 10, y 3 CVE × 2
    assert row["level"] == "low"


def test_score_is_capped_at_100_and_assets_are_sorted_worst_first():
    dns = ent(EntityType.RECORD, "dns:example.com", SEED.key)
    ip = ent(EntityType.IP, "203.0.113.7", SEED.key)
    service = ent(EntityType.SERVICE, "203.0.113.7:23", ip.key)
    rows = risk.score(
        scan(
            dns,
            *[finding(f"r{i}", "critical", dns) for i in range(4)],
            ip,
            service,
            finding("telnet", "high", service),
        )
    )
    assert [r["asset"] for r in rows] == ["domain:example.com", "ip:203.0.113.7"]
    assert rows[0]["score"] == 100 and rows[0]["level"] == "critical"
    assert rows[1]["score"] == 27


def test_info_findings_are_counted_but_add_nothing():
    dns = ent(EntityType.RECORD, "dns:example.com", SEED.key)
    [row] = risk.score(scan(dns, finding("note", "info", dns)))
    assert row["findings"] == {"info": 1} and row["score"] == 0 and row["level"] == "info"


def test_levels():
    assert [risk.level_for(n) for n in (0, 1, 19, 20, 49, 50, 74, 75, 100)] == [
        "info", "low", "low", "medium", "medium", "high", "high", "critical", "critical",
    ]  # fmt: skip


def test_cli_risk_json_and_table(tmp_path):
    dns = ent(EntityType.RECORD, "dns:example.com", SEED.key)
    db = tmp_path / "r.db"
    with Storage(db) as store:
        store.save(scan(dns, finding("spf", "high", dns, "SPF permisivo")))
    data = json.loads(runner.invoke(app, ["risk", "1", "--db", str(db), "--json"]).stdout)
    assert data["scan_id"] == 1 and data["assets"][0]["score"] == 25
    assert "domain:example.com" in runner.invoke(app, ["risk", "1", "--db", str(db)]).stdout
    assert runner.invoke(app, ["risk", "5", "--db", str(db)]).exit_code != 0

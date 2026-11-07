"""F8.1: exportación STIX 2.1 de la infraestructura descubierta."""

from __future__ import annotations

import json

import pytest
import stix2
from typer.testing import CliRunner

from osineitor import report
from osineitor.cli import app
from osineitor.errors import ExportUnavailable
from osineitor.models import Entity, EntityType, ScanResult
from osineitor.storage import Storage

runner = CliRunner()
SEED = Entity(type=EntityType.DOMAIN, value="example.com")


def ent(kind, value, parent=SEED, **data) -> Entity:
    return Entity(type=kind, value=value, parent=parent.key if parent else None, data=data)


def sample() -> ScanResult:
    ip = ent(EntityType.IP, "203.0.113.7")
    ip6 = ent(EntityType.IP, "2001:db8::1")
    sub = ent(EntityType.DOMAIN, "www.example.com", subdomain=True)
    sub_ip = ent(EntityType.IP, "203.0.113.8", parent=sub)
    return ScanResult(
        target=SEED,
        depth=2,
        entities=[
            ip,
            ip6,
            sub,
            sub_ip,
            ent(EntityType.URL, "https://www.example.com/login", parent=sub),
            ent(EntityType.EMAIL, "admin@example.com"),
            ent(EntityType.VULNERABILITY, "CVE-2026-0001", parent=ip),
            ent(EntityType.USERNAME, "maria"),  # sin equivalente STIX de infraestructura
            ent(EntityType.FINDING, "x: example.com"),
        ],
    )


def objects(result: ScanResult) -> list[dict]:
    return json.loads(report.render(result, "stix"))["objects"]


def test_bundle_parses_and_validates_with_the_stix_library():
    text = report.render(sample(), "stix")
    parsed = stix2.parse(text, allow_custom=False)
    assert parsed.type == "bundle"
    kinds = sorted({o["type"] for o in json.loads(text)["objects"]})
    assert kinds == [
        "domain-name",
        "email-addr",
        "ipv4-addr",
        "ipv6-addr",
        "relationship",
        "url",
        "vulnerability",
    ]


def test_observables_use_deterministic_ids_and_skip_unsupported_types():
    objs = objects(sample())
    values = sorted(o["value"] for o in objs if "value" in o)
    assert values == [
        "2001:db8::1",
        "203.0.113.7",
        "203.0.113.8",
        "admin@example.com",
        "example.com",
        "https://www.example.com/login",
        "www.example.com",
    ]
    assert not any(o.get("value") == "maria" for o in objs)
    ids = [o["id"] for o in objs]
    assert len(ids) == len(set(ids))
    assert ids == [o["id"] for o in objects(sample())]  # mismo scan, mismo resultado


def test_domain_resolves_to_its_ip_and_other_links_are_related_to():
    objs = objects(sample())
    by_value = {o["value"]: o for o in objs if "value" in o}
    assert by_value["www.example.com"]["resolves_to_refs"] == [by_value["203.0.113.8"]["id"]]
    rels = [o for o in objs if o["type"] == "relationship"]
    assert rels and all(r["relationship_type"] == "related-to" for r in rels)
    pairs = {(r["source_ref"], r["target_ref"]) for r in rels}
    assert (by_value["example.com"]["id"], by_value["www.example.com"]["id"]) in pairs
    # una relación solo existe entre objetos que están en el bundle
    known = {o["id"] for o in objs}
    assert all(r["source_ref"] in known and r["target_ref"] in known for r in rels)


def test_vulnerability_carries_the_cve_reference():
    [vuln] = [o for o in objects(sample()) if o["type"] == "vulnerability"]
    assert vuln["name"] == "CVE-2026-0001"
    assert vuln["external_references"] == [{"source_name": "cve", "external_id": "CVE-2026-0001"}]


def test_empty_scan_gives_an_empty_valid_bundle_with_just_the_seed():
    text = report.render(ScanResult(target=SEED, depth=1), "stix")
    assert [o["value"] for o in json.loads(text)["objects"]] == ["example.com"]


def test_missing_library_gives_a_clear_error(monkeypatch):
    import builtins

    real = builtins.__import__

    def deny(name, *args, **kwargs):
        if name == "stix2":
            raise ImportError("no hay stix2")
        return real(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", deny)
    with pytest.raises(ExportUnavailable, match=r"osineitor\[stix\]"):
        report.render(sample(), "stix")


def test_cli_export_stix(tmp_path):
    db = tmp_path / "s.db"
    with Storage(db) as store:
        store.save(sample())
    out = tmp_path / "bundle.json"
    res = runner.invoke(
        app, ["export", "1", "--db", str(db), "--format", "stix", "--output", str(out)]
    )
    assert res.exit_code == 0, res.output
    assert json.loads(out.read_text(encoding="utf-8"))["type"] == "bundle"

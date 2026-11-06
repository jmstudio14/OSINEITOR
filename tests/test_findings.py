"""F7.8: motor de hallazgos. Cada regla tiene un caso positivo y uno negativo."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from osineitor import registry
from osineitor.engine import Engine
from osineitor.findings import RuleError, evaluate, load_rules
from osineitor.models import Entity, EntityType
from osineitor.modules.analysis.findings import Findings

RULES = load_rules()
NOW = datetime(2026, 11, 4, tzinfo=UTC)


def entity(kind: str, value: str, **data) -> Entity:
    return Entity(type=EntityType(kind), value=value, data=data)


def ids(item: Entity) -> set[str]:
    return {m.rule.id for m in evaluate(RULES, item, NOW)}


# (regla, entidad que la dispara, entidad parecida que no)
CASES = [
    (
        "dmarc-missing",
        entity("record", "dns:example.com", A=["1.1.1.1"], DMARC=None),
        entity("record", "dns:example.com", A=["1.1.1.1"], DMARC="v=DMARC1; p=reject"),
    ),
    (
        "dmarc-monitor-only",
        entity("record", "dns:example.com", DMARC="v=DMARC1; p=none; rua=mailto:a@example.com"),
        entity("record", "dns:example.com", DMARC="v=DMARC1; p=quarantine"),
    ),
    (
        "spf-permissive",
        entity("record", "dns:example.com", SPF="v=spf1 include:x.test +all"),
        entity("record", "dns:example.com", SPF="v=spf1 include:x.test -all"),
    ),
    (
        "mta-sts-missing",
        entity("record", "mail_security:example.com", MTA_STS=None, DKIM=["google"]),
        entity("record", "mail_security:example.com", MTA_STS="v=STSv1; id=1"),
    ),
    (
        "cert-expired",
        entity("certificate", "a" * 64, status="caducado", expires_in_days=-3),
        entity("certificate", "b" * 64, status="valido", expires_in_days=200),
    ),
    (
        "cert-expiring",
        entity("certificate", "a" * 64, status="caduca_pronto", expires_in_days=10),
        entity("certificate", "b" * 64, status="valido", expires_in_days=200),
    ),
    (
        "domain-expiring",
        entity("record", "rdap:example.com", expires="2026-12-01T00:00:00Z"),
        entity("record", "rdap:example.com", expires="2028-12-01T00:00:00Z"),
    ),
    (
        "cve-in-kev",
        entity("vulnerability", "CVE-2024-1", kev=True, cvss=9.8),
        entity("vulnerability", "CVE-2024-2", kev=False, cvss=9.8),
    ),
    (
        "cve-epss-high",
        entity("vulnerability", "CVE-2024-1", epss=0.91),
        entity("vulnerability", "CVE-2024-2", epss=0.02),
    ),
    (
        "dangling-cname",
        entity("record", "takeover:old.example.com", service="Heroku", cname="x.herokuapp.com"),
        entity("record", "dns:old.example.com", CNAME=["x.herokuapp.com"]),
    ),
    (
        "sensitive-archived-url",
        entity("url", "https://example.com/backup/db.sql", archived=True),
        entity("url", "https://example.com/backup/db.sql", archived=False),
    ),
    (
        "ip-blacklisted",
        entity("record", "dnsbl:1.2.3.4", listed_on=["zen.spamhaus.org"], listed=[{}]),
        entity("record", "dnsbl:1.2.3.4", listed_on=[], listed=[]),
    ),
    (
        "missing-security-headers",
        entity("record", "http:example.com", missing_security_headers=["x-frame-options"]),
        entity("record", "http:example.com", missing_security_headers=[]),
    ),
    (
        "exposed-admin-service",
        entity("service", "1.2.3.4:3389", port=3389),
        entity("service", "1.2.3.4:443", port=443),
    ),
    (
        "security-txt-expired",
        entity("record", "web_meta:example.com", security_expired=True),
        entity("record", "web_meta:example.com", security_expired=False),
    ),
]


def test_there_are_at_least_twelve_rules_and_every_one_has_a_case():
    assert len(RULES) >= 12
    assert {rule_id for rule_id, *_ in CASES} == {r.id for r in RULES}


@pytest.mark.parametrize(("rule_id", "positive", "negative"), CASES, ids=[c[0] for c in CASES])
def test_each_rule_fires_on_the_positive_case_and_not_on_the_negative(rule_id, positive, negative):
    assert rule_id in ids(positive)
    assert rule_id not in ids(negative)


def test_dmarc_is_only_required_on_the_root_domain():
    assert "dmarc-missing" not in ids(entity("record", "dns:www.example.com", A=["1.1.1.1"]))


def test_a_finding_carries_severity_recommendation_and_evidence():
    [match] = evaluate(
        RULES, entity("record", "dns:example.com", SPF="v=spf1 ?all", DMARC="v=DMARC1; p=reject")
    )
    assert match.rule.severity == "high"
    assert match.rule.recommendation
    assert match.evidence == {"SPF": "v=spf1 ?all"}


async def test_the_analyzer_emits_findings_that_point_at_the_affected_entity(ctx):
    record = entity("record", "dns:example.com", SPF="v=spf1 +all", DMARC="v=DMARC1; p=none")
    out = await Findings(ctx).run(record)
    assert {e.data["rule"] for e in out} == {"spf-permissive", "dmarc-monitor-only"}
    assert all(e.type == EntityType.FINDING and e.data["affected"] == [record.key] for e in out)
    assert out[0].value == f"{out[0].data['rule']}: dns:example.com"


async def test_findings_run_in_the_final_pass_without_confidence(ctx):
    from tests.test_cli import fake_module

    dns = fake_module(
        "fake_dns",
        {EntityType.DOMAIN},
        EntityType.RECORD,
        "dns:example.com",
        SPF="v=spf1 +all",
        DMARC="v=DMARC1; p=reject",
    )
    result = await Engine(ctx, [dns, Findings]).run(entity("domain", "example.com"))
    found = [e for e in result.entities if e.type == EntityType.FINDING]
    assert [e.data["rule"] for e in found] == ["spf-permissive"]
    assert found[0].confidence is None


def test_the_analyzer_is_registered_and_offline():
    assert registry.discover()
    assert Findings.analyzer and Findings.passive


def test_invalid_rule_files_are_rejected(tmp_path):
    def write(text: str):
        path = tmp_path / "r.yml"
        path.write_text(text, encoding="utf-8")
        return path

    with pytest.raises(RuleError, match="severidad"):
        load_rules(
            write("rules:\n- {id: x, title: t, severity: grave, type: ip, recommendation: r}")
        )
    with pytest.raises(RuleError, match="falta 'type'"):
        load_rules(write("rules:\n- {id: x, title: t, severity: low, recommendation: r}"))
    with pytest.raises(RuleError, match="condición"):
        head = "{id: x, title: t, severity: low, type: ip, recommendation: r"
        load_rules(write(f"rules:\n- {head}, when: [{{field: a, op: nope}}]}}"))
    with pytest.raises(RuleError, match="repetidos"):
        one = "{id: x, title: t, severity: low, type: ip, recommendation: r}"
        load_rules(write(f"rules:\n- {one}\n- {one}"))

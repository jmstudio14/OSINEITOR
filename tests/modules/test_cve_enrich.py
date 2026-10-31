"""F4.14: cve_enrich (CVSS de NVD, EPSS de FIRST y KEV de CISA)."""

from __future__ import annotations

import httpx
import pytest
import respx

from osineitor.engine import Engine
from osineitor.errors import ModuleError, ModuleQuota
from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module
from osineitor.modules.ip import cve_enrich
from osineitor.modules.ip.cve_enrich import EPSS, KEV, NVD, CveEnrich

LOG4SHELL = Entity(type=EntityType.VULNERABILITY, value="CVE-2021-44228", data={"ip": "1.2.3.4"})

NVD_BODY = {
    "vulnerabilities": [
        {
            "cve": {
                "metrics": {
                    "cvssMetricV2": [{"cvssData": {"baseScore": 9.3}, "baseSeverity": "HIGH"}],
                    "cvssMetricV31": [
                        {"cvssData": {"baseScore": 10.0, "baseSeverity": "CRITICAL"}}
                    ],
                }
            }
        }
    ]
}
EPSS_BODY = {
    "data": [
        {"cve": "CVE-2021-44228", "epss": "0.94358", "percentile": "0.99970", "date": "2026-10-30"}
    ]
}
KEV_BODY = {
    "vulnerabilities": [
        {
            "cveID": "CVE-2021-44228",
            "dueDate": "2021-12-24",
            "knownRansomwareCampaignUse": "Known",
        },
        {
            "cveID": "CVE-2020-0001",
            "dueDate": "2020-01-01",
            "knownRansomwareCampaignUse": "Unknown",
        },
    ]
}


@pytest.fixture(autouse=True)
def no_pacing(monkeypatch):
    monkeypatch.setattr(cve_enrich, "NVD_INTERVAL", 0.0)
    monkeypatch.setattr(cve_enrich, "NVD_INTERVAL_KEY", 0.0)


def mock_sources(*, nvd=None, epss=None, kev=None):
    routes = {
        "nvd": respx.get(NVD).mock(return_value=nvd or httpx.Response(200, json=NVD_BODY)),
        "epss": respx.get(EPSS).mock(return_value=epss or httpx.Response(200, json=EPSS_BODY)),
        "kev": respx.get(KEV).mock(return_value=kev or httpx.Response(200, json=KEV_BODY)),
    }
    return routes


@respx.mock
async def test_cve_enrich(ctx):
    routes = mock_sources()
    (vuln,) = await CveEnrich(ctx).run(LOG4SHELL)
    assert (vuln.type, vuln.value) == (EntityType.VULNERABILITY, "CVE-2021-44228")
    assert vuln.data == {
        "cvss": 10.0,
        "cvss_version": "3.1",  # gana la versión más reciente que traiga la CVE
        "cvss_severity": "CRITICAL",
        "epss": 0.94358,
        "epss_percentile": 0.9997,
        "epss_date": "2026-10-30",
        "kev": True,
        "kev_due_date": "2021-12-24",
        "kev_ransomware": True,
    }
    assert routes["nvd"].calls[0].request.url.params["cveId"] == "CVE-2021-44228"
    assert routes["epss"].calls[0].request.url.params["cve"] == "CVE-2021-44228"


@respx.mock
async def test_cve_enrich_a_cve_outside_kev_is_marked_false(ctx):
    mock_sources()
    other = Entity(type=EntityType.VULNERABILITY, value="CVE-2019-0001")
    (vuln,) = await CveEnrich(ctx).run(other)
    assert vuln.data["kev"] is False
    assert "kev_due_date" not in vuln.data


@respx.mock
async def test_cve_enrich_downloads_the_kev_catalog_once_per_scan(ctx):
    routes = mock_sources()
    module = CveEnrich(ctx)
    for cve in ("CVE-2021-44228", "CVE-2020-0001", "CVE-2019-0001"):
        await module.run(Entity(type=EntityType.VULNERABILITY, value=cve))
    assert routes["kev"].call_count == 1


@respx.mock
async def test_cve_enrich_one_source_failing_keeps_the_others(ctx):
    mock_sources(epss=httpx.Response(500))
    (vuln,) = await CveEnrich(ctx).run(LOG4SHELL)
    assert vuln.data["cvss"] == 10.0
    assert vuln.data["kev"] is True
    assert "epss" not in vuln.data


@respx.mock
async def test_cve_enrich_nvd_rate_limit_keeps_epss_and_kev(ctx):
    mock_sources(nvd=httpx.Response(403))
    (vuln,) = await CveEnrich(ctx).run(LOG4SHELL)
    assert "cvss" not in vuln.data
    assert vuln.data["epss"] == 0.94358


@respx.mock
async def test_cve_enrich_all_sources_failing_is_an_error(ctx):
    mock_sources(nvd=httpx.Response(500), epss=httpx.Response(500), kev=httpx.Response(500))
    with pytest.raises(ModuleError, match="500"):
        await CveEnrich(ctx).run(LOG4SHELL)


@respx.mock
async def test_cve_enrich_quota_wins_over_another_failure(ctx):
    mock_sources(nvd=httpx.Response(403), epss=httpx.Response(500), kev=httpx.Response(500))
    with pytest.raises(ModuleQuota, match="NVD"):
        await CveEnrich(ctx).run(LOG4SHELL)


@respx.mock
async def test_cve_enrich_new_cve_without_scores_is_not_an_error(ctx):
    mock_sources(
        nvd=httpx.Response(200, json={"vulnerabilities": []}),
        epss=httpx.Response(200, json={"data": []}),
    )
    (vuln,) = await CveEnrich(ctx).run(Entity(type=EntityType.VULNERABILITY, value="CVE-2026-9999"))
    assert vuln.data == {"kev": False}


@respx.mock
async def test_cve_enrich_sends_the_nvd_key_in_a_header_not_in_the_url(ctx):
    ctx.config.keys["nvd"] = "secreto"
    routes = mock_sources()
    await CveEnrich(ctx).run(LOG4SHELL)
    request = routes["nvd"].calls[0].request
    assert request.headers["apikey"] == "secreto"
    assert "secreto" not in str(request.url)
    assert "apikey" not in routes["epss"].calls[0].request.headers


@respx.mock
async def test_cve_enrich_limits_the_nvd_lookups_per_scan(ctx, monkeypatch):
    monkeypatch.setattr(cve_enrich, "MAX_CVSS", 2)
    routes = mock_sources()
    module = CveEnrich(ctx)
    results = [
        (await module.run(Entity(type=EntityType.VULNERABILITY, value=f"CVE-2020-100{i}")))[0]
        for i in range(4)
    ]
    assert routes["nvd"].call_count == 2
    assert ["cvss" in r.data for r in results] == [True, True, False, False]
    assert all("epss" in r.data and "kev" in r.data for r in results)


def test_cve_enrich_only_accepts_well_formed_cve_ids(ctx):
    module = CveEnrich(ctx)
    assert module.accepts(LOG4SHELL)
    assert module.accepts(Entity(type=EntityType.VULNERABILITY, value="cve-2021-44228"))
    for bad in ("CVE-21-1", "CVE-2021-44228/../x", "GHSA-xxxx-yyyy-zzzz", "CVE-2021-44228?a=b"):
        assert not module.accepts(Entity(type=EntityType.VULNERABILITY, value=bad))
    assert not module.accepts(Entity(type=EntityType.DOMAIN, value="example.com"))


class FakeVulns(Module):
    name = "fake_vulns"
    description = "deja una CVE como lo hace internetdb"
    consumes = frozenset({EntityType.IP})
    produces = frozenset({EntityType.VULNERABILITY})

    async def run(self, entity):
        return [self.emit(entity, EntityType.VULNERABILITY, "CVE-2021-44228", ip=entity.value)]


@respx.mock
async def test_the_enrichment_merges_into_the_vulnerability_the_other_module_found(ctx):
    mock_sources()
    seed = Entity(type=EntityType.IP, value="1.2.3.4")
    result = await Engine(ctx, [FakeVulns, CveEnrich], depth=2).run(seed)
    (vuln,) = [e for e in result.entities if e.type == EntityType.VULNERABILITY]
    assert vuln.parent == "ip:1.2.3.4"  # no cambia de padre
    assert vuln.data["ip"] == "1.2.3.4"
    assert vuln.data["cvss"] == 10.0
    assert vuln.data["kev"] is True
    assert set(vuln.sources) == {"fake_vulns", "cve_enrich"}
    assert {r.module: r.status for r in result.runs} == {"fake_vulns": "ok", "cve_enrich": "ok"}

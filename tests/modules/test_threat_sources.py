"""Fuentes con API de la fase 4 (F4.1, F4.2, F4.3, F4.10, F4.15) con respuestas simuladas."""

from __future__ import annotations

import httpx
import pytest
import respx

from osineitor.models import Entity, EntityType
from osineitor.modules.base import ModuleError, ModuleQuota
from osineitor.modules.domain.otx import Otx
from osineitor.modules.domain.urlscan import Urlscan
from osineitor.modules.domain.virustotal import VirusTotal
from osineitor.modules.ip.abusech import AbuseCh
from osineitor.modules.ip.censys import Censys

DOMAIN = Entity(type=EntityType.DOMAIN, value="example.com")
SUB = Entity(type=EntityType.DOMAIN, value="a.example.com", data={"subdomain": True})
IP = Entity(type=EntityType.IP, value="1.1.1.1")

URLSCAN = "https://urlscan.io/api/v1/search/"
OTX = "https://otx.alienvault.com/api/v1/indicators"
VT = "https://www.virustotal.com/api/v3"
CENSYS = "https://api.platform.censys.io/v3/global/asset/host/1.1.1.1"
THREATFOX = "https://threatfox-api.abuse.ch/api/v1/"
URLHAUS = "https://urlhaus-api.abuse.ch/v1/host/"


@pytest.fixture(autouse=True)
def keys(config):
    config.keys.update(otx="O", virustotal="V", censys="C", abusech="A")


def pairs(out):
    return [(e.type, e.value) for e in out]


# --- urlscan ---------------------------------------------------------------------------------


@respx.mock
async def test_urlscan_keeps_only_hosts_of_the_target(ctx):
    results = [
        {
            "task": {"url": "https://www.example.com/login", "time": "2026-01-02T00:00:00Z"},
            "page": {"domain": "www.example.com", "ip": "93.184.216.34", "country": "US"},
        },
        {
            "task": {"url": "https://evil.test/?u=example.com", "time": "2026-02-01T00:00:00Z"},
            "page": {"domain": "evil.test", "ip": "6.6.6.6", "country": "RU"},
        },
        {"task": {}, "page": {"domain": "bad host!", "ip": "7.7.7.7"}},
    ]
    route = respx.get(URLSCAN).mock(return_value=httpx.Response(200, json={"results": results}))
    out = await Urlscan(ctx).run(DOMAIN)
    assert route.calls[0].request.url.params["q"] == "domain:example.com"
    assert "api-key" not in route.calls[0].request.headers
    assert pairs(out) == [
        (EntityType.RECORD, "urlscan:example.com"),
        (EntityType.IP, "93.184.216.34"),
        (EntityType.DOMAIN, "www.example.com"),
        (EntityType.URL, "https://www.example.com/login"),
    ]
    assert out[0].data["scans"] == 3
    assert out[0].data["countries"] == ["US"]
    assert out[2].data == {"subdomain": True}


@respx.mock
async def test_urlscan_sends_the_optional_key_and_reports_quota(ctx, config):
    config.keys["urlscan"] = "U"
    route = respx.get(URLSCAN).mock(return_value=httpx.Response(429))
    with pytest.raises(ModuleQuota):
        await Urlscan(ctx).run(DOMAIN)
    assert route.calls[0].request.headers["API-Key"] == "U"


@respx.mock
async def test_urlscan_without_results_is_empty_and_ignores_subdomains(ctx):
    respx.get(URLSCAN).mock(return_value=httpx.Response(200, json={"results": []}))
    assert await Urlscan(ctx).run(DOMAIN) == []
    assert not Urlscan(ctx).accepts(SUB)


# --- otx -------------------------------------------------------------------------------------


@respx.mock
async def test_otx_domain_pulses_and_passive_dns(ctx):
    general = respx.get(f"{OTX}/domain/example.com/general").mock(
        return_value=httpx.Response(200, json={"pulse_info": {"count": 4}, "alexa": "x"})
    )
    respx.get(f"{OTX}/domain/example.com/passive_dns").mock(
        return_value=httpx.Response(
            200,
            json={
                "passive_dns": [
                    {"hostname": "mail.example.com", "address": "1.2.3.4", "record_type": "A"},
                    {"hostname": "other.test", "address": "9.9.9.9", "record_type": "A"},
                    {"hostname": "x.example.com", "address": "mx.example.com", "record_type": "MX"},
                ]
            },
        )
    )
    out = await Otx(ctx).run(DOMAIN)
    assert general.calls[0].request.headers["X-OTX-API-KEY"] == "O"
    assert pairs(out) == [
        (EntityType.RECORD, "otx:example.com"),
        (EntityType.DOMAIN, "mail.example.com"),
        (EntityType.DOMAIN, "x.example.com"),
        (EntityType.IP, "1.2.3.4"),
    ]
    assert out[0].data["pulses"] == 4


@respx.mock
async def test_otx_ip_uses_the_ipv4_path_and_needs_pulses(ctx):
    respx.get(f"{OTX}/IPv4/1.1.1.1/general").mock(
        return_value=httpx.Response(200, json={"pulse_info": {"count": 0}})
    )
    assert await Otx(ctx).run(IP) == []
    respx.get(f"{OTX}/IPv4/1.1.1.1/general").mock(
        return_value=httpx.Response(200, json={"pulse_info": {"count": 2}, "asn": "AS13335"})
    )
    out = await Otx(ctx).run(IP)
    assert pairs(out) == [(EntityType.RECORD, "otx:1.1.1.1")]


@respx.mock
async def test_otx_bad_key(ctx):
    respx.get(f"{OTX}/domain/example.com/general").mock(return_value=httpx.Response(403))
    with pytest.raises(ModuleError, match="inválida"):
        await Otx(ctx).run(DOMAIN)


# --- virustotal ------------------------------------------------------------------------------


@respx.mock
async def test_virustotal_domain_with_subdomains(ctx):
    domain = respx.get(f"{VT}/domains/example.com").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "attributes": {
                        "reputation": -3,
                        "last_analysis_stats": {"malicious": 2, "harmless": 60},
                        "categories": {"a": "business", "b": "business"},
                        "registrar": "RegCo",
                    }
                }
            },
        )
    )
    subs = respx.get(f"{VT}/domains/example.com/subdomains").mock(
        return_value=httpx.Response(
            200, json={"data": [{"id": "www.example.com"}, {"id": "evil.test"}, {"id": "no valid"}]}
        )
    )
    out = await VirusTotal(ctx).run(DOMAIN)
    assert domain.calls[0].request.headers["x-apikey"] == "V"
    assert subs.calls[0].request.url.params["limit"] == "40"
    assert pairs(out) == [
        (EntityType.RECORD, "virustotal:example.com"),
        (EntityType.DOMAIN, "www.example.com"),
    ]
    assert out[0].data["malicious"] == 2
    assert out[0].data["categories"] == ["business"]


@respx.mock
async def test_virustotal_ip_and_unknown_resource(ctx):
    respx.get(f"{VT}/ip_addresses/1.1.1.1").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {"attributes": {"as_owner": "Cloudflare", "asn": 13335, "country": "AU"}}
            },
        )
    )
    out = await VirusTotal(ctx).run(IP)
    assert out[0].data["as_owner"] == "Cloudflare"
    respx.get(f"{VT}/domains/example.com").mock(return_value=httpx.Response(404))
    assert await VirusTotal(ctx).run(DOMAIN) == []


@respx.mock
async def test_virustotal_quota_and_bad_key(ctx):
    respx.get(f"{VT}/domains/example.com").mock(return_value=httpx.Response(429))
    with pytest.raises(ModuleQuota):
        await VirusTotal(ctx).run(DOMAIN)
    respx.get(f"{VT}/domains/example.com").mock(return_value=httpx.Response(401))
    with pytest.raises(ModuleError, match="inválida"):
        await VirusTotal(ctx).run(DOMAIN)


def test_virustotal_declares_the_free_plan_limit():
    assert VirusTotal.min_interval >= 15  # 4 peticiones por minuto


# --- censys ----------------------------------------------------------------------------------


@respx.mock
async def test_censys_host(ctx, config):
    config.keys["censys_org"] = "ORG"
    route = respx.get(CENSYS).mock(
        return_value=httpx.Response(
            200,
            json={
                "result": {
                    "resource": {
                        "autonomous_system": {"asn": 13335, "name": "CLOUDFLARENET"},
                        "location": {"country": "Australia"},
                        "services": [
                            {"port": 53, "transport_protocol": "udp", "protocol": "DNS"},
                            {"port": 443, "software": [{"product": "nginx"}]},
                            {"protocol": "HTTP"},
                        ],
                    }
                }
            },
        )
    )
    out = await Censys(ctx).run(IP)
    request = route.calls[0].request
    assert request.headers["Authorization"] == "Bearer C"
    assert request.headers["X-Organization-ID"] == "ORG"
    assert pairs(out) == [
        (EntityType.RECORD, "censys:1.1.1.1"),
        (EntityType.SERVICE, "1.1.1.1:53"),
        (EntityType.SERVICE, "1.1.1.1:443"),
    ]
    assert out[0].data["asn"] == 13335
    assert out[2].data["product"] == "nginx"


@respx.mock
async def test_censys_errors(ctx):
    respx.get(CENSYS).mock(return_value=httpx.Response(404))
    assert await Censys(ctx).run(IP) == []
    respx.get(CENSYS).mock(return_value=httpx.Response(403))
    with pytest.raises(ModuleError, match="inválido"):
        await Censys(ctx).run(IP)


# --- abuse.ch --------------------------------------------------------------------------------


@respx.mock
async def test_abusech_combines_threatfox_and_urlhaus(ctx):
    fox = respx.post(THREATFOX).mock(
        return_value=httpx.Response(
            200,
            json={
                "query_status": "ok",
                "data": [
                    {
                        "malware_printable": "Cobalt Strike",
                        "threat_type": "botnet_cc",
                        "first_seen": "2026-01-01 00:00:00 UTC",
                        "last_seen": "2026-02-01 00:00:00 UTC",
                        "tags": ["cs"],
                    }
                ],
            },
        )
    )
    haus = respx.post(URLHAUS).mock(
        return_value=httpx.Response(
            200,
            json={
                "query_status": "ok",
                "url_count": "5",
                "urls": [{"url_status": "online", "threat": "malware_download"}],
            },
        )
    )
    out = await AbuseCh(ctx).run(DOMAIN)
    assert fox.calls[0].request.headers["Auth-Key"] == "A"
    assert b"example.com" in haus.calls[0].request.content
    data = out[0].data
    assert out[0].value == "abusech:example.com"
    assert data["malware"] == ["Cobalt Strike"]
    assert data["urlhaus"] == 5
    assert data["urlhaus_online"] == 1
    assert data["tags"] == ["cs"]


@respx.mock
async def test_abusech_without_matches_is_empty(ctx):
    respx.post(THREATFOX).mock(
        return_value=httpx.Response(
            200, json={"query_status": "no_result", "data": "Your search did not yield any results"}
        )
    )
    respx.post(URLHAUS).mock(return_value=httpx.Response(200, json={"query_status": "no_results"}))
    assert await AbuseCh(ctx).run(IP) == []


@respx.mock
async def test_abusech_requires_a_valid_auth_key(ctx):
    respx.post(THREATFOX).mock(return_value=httpx.Response(401))
    with pytest.raises(ModuleError, match="Auth-Key"):
        await AbuseCh(ctx).run(DOMAIN)

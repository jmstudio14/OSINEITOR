from __future__ import annotations

import httpx
import pytest
import respx

from osineitor.models import Entity, EntityType
from osineitor.modules.base import ModuleError
from osineitor.modules.email.hibp import Hibp
from osineitor.modules.email.hunter import HunterDomain, HunterVerify
from osineitor.modules.ip.abuseipdb import AbuseIpDb
from osineitor.modules.ip.greynoise import GreyNoise
from osineitor.modules.ip.shodan import Shodan

IP = Entity(type=EntityType.IP, value="8.8.8.8")
EMAIL = Entity(type=EntityType.EMAIL, value="test@example.com")
DOMAIN = Entity(type=EntityType.DOMAIN, value="example.com")


@pytest.fixture(autouse=True)
def keys(config):
    config.keys.update(shodan="S", abuseipdb="A", greynoise="G", hibp="H", hunter="U")


@respx.mock
async def test_shodan(ctx):
    route = respx.get("https://api.shodan.io/shodan/host/8.8.8.8").mock(
        return_value=httpx.Response(
            200,
            json={
                "org": "Google LLC",
                "os": None,
                "hostnames": ["dns.google"],
                "vulns": ["CVE-1"],
                "data": [
                    {"port": 53, "transport": "udp", "product": "Google DNS"},
                    {"port": 443, "transport": "tcp", "http": {"title": "Google"}},
                ],
            },
        )
    )
    out = await Shodan(ctx).run(IP)
    assert route.calls[0].request.url.params["key"] == "S"
    services = {e.value: e.data for e in out if e.type == EntityType.SERVICE}
    assert services["8.8.8.8:53"]["product"] == "Google DNS"
    assert services["8.8.8.8:443"]["http_title"] == "Google"
    assert [e.value for e in out if e.type == EntityType.VULNERABILITY] == ["CVE-1"]


@respx.mock
async def test_shodan_bad_key(ctx):
    respx.get("https://api.shodan.io/shodan/host/8.8.8.8").mock(return_value=httpx.Response(401))
    with pytest.raises(ModuleError, match="inválida"):
        await Shodan(ctx).run(IP)


@respx.mock
async def test_abuseipdb(ctx):
    route = respx.get("https://api.abuseipdb.com/api/v2/check").mock(
        return_value=httpx.Response(
            200, json={"data": {"abuseConfidenceScore": 87, "totalReports": 12, "isTor": False}}
        )
    )
    out = await AbuseIpDb(ctx).run(IP)
    assert route.calls[0].request.headers["Key"] == "A"
    assert out[0].data["abuse_score"] == 87


@respx.mock
async def test_greynoise(ctx):
    respx.get("https://api.greynoise.io/v3/community/8.8.8.8").mock(
        return_value=httpx.Response(
            200, json={"noise": False, "riot": True, "classification": "benign", "name": "Google"}
        )
    )
    out = await GreyNoise(ctx).run(IP)
    assert out[0].data["riot"] is True and out[0].data["name"] == "Google"


@respx.mock
async def test_hibp(ctx):
    route = respx.get("https://haveibeenpwned.com/api/v3/breachedaccount/test%40example.com").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "Name": "Adobe",
                    "BreachDate": "2013-10-04",
                    "PwnCount": 152445165,
                    "DataClasses": ["Email addresses", "Passwords"],
                }
            ],
        )
    )
    out = await Hibp(ctx).run(EMAIL)
    assert route.calls[0].request.headers["hibp-api-key"] == "H"
    assert out[0].type == EntityType.BREACH and out[0].value == "Adobe"
    assert out[0].data["data_classes"] == ["Email addresses", "Passwords"]


@respx.mock
async def test_hibp_clean(ctx):
    respx.get(url__startswith="https://haveibeenpwned.com/").mock(return_value=httpx.Response(404))
    assert await Hibp(ctx).run(EMAIL) == []


@respx.mock
async def test_hunter_verify(ctx):
    respx.get("https://api.hunter.io/v2/email-verifier").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "status": "valid",
                    "score": 95,
                    "sources": [{"uri": "https://example.com/team"}],
                }
            },
        )
    )
    out = await HunterVerify(ctx).run(EMAIL)
    assert out[0].data["status"] == "valid"
    assert out[1].type == EntityType.URL and out[1].value == "https://example.com/team"


@respx.mock
async def test_hunter_domain(ctx):
    respx.get("https://api.hunter.io/v2/domain-search").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "organization": "Example",
                    "pattern": "{first}.{last}",
                    "emails": [
                        {
                            "value": "Jane.Doe@example.com",
                            "first_name": "Jane",
                            "last_name": "Doe",
                            "type": "personal",
                            "confidence": 94,
                        }
                    ],
                }
            },
        )
    )
    out = await HunterDomain(ctx).run(DOMAIN)
    assert out[0].data["pattern"] == "{first}.{last}"
    assert out[1].value == "jane.doe@example.com"
    assert out[1].data["name"] == "Jane Doe" and out[1].data["email_type"] == "personal"

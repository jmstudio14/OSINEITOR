from __future__ import annotations

import json
import os
import time

import httpx
import pytest
import respx

from osineitor.errors import ModuleSkipped
from osineitor.models import Entity, EntityType
from osineitor.modules.domain import _bootstrap as bootstrap
from osineitor.modules.domain.crtsh import CrtSh
from osineitor.modules.domain.dns import Dns
from osineitor.modules.domain.http_fingerprint import HttpFingerprint
from osineitor.modules.domain.rdap import Rdap
from osineitor.modules.domain.wayback import Wayback
from tests.conftest import FakeResolver

DOMAIN = Entity(type=EntityType.DOMAIN, value="example.com")
SUB = Entity(type=EntityType.DOMAIN, value="a.example.com", data={"subdomain": True})

RDAP = {
    "status": ["client transfer prohibited"],
    "events": [
        {"eventAction": "registration", "eventDate": "2007-10-09T18:20:50Z"},
        {"eventAction": "expiration", "eventDate": "2028-10-09T18:20:50Z"},
    ],
    "nameservers": [{"ldhName": "NS1.EXAMPLE.NET"}],
    "secureDNS": {"delegationSigned": False},
    "entities": [
        {
            "roles": ["registrar"],
            "vcardArray": [
                "vcard",
                [["version", {}, "text", "4.0"], ["fn", {}, "text", "MarkMonitor"]],
            ],
        },
        {
            "roles": ["registrant"],
            "vcardArray": [
                "vcard",
                [["fn", {}, "text", "ACME"], ["email", {}, "text", "Admin@Acme.io"]],
            ],
        },
    ],
}


IANA = "https://data.iana.org/rdap/dns.json"
BOOTSTRAP = {
    "publication": "2026-10-28T22:00:04Z",
    "services": [[["com", "NET"], ["https://rdap.verisign.com/com/v1/"]]],
}


@respx.mock
async def test_rdap(ctx):
    respx.get(IANA).mock(return_value=httpx.Response(200, json=BOOTSTRAP))
    respx.get("https://rdap.org/domain/example.com").mock(
        return_value=httpx.Response(200, json=RDAP)
    )
    out = await Rdap(ctx).run(DOMAIN)
    record = out[0].data
    assert record["registrar"] == "MarkMonitor"
    assert record["created"].startswith("2007")
    assert record["nameservers"] == ["ns1.example.net"]
    assert out[1].type == EntityType.EMAIL and out[1].value == "admin@acme.io"
    assert not Rdap(ctx).accepts(SUB)


@respx.mock
async def test_rdap_skips_tld_without_rdap(ctx):
    respx.get(IANA).mock(return_value=httpx.Response(200, json=BOOTSTRAP))
    rdap_org = respx.get(url__startswith="https://rdap.org/")
    with pytest.raises(ModuleSkipped, match=r"\.es no tiene servidor RDAP"):
        await Rdap(ctx).run(Entity(type=EntityType.DOMAIN, value="ejemplo.es"))
    assert not rdap_org.called


@respx.mock
async def test_rdap_bootstrap_is_cached_on_disk(ctx):
    iana = respx.get(IANA).mock(return_value=httpx.Response(200, json=BOOTSTRAP))
    respx.get("https://rdap.org/domain/example.com").mock(
        return_value=httpx.Response(200, json=RDAP)
    )
    await Rdap(ctx).run(DOMAIN)
    await Rdap(ctx).run(DOMAIN)
    assert iana.call_count == 1
    assert bootstrap.cache_path().exists()


@respx.mock
async def test_rdap_without_bootstrap_still_tries_the_query(ctx):
    respx.get(IANA).mock(side_effect=httpx.ConnectError("sin red"))
    respx.get("https://rdap.org/domain/example.com").mock(
        return_value=httpx.Response(200, json=RDAP)
    )
    out = await Rdap(ctx).run(DOMAIN)
    assert out[0].data["registrar"] == "MarkMonitor"


@respx.mock
async def test_rdap_uses_stale_cache_when_iana_is_down(ctx):
    path = bootstrap.cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(BOOTSTRAP), encoding="utf-8")
    old = time.time() - 30 * 24 * 3600
    os.utime(path, (old, old))
    respx.get(IANA).mock(return_value=httpx.Response(503))
    with pytest.raises(ModuleSkipped):
        await Rdap(ctx).run(Entity(type=EntityType.DOMAIN, value="ejemplo.es"))


def test_bootstrap_parse_lowercases():
    assert bootstrap.parse(BOOTSTRAP) == {"com", "net"}


@respx.mock
async def test_rdap_ignores_invalid_contact_email(ctx):
    data = json.loads(json.dumps(RDAP))
    data["entities"][1]["vcardArray"][1][1][3] = "@@"
    respx.get(IANA).mock(return_value=httpx.Response(200, json=BOOTSTRAP))
    respx.get("https://rdap.org/domain/example.com").mock(
        return_value=httpx.Response(200, json=data)
    )
    out = await Rdap(ctx).run(DOMAIN)
    assert [e.type for e in out] == [EntityType.RECORD]


async def test_dns(ctx):
    ctx.resolver = FakeResolver(
        {
            ("example.com", "A"): ["93.184.216.34"],
            ("example.com", "MX"): ["10 mail.example.com."],
            ("example.com", "TXT"): ["v=spf1 -all", "google-site-verification=x"],
            ("_dmarc.example.com", "TXT"): ["v=DMARC1; p=reject"],
        }
    )
    out = await Dns(ctx).run(DOMAIN)
    record, ip = out
    assert record.data["SPF"] == "v=spf1 -all"
    assert record.data["DMARC"] == "v=DMARC1; p=reject"
    assert record.data["MX"] == ["10 mail.example.com"]
    assert ip.type == EntityType.IP and ip.value == "93.184.216.34"


async def test_dns_nothing(ctx):
    ctx.resolver = FakeResolver({})
    assert await Dns(ctx).run(DOMAIN) == []


@respx.mock
async def test_crtsh(ctx):
    respx.get("https://crt.sh/").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"name_value": "*.example.com\nwww.example.com"},
                {"name_value": "API.example.com"},
                {"name_value": "evil-example.com"},
            ],
        )
    )
    out = await CrtSh(ctx).run(DOMAIN)
    assert [e.value for e in out] == ["api.example.com", "www.example.com"]
    assert all(e.data["subdomain"] for e in out)


@respx.mock
async def test_wayback(ctx):
    rows = [
        ["timestamp", "original"],
        ["20200101000000", "https://example.com/"],
        ["20150101000000", "https://example.com/backup.sql"],
        ["20210101000000", "https://example.com/wp-admin/"],
        ["20220101000000", "https://example.com/x?token=abc"],
    ]
    respx.get("https://web.archive.org/cdx/search/cdx").mock(
        return_value=httpx.Response(200, json=rows)
    )
    out = await Wayback(ctx).run(DOMAIN)
    assert out[0].data["urls"] == 4
    assert out[0].data["first_seen"] == "20150101000000"
    assert {e.value for e in out[1:]} == {
        "https://example.com/backup.sql",
        "https://example.com/wp-admin/",
        "https://example.com/x?token=abc",
    }


@respx.mock
async def test_http_fingerprint(ctx):
    respx.get("https://example.com").mock(
        return_value=httpx.Response(
            200,
            headers={
                "server": "cloudflare",
                "cf-ray": "1",
                "strict-transport-security": "max-age=1",
            },
            text="<title> Hola  mundo </title><script src='/wp-content/x.js'></script>",
        )
    )
    out = await HttpFingerprint(ctx).run(DOMAIN)
    data = out[0].data
    assert data["title"] == "Hola mundo"
    assert {"Cloudflare", "WordPress"} <= set(data["technologies"])
    assert "strict-transport-security" not in data["missing_security_headers"]
    assert "content-security-policy" in data["missing_security_headers"]
    assert HttpFingerprint.passive is False

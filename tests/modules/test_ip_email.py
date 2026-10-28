from __future__ import annotations

import hashlib

import httpx
import pytest
import respx

from osineitor.models import Entity, EntityType
from osineitor.modules.base import ModuleError
from osineitor.modules.email.gravatar import Gravatar
from osineitor.modules.email.validate import EmailValidate
from osineitor.modules.ip.geo import IpInfo
from osineitor.modules.ip.internetdb import InternetDb
from tests.conftest import FakeResolver

IP = Entity(type=EntityType.IP, value="1.1.1.1")


@respx.mock
async def test_internetdb(ctx):
    respx.get("https://internetdb.shodan.io/1.1.1.1").mock(
        return_value=httpx.Response(
            200,
            json={
                "cpes": ["cpe:/a:cloudflare:cloudflare"],
                "hostnames": ["one.one.one.one"],
                "ip": "1.1.1.1",
                "ports": [53, 443],
                "tags": [],
                "vulns": ["CVE-2024-0001"],
            },
        )
    )
    out = await InternetDb(ctx).run(IP)
    assert out[0].data["hostnames"] == ["one.one.one.one"]
    assert [e.value for e in out if e.type == EntityType.SERVICE] == ["1.1.1.1:53", "1.1.1.1:443"]
    assert [e.value for e in out if e.type == EntityType.VULNERABILITY] == ["CVE-2024-0001"]


@respx.mock
async def test_internetdb_unknown_ip(ctx):
    respx.get("https://internetdb.shodan.io/1.1.1.1").mock(return_value=httpx.Response(404))
    assert await InternetDb(ctx).run(IP) == []


@respx.mock
async def test_ipinfo(ctx):
    respx.get("https://ipinfo.io/1.1.1.1/json").mock(
        return_value=httpx.Response(
            200,
            json={
                "ip": "1.1.1.1",
                "hostname": "one.one.one.one",
                "city": "Brisbane",
                "country": "AU",
                "org": "AS13335 Cloudflare, Inc.",
                "anycast": True,
            },
        )
    )
    out = await IpInfo(ctx).run(IP)
    assert out[0].data["org"] == "AS13335 Cloudflare, Inc."


@respx.mock
async def test_ipinfo_rate_limited(ctx):
    respx.get("https://ipinfo.io/1.1.1.1/json").mock(return_value=httpx.Response(429))
    with pytest.raises(ModuleError):
        await IpInfo(ctx).run(IP)


async def test_email_validate_corporate(ctx):
    ctx.resolver = FakeResolver({("acme.io", "MX"): ["10 mx.acme.io."]})
    out = await EmailValidate(ctx).run(Entity(type=EntityType.EMAIL, value="John.Doe+news@acme.io"))
    record, domain, username = out
    assert record.data["accepts_mail"] and not record.data["free_provider"]
    assert domain.value == "acme.io"
    assert username.value == "john.doe"


async def test_email_validate_free_provider_does_not_pivot_domain(ctx):
    ctx.resolver = FakeResolver({("gmail.com", "MX"): ["5 gmail-smtp-in.l.google.com."]})
    out = await EmailValidate(ctx).run(Entity(type=EntityType.EMAIL, value="someone@gmail.com"))
    assert [e.type for e in out] == [EntityType.RECORD, EntityType.USERNAME]


async def test_email_validate_bad_syntax(ctx):
    out = await EmailValidate(ctx).run(Entity(type=EntityType.EMAIL, value="not-an-email"))
    assert out[0].data == {"valid_syntax": False}


@respx.mock
async def test_gravatar(ctx):
    email = "user@example.com"
    digest = hashlib.sha256(email.encode()).hexdigest()
    respx.get(f"https://gravatar.com/{digest}.json").mock(
        return_value=httpx.Response(
            200,
            json={
                "entry": [
                    {
                        "profileUrl": "https://gravatar.com/juan",
                        "preferredUsername": "juan",
                        "displayName": "Juan",
                        "accounts": [
                            {
                                "url": "https://github.com/juan",
                                "shortname": "github",
                                "username": "juan",
                            }
                        ],
                    }
                ]
            },
        )
    )
    out = await Gravatar(ctx).run(Entity(type=EntityType.EMAIL, value=email))
    assert [(e.type, e.value) for e in out] == [
        (EntityType.PROFILE, "https://gravatar.com/juan"),
        (EntityType.USERNAME, "juan"),
        (EntityType.PROFILE, "https://github.com/juan"),
    ]

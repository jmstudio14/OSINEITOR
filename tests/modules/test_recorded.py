"""Cada módulo sin API key contra respuestas REALES grabadas (F0.2).

Las fixtures las genera `scripts/record_fixtures.py` (ver `docs/PRUEBAS_WINDOWS.md`). A
diferencia del resto de tests de módulos, aquí nada está inventado: si el servicio cambia de
formato, la fixture se vuelve a grabar y estos tests dicen qué parseo ha dejado de valer.
"""

from __future__ import annotations

import re

import pytest
import respx

from osineitor.models import Entity, EntityType, detect_type
from osineitor.modules.base import Context
from osineitor.modules.domain.crtsh import CrtSh
from osineitor.modules.domain.dns import Dns
from osineitor.modules.domain.http_fingerprint import HttpFingerprint
from osineitor.modules.domain.rdap import Rdap
from osineitor.modules.domain.wayback import Wayback
from osineitor.modules.email.gravatar import Gravatar
from osineitor.modules.email.validate import EmailValidate
from osineitor.modules.ip.geo import IpInfo
from osineitor.modules.ip.internetdb import InternetDb
from osineitor.modules.username import sites as username_sites
from tests import recorded


def entity(fixture: dict) -> Entity:
    return Entity(type=detect_type(fixture["target"]), value=fixture["target"])


def by_type(out: list[Entity], kind: EntityType) -> list[Entity]:
    return [e for e in out if e.type == kind]


@respx.mock
async def run(module_cls, ctx, case: str = "real") -> tuple[dict, list[Entity]]:
    fixture = recorded.load(module_cls.name, case)
    recorded.serve(fixture)
    context = Context(config=ctx.config, http=ctx.http, resolver=recorded.resolver(fixture))
    out = await module_cls(context).run(entity(fixture))
    assert len(out) == fixture["entities"], "el módulo ya no produce lo que produjo al grabar"
    return fixture, out


async def test_dns_github(ctx):
    _, out = await run(Dns, ctx)
    record = by_type(out, EntityType.RECORD)[0]
    assert record.value == "dns:github.com"
    assert record.data["A"] == ["20.250.119.67"]
    assert record.data["MX"] == ["0 github-com.mail.protection.outlook.com"]
    assert len(record.data["NS"]) == 8 and not any(n.endswith(".") for n in record.data["NS"])
    assert record.data["SPF"].startswith("v=spf1 ")
    assert record.data["DMARC"].startswith("v=DMARC1;")
    assert record.data["CAA"][0] == '0 issue "digicert.com"'
    assert [e.value for e in by_type(out, EntityType.IP)] == ["20.250.119.67"]


async def test_rdap_github(ctx):
    _, out = await run(Rdap, ctx)
    data = out[0].data
    assert out[0].value == "rdap:github.com"
    assert data["registrar"] == "MarkMonitor Inc."
    assert data["created"] == "2007-10-09T18:20:50Z"
    assert data["expires"] == "2028-10-09T18:20:50Z"
    assert "client transfer prohibited" in data["status"]
    assert len(data["nameservers"]) == 8
    assert data["dnssec"] is False


async def test_crtsh_example_org(ctx):
    _, out = await run(CrtSh, ctx)
    assert sorted(e.value for e in out) == ["www.example.org", "www.testdomain.example.org"]
    assert all(e.data == {"subdomain": True} for e in out)


async def test_wayback_example_org(ctx):
    _, out = await run(Wayback, ctx)
    summary = by_type(out, EntityType.RECORD)[0]
    assert summary.data["urls"] == 5000 and summary.data["truncated"] is True
    assert summary.data["first_seen"] == "20020121085054"
    assert summary.data["interesting"] == len(by_type(out, EntityType.URL)) == 90


async def test_ipinfo_cloudflare_dns(ctx):
    _, out = await run(IpInfo, ctx)
    assert out[0].data["org"] == "AS13335 Cloudflare, Inc."
    assert out[0].data["hostname"] == "one.one.one.one"
    assert out[0].data["anycast"] is True


async def test_internetdb_cloudflare_dns(ctx):
    _, out = await run(InternetDb, ctx)
    services = by_type(out, EntityType.SERVICE)
    assert [s.value for s in services][:2] == ["1.1.1.1:53", "1.1.1.1:69"]
    assert len(services) == 11
    assert "one.one.one.one" in out[0].data["hostnames"]
    assert not by_type(out, EntityType.VULNERABILITY)


async def test_gravatar_without_profile(ctx):
    _, out = await run(Gravatar, ctx)
    assert out == []


async def test_gravatar_profile(ctx):
    _, out = await run(Gravatar, ctx, "perfil")
    profile = by_type(out, EntityType.PROFILE)[0]
    assert profile.value == "https://gravatar.com/theoctocat"
    assert profile.data["site"] == "Gravatar"
    assert by_type(out, EntityType.USERNAME)[0].value == "theoctocat"


async def test_email_validate_resolvable_domain(ctx):
    _, out = await run(EmailValidate, ctx)
    data = by_type(out, EntityType.RECORD)[0].data
    assert data["accepts_mail"] is True
    assert data["mx"] == ["0 github-com.mail.protection.outlook.com"]
    assert [e.value for e in by_type(out, EntityType.DOMAIN)] == ["github.com"]
    assert [e.value for e in by_type(out, EntityType.USERNAME)] == ["octocat"]


async def test_http_fingerprint_reads_the_real_headers(ctx):
    _, out = await run(HttpFingerprint, ctx)
    data = out[0].data
    assert data["status"] == 200 and data["title"] == "Example Domain"
    assert data["server"] == "cloudflare"
    assert "Cloudflare" in data["technologies"]
    assert "strict-transport-security" in data["missing_security_headers"]


# --- username_sites: un subconjunto de sitios, con un username real y con uno inexistente --------


def subset_of(fixture: dict):
    class Subset(username_sites.UsernameSites):
        def sites(self):
            every = super().sites()
            return {name: every[name] for name in fixture["sites"]}

    return Subset


def control_username(fixture: dict) -> str:
    """El username de control que `_verify` generó al grabar (aparece en las URL grabadas)."""
    for call in fixture["http"]:
        found = re.search(r"/(x[0-9a-f]{14})\b", call["url"])
        if found:
            return found.group(1)
    raise AssertionError("la fixture no contiene la petición de control")


@pytest.mark.parametrize(
    ("case", "expected"),
    [
        # GitLab responde `[]` (octocat no existe allí). Reddit responde 200 también al username
        # de control: se descarta por falso positivo. npm (403, WAF) y HackerNews (419) no se
        # pudieron evaluar desde esta red: no son hallazgos.
        ("existe", ["GitHub", "Keybase", "Medium"]),
        ("inexistente", []),
    ],
)
async def test_username_sites_real_responses(ctx, monkeypatch, case, expected):
    fixture = recorded.load("username_sites", case)
    control = control_username(fixture)
    monkeypatch.setattr(username_sites.secrets, "token_hex", lambda _n: control[1:])
    with respx.mock:
        recorded.serve(fixture)
        module = subset_of(fixture)(ctx)
        out = await module.run(entity(fixture))
    assert sorted(e.data["site"] for e in out) == sorted(expected)
    assert all(e.data["verified"] is True for e in out)

"""F4.4, F4.11, F4.12 y F4.13: mail_security, whois, cert_details y saas_footprint."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
from datetime import UTC, datetime, timedelta

import dns.exception
import httpx
import pytest
import respx

from osineitor.engine import Engine
from osineitor.errors import ModuleError, ModuleQuota, ModuleSkipped
from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module
from osineitor.modules.domain import whois as whois_module
from osineitor.modules.domain.cert_details import CertDetails
from osineitor.modules.domain.mail_security import MailSecurity
from osineitor.modules.domain.saas_footprint import SaasFootprint
from osineitor.modules.domain.whois import Whois
from tests.conftest import FakeResolver

DOMAIN = Entity(type=EntityType.DOMAIN, value="example.com")
SUB = Entity(type=EntityType.DOMAIN, value="a.example.com", data={"subdomain": True})


class DeadResolver:
    async def resolve(self, name, rtype, lifetime=None):
        raise dns.exception.Timeout()


# --- mail_security ---------------------------------------------------------------------------


async def test_mail_security(ctx):
    ctx.resolver = FakeResolver(
        {
            ("_mta-sts.example.com", "TXT"): ["v=STSv1; id=20260101"],
            ("_smtp._tls.example.com", "TXT"): ["v=TLSRPTv1; rua=mailto:tls@example.com"],
            ("default._bimi.example.com", "TXT"): ["v=BIMI1; l=https://example.com/logo.svg"],
            ("google._domainkey.example.com", "TXT"): ["k=rsa; p=MIGfMA0"],
            ("selector1._domainkey.example.com", "TXT"): ["v=DKIM1; k=rsa; p=MIIBIj"],
            ("k1._domainkey.example.com", "TXT"): ["v=spf1 -all"],  # TXT cualquiera: no es DKIM
        }
    )
    (record,) = await MailSecurity(ctx).run(DOMAIN)
    assert record.type == EntityType.RECORD
    assert record.value == "mail_security:example.com"
    assert record.data["MTA_STS"] == "v=STSv1; id=20260101"
    assert record.data["TLS_RPT"].startswith("v=TLSRPTv1")
    assert record.data["BIMI"].startswith("v=BIMI1")
    assert record.data["DKIM"] == ["google", "selector1"]


async def test_mail_security_without_any_policy_is_empty(ctx):
    ctx.resolver = FakeResolver({})
    assert await MailSecurity(ctx).run(DOMAIN) == []


async def test_mail_security_with_a_dead_resolver_is_an_error(ctx):
    ctx.resolver = DeadResolver()
    with pytest.raises(ModuleError, match="no respondió"):
        await MailSecurity(ctx).run(DOMAIN)


def test_mail_security_only_runs_on_the_investigated_domain(ctx):
    module = MailSecurity(ctx)
    assert module.accepts(DOMAIN)
    assert not module.accepts(SUB)


# --- whois -----------------------------------------------------------------------------------

WHOIS_IO = """\
This domain is protected by the Registry Lock service.

Domain Name: google.io
Updated Date: 2026-09-03T10:48:03Z
Creation Date: 2002-10-01T01:00:00Z
Registry Expiry Date: 2027-09-30T01:00:00Z
Registrar: MarkMonitor Inc.
Domain Status: clientDeleteProhibited https://icann.org/epp#clientDeleteProhibited
Domain Status: serverDeleteProhibited https://icann.org/epp#serverDeleteProhibited
Registrant Name: Ana Pérez
Registrant Organization: Acme Titular SL
Registrant Email: ana@acme.example
Registrant Phone: +34 600 000 000
Admin Name: Luis Gómez
Name Server: NS1.GOOGLE.COM
Name Server: ns2.google.com
DNSSEC: unsigned
"""

WHOIS_DE = """\
% Restricted rights.
Domain: denic.de
Nserver: ns1.denic.de 77.67.63.106 2001:668:1f:11:0:0:0:106
Nserver: ns4.denic.net
Status: connect
Changed: 2024-12-19T13:33:43+01:00
"""

WHOIS_BE = """\
Domain:\tgoogle.be
Status:\tNOT AVAILABLE
Registered:\tTue Dec 12 2000

Registrant:
\tNot shown, please visit www.dnsbelgium.be for webbased whois.

Registrar:
\tName:\tMarkmonitor Inc.
\tWebsite:\thttps://www.markmonitor.com

Nameservers:
\tns3.google.com
\tns1.google.com
"""


@pytest.fixture
def ask(monkeypatch):
    """Sustituye el socket: devuelve el texto indicado y anota (servidor, consulta)."""
    calls: list[tuple[str, str]] = []
    reply = {"text": WHOIS_IO}

    async def fake(self, server, query, port=43):
        calls.append((server, query))
        return reply["text"]

    monkeypatch.setattr(Whois, "_ask", fake)
    return calls, reply


async def test_whois_extracts_registration_data(ctx, ask):
    calls, _ = ask
    (record,) = await Whois(ctx).run(Entity(type=EntityType.DOMAIN, value="google.io"))
    assert calls == [("whois.nic.io", "google.io")]
    assert record.value == "whois:google.io"
    assert record.data == {
        "registrar": "MarkMonitor Inc.",
        "created": "2002-10-01T01:00:00+00:00",
        "expires": "2027-09-30T01:00:00+00:00",
        "updated": "2026-09-03T10:48:03+00:00",
        "status": ["clientDeleteProhibited", "serverDeleteProhibited"],
        "nameservers": ["ns1.google.com", "ns2.google.com"],
        "dnssec": False,
    }


async def test_whois_never_keeps_the_holders_personal_data(ctx, ask):
    out = await Whois(ctx).run(Entity(type=EntityType.DOMAIN, value="google.io"))
    assert [e.type for e in out] == [EntityType.RECORD]  # ni siquiera un email
    dumped = json.dumps(out[0].data, ensure_ascii=False)
    for private in ("Ana", "Acme", "acme.example", "+34", "Luis"):
        assert private not in dumped


async def test_whois_de_uses_its_query_syntax_and_keeps_only_what_is_public(ctx, ask):
    calls, reply = ask
    reply["text"] = WHOIS_DE
    (record,) = await Whois(ctx).run(Entity(type=EntityType.DOMAIN, value="denic.de"))
    assert calls == [("whois.denic.de", "-T dn,ace denic.de")]
    assert record.data["registrar"] is None  # DENIC no lo publica: se omite, no se inventa
    assert record.data["nameservers"] == ["ns1.denic.de", "ns4.denic.net"]
    assert record.data["status"] == ["connect"]
    assert record.data["updated"] == "2024-12-19T13:33:43+01:00"


async def test_whois_reads_blocks_with_headings_and_bare_values(ctx, ask):
    _, reply = ask
    reply["text"] = WHOIS_BE
    (record,) = await Whois(ctx).run(Entity(type=EntityType.DOMAIN, value="google.be"))
    assert record.data["registrar"] == "Markmonitor Inc."
    assert record.data["nameservers"] == ["ns3.google.com", "ns1.google.com"]
    assert record.data["created"] == "2000-12-12T00:00:00"
    assert record.data["status"] == ["NOT AVAILABLE"]


@pytest.mark.parametrize(
    "text", ['No match for domain "NOPE.IO"', "Domain: x.de\nStatus: free", "NOT FOUND"]
)
async def test_whois_unregistered_domain_is_empty_not_an_error(ctx, ask, text):
    ask[1]["text"] = text
    assert await Whois(ctx).run(Entity(type=EntityType.DOMAIN, value="nope.io")) == []


async def test_whois_unreadable_answer_is_an_error_never_a_silent_empty(ctx, ask):
    ask[1]["text"] = "algo que no es una respuesta WHOIS"
    with pytest.raises(ModuleError, match="no trae campos de registro"):
        await Whois(ctx).run(Entity(type=EntityType.DOMAIN, value="google.io"))


async def test_whois_rate_limited_is_a_quota_error(ctx, ask):
    ask[1]["text"] = "WHOIS LIMIT EXCEEDED - SEE WWW.NIC.IO/WHOIS FOR DETAILS"
    with pytest.raises(ModuleQuota):
        await Whois(ctx).run(Entity(type=EntityType.DOMAIN, value="google.io"))


async def test_whois_es_says_why_there_is_no_data(ctx, ask):
    with pytest.raises(ModuleSkipped, match=r"\.es.*Red\.es"):
        await Whois(ctx).run(Entity(type=EntityType.DOMAIN, value="example.es"))
    assert ask[0] == []  # ni se intenta la conexión


async def test_whois_tld_without_a_server_is_skipped_with_a_warning(ctx, ask):
    with pytest.raises(ModuleSkipped, match=r"\.com.*rdap"):
        await Whois(ctx).run(DOMAIN)


async def test_whois_talks_to_the_server_over_a_socket(ctx, monkeypatch):
    monkeypatch.setattr(whois_module, "MIN_INTERVAL", 0.0)
    received: list[bytes] = []

    async def handle(reader, writer):
        received.append(await reader.readline())
        writer.write(WHOIS_IO.encode())
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    async with server:
        text = await Whois(ctx)._ask("127.0.0.1", "google.io", port=port)
    assert received == [b"google.io\r\n"]
    assert text == WHOIS_IO


async def test_whois_unreachable_server_is_an_error(ctx, monkeypatch):
    monkeypatch.setattr(whois_module, "MIN_INTERVAL", 0.0)
    server = await asyncio.start_server(lambda r, w: None, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    server.close()
    await server.wait_closed()  # el puerto queda libre y nadie escucha
    with pytest.raises(ModuleError, match="no respondió"):
        await Whois(ctx)._ask("127.0.0.1", "google.io", port=port)


async def test_whois_spaces_out_queries_to_the_same_server(ctx, monkeypatch):
    monkeypatch.setattr(whois_module, "MIN_INTERVAL", 0.3)

    async def handle(reader, writer):
        await reader.readline()
        writer.write(b"x")
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    module = Whois(ctx)
    async with server:
        start = asyncio.get_running_loop().time()
        await asyncio.gather(
            module._ask("127.0.0.1", "a.io", port=port), module._ask("127.0.0.1", "b.io", port=port)
        )
    assert asyncio.get_running_loop().time() - start >= 0.25


def test_whois_is_not_run_over_a_proxy():
    assert Whois.direct_dns  # el socket no pasa por --proxy: con proxy el engine lo omite


# --- cert_details ----------------------------------------------------------------------------


def _pem(der: bytes) -> str:
    # `ssl.PEM_cert_to_DER_cert` solo decodifica el base64: sirve cualquier contenido.
    body = base64.encodebytes(der).decode()
    return f"-----BEGIN CERTIFICATE-----\n{body}-----END CERTIFICATE-----\n"


def _ts(delta: timedelta) -> str:
    return (datetime.now(UTC) + delta).strftime("%Y-%m-%dT%H:%M:%S")


def _row(cert_id: int, names: str, *, after: timedelta, before: timedelta = timedelta(days=-60)):
    return {
        "id": cert_id,
        "issuer_name": "C=US, O=Let's Encrypt, CN=R11",
        "common_name": "example.com",
        "name_value": names,
        "not_before": _ts(before),
        "not_after": _ts(after),
        "serial_number": f"0{cert_id}ab",
    }


CRT = "https://crt.sh/"


@respx.mock
async def test_cert_details(ctx):
    rows = [
        _row(1, "example.com\n*.example.com\nwww.example.com\nOtro.ORG", after=timedelta(days=80)),
        _row(2, "example.com", after=timedelta(days=10), before=timedelta(days=-100)),
        _row(3, "example.com", after=timedelta(days=-5), before=timedelta(days=-200)),
    ]
    respx.get(CRT, params={"q": "example.com", "output": "json"}).mock(
        return_value=httpx.Response(200, json=rows)
    )
    for i in (1, 2, 3):
        respx.get(CRT, params={"d": str(i)}).mock(
            return_value=httpx.Response(200, text=_pem(f"der-{i}".encode()))
        )

    out = await CertDetails(ctx).run(DOMAIN)
    certs = {e.value: e for e in out if e.type == EntityType.CERTIFICATE}
    assert set(certs) == {hashlib.sha256(f"der-{i}".encode()).hexdigest() for i in (1, 2, 3)}
    first = certs[hashlib.sha256(b"der-1").hexdigest()]
    assert first.data["issuer"] == "C=US, O=Let's Encrypt, CN=R11"
    assert first.data["serial"] == "01ab"
    assert first.data["san"] == ["*.example.com", "example.com", "otro.org", "www.example.com"]
    assert first.data["status"] == "valido"
    assert first.data["expires_in_days"] in (79, 80)
    assert certs[hashlib.sha256(b"der-2").hexdigest()].data["status"] == "caduca_pronto"
    assert certs[hashlib.sha256(b"der-3").hexdigest()].data["status"] == "caducado"

    domains = {e.value: e.data for e in out if e.type == EntityType.DOMAIN}
    assert domains == {"otro.org": {}, "www.example.com": {"subdomain": True}}


@respx.mock
async def test_cert_details_a_failed_certificate_does_not_lose_the_rest(ctx):
    rows = [
        _row(1, "example.com", after=timedelta(days=80)),
        _row(2, "example.com", after=timedelta(days=9)),
    ]
    respx.get(CRT, params={"q": "example.com", "output": "json"}).mock(
        return_value=httpx.Response(200, json=rows)
    )
    respx.get(CRT, params={"d": "1"}).mock(return_value=httpx.Response(200, text=_pem(b"der-1")))
    respx.get(CRT, params={"d": "2"}).mock(return_value=httpx.Response(500))
    out = await CertDetails(ctx).run(DOMAIN)
    assert [e.value for e in out] == [hashlib.sha256(b"der-1").hexdigest()]


@respx.mock
async def test_cert_details_every_certificate_failing_is_an_error(ctx):
    respx.get(CRT, params={"q": "example.com", "output": "json"}).mock(
        return_value=httpx.Response(200, json=[_row(1, "example.com", after=timedelta(days=9))])
    )
    respx.get(CRT, params={"d": "1"}).mock(return_value=httpx.Response(500))
    with pytest.raises(ModuleError, match="500"):
        await CertDetails(ctx).run(DOMAIN)


@respx.mock
async def test_cert_details_keeps_at_most_the_newest_certificates(ctx, monkeypatch):
    rows = [
        _row(i, "example.com", after=timedelta(days=80), before=timedelta(days=-i))
        for i in range(1, 6)
    ]
    respx.get(CRT, params={"q": "example.com", "output": "json"}).mock(
        return_value=httpx.Response(200, json=rows)
    )
    pem = respx.get(url__regex=r"https://crt\.sh/\?d=\d+").mock(
        return_value=httpx.Response(200, text=_pem(b"der"))
    )
    monkeypatch.setattr("osineitor.modules.domain.cert_details.MAX_CERTS", 2)
    await CertDetails(ctx).run(DOMAIN)
    # `not_before` más reciente = id más bajo en este ejemplo
    assert sorted(c.request.url.params["d"] for c in pem.calls) == ["1", "2"]


@respx.mock
async def test_cert_details_ignores_invalid_names_in_a_certificate(ctx):
    rows = [_row(1, "example.com\nno es un host\n-malo-.example.com", after=timedelta(days=80))]
    respx.get(CRT, params={"q": "example.com", "output": "json"}).mock(
        return_value=httpx.Response(200, json=rows)
    )
    respx.get(CRT, params={"d": "1"}).mock(return_value=httpx.Response(200, text=_pem(b"der")))
    out = await CertDetails(ctx).run(DOMAIN)
    assert [e.type for e in out] == [EntityType.CERTIFICATE]


@respx.mock
async def test_cert_details_rate_limit_is_a_quota_error(ctx):
    respx.get(CRT, params={"q": "example.com", "output": "json"}).mock(
        return_value=httpx.Response(429)
    )
    with pytest.raises(ModuleQuota):
        await CertDetails(ctx).run(DOMAIN)


@respx.mock
async def test_cert_details_overloaded_crtsh_is_an_error(ctx):
    respx.get(CRT, params={"q": "example.com", "output": "json"}).mock(
        return_value=httpx.Response(200, text="<html>busy</html>")
    )
    with pytest.raises(ModuleError, match="JSON"):
        await CertDetails(ctx).run(DOMAIN)


# --- saas_footprint --------------------------------------------------------------------------

DNS_RECORD = Entity(
    type=EntityType.RECORD,
    value="dns:example.com",
    data={
        "MX": ["1 aspmx.l.google.com", "5 ALT1.ASPMX.L.GOOGLE.COM."],
        "NS": ["ada.ns.cloudflare.com", "bob.ns.cloudflare.com"],
        "TXT": [
            "v=spf1 include:_spf.google.com include:sendgrid.net ~all",
            "google-site-verification=abc",
            "MS=ms12345678",
            "atlassian-domain-verification=xyz",
        ],
        "SPF": "v=spf1 include:_spf.google.com include:sendgrid.net ~all",
    },
)


async def test_saas_footprint(ctx):
    found = {e.value: e.data for e in await SaasFootprint(ctx).run(DNS_RECORD)}
    assert {name: d["category"] for name, d in found.items()} == {
        "Google Workspace": "email",
        "SendGrid": "email",
        "Cloudflare DNS": "dns",
        "Microsoft Entra ID": "identity",
        "Google (verificación de dominio)": "collaboration",
        "Atlassian": "collaboration",
    }
    assert found["Google Workspace"]["evidence"] == [
        "MX alt1.aspmx.l.google.com (aspmx.l.google.com)",
        "MX aspmx.l.google.com (aspmx.l.google.com)",
        "SPF include:_spf.google.com (_spf.google.com)",
    ]
    assert found["Cloudflare DNS"]["signatures"] == 1


async def test_saas_footprint_without_signatures_matching_is_empty(ctx):
    record = Entity(type=EntityType.RECORD, value="dns:x.test", data={"MX": ["10 mail.x.test"]})
    assert await SaasFootprint(ctx).run(record) == []


def test_saas_footprint_only_reads_dns_records(ctx):
    module = SaasFootprint(ctx)
    assert module.accepts(DNS_RECORD)
    assert not module.accepts(Entity(type=EntityType.RECORD, value="rdap:example.com"))
    assert not module.accepts(DOMAIN)


def test_the_signature_table_is_versioned_and_well_formed():
    from osineitor.modules.domain.saas_footprint import signatures

    table = signatures()
    assert isinstance(table["version"], int)
    names = [p["name"] for p in table["providers"]]
    assert len(names) == len(set(names))
    for provider in table["providers"]:
        assert provider["category"] in {"email", "dns", "identity", "collaboration"}
        assert any(k in provider for k in ("mx", "ns", "ns_contains", "spf", "txt"))


class FakeDns(Module):
    name = "fake_dns"
    description = "deja un registro DNS ya hecho"
    consumes = frozenset({EntityType.DOMAIN})
    produces = frozenset({EntityType.RECORD})

    async def run(self, entity):
        return [self.emit(entity, EntityType.RECORD, "dns:example.com", **DNS_RECORD.data)]


async def test_saas_footprint_makes_no_request_and_costs_no_budget(ctx):
    with respx.mock(assert_all_mocked=True) as router:
        engine = Engine(ctx, [FakeDns, SaasFootprint])
        result = await engine.run(DOMAIN)
    assert not router.calls
    assert engine.budget.requests == 0
    assert {r.module: r.status for r in result.runs} == {"fake_dns": "ok", "saas_footprint": "ok"}
    technologies = {e.value for e in result.entities if e.type == EntityType.TECHNOLOGY}
    assert {"Google Workspace", "Cloudflare DNS", "Atlassian"} <= technologies


@respx.mock
async def test_cert_details_certificates_that_arrive_late_do_not_lose_the_rest(ctx, monkeypatch):
    monkeypatch.setattr("osineitor.modules.domain.cert_details.DOWNLOAD_BUDGET", 0.3)
    rows = [
        _row(1, "example.com", after=timedelta(days=80)),
        _row(2, "example.com", after=timedelta(days=80), before=timedelta(days=-90)),
    ]
    respx.get(CRT, params={"q": "example.com", "output": "json"}).mock(
        return_value=httpx.Response(200, json=rows)
    )
    respx.get(CRT, params={"d": "1"}).mock(return_value=httpx.Response(200, text=_pem(b"der-1")))

    async def slow(request):
        await asyncio.sleep(5)
        return httpx.Response(200, text=_pem(b"der-2"))

    respx.get(CRT, params={"d": "2"}).mock(side_effect=slow)
    out = await CertDetails(ctx).run(DOMAIN)
    assert [e.value for e in out] == [hashlib.sha256(b"der-1").hexdigest()]


@respx.mock
async def test_cert_details_nothing_arriving_in_time_is_an_error(ctx, monkeypatch):
    monkeypatch.setattr("osineitor.modules.domain.cert_details.DOWNLOAD_BUDGET", 0.2)
    respx.get(CRT, params={"q": "example.com", "output": "json"}).mock(
        return_value=httpx.Response(200, json=[_row(1, "example.com", after=timedelta(days=80))])
    )

    async def slow(request):
        await asyncio.sleep(5)
        return httpx.Response(200, text=_pem(b"der"))

    respx.get(CRT, params={"d": "1"}).mock(side_effect=slow)
    with pytest.raises(ModuleError, match="a tiempo"):
        await CertDetails(ctx).run(DOMAIN)

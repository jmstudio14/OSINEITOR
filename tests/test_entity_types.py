"""F3.1 y F3.6: tipos de entidad ampliados, su normalización y las semillas URL, CIDR y ASN."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from osineitor.cli import app
from osineitor.engine import Engine
from osineitor.errors import InvalidEntityValue
from osineitor.models import Entity, EntityType, ScanResult, decompose, detect_type
from tests.test_cli import fake_module, use_modules

runner = CliRunner()


@pytest.mark.parametrize(
    ("kind", "raw", "expected"),
    [
        ("asn", "as13335", "AS13335"),
        ("asn", " 13335 ", "AS13335"),
        ("asn", "AS0013335", "AS13335"),
        ("netblock", "10.0.0.5/24", "10.0.0.0/24"),
        ("netblock", "2001:DB8::1/32", "2001:db8::/32"),
        ("certificate", "AB:" * 31 + "AB", "ab" * 32),
        ("phone", "+34 600-123-456", "+34600123456"),
        ("phone", "0034 (600) 123.456", "+34600123456"),
        ("crypto_address", " bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq ", None),
        ("organization", "  Acme   Corp \n", "Acme Corp"),
        ("person", "Ana  Pérez", "Ana Pérez"),
        ("technology", "nginx", "nginx"),
        ("location", "Madrid,  España", "Madrid, España"),
        ("file", "informe.pdf", "informe.pdf"),
        ("finding", "Panel de administración expuesto", "Panel de administración expuesto"),
    ],
)
def test_each_new_type_is_stored_in_canonical_form(kind, raw, expected):
    entity = Entity(type=kind, value=raw)
    assert entity.value == (expected or raw.strip())


@pytest.mark.parametrize(
    ("kind", "bad"),
    [
        ("asn", "AS"),
        ("asn", "AS4294967296"),
        ("asn", "AS0"),
        ("asn", "ASX1"),
        ("netblock", "10.0.0.0/33"),
        ("netblock", "example.com"),
        ("certificate", "abc"),
        ("certificate", "zz" * 32),
        ("phone", "600123456"),  # sin prefijo internacional
        ("phone", "+0123456789"),
        ("crypto_address", "corta"),
        ("crypto_address", "con espacios en medio de la dirección"),
        ("organization", "   "),
        ("person", "con\x00nulo"),
        ("location", "x" * 513),
    ],
)
def test_invalid_values_are_rejected(kind, bad):
    with pytest.raises(ValueError):
        Entity(type=kind, value=bad)


def test_identity_uses_the_canonical_form():
    assert Entity(type="asn", value="as13335").key == Entity(type="asn", value="13335").key


def test_every_entity_type_has_a_valid_example():
    """Un tipo nuevo en `EntityType` sin regla de normalización pasaría sin validar nada."""
    examples = {
        "domain": "example.com",
        "ip": "1.1.1.1",
        "email": "a@example.com",
        "username": "ana",
        "url": "https://example.com/",
        "profile": "https://x.test/ana",
        "service": "1.1.1.1:443",
        "vulnerability": "CVE-2024-0001",
        "breach": "Adobe",
        "record": "txt:v=spf1",
        "asn": "AS13335",
        "netblock": "1.1.1.0/24",
        "certificate": "ab" * 32,
        "technology": "nginx",
        "organization": "Acme",
        "person": "Ana",
        "phone": "+34600123456",
        "crypto_address": "bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq",
        "file": "a.pdf",
        "location": "Madrid",
        "finding": "algo",
    }
    assert set(examples) == {t.value for t in EntityType}
    for kind, value in examples.items():
        assert Entity(type=kind, value=value).type == kind


def test_new_types_survive_the_database(storage):
    seed = Entity(type=EntityType.DOMAIN, value="example.com")
    result = ScanResult(
        target=seed,
        depth=1,
        entities=[
            Entity(type=EntityType.ASN, value="13335", data={"holder": "Cloudflare"}),
            Entity(type=EntityType.CERTIFICATE, value="AB:" * 31 + "AB"),
        ],
    )
    scan_id = storage.save(result)
    loaded = storage.load(scan_id)
    assert [(e.type, e.value) for e in loaded.entities] == [
        (EntityType.ASN, "AS13335"),
        (EntityType.CERTIFICATE, "ab" * 32),
    ]


# --- F3.6: semillas ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("https://Example.com/a?b=1", EntityType.URL),
        ("http://user:clave@example.com/", EntityType.URL),  # el `@` no lo hace un email
        ("http://[2001:db8::1]:8080/", EntityType.URL),
        ("1.1.1.0/24", EntityType.NETBLOCK),
        ("10.0.0.5/8", EntityType.NETBLOCK),
        ("2001:db8::/32", EntityType.NETBLOCK),
        ("AS13335", EntityType.ASN),
        ("as15169", EntityType.ASN),
        ("1.1.1.1", EntityType.IP),
        ("ana@example.com", EntityType.EMAIL),
        ("example.com", EntityType.DOMAIN),
        ("ana", EntityType.USERNAME),
        ("asimov", EntityType.USERNAME),  # empieza por «as» pero no es un ASN
        ("a/b", EntityType.USERNAME),
        ("ftp://example.com", EntityType.USERNAME),  # solo http y https
    ],
)
def test_detect_type_recognizes_urls_networks_and_asns(text, expected):
    assert detect_type(text) == expected


def test_a_url_decomposes_into_its_host():
    url = Entity(type=EntityType.URL, value="https://Sub.Example.COM:8443/a?b=1")
    [host] = decompose(url)
    assert (host.type, host.value, host.parent, host.source) == (
        EntityType.DOMAIN,
        "sub.example.com",
        url.key,
        "engine",
    )
    assert [o.module for o in host.observations] == ["engine"]


def test_a_url_with_an_ip_host_decomposes_into_an_ip():
    [host] = decompose(Entity(type=EntityType.URL, value="http://[2001:db8::1]:8080/"))
    assert (host.type, host.value) == (EntityType.IP, "2001:db8::1")


def test_only_urls_decompose():
    assert decompose(Entity(type=EntityType.DOMAIN, value="example.com")) == []


def test_a_url_without_a_valid_host_is_an_error():
    with pytest.raises(InvalidEntityValue):
        decompose(Entity(type=EntityType.URL, value="https://exa mple.com/"))


async def test_scanning_a_url_investigates_its_host(ctx):
    dns = fake_module("fake_dns", {EntityType.DOMAIN}, EntityType.IP, "9.9.9.9")
    seed = Entity(type=EntityType.URL, value="https://example.com/login")
    result = await Engine(ctx, [dns]).run(seed)
    assert [(e.type, e.value) for e in result.entities] == [
        (EntityType.DOMAIN, "example.com"),
        (EntityType.IP, "9.9.9.9"),
    ]
    assert result.target == seed


async def test_the_scope_applies_to_the_host_of_a_url(ctx):
    from osineitor.scope import Scope

    dns = fake_module("fake_dns", {EntityType.DOMAIN}, EntityType.IP, "9.9.9.9")
    scope = Scope.parse({"domains": ["otro.test"]})
    seed = Entity(type=EntityType.URL, value="https://example.com/")
    result = await Engine(ctx, [dns], scope=scope).run(seed)
    assert result.entities == []


def test_the_cli_scans_a_url_and_rejects_a_hostless_one(monkeypatch, tmp_path):
    use_modules(
        monkeypatch, [fake_module("fake_dns", {EntityType.DOMAIN}, EntityType.IP, "9.9.9.9")]
    )
    ok = runner.invoke(app, ["scan", "--json", "--no-save", "https://example.com/a"])
    assert ok.exit_code == 0, ok.output
    data = json.loads(ok.output)
    assert data["target"]["type"] == "url"
    assert [e["value"] for e in data["entities"]] == ["example.com", "9.9.9.9"]
    assert runner.invoke(app, ["scan", "--no-save", "https://@/"]).exit_code == 2


def test_a_network_or_asn_seed_is_accepted(monkeypatch):
    use_modules(monkeypatch, [])
    for target, kind in (("1.1.1.0/24", "netblock"), ("AS13335", "asn")):
        done = runner.invoke(app, ["scan", "--json", "--no-save", target])
        assert done.exit_code == 0, done.output
        assert json.loads(done.output)["target"]["type"] == kind

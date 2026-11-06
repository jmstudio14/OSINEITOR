from __future__ import annotations

import dns.exception
import pytest
import respx

from osineitor.models import Entity, EntityType
from osineitor.modules.base import ModuleError
from osineitor.modules.domain import lookalike_domains
from osineitor.modules.domain.lookalike_domains import LookalikeDomains, permutations
from tests.conftest import FakeResolver

DOMAIN = Entity(type=EntityType.DOMAIN, value="example.com")


def test_permutations_cover_every_technique_and_exclude_the_domain():
    found = permutations("example.com")
    assert "example.com" not in found
    assert found["exmple.com"] == "omisión"
    assert found["eexample.com"] == "repetición"
    assert found["examlpe.com"] == "transposición"
    assert found["wxample.com"] == "teclado"
    assert found["ex-ample.com"] == "guion"
    assert found["examp1e.com"] == "homógrafo"
    assert found["example.net"] == "tld"
    # un homógrafo cirílico sale como punycode, no como Unicode
    assert all(name.isascii() for name in found)
    assert any(name.startswith("xn--") for name in found)


def test_permutations_are_capped_and_deterministic(monkeypatch):
    monkeypatch.setattr(lookalike_domains, "MAX_CANDIDATES", 40)
    found = permutations("averyveryverylongexamplename.com")
    assert len(found) == 40
    assert found == permutations("averyveryverylongexamplename.com")
    assert {"tld", "omisión", "homógrafo"} <= set(found.values())  # el tope no deja fuera técnicas


def test_permutations_never_produce_an_invalid_label():
    for name in permutations("ab.es"):
        label = name.partition(".")[0]
        assert label and not label.startswith("-") and not label.endswith("-")


@respx.mock  # cualquier petición HTTP sin ruta simulada fallaría
async def test_registered_lookalikes_are_reported_without_http_or_domain_entities(ctx):
    ctx.resolver = FakeResolver(
        {
            ("exmple.com", "NS"): ["ns1.parking.test."],
            ("exmple.com", "A"): ["203.0.113.7"],
            ("exmple.com", "MX"): ["mail.parking.test."],
            ("example.net", "NS"): ["ns.example.net."],
        }
    )
    out = await LookalikeDomains(ctx).run(DOMAIN)
    assert [(e.type, e.value) for e in out] == [(EntityType.RECORD, "lookalike:example.com")]
    data = out[0].data
    assert [r["domain"] for r in data["registered"]] == ["example.net", "exmple.com"]
    typo = data["registered"][1]
    assert typo == {
        "domain": "exmple.com",
        "technique": "omisión",
        "ns": ["ns1.parking.test"],
        "a": ["203.0.113.7"],
        "mx": ["mail.parking.test"],
    }
    assert data["with_mx"] == 1
    assert data["checked"] == len(permutations("example.com"))


async def test_nothing_registered_is_empty(ctx):
    ctx.resolver = FakeResolver({})
    assert await LookalikeDomains(ctx).run(DOMAIN) == []


async def test_a_resolver_that_never_answers_is_an_error(ctx):
    class Down:
        async def resolve(self, name, rtype, lifetime=None):
            raise dns.exception.Timeout()

    ctx.resolver = Down()
    with pytest.raises(ModuleError, match="no respondió"):
        await LookalikeDomains(ctx).run(DOMAIN)


def test_only_the_investigated_domain_is_accepted(ctx):
    sub = Entity(type=EntityType.DOMAIN, value="a.example.com", data={"subdomain": True})
    assert not LookalikeDomains(ctx).accepts(sub)
    assert LookalikeDomains(ctx).accepts(DOMAIN)

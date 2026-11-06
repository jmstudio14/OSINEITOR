"""F4.7, F4.8, F4.9 y F4.16: ptr, ripestat, dnsbl y asn_netblock."""

from __future__ import annotations

import dns.exception
import dns.resolver
import httpx
import pytest
import respx

from osineitor.errors import ModuleError, ModuleQuota, ModuleSkipped
from osineitor.models import Entity, EntityType
from osineitor.modules.ip import asn_netblock
from osineitor.modules.ip.asn_netblock import AsnNetblock
from osineitor.modules.ip.dnsbl import Dnsbl
from osineitor.modules.ip.ptr import Ptr
from osineitor.modules.ip.ripestat import BASE, RipeStat
from tests.conftest import FakeResolver

IP = Entity(type=EntityType.IP, value="93.184.216.34")
CLOUDFLARE = Entity(type=EntityType.IP, value="1.1.1.1")
PRIVATE = Entity(type=EntityType.IP, value="192.168.0.10")


class Failing:
    """Resolvedor que falla igual con todo."""

    def __init__(self, exc: Exception):
        self.exc = exc

    async def resolve(self, name, rtype, lifetime=None):
        raise self.exc


class Mixed(FakeResolver):
    """Como FakeResolver, pero algunos nombres terminan en un fallo del resolvedor."""

    def __init__(self, records, broken):
        super().__init__(records)
        self.broken = broken

    async def resolve(self, name, rtype, lifetime=None):
        if any(name.endswith(zone) for zone in self.broken):
            raise dns.exception.Timeout()
        return await super().resolve(name, rtype, lifetime)


# --- ptr -------------------------------------------------------------------------------------


async def test_ptr(ctx):
    ctx.resolver = FakeResolver({("1.1.1.1.in-addr.arpa", "PTR"): ["one.one.one.one."]})
    out = await Ptr(ctx).run(CLOUDFLARE)
    assert [(e.type, e.value) for e in out] == [
        (EntityType.RECORD, "ptr:1.1.1.1"),
        (EntityType.DOMAIN, "one.one.one.one"),
    ]
    assert out[0].data["names"] == ["one.one.one.one"]
    # un PTR es un host: no debe lanzar RDAP o crt.sh como si fuera el dominio investigado
    assert out[1].data == {"subdomain": True, "ptr_of": "1.1.1.1"}


async def test_ptr_ipv6_uses_the_ip6_arpa_zone(ctx):
    name = ".".join(reversed("26064700470000000000000000001111")) + ".ip6.arpa"
    ctx.resolver = FakeResolver({(name, "PTR"): ["host.example.net."]})
    out = await Ptr(ctx).run(Entity(type=EntityType.IP, value="2606:4700:4700::1111"))
    assert out[1].value == "host.example.net"


async def test_ptr_without_a_reverse_name_is_empty(ctx):
    ctx.resolver = FakeResolver({})
    assert await Ptr(ctx).run(CLOUDFLARE) == []


async def test_ptr_ignores_garbage_names(ctx):
    ctx.resolver = FakeResolver({("1.1.1.1.in-addr.arpa", "PTR"): ["no es un host.", "-x-."]})
    assert await Ptr(ctx).run(CLOUDFLARE) == []


async def test_ptr_does_not_ask_for_private_addresses(ctx):
    ctx.resolver = Failing(AssertionError("no debe consultarse"))
    with pytest.raises(ModuleSkipped, match="no es pública"):
        await Ptr(ctx).run(PRIVATE)


async def test_ptr_dead_resolver_is_an_error(ctx):
    ctx.resolver = Failing(dns.exception.Timeout())
    with pytest.raises(ModuleError, match="no respondió"):
        await Ptr(ctx).run(CLOUDFLARE)


# --- dnsbl -----------------------------------------------------------------------------------

REVERSED = "34.216.184.93"


async def test_dnsbl(ctx):
    ctx.resolver = FakeResolver(
        {
            (f"{REVERSED}.zen.spamhaus.org", "A"): ["127.0.0.2", "127.0.0.10"],
            (f"{REVERSED}.dnsbl.dronebl.org", "A"): ["127.0.0.19"],
        }
    )
    (record,) = await Dnsbl(ctx).run(IP)
    assert record.value == "dnsbl:93.184.216.34"
    assert record.data["listed_on"] == ["dnsbl.dronebl.org", "zen.spamhaus.org"]
    assert {"list": "zen.spamhaus.org", "code": "127.0.0.2", "meaning": "SBL"} in record.data[
        "listed"
    ]
    assert {"list": "dnsbl.dronebl.org", "code": "127.0.0.19"} in record.data["listed"]


async def test_dnsbl_not_listed_is_empty(ctx):
    ctx.resolver = FakeResolver({})
    assert await Dnsbl(ctx).run(IP) == []


async def test_dnsbl_a_spamhaus_refusal_is_a_quota_error_not_a_listing(ctx):
    # 127.255.255.254: Spamhaus rechaza el resolvedor público; no dice nada de la IP
    ctx.resolver = FakeResolver({(f"{REVERSED}.zen.spamhaus.org", "A"): ["127.255.255.254"]})
    with pytest.raises(ModuleQuota, match="resolvedor propio"):
        await Dnsbl(ctx).run(IP)


async def test_dnsbl_a_list_that_does_not_answer_is_reported(ctx):
    ctx.resolver = Mixed(
        {(f"{REVERSED}.bl.spamcop.net", "A"): ["127.0.0.2"]}, broken=["dnsbl.dronebl.org"]
    )
    (record,) = await Dnsbl(ctx).run(IP)
    assert record.data["unanswered"] == ["dnsbl.dronebl.org"]
    assert record.data["listed_on"] == ["bl.spamcop.net"]


async def test_dnsbl_no_list_answering_is_an_error(ctx):
    ctx.resolver = Failing(dns.exception.Timeout())
    with pytest.raises(ModuleError, match="ninguna lista"):
        await Dnsbl(ctx).run(IP)


async def test_dnsbl_skips_ipv6_and_private_addresses(ctx):
    ctx.resolver = Failing(AssertionError("no debe consultarse"))
    with pytest.raises(ModuleSkipped, match="IPv4"):
        await Dnsbl(ctx).run(Entity(type=EntityType.IP, value="2001:db8::1"))
    with pytest.raises(ModuleSkipped, match="no es pública"):
        await Dnsbl(ctx).run(PRIVATE)


# --- ripestat --------------------------------------------------------------------------------

OVERVIEW = {
    "data": {
        "resource": "1.1.1.0/24",
        "announced": True,
        "asns": [{"asn": 13335, "holder": "CLOUDFLARENET - Cloudflare, Inc."}],
        "block": {"resource": "1.0.0.0/8", "desc": "APNIC (Status: ALLOCATED)"},
    }
}
GEO = {"data": {"located_resources": [{"resource": "1.1.1.0/24", "location": "AU"}]}}
HISTORY = {
    "data": {
        "by_origin": [
            {
                "origin": "13335",
                "prefixes": [
                    {
                        "prefix": "1.1.1.0/24",
                        "timelines": [
                            {"starttime": "2018-04-01T00:00:00", "endtime": "2019-01-01T00:00:00"},
                            {"starttime": "2020-01-01T00:00:00", "endtime": "2026-10-30T00:00:00"},
                        ],
                    },
                    {"prefix": "1.0.0.0/8", "timelines": []},
                ],
            },
            {
                "origin": "64500",
                "prefixes": [
                    {
                        "prefix": "1.1.1.0/24",
                        "timelines": [
                            {"starttime": "2010-07-01T00:00:00", "endtime": "2010-07-02T00:00:00"}
                        ],
                    }
                ],
            },
        ]
    }
}


def mock_ripe(overview=OVERVIEW, geo=GEO, history=HISTORY):
    return {
        "overview": respx.get(f"{BASE}/prefix-overview/data.json").mock(
            return_value=httpx.Response(200, json=overview)
        ),
        "geo": respx.get(f"{BASE}/rir-geo/data.json").mock(
            return_value=httpx.Response(200, json=geo)
        ),
        "history": respx.get(f"{BASE}/routing-history/data.json").mock(
            return_value=httpx.Response(200, json=history)
        ),
    }


@respx.mock
async def test_ripestat(ctx):
    routes = mock_ripe()
    out = await RipeStat(ctx).run(CLOUDFLARE)
    by_type = {e.type: e for e in out}
    record = by_type[EntityType.RECORD]
    assert record.value == "ripestat:1.1.1.1"
    assert record.data["prefix"] == "1.1.1.0/24"
    assert record.data["asns"] == ["AS13335"]
    assert record.data["country"] == "AU"
    assert record.data["announced"] is True
    assert record.data["first_seen"] == "2010-07-01T00:00:00"
    assert record.data["last_seen"] == "2026-10-30T00:00:00"
    assert record.data["origins_seen"] == ["AS13335", "AS64500"]
    assert by_type[EntityType.NETBLOCK].value == "1.1.1.0/24"
    assert by_type[EntityType.ASN].value == "AS13335"
    assert by_type[EntityType.ASN].data["holder"] == "CLOUDFLARENET - Cloudflare, Inc."
    # el uso de la API de RIPEstat se identifica, como piden sus condiciones
    assert routes["overview"].calls[0].request.url.params["sourceapp"] == "osineitor"
    assert routes["history"].calls[0].request.url.params["resource"] == "1.1.1.0/24"


@respx.mock
async def test_ripestat_unrouted_ip_has_no_asn_and_no_history(ctx):
    overview = {"data": {"resource": "198.51.100.0/24", "announced": False, "asns": []}}
    routes = mock_ripe(overview=overview)
    out = await RipeStat(ctx).run(Entity(type=EntityType.IP, value="93.184.216.34"))
    assert {e.type for e in out} == {EntityType.RECORD, EntityType.NETBLOCK}
    assert not routes["history"].called


@respx.mock
async def test_ripestat_no_prefix_is_empty(ctx):
    mock_ripe(overview={"data": {}})
    assert await RipeStat(ctx).run(CLOUDFLARE) == []


@respx.mock
async def test_ripestat_rate_limit_is_a_quota_error(ctx):
    respx.get(f"{BASE}/prefix-overview/data.json").mock(return_value=httpx.Response(429))
    with pytest.raises(ModuleQuota):
        await RipeStat(ctx).run(CLOUDFLARE)


async def test_ripestat_skips_private_addresses(ctx):
    with pytest.raises(ModuleSkipped):
        await RipeStat(ctx).run(PRIVATE)


# --- asn_netblock ----------------------------------------------------------------------------

CYMRU = {
    ("1.1.1.1.origin.asn.cymru.com", "TXT"): ["13335 | 1.1.1.0/24 | AU | apnic | 2011-08-11"],
    ("AS13335.asn.cymru.com", "TXT"): [
        "13335 | US | arin | 2010-07-14 | CLOUDFLARENET - Cloudflare, Inc., US"
    ],
}


async def test_asn_netblock_from_an_ip(ctx):
    ctx.resolver = FakeResolver(CYMRU)
    out = await AsnNetblock(ctx).run(CLOUDFLARE)
    block, asn = out
    assert (block.type, block.value) == (EntityType.NETBLOCK, "1.1.1.0/24")
    assert block.data["country"] == "AU"
    assert block.data["registry"] == "apnic"
    assert (asn.type, asn.value) == (EntityType.ASN, "AS13335")
    assert asn.data["holder"] == "CLOUDFLARENET - Cloudflare, Inc., US"


async def test_asn_netblock_ip_without_origin_is_empty(ctx):
    ctx.resolver = FakeResolver({})
    assert await AsnNetblock(ctx).run(CLOUDFLARE) == []


async def test_asn_netblock_multi_origin_prefix_yields_every_asn(ctx):
    ctx.resolver = FakeResolver(
        {
            ("1.1.1.1.origin.asn.cymru.com", "TXT"): [
                "64500 64501 | 1.1.1.0/24 | AU | apnic | 2011-08-11"
            ]
        }
    )
    out = await AsnNetblock(ctx).run(CLOUDFLARE)
    assert [e.value for e in out] == ["1.1.1.0/24", "AS64500", "AS64501"]
    assert out[0].data["asns"] == ["AS64500", "AS64501"]


def test_asn_netblock_ipv6_origin_name_uses_nibbles():
    name = asn_netblock._origin_name("2001:db8::1")
    assert name == ".".join(reversed("20010db8000000000000000000000001")) + ".origin6.asn.cymru.com"


async def test_asn_netblock_skips_private_addresses(ctx):
    with pytest.raises(ModuleSkipped):
        await AsnNetblock(ctx).run(PRIVATE)


async def test_asn_netblock_dead_resolver_is_an_error(ctx):
    ctx.resolver = Failing(dns.exception.Timeout())
    with pytest.raises(ModuleError, match="Team Cymru"):
        await AsnNetblock(ctx).run(CLOUDFLARE)


ANNOUNCED = "https://stat.ripe.net/data/announced-prefixes/data.json"


@respx.mock
async def test_asn_netblock_from_an_asn_is_capped_and_widest_first(ctx, monkeypatch):
    monkeypatch.setattr(asn_netblock, "MAX_PREFIXES", 3)
    prefixes = [
        {"prefix": "104.22.119.0/24"},
        {"prefix": "104.16.0.0/13"},
        {"prefix": "2606:4700::/32"},
        {"prefix": "1.1.1.0/24"},
        {"prefix": "104.24.0.0/14"},
        {"prefix": "no es una red"},
    ]
    route = respx.get(ANNOUNCED).mock(
        return_value=httpx.Response(200, json={"data": {"prefixes": prefixes}})
    )
    ctx.resolver = FakeResolver(CYMRU)
    seed = Entity(type=EntityType.ASN, value="AS13335")
    out = await AsnNetblock(ctx).run(seed)
    blocks = [e.value for e in out if e.type == EntityType.NETBLOCK]
    assert blocks == ["104.16.0.0/13", "104.24.0.0/14", "1.1.1.0/24"]
    assert route.calls[0].request.url.params["resource"] == "AS13335"
    asn = next(e for e in out if e.type == EntityType.ASN)
    assert asn.value == "AS13335"  # misma clave que la semilla: se fusiona en ella
    assert asn.data["announced_prefixes"] == 5
    assert asn.data["holder"] == "CLOUDFLARENET - Cloudflare, Inc., US"


@respx.mock
async def test_asn_netblock_from_an_asn_rate_limit_is_a_quota_error(ctx):
    respx.get(ANNOUNCED).mock(return_value=httpx.Response(429))
    ctx.resolver = FakeResolver(CYMRU)
    with pytest.raises(ModuleQuota):
        await AsnNetblock(ctx).run(Entity(type=EntityType.ASN, value="AS13335"))

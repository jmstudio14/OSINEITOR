"""Fase 6, fuentes con red (mempool.space y GLEIF), sin red real."""

from __future__ import annotations

import httpx
import pytest
import respx

from osineitor.models import Entity, EntityType
from osineitor.modules.base import ModuleQuota
from osineitor.modules.crypto.btc_explorer import BtcExplorer
from osineitor.modules.org.gleif import Gleif

ADDRESS = "bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq"
INFO_URL = f"https://mempool.space/api/address/{ADDRESS}"


def crypto(value: str) -> Entity:
    return Entity(type=EntityType.CRYPTO_ADDRESS, value=value)


def info(count: int) -> dict:
    return {
        "chain_stats": {
            "funded_txo_sum": 150_000,
            "spent_txo_sum": 100_000,
            "tx_count": count,
        },
        "mempool_stats": {"tx_count": 1},
    }


def txs(*times: int) -> list[dict]:
    return [{"status": {"block_time": t}} for t in times] + [{"status": {}}]


# --- btc_explorer ----------------------------------------------------------------------------


def test_btc_explorer_only_takes_bitcoin_addresses(ctx):
    module = BtcExplorer(ctx)
    assert module.accepts(crypto(ADDRESS))
    assert not module.accepts(crypto("0x52908400098527886E0F7030069857D2E4169EE7"))
    assert not module.accepts(crypto("a" * 30))


@respx.mock
async def test_btc_explorer_balance_and_first_and_last_activity(ctx):
    respx.get(INFO_URL).mock(return_value=httpx.Response(200, json=info(3)))
    respx.get(f"{INFO_URL}/txs").mock(
        return_value=httpx.Response(200, json=txs(1_700_000_000, 1_600_000_000, 1_650_000_000))
    )
    [record] = await BtcExplorer(ctx).run(crypto(ADDRESS))
    data = record.data
    assert record.value == f"btc:{ADDRESS}"
    assert (data["balance_sat"], data["transactions"]) == (50_000, 3)
    assert data["unconfirmed_transactions"] == 1
    assert data["last_activity"] == "2023-11-14T22:13:20Z"
    assert data["first_activity"] == "2020-09-13T12:26:40Z"


@respx.mock
async def test_btc_explorer_does_not_guess_the_first_activity_of_a_busy_address(ctx):
    respx.get(INFO_URL).mock(return_value=httpx.Response(200, json=info(5000)))
    respx.get(f"{INFO_URL}/txs").mock(return_value=httpx.Response(200, json=txs(1_700_000_000)))
    [record] = await BtcExplorer(ctx).run(crypto(ADDRESS))
    assert record.data["first_activity"] is None
    assert record.data["last_activity"] == "2023-11-14T22:13:20Z"


@respx.mock
async def test_btc_explorer_unused_address_makes_one_request(ctx):
    route = respx.get(INFO_URL).mock(return_value=httpx.Response(200, json=info(0)))
    [record] = await BtcExplorer(ctx).run(crypto(ADDRESS))
    assert route.call_count == 1
    assert record.data["last_activity"] is None


@respx.mock
async def test_btc_explorer_rate_limit_is_a_quota(ctx):
    respx.get(INFO_URL).mock(return_value=httpx.Response(429))
    with pytest.raises(ModuleQuota):
        await BtcExplorer(ctx).run(crypto(ADDRESS))


# --- gleif -----------------------------------------------------------------------------------

LEI = "5493006MHB84DD0ZWV18"
BASE = "https://api.gleif.org/api/v1/lei-records"


def record(lei: str, name: str, **relationships: bool) -> dict:
    links = {"related": f"{BASE}/{lei}/x"}
    return {
        "type": "lei-records",
        "id": lei,
        "attributes": {
            "lei": lei,
            "entity": {
                "legalName": {"name": name},
                "legalAddress": {"country": "ES", "city": "MADRID"},
                "jurisdiction": "ES",
                "status": "ACTIVE",
            },
            "registration": {"status": "ISSUED", "lastUpdateDate": "2026-01-01T00:00:00Z"},
        },
        "relationships": {rel: {"links": links} for rel, on in relationships.items() if on},
    }


def org(name: str, **data) -> Entity:
    return Entity(type=EntityType.ORGANIZATION, value=name, data=data)


def test_gleif_ignores_github_organizations(ctx):
    module = Gleif(ctx)
    assert module.accepts(org("ACME S.A."))
    assert not module.accepts(org("acme-oss", platform="github"))


@respx.mock
async def test_gleif_exact_match_follows_parent_and_children(ctx):
    respx.get(BASE, params={"filter[entity.legalName]": "ACME S.A.", "page[size]": "5"}).mock(
        return_value=httpx.Response(
            200, json={"data": [record(LEI, "ACME S.A.", **{"direct-parent": True})]}
        )
    )
    respx.get(f"{BASE}/{LEI}/direct-parent").mock(
        return_value=httpx.Response(200, json={"data": record("P" * 20, "ACME HOLDING S.L.")})
    )
    out = await Gleif(ctx).run(org("ACME S.A."))
    assert [(e.type, e.value) for e in out] == [
        (EntityType.RECORD, f"gleif:{LEI}"),
        (EntityType.ORGANIZATION, "ACME HOLDING S.L."),
    ]
    assert out[0].data["match"] == "exact"
    assert (out[0].data["country"], out[0].data["registration_status"]) == ("ES", "ISSUED")
    assert out[1].data == {"relationship": "parent", "lei": "P" * 20}


@respx.mock
async def test_gleif_children_become_subsidiaries(ctx):
    respx.get(BASE, params={"filter[entity.legalName]": "ACME S.A.", "page[size]": "5"}).mock(
        return_value=httpx.Response(
            200, json={"data": [record(LEI, "ACME S.A.", **{"direct-children": True})]}
        )
    )
    respx.get(f"{BASE}/{LEI}/direct-children").mock(
        return_value=httpx.Response(
            200, json={"data": [record("C" * 20, "ACME IBERIA S.L."), {"id": "sin atributos"}]}
        )
    )
    out = await Gleif(ctx).run(org("ACME S.A."))
    subsidiaries = [e for e in out if e.type == EntityType.ORGANIZATION]
    assert [(e.value, e.data["relationship"]) for e in subsidiaries] == [
        ("ACME IBERIA S.L.", "subsidiary")
    ]


@respx.mock
async def test_gleif_approximate_matches_are_labelled_and_not_followed(ctx):
    respx.get(BASE, params={"filter[entity.legalName]": "Acme", "page[size]": "5"}).mock(
        return_value=httpx.Response(200, json={"data": []})
    )
    respx.get(BASE, params={"filter[fulltext]": "Acme", "page[size]": "3"}).mock(
        return_value=httpx.Response(
            200, json={"data": [record(LEI, "ACME OTHER S.A.", **{"direct-parent": True})]}
        )
    )
    out = await Gleif(ctx).run(org("Acme"))
    assert [(e.type, e.data["match"]) for e in out] == [(EntityType.RECORD, "approximate")]


@respx.mock
async def test_gleif_no_match_is_empty(ctx):
    respx.get(BASE).mock(return_value=httpx.Response(200, json={"data": []}))
    assert await Gleif(ctx).run(org("Nadie S.A.")) == []

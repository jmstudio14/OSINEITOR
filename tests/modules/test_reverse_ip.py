"""Módulo reverse_ip (F4.22): hostnames en la misma IP según HackerTarget, sin red."""

from __future__ import annotations

import httpx
import pytest
import respx

from osineitor.models import Entity, EntityType
from osineitor.modules.base import ModuleError, ModuleQuota, ModuleSkipped
from osineitor.modules.ip.reverse_ip import MAX_PIVOT, ReverseIp

API = "https://api.hackertarget.com/reverseiplookup/"
IP = Entity(type=EntityType.IP, value="93.184.216.34")


@respx.mock
async def test_reverse_ip_emits_the_hostnames_that_share_the_ip(ctx):
    route = respx.get(API).mock(
        return_value=httpx.Response(200, text="www.example.org\nAPI.example.org\nno valido\n\n")
    )
    out = await ReverseIp(ctx).run(IP)
    assert route.calls[0].request.url.params["q"] == "93.184.216.34"
    assert [(e.type, e.value) for e in out] == [
        (EntityType.DOMAIN, "www.example.org"),
        (EntityType.DOMAIN, "api.example.org"),
    ]
    assert out[0].data["via"] == "reverse_ip"


@respx.mock
async def test_a_busy_shared_ip_gives_one_summary_instead_of_domains_to_pivot_on(ctx):
    hosts = [f"host{i}.example.net" for i in range(MAX_PIVOT + 1)]
    respx.get(API).mock(return_value=httpx.Response(200, text="\n".join(hosts)))
    [summary] = await ReverseIp(ctx).run(IP)
    assert (summary.type, summary.value) == (EntityType.RECORD, "reverse_ip:93.184.216.34")
    assert summary.data["hostnames"] == MAX_PIVOT + 1
    assert summary.data["sample"] == hosts[:20]


@respx.mock
@pytest.mark.parametrize("text", ["No DNS A records found", "no records found"])
async def test_reverse_ip_without_records_gives_nothing(ctx, text):
    respx.get(API).mock(return_value=httpx.Response(200, text=text))
    assert await ReverseIp(ctx).run(IP) == []


@respx.mock
async def test_reverse_ip_quota_and_error_messages(ctx):
    respx.get(API).mock(
        return_value=httpx.Response(200, text="API count exceeded - Increase Quota with Membership")
    )
    with pytest.raises(ModuleQuota):
        await ReverseIp(ctx).run(IP)
    respx.get(API).mock(return_value=httpx.Response(200, text="error check your search parameter"))
    with pytest.raises(ModuleError, match="error check"):
        await ReverseIp(ctx).run(IP)
    respx.get(API).mock(return_value=httpx.Response(429))
    with pytest.raises(ModuleQuota):
        await ReverseIp(ctx).run(IP)


async def test_a_private_ip_is_never_sent_to_a_third_party(ctx):
    with pytest.raises(ModuleSkipped):
        await ReverseIp(ctx).run(Entity(type=EntityType.IP, value="10.0.0.1"))

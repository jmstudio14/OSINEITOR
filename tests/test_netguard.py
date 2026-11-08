from __future__ import annotations

import gzip

import httpx
import pytest
import respx

from osineitor import http as http_module
from osineitor import netguard
from osineitor.budget import Budget
from osineitor.config import Config
from osineitor.errors import BudgetExceeded, NetworkGuardError
from osineitor.http import MAX_REDIRECTS, HttpClient, ResponseTooLarge
from osineitor.netguard import resolve_host as real_resolve_host


@pytest.mark.parametrize(
    ("address", "public"),
    [
        ("8.8.8.8", True),
        ("93.184.216.34", True),
        ("2606:4700:4700::1111", True),
        ("10.0.0.1", False),
        ("172.16.5.5", False),
        ("192.168.1.5", False),
        ("127.0.0.1", False),
        ("0.0.0.0", False),
        ("169.254.169.254", False),
        ("100.64.0.1", False),
        ("224.0.0.1", False),
        ("::1", False),
        ("fd00:ec2::254", False),
        ("::ffff:127.0.0.1", False),
        ("::ffff:10.0.0.1", False),
        ("fe80::1%eth0", False),
        ("::127.0.0.1", False),  # IPv4-compatible
        ("::ffff:0:7f00:1", False),  # SIIT
        ("64:ff9b::a9fe:a9fe", False),  # NAT64 hacia 169.254.169.254
        ("64:ff9b::7f00:1", False),
        ("64:ff9b::808:808", True),  # NAT64 hacia 8.8.8.8
        ("fec0::1", False),  # site-local
        ("no-es-una-ip", False),
    ],
)
def test_is_public(address, public):
    assert netguard.is_public(address) is public


def resolver(mapping: dict[str, list[str]]):
    async def resolve(host: str) -> list[str]:
        return mapping.get(host, [])

    return resolve


async def test_ensure_public_checks_literals_and_names(monkeypatch):
    monkeypatch.setattr(
        netguard,
        "resolve_host",
        resolver(
            {
                "ok.test": ["93.184.216.34"],
                "internal.test": ["10.1.2.3"],
                "mixed.test": ["93.184.216.34", "127.0.0.1"],
            }
        ),
    )
    await netguard.ensure_public("https://8.8.8.8/x")
    await netguard.ensure_public("https://ok.test/x")
    await netguard.ensure_public("https://sin-resolver.test/x", resolve=False)  # con proxy
    for url in ("http://127.0.0.1/", "http://[::1]/", "http://169.254.169.254/latest/meta-data"):
        with pytest.raises(NetworkGuardError):
            await netguard.ensure_public(url)
    for url in ("https://internal.test/", "https://mixed.test/"):
        with pytest.raises(NetworkGuardError, match="--allow-private"):
            await netguard.ensure_public(url)


@respx.mock
async def test_unresolvable_host_is_blocked_and_not_remembered(monkeypatch):
    """Fail-closed: si la guardia no ve IP, httpx no debe resolver por su cuenta y conectar."""
    mapping: dict[str, list[str]] = {}
    monkeypatch.setattr(netguard, "resolve_host", resolver(mapping))
    route = respx.get("https://rebind.test/").mock(return_value=httpx.Response(200))
    async with client() as http:
        with pytest.raises(httpx.ConnectError, match="no resuelve"):
            await http.get("https://rebind.test/")
        assert not route.called
        mapping["rebind.test"] = ["10.0.0.7"]  # luego resuelve a la red interna
        with pytest.raises(NetworkGuardError):
            await http.get("https://rebind.test/")
    assert not route.called


async def test_guard_message_does_not_leak_the_query(monkeypatch):
    monkeypatch.setattr(netguard, "resolve_host", resolver({"internal.test": ["10.0.0.9"]}))
    with pytest.raises(NetworkGuardError) as info:
        await netguard.ensure_public("https://internal.test/x?key=SECRETO")
    assert "SECRETO" not in str(info.value)


def client(**kwargs) -> HttpClient:
    return HttpClient(Config(), backoff=0, **kwargs)


@respx.mock
async def test_client_blocks_private_hosts(monkeypatch):
    monkeypatch.setattr(netguard, "resolve_host", resolver({"internal.test": ["192.168.0.10"]}))
    route = respx.get("https://internal.test/").mock(return_value=httpx.Response(200))
    async with client() as http:
        with pytest.raises(NetworkGuardError):
            await http.get("https://internal.test/")
    assert not route.called


@respx.mock
async def test_allow_private_disables_the_guard(monkeypatch):
    monkeypatch.setattr(netguard, "resolve_host", resolver({"internal.test": ["192.168.0.10"]}))
    respx.get("https://internal.test/").mock(return_value=httpx.Response(200, text="ok"))
    async with client(allow_private=True) as http:
        assert (await http.get("https://internal.test/")).text == "ok"


@respx.mock
async def test_redirect_to_private_host_is_blocked(monkeypatch):
    monkeypatch.setattr(
        netguard,
        "resolve_host",
        resolver({"public.test": ["93.184.216.34"], "internal.test": ["10.0.0.5"]}),
    )
    respx.get("https://public.test/start").mock(
        return_value=httpx.Response(302, headers={"location": "http://internal.test/admin"})
    )
    target = respx.get("http://internal.test/admin").mock(return_value=httpx.Response(200))
    async with client() as http:
        with pytest.raises(NetworkGuardError):
            await http.get("https://public.test/start")
    assert not target.called


@respx.mock
async def test_redirects_are_followed_with_relative_locations():
    respx.get("https://a.test/start").mock(
        return_value=httpx.Response(301, headers={"location": "/final"})
    )
    respx.get("https://a.test/final").mock(return_value=httpx.Response(200, text="fin"))
    async with client() as http:
        response = await http.get("https://a.test/start")
    assert response.text == "fin"
    assert str(response.url) == "https://a.test/final"


@respx.mock
async def test_follow_redirects_false_returns_the_redirect():
    respx.get("https://a.test/start").mock(
        return_value=httpx.Response(302, headers={"location": "/final"})
    )
    async with client() as http:
        response = await http.get("https://a.test/start", follow_redirects=False)
    assert response.status_code == 302


@respx.mock
async def test_cross_origin_redirect_drops_request_headers_and_params():
    respx.get("https://a.test/start").mock(
        return_value=httpx.Response(302, headers={"location": "https://b.test/final?x=1"})
    )
    final = respx.get("https://b.test/final").mock(return_value=httpx.Response(200))
    async with client() as http:
        await http.get("https://a.test/start", headers={"Key": "secreto"}, params={"key": "s"})
    sent = final.calls[0].request
    assert "key" not in sent.headers
    assert sent.url.query == b"x=1"


@respx.mock
async def test_same_origin_redirect_keeps_request_headers():
    respx.get("https://a.test/start").mock(
        return_value=httpx.Response(302, headers={"location": "/final"})
    )
    final = respx.get("https://a.test/final").mock(return_value=httpx.Response(200))
    async with client() as http:
        await http.get("https://a.test/start", headers={"X-Token": "t"})
    assert final.calls[0].request.headers["x-token"] == "t"


@respx.mock
async def test_post_redirected_with_302_becomes_get_without_body():
    respx.post("https://a.test/form").mock(
        return_value=httpx.Response(302, headers={"location": "/done"})
    )
    done = respx.route(url="https://a.test/done").mock(return_value=httpx.Response(200))
    async with client() as http:
        await http.post("https://a.test/form", json={"a": 1})
    request = done.calls[0].request
    assert request.method == "GET"
    assert request.content == b""


@respx.mock
async def test_too_many_redirects():
    respx.get("https://a.test/loop").mock(
        return_value=httpx.Response(302, headers={"location": "/loop"})
    )
    async with client() as http:
        with pytest.raises(httpx.TooManyRedirects):
            await http.get("https://a.test/loop")
    assert respx.calls.call_count == MAX_REDIRECTS + 1


@respx.mock
async def test_each_host_is_resolved_once_within_the_ttl(monkeypatch):
    calls = []

    async def resolve(host: str) -> list[str]:
        calls.append(host)
        return ["93.184.216.34"]

    monkeypatch.setattr(netguard, "resolve_host", resolve)
    respx.get("https://a.test/x").mock(return_value=httpx.Response(200))
    async with client() as http:
        await http.get("https://a.test/x")
        await http.get("https://a.test/x")
    assert calls == ["a.test"]


@respx.mock
async def test_body_over_the_limit_is_cut_without_retries(monkeypatch):
    monkeypatch.setattr(http_module, "MAX_RESPONSE", 100)
    route = respx.get("https://a.test/big").mock(
        return_value=httpx.Response(200, content=b"x" * 1000)
    )
    async with client() as http:
        with pytest.raises(ResponseTooLarge, match="supera"):
            await http.get("https://a.test/big")
    assert route.call_count == 1


@respx.mock
async def test_limit_counts_decompressed_bytes(monkeypatch):
    """Una bomba gzip: pocos bytes en la red que se expanden al descomprimir."""
    monkeypatch.setattr(http_module, "MAX_RESPONSE", 1000)
    bomb = gzip.compress(b"\0" * 100_000)
    assert len(bomb) < 1000
    respx.get("https://a.test/bomb").mock(
        return_value=httpx.Response(200, content=bomb, headers={"content-encoding": "gzip"})
    )
    async with client() as http:
        with pytest.raises(ResponseTooLarge):
            await http.get("https://a.test/bomb")


@respx.mock
async def test_body_under_the_limit_is_decoded(monkeypatch):
    monkeypatch.setattr(http_module, "MAX_RESPONSE", 1000)
    respx.get("https://a.test/ok").mock(
        return_value=httpx.Response(
            200, content=gzip.compress(b"hola"), headers={"content-encoding": "gzip"}
        )
    )
    async with client() as http:
        response = await http.get("https://a.test/ok")
    assert response.text == "hola"


@respx.mock
async def test_request_budget_counts_retries_and_blocks():
    respx.get("https://a.test/x").mock(return_value=httpx.Response(200))
    budget = Budget(max_requests=2)
    async with client(budget=budget) as http:
        await http.get("https://a.test/x")
        await http.get("https://a.test/x")
        with pytest.raises(BudgetExceeded):
            await http.get("https://a.test/x")
    assert budget.requests == 2
    assert budget.blocked_reason


async def test_real_resolver_resolves_localhost_and_swallows_failures():
    addresses = await real_resolve_host("localhost")
    assert addresses
    assert all(not netguard.is_public(a) for a in addresses)
    assert await real_resolve_host("nombre-que-no-existe.invalid") == []

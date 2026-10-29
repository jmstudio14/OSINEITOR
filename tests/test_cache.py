from __future__ import annotations

import sqlite3
import time

import httpx
import respx

from osineitor.cache import ResponseCache, cache_key
from osineitor.config import Config
from osineitor.http import HttpClient, RunStats, current_stats

URL = "https://api.example.test/data"


def response(status=200, body=b'{"a": 1}'):
    return httpx.Response(
        status,
        content=body,
        headers={"content-type": "application/json"},
        request=httpx.Request("GET", URL),
    )


def test_cache_roundtrip_and_expiry(tmp_path):
    with ResponseCache(tmp_path / "c.db") as cache:
        key = cache_key(URL, {"q": "1"})
        assert cache.get(key, URL) is None
        cache.put(key, response(), ttl=60)
        hit = cache.get(key, URL)
        assert hit.json() == {"a": 1}
        assert hit.headers["content-type"] == "application/json"
        cache.put(key, response(), ttl=-1)  # ya caducada
        assert cache.get(key, URL) is None


def test_cache_only_stores_successful_responses(tmp_path):
    with ResponseCache(tmp_path / "c.db") as cache:
        cache.put("k1", response(404), ttl=60)
        cache.put("k2", response(500), ttl=60)
        assert cache.info() == (0, 0)


def test_cache_key_depends_on_params_and_never_stores_the_url(tmp_path):
    assert cache_key(URL, {"q": "1"}) != cache_key(URL, {"q": "2"})
    assert cache_key(URL, {"q": "1"}) == cache_key(URL + "?q=1")
    secret = "SUPERSECRETKEY"
    with ResponseCache(tmp_path / "c.db") as cache:
        cache.put(cache_key(URL, {"token": secret}), response(), ttl=60)
    raw = sqlite3.connect(tmp_path / "c.db").execute("SELECT * FROM responses").fetchall()
    assert secret not in repr(raw)


def test_cache_clear_and_info(tmp_path):
    with ResponseCache(tmp_path / "c.db") as cache:
        cache.put("a", response(), ttl=60)
        cache.put("b", response(), ttl=60)
        assert cache.info()[0] == 2
        assert cache.clear() == 2
        assert cache.info() == (0, 0)


@respx.mock
async def test_client_serves_second_get_from_cache(tmp_path):
    route = respx.get(URL).mock(return_value=httpx.Response(200, json={"a": 1}))
    cache = ResponseCache(tmp_path / "c.db")
    async with HttpClient(Config(), cache=cache) as http:
        stats = RunStats()
        current_stats.set(stats)
        first = await http.get(URL, cache_ttl=60)
        second = await http.get(URL, cache_ttl=60)
    assert first.json() == second.json() == {"a": 1}
    assert route.call_count == 1
    assert (stats.requests, stats.cache_hits) == (1, 1)


@respx.mock
async def test_client_refresh_requeries_and_updates(tmp_path):
    route = respx.get(URL).mock(
        side_effect=[httpx.Response(200, json=1), httpx.Response(200, json=2)]
    )
    cache = ResponseCache(tmp_path / "c.db")
    async with HttpClient(Config(), cache=cache) as http:
        await http.get(URL, cache_ttl=60)
        http._refresh = True
        assert (await http.get(URL, cache_ttl=60)).json() == 2
        http._refresh = False
        assert (await http.get(URL, cache_ttl=60)).json() == 2  # lo nuevo quedó guardado
    assert route.call_count == 2


@respx.mock
async def test_client_does_not_cache_without_ttl_post_or_errors(tmp_path):
    get = respx.get(URL).mock(return_value=httpx.Response(200, json={}))
    post = respx.post(URL).mock(return_value=httpx.Response(200, json={}))
    cache = ResponseCache(tmp_path / "c.db")
    async with HttpClient(Config(), cache=cache) as http:
        await http.get(URL)  # sin ttl
        await http.get(URL)
        await http.post(URL, cache_ttl=60)
        await http.post(URL, cache_ttl=60)
    assert (get.call_count, post.call_count) == (2, 2)


@respx.mock
async def test_client_without_cache_ignores_ttl():
    route = respx.get(URL).mock(return_value=httpx.Response(200, json={}))
    async with HttpClient(Config()) as http:
        await http.get(URL, cache_ttl=60)
        await http.get(URL, cache_ttl=60)
    assert route.call_count == 2


@respx.mock
async def test_source_throttle_spaces_requests():
    respx.get(URL).mock(return_value=httpx.Response(200, json={}))
    async with HttpClient(Config()) as http:
        source = http.bind("slow", min_interval=0.2)
        start = time.monotonic()
        await source.get(URL)
        await source.get(URL)
        await source.get(URL)
        assert time.monotonic() - start >= 0.4 - 0.05
        # Una fuente sin intervalo no pasa por el límite de las demás.
        await http.bind("other").get(URL)
        assert set(http._last_call) == {"slow"}

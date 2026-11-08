from __future__ import annotations

import base64

import httpx
import pytest
import respx

from osineitor.models import Entity, EntityType
from osineitor.modules.base import ModuleError
from osineitor.modules.domain.favicon_pivot import FaviconPivot, favicon_hash, murmur3_32

DOMAIN = Entity(type=EntityType.DOMAIN, value="example.com")
SEARCH = "https://api.shodan.io/shodan/host/search"


@pytest.fixture(autouse=True)
def key(config):
    config.keys["shodan"] = "S"


@pytest.mark.parametrize(
    ("data", "seed", "expected"),
    [  # vectores de referencia de MurmurHash3_x86_32 (valor sin signo)
        (b"", 0, 0x00000000),
        (b"", 1, 0x514E28B7),
        (b"test", 0, 0xBA6BD213),
        (b"Hello, world!", 0, 0xC0363E43),
        (b"The quick brown fox jumps over the lazy dog", 0, 0x2E4FF723),
    ],
)
def test_murmur3_matches_the_reference_vectors(data, seed, expected):
    assert murmur3_32(data, seed) & 0xFFFFFFFF == expected


def test_the_hash_is_signed_and_uses_line_wrapped_base64():
    assert murmur3_32(b"test") == 0xBA6BD213 - (1 << 32)
    content = bytes(range(200))
    assert favicon_hash(content) == murmur3_32(base64.encodebytes(content))
    assert b"\n" in base64.encodebytes(content)[:-1]  # Shodan hashea con los saltos de línea


@respx.mock
async def test_pivots_to_other_hosts_with_the_same_icon(ctx):
    icon = b"\x00\x00\x01\x00icon-bytes"
    respx.get("https://example.com/favicon.ico").mock(
        return_value=httpx.Response(200, content=icon, headers={"content-type": "image/x-icon"})
    )
    route = respx.get(SEARCH).mock(
        return_value=httpx.Response(
            200,
            json={
                "matches": [
                    {"ip_str": "203.0.113.5", "port": 443, "hostnames": ["a.test"]},
                    {"ip_str": "203.0.113.5", "port": 80},
                    {"ip_str": "198.51.100.9", "port": 8080},
                ]
            },
        )
    )
    out = await FaviconPivot(ctx).run(DOMAIN)
    digest = favicon_hash(icon)
    params = route.calls[0].request.url.params
    assert params["query"] == f"http.favicon.hash:{digest}"
    assert params["key"] == "S"
    assert [(e.type, e.value) for e in out] == [
        (EntityType.RECORD, "favicon:example.com"),
        (EntityType.IP, "203.0.113.5"),
        (EntityType.IP, "198.51.100.9"),
    ]
    assert out[0].data["matches"] == 2
    assert out[1].data["ports"] == [443, 80]


@respx.mock
async def test_a_site_without_favicon_is_empty_and_does_not_search(ctx):
    respx.get("https://example.com/favicon.ico").mock(
        return_value=httpx.Response(
            200, text="<html>home</html>", headers={"content-type": "text/html"}
        )
    )
    route = respx.get(SEARCH)
    assert await FaviconPivot(ctx).run(DOMAIN) == []
    assert not route.called


@respx.mock
async def test_a_key_without_search_access_is_an_error(ctx):
    respx.get("https://example.com/favicon.ico").mock(
        return_value=httpx.Response(200, content=b"i")
    )
    respx.get(SEARCH).mock(return_value=httpx.Response(403))
    with pytest.raises(ModuleError, match="búsqueda"):
        await FaviconPivot(ctx).run(DOMAIN)


def test_the_module_is_active_and_needs_the_shodan_key():
    assert FaviconPivot.passive is False
    assert FaviconPivot.requires_key == "shodan"

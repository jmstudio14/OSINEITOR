"""Módulo analytics_ids (F4.21): IDs de analítica y publicidad de la página, sin red."""

from __future__ import annotations

import httpx
import pytest
import respx

from osineitor.models import Entity, EntityType
from osineitor.modules.base import ModuleError
from osineitor.modules.domain.analytics_ids import AnalyticsIds

DOMAIN = Entity(type=EntityType.DOMAIN, value="example.com")
PAGE = """<html><head>
<script async src="https://www.googletagmanager.com/gtag/js?id=G-AB12CD34EF"></script>
<script>ga('create', 'UA-1234567-1', 'auto'); gtag('config', 'AW-123456789');</script>
<script>(function(w,d,s,l,i){})(window,document,'script','dataLayer','GTM-ABC123');</script>
<script data-ad-client="ca-pub-1234567890123456"></script>
<style>.G-STRETCH { color: red } .G-ABCDEFGH {}</style>
<p>UA-12-1 no es un ID y GTM-X tampoco</p>
</head></html>"""


@respx.mock
async def test_analytics_ids_extracts_each_kind_once(ctx):
    respx.get("https://example.com/").mock(return_value=httpx.Response(200, text=PAGE + PAGE))
    out = await AnalyticsIds(ctx).run(DOMAIN)
    found = {e.value: e.data["kind"] for e in out}
    assert found == {
        "analytics:G-AB12CD34EF": "Google Analytics 4",
        "analytics:UA-1234567-1": "Google Analytics (Universal)",
        "analytics:AW-123456789": "Google Ads",
        "analytics:GTM-ABC123": "Google Tag Manager",
        "analytics:ca-pub-1234567890123456": "Google AdSense",
    }
    assert all(e.type == EntityType.RECORD and e.data["domain"] == "example.com" for e in out)


@respx.mock
async def test_analytics_ids_falls_back_to_http(ctx):
    respx.get("https://example.com/").mock(side_effect=httpx.ConnectError("sin TLS"))
    respx.get("http://example.com/").mock(return_value=httpx.Response(200, text=PAGE))
    assert len(await AnalyticsIds(ctx).run(DOMAIN)) == 5


@respx.mock
async def test_a_page_without_ids_or_a_missing_page_gives_nothing(ctx):
    respx.get("https://example.com/").mock(return_value=httpx.Response(404))
    assert await AnalyticsIds(ctx).run(DOMAIN) == []
    respx.get("https://example.com/").mock(return_value=httpx.Response(200, text="<html></html>"))
    assert await AnalyticsIds(ctx).run(DOMAIN) == []


@respx.mock
async def test_analytics_ids_unreachable_site_is_an_error(ctx):
    respx.get("https://example.com/").mock(side_effect=httpx.ConnectError("no"))
    respx.get("http://example.com/").mock(side_effect=httpx.ConnectError("no"))
    with pytest.raises(ModuleError, match="no responde"):
        await AnalyticsIds(ctx).run(DOMAIN)


def test_it_contacts_the_target_so_it_is_active_and_only_for_root_domains():
    assert AnalyticsIds.passive is False
    sub = Entity(type=EntityType.DOMAIN, value="a.example.com", data={"subdomain": True})
    assert AnalyticsIds(None).accepts(DOMAIN) and not AnalyticsIds(None).accepts(sub)

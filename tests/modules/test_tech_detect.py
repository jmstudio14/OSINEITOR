from __future__ import annotations

import json
import re

import httpx
import pytest
import respx

from osineitor.models import Entity, EntityType
from osineitor.modules.base import ModuleError
from osineitor.modules.domain.tech_detect import TechDetect, signatures

DOMAIN = Entity(type=EntityType.DOMAIN, value="example.com")
HTML = """<html><head>
<meta content="WordPress 6.5.2" name="generator">
<script src="/wp-includes/js/jquery/jquery-3.7.1.min.js"></script>
<script src='https://www.googletagmanager.com/gtm.js?id=GTM-X'></script>
</head><body class="x"></body></html>"""


@respx.mock
async def test_detects_by_headers_cookies_meta_scripts_and_html(ctx):
    respx.get("https://example.com").mock(
        return_value=httpx.Response(
            200,
            text=HTML,
            headers=[
                ("Server", "nginx/1.25.3"),
                ("X-Powered-By", "PHP/8.3.1"),
                ("CF-Ray", "abc"),
                ("Set-Cookie", "PHPSESSID=1; Path=/"),
                ("Set-Cookie", "__cf_bm=2; Path=/"),
            ],
        )
    )
    out = await TechDetect(ctx).run(DOMAIN)
    found = {e.value: e.data for e in out}
    assert found["WordPress"]["version"] == "6.5.2"
    assert "meta generator" in found["WordPress"]["evidence"]
    assert found["jQuery"]["version"] == "3.7.1"
    assert found["Nginx"]["version"] == "1.25.3"
    assert found["PHP"]["version"] == "8.3.1"
    assert set(found["PHP"]["evidence"]) == {"cabecera x-powered-by", "cookie PHPSESSID"}
    assert found["Cloudflare"]["category"] == "cdn"
    assert "Google Tag Manager" in found
    assert all(d["signatures"] == signatures()["version"] for d in found.values())
    assert [e.value for e in out] == sorted(found)


WP_ASSETS_HTML = """<html><head>
<link rel='stylesheet' href='https://example.com/wp-content/themes/Twentytwentyfour/style.css?ver=1.2'>
<script src="/wp-content/plugins/akismet/_inc/akismet.js?ver=5.3"></script>
<script src="/wp-content/plugins/akismet/other.js?ver=5.3.1"></script>
<img src="/wp-content/plugins/contact-form-7/img.png">
<a href="/wp-content/plugins/../evil/x.js?ver=9">x</a>
</head></html>"""


@respx.mock
async def test_wordpress_plugins_and_themes_come_from_the_homepage_without_extra_requests(ctx):
    route = respx.get("https://example.com").mock(
        return_value=httpx.Response(200, text=WP_ASSETS_HTML)
    )
    out = await TechDetect(ctx).run(DOMAIN)
    found = {e.value: e.data for e in out}
    assert route.call_count == 1
    assert found["WordPress plugin: akismet"]["version"] == "5.3"
    assert found["WordPress plugin: akismet"]["category"] == "plugin"
    assert found["WordPress plugin: akismet"]["evidence"] == ["html"]
    assert found["WordPress plugin: contact-form-7"]["version"] is None
    assert found["WordPress theme: twentytwentyfour"]["version"] == "1.2"
    assert found["WordPress theme: twentytwentyfour"]["category"] == "theme"
    assert not any("evil" in value or ".." in value for value in found)


@respx.mock
async def test_wordpress_assets_are_capped(ctx):
    body = "".join(f'<script src="/wp-content/plugins/p{i}/a.js"></script>' for i in range(80))
    respx.get("https://example.com").mock(return_value=httpx.Response(200, text=body))
    out = await TechDetect(ctx).run(DOMAIN)
    assert len([e for e in out if e.value.startswith("WordPress plugin: ")]) == 50


@respx.mock
async def test_plain_page_detects_nothing_and_falls_back_to_http(ctx):
    respx.get("https://example.com").mock(side_effect=httpx.ConnectError("x"))
    respx.get("http://example.com").mock(return_value=httpx.Response(200, text="<html></html>"))
    assert await TechDetect(ctx).run(DOMAIN) == []


@respx.mock
async def test_unreachable_site_is_an_error(ctx):
    respx.get("https://example.com").mock(side_effect=httpx.ConnectError("x"))
    respx.get("http://example.com").mock(side_effect=httpx.ConnectError("x"))
    with pytest.raises(ModuleError, match="no responde"):
        await TechDetect(ctx).run(DOMAIN)


def test_the_module_is_active():
    assert TechDetect.passive is False


def test_every_signature_is_well_formed():
    data = signatures()
    names = [s["name"] for s in data["technologies"]]
    assert len(names) == len(set(names)) >= 50
    for sig in data["technologies"]:
        assert {"name", "category"} <= set(sig)
        assert set(sig) <= {"name", "category", "headers", "cookies", "meta", "scripts", "html"}
        patterns = [*sig.get("headers", {}).values(), *sig.get("meta", {}).values()]
        patterns += [*sig.get("cookies", []), *sig.get("scripts", []), *sig.get("html", [])]
        assert patterns, sig["name"]
        for pattern in patterns:
            re.compile(pattern)
    assert "GPL" in json.dumps(
        data["license"]
    )  # deja constancia de por qué no se usa webappanalyzer

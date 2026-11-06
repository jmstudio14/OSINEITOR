"""`username_wmn` (F5.3): firmas de WhatsMyName y confirmación cruzada con Sherlock."""

from __future__ import annotations

import asyncio
import json

import httpx
import respx

from osineitor.engine import Engine
from osineitor.models import Entity, EntityType
from osineitor.modules.username.sites import UsernameSites
from osineitor.modules.username.wmn import UsernameWmn, load_wmn

SITES = {
    "Plain": {
        "uri_check": "https://plain.test/u/{account}",
        "e_code": 200,
        "e_string": "profile-header",
        "m_string": "not found",
        "m_code": 404,
    },
    "Pretty": {
        "uri_check": "https://api.pretty.test/v1/{account}",
        "uri_pretty": "https://pretty.test/@{account}",
        "e_code": 200,
        "e_string": '"id"',
        "m_string": "",
        "m_code": 404,
    },
    "Post": {
        "uri_check": "https://post.test/graphql",
        "uri_pretty": "https://post.test/user/{account}",
        "post_body": '{"name":"{account}"}',
        "headers": {"Content-Type": "application/json"},
        "e_code": 200,
        "e_string": '"id"',
        "m_string": "Not Found",
        "m_code": 404,
    },
    "Strip": {
        "uri_check": "https://strip.test/{account}",
        "strip_bad_char": ".",
        "e_code": 200,
        "e_string": "ok",
        "m_string": "",
        "m_code": 404,
    },
}


class FakeWmn(UsernameWmn):
    def sites(self):
        return SITES


def controls_absent():
    respx.get(url__regex=r"https://plain\.test/u/x[0-9a-f]+$").mock(
        return_value=httpx.Response(200, text="not found")
    )
    respx.get(url__regex=r"https://api\.pretty\.test/v1/x[0-9a-f]+$").mock(
        return_value=httpx.Response(404)
    )
    respx.post("https://post.test/graphql").mock(
        side_effect=lambda r: httpx.Response(
            200, text='{"id":1}' if b'"ana"' in r.content else "Not Found"
        )
    )
    respx.get(url__regex=r"https://strip\.test/x[0-9a-f]+$").mock(return_value=httpx.Response(404))


@respx.mock
async def test_wmn_detects_with_status_and_strings(ctx):
    respx.get("https://plain.test/u/ana").mock(
        return_value=httpx.Response(200, text="<div class='profile-header'>")
    )
    respx.get("https://api.pretty.test/v1/ana").mock(
        return_value=httpx.Response(200, json={"id": 7})
    )
    respx.get("https://strip.test/ana").mock(return_value=httpx.Response(200, text="ok"))
    controls_absent()
    out = await FakeWmn(ctx).run(Entity(type=EntityType.USERNAME, value="ana"))
    assert {e.data["site"]: e.value for e in out} == {
        "Plain": "https://plain.test/u/ana",
        "Pretty": "https://pretty.test/@ana",
        "Post": "https://post.test/user/ana",
        "Strip": "https://strip.test/ana",
    }


@respx.mock
async def test_wmn_post_escapes_the_username_inside_json(ctx):
    route = respx.post("https://post.test/graphql").mock(
        return_value=httpx.Response(200, text='{"id":1}')
    )
    module = FakeWmn(ctx)
    username = 'a"b'
    await module._probe(asyncio.Semaphore(1), SITES["Post"], username)
    assert json.loads(route.calls[0].request.content) == {"name": username}
    assert route.calls[0].request.headers["content-type"] == "application/json"


@respx.mock
async def test_wmn_missing_string_or_wrong_status_is_not_a_profile(ctx):
    respx.get("https://plain.test/u/ana").mock(
        return_value=httpx.Response(200, text="not found profile-header")  # m_string presente
    )
    respx.get("https://api.pretty.test/v1/ana").mock(return_value=httpx.Response(404))
    respx.get("https://strip.test/ana").mock(return_value=httpx.Response(200, text="nada"))
    respx.post("https://post.test/graphql").mock(side_effect=httpx.ConnectError("x"))
    out = await FakeWmn(ctx).run(Entity(type=EntityType.USERNAME, value="ana"))
    assert out == []


@respx.mock
async def test_wmn_strips_bad_characters_from_the_account(ctx):
    respx.get("https://strip.test/ana").mock(return_value=httpx.Response(200, text="ok"))
    controls_absent()
    respx.route().mock(return_value=httpx.Response(404))  # el resto de sitios, sin perfil
    out = await FakeWmn(ctx).run(Entity(type=EntityType.USERNAME, value="a.n.a"))
    assert [e.value for e in out if e.data["site"] == "Strip"] == ["https://strip.test/ana"]


@respx.mock
async def test_wmn_site_that_finds_the_control_is_dropped(ctx):
    respx.get(url__regex=r"https://strip\.test/.+").mock(
        return_value=httpx.Response(200, text="ok")  # también «existe» para el control
    )
    respx.route().mock(return_value=httpx.Response(404))
    out = await FakeWmn(ctx).run(Entity(type=EntityType.USERNAME, value="ana"))
    assert out == []


def test_bundled_signatures_skip_adult_and_protected_sites():
    sites = load_wmn()
    assert len(sites) > 400
    assert all(s.get("cat") != "xx NSFW xx" and not s.get("protection") for s in sites.values())
    assert all("{account}" in s["uri_check"] for s in sites.values() if not s.get("post_body"))


class FakeSherlock(UsernameSites):
    def sites(self):
        return {"Plain": {"errorType": "status_code", "url": "https://plain.test/u/{}"}}


@respx.mock
async def test_profile_seen_by_both_sources_is_confirmed(ctx):
    respx.get("https://plain.test/u/ana").mock(
        return_value=httpx.Response(200, text="profile-header")
    )
    respx.get(url__regex=r"https://plain\.test/u/x[0-9a-f]+$").mock(
        return_value=httpx.Response(404)
    )
    only_wmn = {"Plain": SITES["Plain"], "Strip": SITES["Strip"]}
    respx.get("https://strip.test/ana").mock(return_value=httpx.Response(200, text="ok"))
    respx.get(url__regex=r"https://strip\.test/x[0-9a-f]+$").mock(return_value=httpx.Response(404))

    class TwoSites(FakeWmn):
        def sites(self):
            return only_wmn

    seed = Entity(type=EntityType.USERNAME, value="ana")
    result = await Engine(ctx, [FakeSherlock, TwoSites], depth=1).run(seed)
    profiles = {e.value: e for e in result.entities if e.type == EntityType.PROFILE}
    both = profiles["https://plain.test/u/ana"]
    alone = profiles["https://strip.test/ana"]
    assert sorted(both.sources) == ["username_sites", "username_wmn"]
    assert (both.confidence, alone.confidence) == ("medio", "bajo")

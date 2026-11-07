"""Módulo profile_extract (F5.4, F5.5): datos que el propio dueño publicó en APIs oficiales."""

from __future__ import annotations

import httpx
import pytest
import respx

from osineitor.models import Entity, EntityType
from osineitor.modules.base import ModuleError, ModuleQuota
from osineitor.modules.username.profile_extract import ProfileExtract

DEVTO = "https://dev.to/api/users/by_username"
CODEBERG = "https://codeberg.org/api/v1/users/ana"
USER = Entity(type=EntityType.USERNAME, value="ana")
DEVTO_BODY = {
    "username": "ana",
    "name": "Ana García",
    "twitter_username": "anatw",
    "github_username": "anagh",
    "summary": "Desarrolladora",
    "location": "Madrid",
    "website_url": "http://ana.example.com",
    "joined_at": "Dec 27, 2015",
}
CODEBERG_BODY = {
    "login": "ana",
    "full_name": "Ana G.",
    "html_url": "https://codeberg.org/ana",
    "email": "ana@noreply.codeberg.org",
    "location": "Sevilla",
    "website": "https://ana.example.org",
    "description": '<a href="https://x.test">hola</a>\r\n  <b>mundo</b>',
    "created": "2019-10-12T05:05:49+02:00",
}


def by_type(out, kind):
    return [e for e in out if e.type == kind]


def quiet(devto: bool = True, codeberg: bool = True) -> None:
    if devto:
        respx.get(DEVTO).mock(return_value=httpx.Response(404))
    if codeberg:
        respx.get(CODEBERG).mock(return_value=httpx.Response(404))


@respx.mock
async def test_devto_profile_is_enriched_with_what_the_owner_declared(ctx):
    route = respx.get(DEVTO).mock(return_value=httpx.Response(200, json=DEVTO_BODY))
    quiet(devto=False)
    out = await ProfileExtract(ctx).run(USER)
    assert route.calls[0].request.url.params["url"] == "ana"
    [profile] = by_type(out, EntityType.PROFILE)
    assert profile.value == "https://dev.to/ana"
    assert profile.data["site"] == "DEV Community"
    assert profile.data["display_name"] == "Ana García"
    assert profile.data["bio"] == "Desarrolladora" and profile.data["location"] == "Madrid"
    assert profile.data["created_at"] == "2015-12-27"
    assert profile.data["verified"] is True


@respx.mock
async def test_declared_handles_and_website_become_entities_to_pivot_on(ctx):
    respx.get(DEVTO).mock(return_value=httpx.Response(200, json=DEVTO_BODY))
    quiet(devto=False)
    out = await ProfileExtract(ctx).run(USER)
    handles = {e.value: e.data for e in by_type(out, EntityType.USERNAME)}
    assert set(handles) == {"anatw", "anagh"}
    assert handles["anatw"]["declared_on"] == "https://dev.to/ana"
    assert handles["anatw"]["platform"] == "twitter"
    [site] = by_type(out, EntityType.URL)
    assert (
        site.value == "http://ana.example.com" and site.data["declared_on"] == "https://dev.to/ana"
    )


@respx.mock
async def test_a_declared_handle_equal_to_the_investigated_one_is_not_repeated(ctx):
    body = {**DEVTO_BODY, "twitter_username": "ANA", "github_username": None}
    respx.get(DEVTO).mock(return_value=httpx.Response(200, json=body))
    quiet(devto=False)
    out = await ProfileExtract(ctx).run(USER)
    assert by_type(out, EntityType.USERNAME) == []


@respx.mock
async def test_codeberg_profile_never_keeps_the_email_and_strips_html(ctx):
    respx.get(CODEBERG).mock(return_value=httpx.Response(200, json=CODEBERG_BODY))
    quiet(codeberg=False)
    out = await ProfileExtract(ctx).run(USER)
    [profile] = by_type(out, EntityType.PROFILE)
    assert profile.value == "https://codeberg.org/ana"
    assert profile.data["site"] == "Codeberg" and profile.data["display_name"] == "Ana G."
    assert profile.data["bio"] == "hola mundo"
    assert profile.data["created_at"] == "2019-10-12T05:05:49+02:00"
    assert "email" not in profile.data
    assert by_type(out, EntityType.EMAIL) == []
    assert [e.value for e in by_type(out, EntityType.URL)] == ["https://ana.example.org"]


@respx.mock
async def test_hostile_values_are_dropped_without_losing_the_rest(ctx):
    body = {
        **DEVTO_BODY,
        "twitter_username": "no valido!",
        "github_username": "<script>",
        "website_url": "javascript:alert(1)",
        "joined_at": "ayer",
    }
    respx.get(DEVTO).mock(return_value=httpx.Response(200, json=body))
    quiet(devto=False)
    out = await ProfileExtract(ctx).run(USER)
    assert by_type(out, EntityType.USERNAME) == [] and by_type(out, EntityType.URL) == []
    [profile] = by_type(out, EntityType.PROFILE)
    assert not profile.data.get("created_at") and profile.data["display_name"] == "Ana García"


@respx.mock
async def test_nothing_found_gives_nothing(ctx):
    quiet()
    assert await ProfileExtract(ctx).run(USER) == []


@respx.mock
async def test_one_failing_source_keeps_the_other(ctx):
    respx.get(DEVTO).mock(return_value=httpx.Response(500))
    respx.get(CODEBERG).mock(return_value=httpx.Response(200, json=CODEBERG_BODY))
    out = await ProfileExtract(ctx).run(USER)
    assert [e.value for e in by_type(out, EntityType.PROFILE)] == ["https://codeberg.org/ana"]


@respx.mock
async def test_all_sources_failing_is_an_error_and_a_429_is_a_quota(ctx):
    respx.get(DEVTO).mock(return_value=httpx.Response(429))
    respx.get(CODEBERG).mock(return_value=httpx.Response(500))
    with pytest.raises(ModuleQuota):
        await ProfileExtract(ctx).run(USER)
    respx.get(DEVTO).mock(return_value=httpx.Response(500))
    with pytest.raises(ModuleError):
        await ProfileExtract(ctx).run(USER)


@respx.mock
async def test_the_engine_pivots_on_the_declared_handles_up_to_the_scan_depth():
    from osineitor import Scanner

    respx.get(DEVTO, params={"url": "ana"}).mock(return_value=httpx.Response(200, json=DEVTO_BODY))
    second = respx.get(DEVTO, params={"url": "anatw"}).mock(return_value=httpx.Response(404))
    respx.get(DEVTO, params={"url": "anagh"}).mock(return_value=httpx.Response(404))
    respx.get(url__regex=r"https://codeberg\.org/api/v1/users/.*").mock(
        return_value=httpx.Response(404)
    )
    result = await Scanner(only=["profile_extract"], depth=2, use_cache=False).ascan(
        "ana", EntityType.USERNAME
    )
    assert second.called  # el segundo nivel investigó el username que declaró el perfil
    assert {"username:anatw", "username:anagh"} <= {e.key for e in result.entities}

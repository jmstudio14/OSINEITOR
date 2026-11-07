"""Módulo bluesky (F5.10): perfil público por handle de atproto, sin red."""

from __future__ import annotations

import httpx
import pytest
import respx

from osineitor.models import Entity, EntityType
from osineitor.modules.base import ModuleError, ModuleQuota, ModuleSkipped
from osineitor.modules.username.bluesky import Bluesky

API = "https://public.api.bsky.app/xrpc/app.bsky.actor.getProfile"
PROFILE = {
    "did": "did:plc:abc123",
    "handle": "ana.bsky.social",
    "displayName": "Ana García",
    "description": "Hago cosas\ncon redes",
    "createdAt": "2023-05-01T10:00:00.000Z",
    "followersCount": 12,
    "followsCount": 34,
    "postsCount": 56,
}


def user(value: str) -> Entity:
    return Entity(type=EntityType.USERNAME, value=value)


@respx.mock
async def test_bluesky_reads_the_public_profile_of_a_bare_username(ctx):
    route = respx.get(API).mock(return_value=httpx.Response(200, json=PROFILE))
    [profile] = await Bluesky(ctx).run(user("ana"))
    assert route.calls[0].request.url.params["actor"] == "ana.bsky.social"
    assert profile.type == EntityType.PROFILE
    assert profile.value == "https://bsky.app/profile/ana.bsky.social"
    assert profile.data["site"] == "Bluesky"
    assert profile.data["display_name"] == "Ana García"
    assert profile.data["did"] == "did:plc:abc123"
    assert profile.data["followers"] == 12 and profile.data["posts"] == 56
    assert profile.data["created_at"] == "2023-05-01T10:00:00.000Z"
    assert profile.data["verified"] is True


@respx.mock
async def test_bluesky_uses_a_username_with_dots_as_a_full_handle(ctx):
    route = respx.get(API).mock(
        return_value=httpx.Response(200, json={**PROFILE, "handle": "ana.example.com"})
    )
    [profile] = await Bluesky(ctx).run(user("Ana.Example.com"))
    assert route.calls[0].request.url.params["actor"] == "ana.example.com"
    assert profile.value == "https://bsky.app/profile/ana.example.com"


@respx.mock
@pytest.mark.parametrize("status", [400, 404])
async def test_bluesky_profile_not_found_gives_nothing(ctx, status):
    respx.get(API).mock(
        return_value=httpx.Response(
            status, json={"error": "InvalidRequest", "message": "Profile not found"}
        )
    )
    assert await Bluesky(ctx).run(user("ana")) == []


@pytest.mark.parametrize("value", ["ana_garcia", "-ana", "ana.123", "ana..es"])
async def test_bluesky_skips_values_that_cannot_be_a_handle(ctx, value):
    with pytest.raises(ModuleSkipped):
        await Bluesky(ctx).run(user(value))


@respx.mock
async def test_bluesky_rate_limit_is_a_quota_error(ctx):
    respx.get(API).mock(return_value=httpx.Response(429))
    with pytest.raises(ModuleQuota):
        await Bluesky(ctx).run(user("ana"))


@respx.mock
async def test_bluesky_server_error_is_a_module_error(ctx):
    respx.get(API).mock(return_value=httpx.Response(500))
    with pytest.raises(ModuleError):
        await Bluesky(ctx).run(user("ana"))


@respx.mock
async def test_bluesky_ignores_a_profile_without_handle(ctx):
    respx.get(API).mock(return_value=httpx.Response(200, json={"did": "did:plc:x"}))
    assert await Bluesky(ctx).run(user("ana")) == []

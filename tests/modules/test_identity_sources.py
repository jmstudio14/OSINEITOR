"""Fuentes de identidad de la fase 5 (F5.2, F5.7, F5.10, F5.11, F5.13, F5.14), sin red."""

from __future__ import annotations

import httpx
import pytest
import respx

from osineitor.models import Entity, EntityType
from osineitor.modules.base import ModuleError, ModuleQuota
from osineitor.modules.email.github_email import GithubEmail
from osineitor.modules.email.hibp_pastes import HibpPastes
from osineitor.modules.username.dev_registries import DevRegistries
from osineitor.modules.username.discord_snowflake import DiscordSnowflake
from osineitor.modules.username.fediverse import Fediverse
from osineitor.modules.username.github_user import GithubUser

EMAIL = Entity(type=EntityType.EMAIL, value="ana@example.com")
USER = Entity(type=EntityType.USERNAME, value="ana")


def pairs(out):
    return [(e.type, e.value) for e in out]


# --- hibp_pastes -----------------------------------------------------------------------------


@respx.mock
async def test_hibp_pastes_summarises_without_paste_ids(ctx, config):
    config.keys["hibp"] = "H"
    route = respx.get("https://haveibeenpwned.com/api/v3/pasteaccount/ana%40example.com").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "Source": "Pastebin",
                    "Id": "SECRET1",
                    "Title": "dump",
                    "Date": "2020-01-01T00:00:00Z",
                },
                {"Source": "Pastebin", "Id": "X2", "Date": "2021-05-05T00:00:00Z"},
                {"Source": "Slexy", "Id": "X3", "Date": None},
            ],
        )
    )
    out = await HibpPastes(ctx).run(EMAIL)
    assert route.calls[0].request.headers["hibp-api-key"] == "H"
    assert pairs(out) == [(EntityType.RECORD, "hibp_pastes:ana@example.com")]
    data = out[0].data
    assert data["pastes"] == 3
    assert data["sources"] == ["Pastebin", "Slexy"]
    assert (data["first_paste"], data["last_paste"]) == (
        "2020-01-01T00:00:00Z",
        "2021-05-05T00:00:00Z",
    )
    assert "SECRET1" not in str(data)


@respx.mock
async def test_hibp_pastes_not_found_and_bad_key(ctx, config):
    config.keys["hibp"] = "H"
    url = "https://haveibeenpwned.com/api/v3/pasteaccount/ana%40example.com"
    respx.get(url).mock(return_value=httpx.Response(404))
    assert await HibpPastes(ctx).run(EMAIL) == []
    respx.get(url).mock(return_value=httpx.Response(401))
    with pytest.raises(ModuleError, match="inválida"):
        await HibpPastes(ctx).run(EMAIL)


# --- github_email ----------------------------------------------------------------------------


@respx.mock
async def test_github_email_finds_authors_repositories_and_logins(ctx):
    route = respx.get("https://api.github.com/search/commits").mock(
        return_value=httpx.Response(
            200,
            json={
                "total_count": 7,
                "items": [
                    {
                        "commit": {"author": {"name": "Ana G", "date": "2024-02-01T00:00:00Z"}},
                        "repository": {"full_name": "ana/tool"},
                        "author": {"login": "ana-g"},
                    },
                    {
                        "commit": {"author": {"name": "A. García", "date": "2023-01-01T00:00:00Z"}},
                        "repository": {"full_name": "org/lib"},
                        "author": None,
                    },
                ],
            },
        )
    )
    out = await GithubEmail(ctx).run(EMAIL)
    assert route.calls[0].request.url.params["q"] == "author-email:ana@example.com"
    assert pairs(out) == [
        (EntityType.RECORD, "github_email:ana@example.com"),
        (EntityType.USERNAME, "ana-g"),
    ]
    data = out[0].data
    assert data["commits"] == 7
    assert data["names"] == ["Ana G", "A. García"]
    assert (data["first_commit"], data["last_commit"]) == (
        "2023-01-01T00:00:00Z",
        "2024-02-01T00:00:00Z",
    )


@respx.mock
async def test_github_email_rate_limit_and_empty(ctx):
    respx.get("https://api.github.com/search/commits").mock(
        return_value=httpx.Response(403, headers={"x-ratelimit-remaining": "0"})
    )
    with pytest.raises(ModuleQuota):
        await GithubEmail(ctx).run(EMAIL)
    respx.get("https://api.github.com/search/commits").mock(
        return_value=httpx.Response(200, json={"total_count": 0, "items": []})
    )
    assert await GithubEmail(ctx).run(EMAIL) == []


def test_github_search_respects_the_unauthenticated_limit():
    assert GithubEmail.min_interval >= 6  # 10 búsquedas por minuto


# --- github_user -----------------------------------------------------------------------------


@respx.mock
async def test_github_user_profile_orgs_and_commit_emails(ctx, config):
    config.keys["github"] = "T"
    user = respx.get("https://api.github.com/users/ana").mock(
        return_value=httpx.Response(
            200,
            json={
                "html_url": "https://github.com/ana",
                "name": "Ana García",
                "company": "ACME",
                "blog": "ana.dev",
                "twitter_username": "ana_tw",
                "created_at": "2015-01-01T00:00:00Z",
            },
        )
    )
    respx.get("https://api.github.com/users/ana/orgs").mock(
        return_value=httpx.Response(200, json=[{"login": "acme-oss"}, {"x": 1}])
    )
    respx.get("https://api.github.com/users/ana/events/public").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"type": "WatchEvent"},
                {
                    "type": "PushEvent",
                    "payload": {
                        "commits": [
                            {"author": {"email": "Ana@Example.com", "name": "Ana"}},
                            {"author": {"email": "123+ana@users.noreply.github.com", "name": "x"}},
                            {"author": {"email": "ana@example.com", "name": "dup"}},
                        ]
                    },
                },
            ],
        )
    )
    out = await GithubUser(ctx).run(USER)
    assert user.calls[0].request.headers["Authorization"] == "Bearer T"
    assert pairs(out) == [
        (EntityType.PROFILE, "https://github.com/ana"),
        (EntityType.URL, "https://ana.dev"),
        (EntityType.ORGANIZATION, "acme-oss"),
        (EntityType.EMAIL, "ana@example.com"),
    ]
    assert out[0].data["name"] == "Ana García"
    assert out[3].data == {"role": "commit", "commit_author": "Ana"}


@respx.mock
async def test_github_user_missing_and_rate_limited(ctx):
    respx.get("https://api.github.com/users/ana").mock(return_value=httpx.Response(404))
    assert await GithubUser(ctx).run(USER) == []
    respx.get("https://api.github.com/users/ana").mock(
        return_value=httpx.Response(403, headers={"x-ratelimit-remaining": "0"})
    )
    with pytest.raises(ModuleQuota):
        await GithubUser(ctx).run(USER)


# --- fediverse -------------------------------------------------------------------------------


@respx.mock
async def test_fediverse_lookup(ctx):
    route = respx.get("https://mastodon.example/api/v1/accounts/lookup").mock(
        return_value=httpx.Response(
            200,
            json={
                "url": "https://mastodon.example/@ana",
                "display_name": "Ana",
                "note": "<p>Hola <a href='x'>mundo</a></p>",
                "followers_count": 10,
            },
        )
    )
    out = await Fediverse(ctx).run(Entity(type=EntityType.EMAIL, value="ana@mastodon.example"))
    assert route.calls[0].request.url.params["acct"] == "ana"
    assert pairs(out) == [(EntityType.PROFILE, "https://mastodon.example/@ana")]
    assert out[0].data["bio"] == "Hola mundo"


@respx.mock
async def test_fediverse_falls_back_to_webfinger_and_ignores_plain_mail_hosts(ctx):
    respx.get("https://pleroma.example/api/v1/accounts/lookup").mock(
        return_value=httpx.Response(404)
    )
    respx.get("https://pleroma.example/.well-known/webfinger").mock(
        return_value=httpx.Response(
            200,
            json={
                "links": [
                    {"rel": "self", "href": "https://pleroma.example/users/ana"},
                    {
                        "rel": "http://webfinger.net/rel/profile-page",
                        "href": "https://pleroma.example/@ana",
                    },
                ]
            },
        )
    )
    mail = Entity(type=EntityType.EMAIL, value="ana@pleroma.example")
    assert pairs(await Fediverse(ctx).run(mail)) == [
        (EntityType.PROFILE, "https://pleroma.example/@ana")
    ]
    respx.get("https://gmail.test/api/v1/accounts/lookup").mock(return_value=httpx.Response(404))
    respx.get("https://gmail.test/.well-known/webfinger").mock(return_value=httpx.Response(404))
    assert await Fediverse(ctx).run(Entity(type=EntityType.EMAIL, value="ana@gmail.test")) == []


def test_fediverse_is_active():
    assert Fediverse.passive is False


# --- dev_registries --------------------------------------------------------------------------

PYPI_ANA = "https://pypi.org/user/ana/"
STACK = "https://api.stackexchange.com/2.3/users"


def quiet_pypi_and_stack() -> None:
    """Simula PyPI y Stack Exchange sin resultados (para los tests de las otras fuentes)."""
    respx.get(PYPI_ANA).mock(return_value=httpx.Response(404))
    respx.get(STACK).mock(return_value=httpx.Response(200, json={"items": []}))


@respx.mock
async def test_dev_registries_collects_the_profiles_that_exist(ctx):
    npm = respx.get("https://registry.npmjs.org/-/v1/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "objects": [
                    {"package": {"name": "ana-lib", "maintainers": [{"username": "Ana"}]}},
                    {"package": {"name": "other", "maintainers": [{"username": "bob"}]}},
                ]
            },
        )
    )
    respx.get("https://crates.io/api/v1/users/ana").mock(return_value=httpx.Response(404))
    respx.get("https://hub.docker.com/v2/users/ana/").mock(
        return_value=httpx.Response(200, json={"username": "ana", "full_name": "Ana G"})
    )
    respx.get("https://hub.docker.com/v2/repositories/ana/").mock(
        return_value=httpx.Response(200, json={"results": [{"name": "img"}]})
    )
    quiet_pypi_and_stack()
    out = await DevRegistries(ctx).run(USER)
    assert npm.calls[0].request.url.params["text"] == "maintainer:ana"
    assert npm.calls[0].request.headers["User-Agent"] == "osineitor"
    assert pairs(out) == [
        (EntityType.PROFILE, "https://www.npmjs.com/~ana"),
        (EntityType.PROFILE, "https://hub.docker.com/u/ana"),
    ]
    assert out[0].data["packages"] == ["ana-lib"]
    assert out[1].data["packages"] == ["img"]


@respx.mock
async def test_dev_registries_one_failing_source_does_not_hide_the_rest(ctx):
    respx.get("https://registry.npmjs.org/-/v1/search").mock(return_value=httpx.Response(500))
    respx.get("https://crates.io/api/v1/users/ana").mock(
        return_value=httpx.Response(200, json={"user": {"login": "ana", "name": "Ana"}})
    )
    respx.get("https://hub.docker.com/v2/users/ana/").mock(return_value=httpx.Response(404))
    quiet_pypi_and_stack()
    out = await DevRegistries(ctx).run(USER)
    assert pairs(out) == [(EntityType.PROFILE, "https://crates.io/users/ana")]


@respx.mock
async def test_dev_registries_all_failing_is_an_error(ctx):
    for url in (
        "https://registry.npmjs.org/-/v1/search",
        "https://crates.io/api/v1/users/ana",
        "https://hub.docker.com/v2/users/ana/",
        PYPI_ANA,
        STACK,
    ):
        respx.get(url).mock(return_value=httpx.Response(500))
    with pytest.raises(ModuleError):
        await DevRegistries(ctx).run(USER)


PYPI_PAGE = """<html><head><title>Profile of ana · PyPI</title></head><body>
<h1 class="author-profile__name">Ana García</h1>
<a href="/project/ana-lib/">ana-lib</a> <a href="/project/ana-cli/">ana-cli</a>
<a href="/project/ana-lib/">ana-lib otra vez</a> <a href="/project/&lt;script&gt;/">raro</a>
</body></html>"""


@respx.mock
async def test_dev_registries_reads_the_public_pypi_profile(ctx):
    respx.get("https://registry.npmjs.org/-/v1/search").mock(
        return_value=httpx.Response(200, json={"objects": []})
    )
    respx.get("https://crates.io/api/v1/users/ana").mock(return_value=httpx.Response(404))
    respx.get("https://hub.docker.com/v2/users/ana/").mock(return_value=httpx.Response(404))
    respx.get(STACK).mock(return_value=httpx.Response(200, json={"items": []}))
    respx.get(PYPI_ANA).mock(return_value=httpx.Response(200, text=PYPI_PAGE))
    [profile] = await DevRegistries(ctx).run(USER)
    assert profile.value == "https://pypi.org/user/ana/"
    assert profile.data["site"] == "PyPI" and profile.data["name"] == "Ana García"
    assert profile.data["packages"] == ["ana-lib", "ana-cli"]  # sin repetidos ni nombres raros
    assert profile.data["package_count"] == 2


@respx.mock
async def test_dev_registries_pypi_page_of_another_user_is_ignored(ctx):
    respx.get("https://registry.npmjs.org/-/v1/search").mock(
        return_value=httpx.Response(200, json={"objects": []})
    )
    respx.get("https://crates.io/api/v1/users/ana").mock(return_value=httpx.Response(404))
    respx.get("https://hub.docker.com/v2/users/ana/").mock(return_value=httpx.Response(404))
    respx.get(STACK).mock(return_value=httpx.Response(200, json={"items": []}))
    respx.get(PYPI_ANA).mock(
        return_value=httpx.Response(200, text="<title>Profile of bob · PyPI</title>")
    )
    assert await DevRegistries(ctx).run(USER) == []


STACK_ITEMS = {
    "items": [
        {
            "display_name": "Ana",
            "link": "https://stackoverflow.com/users/1/ana",
            "user_id": 1,
            "reputation": 4200,
            "location": "Madrid",
            "creation_date": 1293376027,
        },
        {"display_name": "Ana Maria", "link": "https://stackoverflow.com/users/2/ana-maria"},
    ]
}


@respx.mock
async def test_dev_registries_stack_exchange_only_keeps_exact_display_name_matches(ctx):
    respx.get("https://registry.npmjs.org/-/v1/search").mock(
        return_value=httpx.Response(200, json={"objects": []})
    )
    respx.get("https://crates.io/api/v1/users/ana").mock(return_value=httpx.Response(404))
    respx.get("https://hub.docker.com/v2/users/ana/").mock(return_value=httpx.Response(404))
    respx.get(PYPI_ANA).mock(return_value=httpx.Response(404))
    route = respx.get(STACK).mock(return_value=httpx.Response(200, json=STACK_ITEMS))
    [profile] = await DevRegistries(ctx).run(USER)
    params = route.calls[0].request.url.params
    assert params["inname"] == "ana" and params["site"] == "stackoverflow"
    assert profile.value == "https://stackoverflow.com/users/1/ana"
    assert profile.data["site"] == "Stack Overflow" and profile.data["reputation"] == 4200
    assert profile.data["created_at"] == "2010-12-26T15:07:07+00:00"
    assert profile.data["match"] == "display_name"  # coincidencia de nombre, no de identidad
    assert "verified" not in profile.data


# --- discord_snowflake -----------------------------------------------------------------------


async def test_discord_snowflake_decodes_the_creation_date(ctx):
    module = DiscordSnowflake(ctx)
    seed = Entity(type=EntityType.USERNAME, value="175928847299117063")  # ID de la documentación
    assert module.accepts(seed)
    out = await module.run(seed)
    assert out[0].value == "discord:175928847299117063"
    assert out[0].data["created_at"] == "2016-04-30T11:18:25.796000Z"


async def test_discord_snowflake_rejects_non_ids(ctx):
    module = DiscordSnowflake(ctx)
    assert not module.accepts(Entity(type=EntityType.USERNAME, value="ana"))
    assert not module.accepts(Entity(type=EntityType.USERNAME, value="12345"))
    assert await module.run(Entity(type=EntityType.USERNAME, value="9" * 19)) == []

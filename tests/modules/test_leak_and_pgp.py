"""Módulos leakcheck (F5.1) y pgp_keyserver (F5.12), sin red."""

from __future__ import annotations

import httpx
import pytest
import respx

from osineitor.models import Entity, EntityType
from osineitor.modules.base import ModuleError, ModuleQuota
from osineitor.modules.email.leakcheck import Leakcheck
from osineitor.modules.email.pgp_keyserver import PgpKeyserver

EMAIL = Entity(type=EntityType.EMAIL, value="ana@example.com")
LEAK = "https://leakcheck.io/api/public"
PGP = "https://keys.openpgp.org/pks/lookup"


# --- leakcheck -------------------------------------------------------------------------------


@respx.mock
async def test_leakcheck_lists_the_breach_sources_without_any_leaked_value(ctx):
    route = respx.get(LEAK).mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "found": 3,
                "fields": ["username", "password", "ip"],
                "sources": [
                    {"name": "Duolingo.com", "date": "2023-08"},
                    {"name": "Stealer Logs", "date": ""},
                    {"name": "<script>", "date": "2020-01"},
                    {"name": "", "date": "2020-01"},
                    "no es un objeto",
                ],
            },
        )
    )
    out = await Leakcheck(ctx).run(EMAIL)
    assert route.calls[0].request.url.params["check"] == "ana@example.com"
    assert [(e.type, e.value) for e in out] == [
        (EntityType.BREACH, "Duolingo.com"),
        (EntityType.BREACH, "Stealer Logs"),
        (EntityType.BREACH, "<script>"),
    ]
    assert out[0].data["date"] == "2023-08" and out[0].data["via"] == "leakcheck"
    assert not out[1].data.get("date")
    assert all("password" not in str(e.data) for e in out)  # solo nombres, nunca datos


@respx.mock
async def test_leakcheck_not_found_gives_nothing(ctx):
    respx.get(LEAK).mock(
        return_value=httpx.Response(200, json={"success": False, "error": "Not found"})
    )
    assert await Leakcheck(ctx).run(EMAIL) == []


@respx.mock
async def test_leakcheck_other_errors_are_module_errors(ctx):
    respx.get(LEAK).mock(
        return_value=httpx.Response(200, json={"success": False, "error": "Invalid email"})
    )
    with pytest.raises(ModuleError, match="Invalid email"):
        await Leakcheck(ctx).run(EMAIL)
    respx.get(LEAK).mock(return_value=httpx.Response(500))
    with pytest.raises(ModuleError):
        await Leakcheck(ctx).run(EMAIL)


@respx.mock
async def test_leakcheck_rate_limit_is_a_quota_error(ctx):
    respx.get(LEAK).mock(return_value=httpx.Response(429))
    with pytest.raises(ModuleQuota):
        await Leakcheck(ctx).run(EMAIL)


# --- pgp_keyserver ---------------------------------------------------------------------------

FPR = "A" * 40
INDEX = (
    "info:1:1\n"
    f"pub:{FPR}:1:4096:1600000000::\n"
    "uid:Ana García <ana@example.com>:1600000000::\n"
    "uid:Ana G. %3Cana@example.com%3E:1600000001::\n"
)


@respx.mock
async def test_pgp_keyserver_reports_the_key_the_owner_verified(ctx):
    route = respx.get(PGP).mock(return_value=httpx.Response(200, text=INDEX))
    [key] = await PgpKeyserver(ctx).run(EMAIL)
    params = route.calls[0].request.url.params
    assert params["op"] == "index" and params["options"] == "mr"
    assert params["search"] == "ana@example.com"
    assert (key.type, key.value) == (EntityType.RECORD, f"pgp:{FPR}")
    assert key.data["algorithm"] == "RSA" and key.data["bits"] == 4096
    assert key.data["created_at"] == "2020-09-13T12:26:40+00:00"
    assert key.data["identities"] == ["Ana García <ana@example.com>", "Ana G. <ana@example.com>"]


@respx.mock
async def test_pgp_keyserver_no_key_gives_nothing(ctx):
    respx.get(PGP).mock(
        return_value=httpx.Response(404, text="No key found for email address ana@example.com")
    )
    assert await PgpKeyserver(ctx).run(EMAIL) == []


@respx.mock
async def test_pgp_keyserver_ignores_malformed_lines_and_bad_fingerprints(ctx):
    respx.get(PGP).mock(
        return_value=httpx.Response(200, text="info:1:1\npub:no-es-una-huella:1:2048:1::\nbasura\n")
    )
    assert await PgpKeyserver(ctx).run(EMAIL) == []


@respx.mock
async def test_pgp_keyserver_rate_limit_and_server_errors(ctx):
    respx.get(PGP).mock(return_value=httpx.Response(429))
    with pytest.raises(ModuleQuota):
        await PgpKeyserver(ctx).run(EMAIL)
    respx.get(PGP).mock(return_value=httpx.Response(500))
    with pytest.raises(ModuleError):
        await PgpKeyserver(ctx).run(EMAIL)

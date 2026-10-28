from __future__ import annotations

import json

import httpx
import respx

from osineitor.models import Entity, EntityType
from osineitor.modules.username.sites import UsernameSites, load_sites

SITES = {
    "ByStatus": {"errorType": "status_code", "url": "https://status.test/{}"},
    "ByMessage": {
        "errorType": "message",
        "errorMsg": ["No such user", "Gone"],
        "url": "https://message.test/u/{}",
    },
    "ByRedirect": {"errorType": "response_url", "url": "https://redirect.test/{}"},
    "Probe": {
        "errorType": "status_code",
        "url": "https://probe.test/{}",
        "urlProbe": "https://api.probe.test/users/{}",
    },
    "Regex": {"errorType": "status_code", "url": "https://regex.test/{}", "regexCheck": "^[0-9]+$"},
    "Down": {"errorType": "status_code", "url": "https://down.test/{}"},
    "Missing": {"errorType": "status_code", "url": "https://missing.test/{}"},
}


class FakeSites(UsernameSites):
    def sites(self):
        return SITES


@respx.mock
async def test_username_detection(ctx):
    respx.get("https://status.test/juan").mock(return_value=httpx.Response(200))
    respx.get("https://message.test/u/juan").mock(return_value=httpx.Response(200, text="hola"))
    respx.get("https://redirect.test/juan").mock(return_value=httpx.Response(200))
    respx.get("https://api.probe.test/users/juan").mock(return_value=httpx.Response(200))
    respx.get("https://down.test/juan").mock(side_effect=httpx.ConnectError("x"))
    respx.get("https://missing.test/juan").mock(return_value=httpx.Response(404))
    out = await FakeSites(ctx).run(Entity(type=EntityType.USERNAME, value="juan"))
    assert {e.data["site"]: e.value for e in out} == {
        "ByStatus": "https://status.test/juan",
        "ByMessage": "https://message.test/u/juan",
        "ByRedirect": "https://redirect.test/juan",
        "Probe": "https://probe.test/juan",
    }


@respx.mock
async def test_username_negative_message_and_redirect(ctx):
    respx.get("https://status.test/juan").mock(return_value=httpx.Response(404))
    respx.get("https://message.test/u/juan").mock(
        return_value=httpx.Response(200, text="Sorry: No such user")
    )
    respx.get("https://redirect.test/juan").mock(
        return_value=httpx.Response(302, headers={"location": "https://redirect.test/"})
    )
    respx.get("https://api.probe.test/users/juan").mock(return_value=httpx.Response(404))
    respx.get("https://down.test/juan").mock(return_value=httpx.Response(404))
    respx.get("https://missing.test/juan").mock(return_value=httpx.Response(404))
    assert await FakeSites(ctx).run(Entity(type=EntityType.USERNAME, value="juan")) == []


def test_bundled_sites_are_valid():
    sites = load_sites()
    assert len(sites) > 400
    assert not any(s.get("isNSFW") for s in sites.values())
    for site in sites.values():
        probe = json.dumps([site["url"], site.get("urlProbe"), site.get("request_payload")])
        assert "{}" in probe
        assert site.get("errorType", "status_code") in {"status_code", "message", "response_url"}

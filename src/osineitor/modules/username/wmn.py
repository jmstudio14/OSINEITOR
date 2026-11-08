"""Presencia del username en cientos de sitios con las firmas de WhatsMyName (CC BY-SA 4.0).

Segunda fuente, complementaria a `username_sites` (Sherlock). Un perfil que ven las dos
fuentes llega con la misma URL, así que el motor lo fusiona: queda con dos fuentes y sube de
confianza (`bajo` → `medio`). Ese es el «confirmado» de la fase 5.
"""

from __future__ import annotations

import asyncio
import json
from functools import cache
from importlib import resources
from typing import Any

import httpx

from osineitor.errors import NetworkGuardError
from osineitor.modules.username.sites import TIMEOUT, UsernameSites
from osineitor.sanitize import quote_segment

NSFW_CATEGORY = "xx NSFW xx"
ACCOUNT = "{account}"


@cache
def load_wmn() -> dict[str, dict[str, Any]]:
    """Firmas aplicables, por nombre.

    Se omiten las de contenido adulto y las que WhatsMyName marca con `protection` (Cloudflare,
    captcha, DDoS-Guard...): no se eluden esas defensas, y sin ellas la respuesta no dice nada.
    """
    raw = resources.files(__package__).joinpath("data/wmn.json").read_text(encoding="utf-8")
    sites: dict[str, dict[str, Any]] = {}
    for site in json.loads(raw)["sites"]:
        if site.get("cat") == NSFW_CATEGORY or site.get("protection"):
            continue
        name = site["name"]
        while name in sites:  # algunos sitios tienen varias firmas con el mismo nombre
            name += "*"
        sites[name] = site
    return sites


def _account(site: dict[str, Any], username: str) -> str:
    return username.translate(str.maketrans("", "", site.get("strip_bad_char", "")))


def wmn_exists(site: dict[str, Any], response: httpx.Response) -> bool:
    """Existe si el código y el texto de «existe» coinciden y no aparece el de «no existe»."""
    if response.status_code != site["e_code"]:
        return False
    text = response.text
    if site["e_string"] not in text:
        return False
    return not (site.get("m_string") and site["m_string"] in text)


class UsernameWmn(UsernameSites):
    name = "username_wmn"
    description = "Presencia del username en ~600 sitios (firmas de WhatsMyName)"
    probe_url = "https://github.com"

    def sites(self) -> dict[str, dict[str, Any]]:
        return load_wmn()

    async def _probe(
        self, sem: asyncio.Semaphore, site: dict[str, Any], username: str
    ) -> bool | None:
        account = _account(site, username)
        if not account:
            return None
        url = site["uri_check"].replace(ACCOUNT, quote_segment(account))
        body = site.get("post_body")
        kwargs: dict[str, Any] = {"headers": site.get("headers")}
        if body:
            # Dentro del JSON de la petición, el username va escapado, no codificado como URL.
            kwargs["content"] = body.replace(ACCOUNT, json.dumps(account)[1:-1])
        async with sem:
            try:
                response = await self.ctx.http.request(
                    "POST" if body else "GET",
                    url,
                    follow_redirects=False,
                    timeout=TIMEOUT,
                    **kwargs,
                )
            except (httpx.HTTPError, ValueError, NetworkGuardError):
                return None
        return wmn_exists(site, response)

    async def _check(
        self, sem: asyncio.Semaphore, name: str, site: dict[str, Any], username: str
    ) -> str | None:
        if await self._probe(sem, site, username):
            template = site.get("uri_pretty") or site["uri_check"]
            return template.replace(ACCOUNT, quote_segment(_account(site, username)))
        return None

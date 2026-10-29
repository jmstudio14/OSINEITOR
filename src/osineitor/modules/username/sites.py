"""Búsqueda del username en cientos de sitios usando las firmas de Sherlock."""

from __future__ import annotations

import asyncio
import json
import re
import secrets
from functools import cache
from importlib import resources
from typing import Any

import httpx

from osineitor.errors import BudgetExceeded, NetworkGuardError
from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module
from osineitor.sanitize import quote_segment

CONCURRENCY = 30
TIMEOUT = 15


@cache
def load_sites(include_nsfw: bool = False) -> dict[str, dict[str, Any]]:
    raw = resources.files(__package__).joinpath("data/sites.json").read_text(encoding="utf-8")
    sites = json.loads(raw)
    return {k: v for k, v in sites.items() if include_nsfw or not v.get("isNSFW")}


def _fill(value: Any, username: str) -> Any:
    """Sustituye `{}` por el username en strings anidados del payload."""
    if isinstance(value, str):
        return value.replace("{}", username)
    if isinstance(value, dict):
        return {k: _fill(v, username) for k, v in value.items()}
    if isinstance(value, list):
        return [_fill(v, username) for v in value]
    return value


def _as_list(value: Any) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def build_urls(site: dict[str, Any], username: str) -> tuple[str, str]:
    """URL del perfil y URL que se consulta, con el username codificado como un solo segmento."""
    safe = quote_segment(username)
    if "{}" in site["url"]:
        profile_url = site["url"].replace("{}", safe)
    else:  # sitios que solo exponen una API de comprobación (p. ej. Discord)
        profile_url = f"{site['url'].rstrip('/')}#{safe}"
    probe_url = site.get("urlProbe", site["url"]).replace("{}", safe)
    return profile_url, probe_url


def profile_exists(site: dict[str, Any], response: httpx.Response) -> bool:
    error_type = site.get("errorType", "status_code")
    error_codes = set(_as_list(site.get("errorCode")))
    if response.status_code in error_codes:
        return False
    if error_type == "message":
        # 403/429 suelen ser un WAF o rate limit, no un perfil: resultado desconocido.
        if response.status_code in (403, 429) or response.status_code >= 500:
            return False
        return not any(m in response.text for m in _as_list(site["errorMsg"]))
    # "status_code" y "response_url" (sin seguir redirecciones): 2xx = existe
    return 200 <= response.status_code < 300


class UsernameSites(Module):
    name = "username_sites"
    description = "Presencia del username en ~460 sitios (firmas de Sherlock)"
    consumes = frozenset({EntityType.USERNAME})
    timeout = 400.0  # ~460 sitios con 30 en paralelo
    cache_ttl = 0  # el resultado depende del username: no tiene sentido cachearlo
    probe_url = "https://github.com"  # sin canario: 460 peticiones no son una prueba de salud
    produces = frozenset({EntityType.PROFILE})

    def sites(self) -> dict[str, dict[str, Any]]:
        return load_sites()

    async def _probe(
        self, sem: asyncio.Semaphore, site: dict[str, Any], username: str
    ) -> bool | None:
        """¿Existe el perfil? `None` = desconocido (sitio caído, bloqueado o firma no aplicable)."""
        regex = site.get("regexCheck")
        if regex and not re.search(regex, username):
            return None
        _, probe_url = build_urls(site, username)
        method = site.get("request_method", "GET")
        payload = _fill(site.get("request_payload"), username)
        async with sem:
            try:
                response = await self.ctx.http.request(
                    method,
                    probe_url,
                    headers=site.get("headers"),
                    json=payload,
                    follow_redirects=site.get("errorType") != "response_url",
                    timeout=TIMEOUT,
                )
            except (httpx.HTTPError, ValueError, NetworkGuardError):
                return None
        return profile_exists(site, response)

    async def _check(
        self, sem: asyncio.Semaphore, name: str, site: dict[str, Any], username: str
    ) -> str | None:
        if await self._probe(sem, site, username):
            return build_urls(site, username)[0]
        return None

    async def run(self, entity: Entity) -> list[Entity]:
        username = entity.value.strip()
        sites = self.sites()
        sem = asyncio.Semaphore(CONCURRENCY)
        names = list(sites)
        outcomes = await asyncio.gather(
            *(self._check(sem, n, sites[n], username) for n in names), return_exceptions=True
        )
        found: dict[str, str] = {}
        for name, outcome in zip(names, outcomes, strict=True):
            # Si se agota el presupuesto se conserva lo ya encontrado; el motor marca el resultado.
            if isinstance(outcome, BaseException) and not isinstance(outcome, BudgetExceeded):
                raise outcome
            if isinstance(outcome, str):
                found[name] = outcome
        verified = await self._verify(sem, sites, found)
        return [
            self.emit(
                entity,
                EntityType.PROFILE,
                url,
                site=name,
                username=username,
                verified=verified[name],
            )
            for name, url in found.items()
            if verified[name] is not False
        ]

    async def _verify(
        self, sem: asyncio.Semaphore, sites: dict[str, dict[str, Any]], found: dict[str, str]
    ) -> dict[str, bool | None]:
        """Comprueba cada positivo con un username que no existe.

        Si el sitio también «encuentra» ese username, la firma está dando falsos positivos y el
        hallazgo se descarta (`False`). `True` = el sitio distingue; `None` = no se pudo comprobar
        (la firma rechaza el username de control o la petición falló) y el hallazgo se conserva.
        Solo se hace sobre los positivos, así que cuesta pocas peticiones.
        """
        control = "x" + secrets.token_hex(7)

        async def one(name: str) -> bool | None:
            try:
                exists = await self._probe(sem, sites[name], control)
            except BudgetExceeded:
                return None
            return None if exists is None else not exists

        results = await asyncio.gather(*(one(n) for n in found))
        return dict(zip(found, results, strict=True))

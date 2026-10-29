"""Cliente HTTP compartido: guardia de red, redirecciones controladas, reintentos y límites."""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from typing import Any

import httpx

from osineitor import netguard
from osineitor.budget import Budget
from osineitor.config import Config

RETRY_STATUS = {429, 500, 502, 503, 504}
MAX_REDIRECTS = 10
GUARD_TTL = 60.0  # segundos que se recuerda que un host ya se comprobó


class HttpClient:
    def __init__(
        self,
        config: Config,
        *,
        per_host: int = 4,
        retries: int = 2,
        backoff: float = 1.0,
        transport: httpx.AsyncBaseTransport | None = None,
        allow_private: bool = False,
        budget: Budget | None = None,
    ) -> None:
        # Las redirecciones las sigue `request()` para poder comprobar cada salto.
        self._client = httpx.AsyncClient(
            timeout=config.timeout,
            headers={"User-Agent": config.user_agent},
            follow_redirects=False,
            transport=transport,
        )
        self._host_limits: dict[str, asyncio.Semaphore] = defaultdict(
            lambda: asyncio.Semaphore(per_host)
        )
        self._retries = retries
        self._backoff = backoff
        self._guard = not allow_private
        self._safe_hosts: dict[str, float] = {}
        self.budget = budget

    async def _check(self, url: str) -> None:
        if not self._guard:
            return
        host = httpx.URL(url).host
        now = time.monotonic()
        if self._safe_hosts.get(host, 0.0) > now:
            return
        await netguard.ensure_public(url)
        self._safe_hosts[host] = now + GUARD_TTL

    async def _send(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        host = httpx.URL(url).host
        attempt = 0
        while True:
            if self.budget:
                self.budget.charge_request()
            try:
                async with self._host_limits[host]:
                    response = await self._client.request(method, url, **kwargs)
                if response.status_code not in RETRY_STATUS or attempt >= self._retries:
                    return response
            except httpx.TransportError:
                if attempt >= self._retries:
                    raise
            attempt += 1
            await asyncio.sleep(self._backoff * 2 ** (attempt - 1))

    async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        follow = kwargs.pop("follow_redirects", True)
        hops = 0
        while True:
            await self._check(url)
            response = await self._send(method, url, **kwargs)
            location = response.headers.get("location")
            if not (follow and location and response.is_redirect):
                return response
            hops += 1
            if hops > MAX_REDIRECTS:
                raise httpx.TooManyRedirects("demasiadas redirecciones", request=response.request)
            target = response.url.join(location)
            if response.status_code in (301, 302, 303) and method.upper() not in ("GET", "HEAD"):
                method = "GET"
                for body in ("json", "data", "content", "files"):
                    kwargs.pop(body, None)
            origin = (response.url.scheme, response.url.host, response.url.port)
            if (target.scheme, target.host, target.port) != origin:
                kwargs.pop("headers", None)  # no se reenvían claves a otro origen
            kwargs.pop("params", None)  # el Location ya trae su consulta completa
            url = str(target)

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("POST", url, **kwargs)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> HttpClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

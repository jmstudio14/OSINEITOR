"""Cliente HTTP compartido: timeouts, reintentos y límite de concurrencia por host."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any

import httpx

from osineitor.config import Config

RETRY_STATUS = {429, 500, 502, 503, 504}


class HttpClient:
    def __init__(
        self,
        config: Config,
        *,
        per_host: int = 4,
        retries: int = 2,
        backoff: float = 1.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            timeout=config.timeout,
            headers={"User-Agent": config.user_agent},
            follow_redirects=True,
            transport=transport,
        )
        self._host_limits: dict[str, asyncio.Semaphore] = defaultdict(
            lambda: asyncio.Semaphore(per_host)
        )
        self._retries = retries
        self._backoff = backoff

    async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        host = httpx.URL(url).host
        attempt = 0
        while True:
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

"""Cliente HTTP compartido: guardia de red, redirecciones controladas, reintentos y límites."""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

import httpx

from osineitor import logs, netguard
from osineitor.budget import Budget
from osineitor.cache import ResponseCache, cache_key
from osineitor.config import Config
from osineitor.evidence import capture
from osineitor.models import Evidence

log = logs.get("http")

RETRY_STATUS = {429, 500, 502, 503, 504}
MAX_REDIRECTS = 10
GUARD_TTL = 60.0  # segundos que se recuerda que un host ya se comprobó


def validate_proxy(value: str) -> str:
    """Devuelve la URL del proxy si es `http(s)`/`socks5(h)` con host; si no, `ValueError`."""
    value = value.strip()
    if not httpx.Proxy(value).url.host:  # httpx ya rechaza los esquemas desconocidos
        raise ValueError(f"el proxy {logs.redact_url(value)!r} no tiene host")
    return value


@dataclass
class RunStats:
    """Contadores de una ejecución de módulo; el motor los fija y `HttpClient` los incrementa."""

    requests: int = 0
    cache_hits: int = 0
    # Con `--evidence` es una lista (el motor la crea); `None` = no se guarda ninguna respuesta.
    evidence: list[Evidence] | None = field(default=None)


# Cada ejecución de módulo corre en su propia tarea: así cada una tiene sus contadores.
current_stats: ContextVar[RunStats | None] = ContextVar("current_stats", default=None)


class SourceHttp:
    """Vista del cliente para un módulo: aplica la caché y el límite de uso de su fuente."""

    def __init__(
        self, client: HttpClient, source: str, *, cache_ttl: int = 0, min_interval: float = 0.0
    ) -> None:
        self._client = client
        self.source = source
        self._cache_ttl = cache_ttl
        self._min_interval = min_interval

    @property
    def proxy(self) -> str | None:
        return self._client.proxy

    async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        return await self._client.request(
            method,
            url,
            source=self.source,
            cache_ttl=self._cache_ttl,
            min_interval=self._min_interval,
            **kwargs,
        )

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("POST", url, **kwargs)


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
        cache: ResponseCache | None = None,
        refresh: bool = False,
        proxy: str | None = None,
    ) -> None:
        self.proxy = proxy
        # Las redirecciones las sigue `request()` para poder comprobar cada salto.
        self._client = httpx.AsyncClient(
            timeout=config.timeout,
            headers={"User-Agent": config.user_agent},
            follow_redirects=False,
            transport=transport,
            proxy=proxy,
        )
        self._host_limits: dict[str, asyncio.Semaphore] = defaultdict(
            lambda: asyncio.Semaphore(per_host)
        )
        self._retries = retries
        self._backoff = backoff
        self._guard = not allow_private
        self._safe_hosts: dict[str, float] = {}
        self.budget = budget
        self._cache = cache
        self._refresh = refresh  # ignora lo cacheado pero sigue guardando lo nuevo
        self._last_call: dict[str, float] = {}
        self._source_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._secrets: list[str] | None = None  # se leen la primera vez que hacen falta

    def bind(self, source: str, *, cache_ttl: int = 0, min_interval: float = 0.0) -> SourceHttp:
        return SourceHttp(self, source, cache_ttl=cache_ttl, min_interval=min_interval)

    async def _throttle(self, source: str, interval: float) -> None:
        """Espera lo necesario para respetar `interval` segundos entre peticiones a la fuente."""
        async with self._source_locks[source]:
            wait = self._last_call.get(source, 0.0) + interval - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_call[source] = time.monotonic()

    async def _check(self, url: str) -> None:
        if not self._guard:
            return
        host = httpx.URL(url).host
        now = time.monotonic()
        if self._safe_hosts.get(host, 0.0) > now:
            return
        await netguard.ensure_public(url, resolve=not self.proxy)
        self._safe_hosts[host] = now + GUARD_TTL

    def _capture(self, method: str, response: httpx.Response) -> None:
        """Guarda la respuesta definitiva de un salto cuando el scan pide evidencias."""
        stats = current_stats.get()
        if stats is None or stats.evidence is None:
            return
        if self._secrets is None:
            self._secrets = logs.known_secrets()
        stats.evidence.append(
            capture(
                "http",
                str(response.url),
                response.content,
                method=method.upper(),
                status=response.status_code,
                secrets=self._secrets,
            )
        )

    async def _send(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        host = httpx.URL(url).host
        source = kwargs.pop("source", None)
        interval = kwargs.pop("min_interval", 0.0)
        attempt = 0
        while True:
            if self.budget:
                self.budget.charge_request()
            if stats := current_stats.get():
                stats.requests += 1
            if source and interval:
                await self._throttle(source, interval)
            started = time.monotonic()
            fields = {"method": method, "url": logs.redact_url(url), "source": source}
            try:
                async with self._host_limits[host]:
                    response = await self._client.request(method, url, **kwargs)
                fields |= {"status": response.status_code, "attempt": attempt}
                fields["ms"] = round((time.monotonic() - started) * 1000)
                log.debug("http", extra={"fields": fields})
                if response.status_code not in RETRY_STATUS or attempt >= self._retries:
                    self._capture(method, response)
                    return response
            except httpx.TransportError as exc:
                fields |= {"error": type(exc).__name__, "attempt": attempt}
                fields["ms"] = round((time.monotonic() - started) * 1000)
                log.warning("http.error", extra={"fields": fields})
                if attempt >= self._retries:
                    raise
            attempt += 1
            await asyncio.sleep(self._backoff * 2 ** (attempt - 1))

    async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        ttl = kwargs.pop("cache_ttl", 0)
        use_cache = bool(ttl) and self._cache is not None and method.upper() == "GET"
        if not use_cache:
            return await self._follow(method, url, **kwargs)
        key = cache_key(url, kwargs.get("params"))
        if not self._refresh and (hit := self._cache.get(key, url)) is not None:
            if stats := current_stats.get():
                stats.cache_hits += 1
            log.debug("http.cache_hit", extra={"fields": {"url": logs.redact_url(url)}})
            return hit
        response = await self._follow(method, url, **kwargs)
        self._cache.put(key, response, ttl)
        return response

    async def _follow(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
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
        if self._cache is not None:
            self._cache.close()

    async def __aenter__(self) -> HttpClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

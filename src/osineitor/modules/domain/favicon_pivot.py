"""Pivote por favicon: hash MurmurHash3 del icono del sitio y otros hosts con el mismo (ACTIVO)."""

from __future__ import annotations

import base64

import httpx

from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module, ModuleError, status_error
from osineitor.modules.domain._util import is_root_domain

MAX_FAVICON = 256 * 1024
MAX_MATCHES = 50
SEARCH = "https://api.shodan.io/shodan/host/search"


def murmur3_32(data: bytes, seed: int = 0) -> int:
    """MurmurHash3 x86 de 32 bits, con signo, como lo calcula la biblioteca `mmh3` de Shodan."""
    c1, c2, mask = 0xCC9E2D51, 0x1B873593, 0xFFFFFFFF
    h = seed & mask
    for i in range(0, len(data) - len(data) % 4, 4):
        k = int.from_bytes(data[i : i + 4], "little")
        k = (k * c1) & mask
        k = ((k << 15) | (k >> 17)) & mask
        h ^= (k * c2) & mask
        h = ((h << 13) | (h >> 19)) & mask
        h = (h * 5 + 0xE6546B64) & mask
    tail = data[len(data) - len(data) % 4 :]
    if tail:
        k = int.from_bytes(tail, "little")
        k = (k * c1) & mask
        k = ((k << 15) | (k >> 17)) & mask
        h ^= (k * c2) & mask
    h ^= len(data)
    h ^= h >> 16
    h = (h * 0x85EBCA6B) & mask
    h ^= h >> 13
    h = (h * 0xC2B2AE35) & mask
    h ^= h >> 16
    return h - (1 << 32) if h & 0x80000000 else h


def favicon_hash(content: bytes) -> int:
    """Valor de `http.favicon.hash`: hash del Base64 con saltos de línea cada 76 caracteres."""
    return murmur3_32(base64.encodebytes(content))


class FaviconPivot(Module):
    name = "favicon_pivot"
    description = "Hosts con el mismo favicon que el sitio, vía Shodan (contacta al objetivo)"
    consumes = frozenset({EntityType.DOMAIN})
    produces = frozenset({EntityType.RECORD, EntityType.IP})
    requires_key = "shodan"
    passive = False
    canary = "example.com"

    def accepts(self, entity: Entity) -> bool:
        return is_root_domain(entity)

    async def _favicon(self, domain: str) -> bytes | None:
        for scheme in ("https", "http"):
            try:
                response = await self.ctx.http.get(f"{scheme}://{domain}/favicon.ico")
            except httpx.TransportError:
                continue
            kind = response.headers.get("content-type", "").lower()
            if response.status_code != 200 or "html" in kind or not response.content:
                return None  # muchos sitios devuelven su portada para una ruta que no existe
            return response.content if len(response.content) <= MAX_FAVICON else None
        raise ModuleError("el sitio no responde por HTTP(S)")

    async def run(self, entity: Entity) -> list[Entity]:
        content = await self._favicon(entity.value)
        if content is None:
            return []
        digest = favicon_hash(content)
        response = await self.ctx.http.get(
            SEARCH, params={"key": self.api_key, "query": f"http.favicon.hash:{digest}"}
        )
        if response.status_code in (401, 403):
            raise ModuleError("API key de Shodan sin acceso a la búsqueda (/shodan/host/search)")
        if response.status_code != 200:
            raise status_error("api.shodan.io", response)
        matches = response.json().get("matches") or []

        ips: dict[str, dict[str, object]] = {}
        for match in matches:
            if ip := match.get("ip_str"):
                ips.setdefault(str(ip), {"ports": [], "hostnames": match.get("hostnames") or []})
                if match.get("port") is not None:
                    ips[str(ip)]["ports"].append(match["port"])  # type: ignore[union-attr]
        out = [
            self.emit(
                entity,
                EntityType.RECORD,
                f"favicon:{entity.value}",
                favicon_hash=digest,
                favicon_bytes=len(content),
                matches=len(ips),
            )
        ]
        for ip, info in list(ips.items())[:MAX_MATCHES]:
            if found := self.try_emit(entity, EntityType.IP, ip, favicon_hash=digest, **info):
                out.append(found)
        return out

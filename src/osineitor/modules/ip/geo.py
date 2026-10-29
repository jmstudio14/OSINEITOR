"""Geolocalización, ASN y hostname de la IP vía ipinfo.io (token opcional)."""

from __future__ import annotations

from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module, ModuleQuota, status_error


class IpInfo(Module):
    name = "ipinfo"
    description = "Geolocalización, organización/ASN y hostname (ipinfo.io)"
    consumes = frozenset({EntityType.IP})
    produces = frozenset({EntityType.RECORD})
    canary = "1.1.1.1"

    async def run(self, entity: Entity) -> list[Entity]:
        # Funciona sin token (cuota limitada); si hay key 'ipinfo' se usa.
        token = self.ctx.config.key("ipinfo")
        params = {"token": token} if token else None
        response = await self.ctx.http.get(f"https://ipinfo.io/{entity.value}/json", params=params)
        if response.status_code == 429:
            raise ModuleQuota("cuota de ipinfo.io agotada (configura la key 'ipinfo')")
        if response.status_code != 200:
            raise status_error("ipinfo.io", response)
        data = response.json()
        if data.get("bogon"):
            return [self.emit(entity, EntityType.RECORD, f"ipinfo:{entity.value}", bogon=True)]
        return [
            self.emit(
                entity,
                EntityType.RECORD,
                f"ipinfo:{entity.value}",
                hostname=data.get("hostname"),
                city=data.get("city"),
                region=data.get("region"),
                country=data.get("country"),
                loc=data.get("loc"),
                org=data.get("org"),
                timezone=data.get("timezone"),
                anycast=data.get("anycast"),
            )
        ]

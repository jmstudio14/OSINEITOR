"""Puertos, CPEs y vulnerabilidades conocidas vía Shodan InternetDB (gratis, sin key)."""

from __future__ import annotations

from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module, status_error


class InternetDb(Module):
    name = "internetdb"
    description = "Puertos abiertos, CPEs, tags y CVEs (Shodan InternetDB, sin key)"
    consumes = frozenset({EntityType.IP})
    produces = frozenset({EntityType.SERVICE, EntityType.VULNERABILITY, EntityType.RECORD})
    canary = "1.1.1.1"

    async def run(self, entity: Entity) -> list[Entity]:
        response = await self.ctx.http.get(f"https://internetdb.shodan.io/{entity.value}")
        if response.status_code == 404:
            return []
        if response.status_code != 200:
            raise status_error("internetdb.shodan.io", response)
        data = response.json()
        out = [
            self.emit(
                entity,
                EntityType.RECORD,
                f"internetdb:{entity.value}",
                hostnames=data.get("hostnames", []),
                tags=data.get("tags", []),
                cpes=data.get("cpes", []),
            )
        ]
        out += [
            self.emit(entity, EntityType.SERVICE, f"{entity.value}:{port}", port=port)
            for port in data.get("ports", [])
        ]
        out += [
            self.emit(entity, EntityType.VULNERABILITY, cve, ip=entity.value)
            for cve in data.get("vulns", [])
        ]
        return out

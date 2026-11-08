"""Inteligencia de amenazas de AlienVault OTX: pulses y DNS pasivo (requiere key gratuita)."""

from __future__ import annotations

import ipaddress
from typing import Any

from osineitor.errors import InvalidEntityValue
from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module, ModuleError, status_error
from osineitor.modules.domain._util import in_domain
from osineitor.normalize import canonical_hostname
from osineitor.sanitize import quote_segment

BASE = "https://otx.alienvault.com/api/v1/indicators"
MAX_ITEMS = 50


class Otx(Module):
    name = "otx"
    description = "Pulses y DNS pasivo de un dominio o IP (AlienVault OTX)"
    consumes = frozenset({EntityType.DOMAIN, EntityType.IP})
    produces = frozenset({EntityType.RECORD, EntityType.DOMAIN, EntityType.IP})
    requires_key = "otx"
    canary = "example.com"
    min_interval = 0.5

    def accepts(self, entity: Entity) -> bool:
        return entity.type == EntityType.IP or (
            entity.type == EntityType.DOMAIN and not entity.data.get("subdomain")
        )

    async def _get(self, path: str) -> dict[str, Any]:
        response = await self.ctx.http.get(
            f"{BASE}/{path}", headers={"X-OTX-API-KEY": self.api_key or ""}
        )
        if response.status_code in (401, 403):
            raise ModuleError("API key de OTX inválida")
        if response.status_code == 404:
            return {}
        if response.status_code != 200:
            raise status_error("otx.alienvault.com", response)
        return response.json()

    async def run(self, entity: Entity) -> list[Entity]:
        if entity.type == EntityType.IP:
            version = ipaddress.ip_address(entity.value).version
            general = await self._get(f"IPv{version}/{quote_segment(entity.value)}/general")
            return self._ip(entity, general)
        return await self._domain(entity)

    def _ip(self, entity: Entity, general: dict[str, Any]) -> list[Entity]:
        pulses = (general.get("pulse_info") or {}).get("count") or 0
        if not pulses:
            return []
        return [
            self.emit(
                entity,
                EntityType.RECORD,
                f"otx:{entity.value}",
                pulses=pulses,
                reputation=general.get("reputation"),
                country=general.get("country_name"),
                asn=general.get("asn"),
            )
        ]

    async def _domain(self, entity: Entity) -> list[Entity]:
        domain = entity.value
        segment = quote_segment(domain)
        general = await self._get(f"domain/{segment}/general")
        passive = (await self._get(f"domain/{segment}/passive_dns")).get("passive_dns") or []
        pulses = (general.get("pulse_info") or {}).get("count") or 0

        hosts: dict[str, None] = {}
        ips: dict[str, None] = {}
        for row in passive:
            try:
                host = canonical_hostname(str(row.get("hostname") or ""))
            except InvalidEntityValue:
                continue
            if not in_domain(host, domain):
                continue
            hosts[host] = None
            if row.get("record_type") in ("A", "AAAA") and row.get("address"):
                ips[str(row["address"])] = None
        if not pulses and not hosts:
            return []
        out = [
            self.emit(
                entity,
                EntityType.RECORD,
                f"otx:{domain}",
                pulses=pulses,
                alexa=general.get("alexa"),
                passive_dns=len(passive),
            )
        ]
        found = [
            self.try_emit(entity, EntityType.DOMAIN, host, subdomain=True)
            for host in list(hosts)[:MAX_ITEMS]
            if host != domain
        ]
        found += [self.try_emit(entity, EntityType.IP, ip) for ip in list(ips)[:MAX_ITEMS]]
        return out + [item for item in found if item]

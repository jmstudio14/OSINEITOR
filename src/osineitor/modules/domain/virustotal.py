"""Reputación, subdominios y resoluciones en VirusTotal (requiere key gratuita)."""

from __future__ import annotations

import ipaddress
from typing import Any

from osineitor.errors import InvalidEntityValue
from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module, ModuleError, status_error
from osineitor.modules.domain._util import in_domain
from osineitor.normalize import canonical_hostname
from osineitor.sanitize import quote_segment

BASE = "https://www.virustotal.com/api/v3"
MAX_SUBDOMAINS = 40


class VirusTotal(Module):
    name = "virustotal"
    description = "Reputación y subdominios de un dominio o IP (VirusTotal)"
    consumes = frozenset({EntityType.DOMAIN, EntityType.IP})
    produces = frozenset({EntityType.RECORD, EntityType.DOMAIN})
    requires_key = "virustotal"
    canary = "example.com"
    # El plan gratuito permite 4 peticiones por minuto (y 500 al día).
    min_interval = 15.0

    def accepts(self, entity: Entity) -> bool:
        return entity.type == EntityType.IP or (
            entity.type == EntityType.DOMAIN and not entity.data.get("subdomain")
        )

    async def _get(self, path: str, **params: str) -> dict[str, Any]:
        response = await self.ctx.http.get(
            f"{BASE}/{path}", params=params, headers={"x-apikey": self.api_key or ""}
        )
        if response.status_code in (401, 403):
            raise ModuleError("API key de VirusTotal inválida o sin acceso")
        if response.status_code == 404:
            return {}
        if response.status_code != 200:
            raise status_error("virustotal.com", response)
        return response.json()

    @staticmethod
    def _summary(attributes: dict[str, Any]) -> dict[str, object]:
        stats = attributes.get("last_analysis_stats") or {}
        return {
            "malicious": stats.get("malicious"),
            "suspicious": stats.get("suspicious"),
            "harmless": stats.get("harmless"),
            "reputation": attributes.get("reputation"),
            "last_analysis": attributes.get("last_analysis_date"),
        }

    async def run(self, entity: Entity) -> list[Entity]:
        if entity.type == EntityType.IP:
            address = str(ipaddress.ip_address(entity.value))
            data = (await self._get(f"ip_addresses/{quote_segment(address)}")).get("data")
            if not data:
                return []
            attrs = data.get("attributes") or {}
            return [
                self.emit(
                    entity,
                    EntityType.RECORD,
                    f"virustotal:{entity.value}",
                    **self._summary(attrs),
                    as_owner=attrs.get("as_owner"),
                    asn=attrs.get("asn"),
                    country=attrs.get("country"),
                )
            ]

        domain = entity.value
        data = (await self._get(f"domains/{quote_segment(domain)}")).get("data")
        if not data:
            return []
        attrs = data.get("attributes") or {}
        out = [
            self.emit(
                entity,
                EntityType.RECORD,
                f"virustotal:{domain}",
                **self._summary(attrs),
                registrar=attrs.get("registrar"),
                categories=sorted(set((attrs.get("categories") or {}).values())),
            )
        ]
        subdomains = await self._get(
            f"domains/{quote_segment(domain)}/subdomains", limit=str(MAX_SUBDOMAINS)
        )
        for item in subdomains.get("data") or []:
            try:
                host = canonical_hostname(str(item.get("id") or ""))
            except InvalidEntityValue:
                continue
            if (
                host != domain
                and in_domain(host, domain)
                and (found := self.try_emit(entity, EntityType.DOMAIN, host, subdomain=True))
            ):
                out.append(found)
        return out

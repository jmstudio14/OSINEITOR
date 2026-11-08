"""Servicios y ASN de la IP en Censys Platform (requiere un token personal)."""

from __future__ import annotations

from typing import Any

from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module, ModuleError, status_error
from osineitor.sanitize import quote_segment

BASE = "https://api.platform.censys.io/v3/global/asset/host"
MAX_SERVICES = 50


class Censys(Module):
    name = "censys"
    description = "Servicios, ASN y país de la IP (Censys Platform)"
    consumes = frozenset({EntityType.IP})
    produces = frozenset({EntityType.RECORD, EntityType.SERVICE})
    requires_key = "censys"
    canary = "1.1.1.1"
    min_interval = 1.0

    async def run(self, entity: Entity) -> list[Entity]:
        headers = {
            "Accept": "application/vnd.censys.api.v3.host.v1+json",
            "Authorization": f"Bearer {self.api_key}",
        }
        # El identificador de organización es opcional: algunas cuentas no lo necesitan.
        if org := self.ctx.config.key("censys_org"):
            headers["X-Organization-ID"] = org
        response = await self.ctx.http.get(f"{BASE}/{quote_segment(entity.value)}", headers=headers)
        if response.status_code == 404:
            return []
        if response.status_code in (401, 403):
            raise ModuleError("token de Censys inválido o sin acceso a la API de la Platform")
        if response.status_code != 200:
            raise status_error("api.platform.censys.io", response)

        host: dict[str, Any] = (response.json().get("result") or {}).get("resource") or {}
        system = host.get("autonomous_system") or {}
        location = host.get("location") or {}
        services = [s for s in host.get("services") or [] if isinstance(s, dict) and s.get("port")]
        out = [
            self.emit(
                entity,
                EntityType.RECORD,
                f"censys:{entity.value}",
                asn=system.get("asn"),
                as_name=system.get("name"),
                bgp_prefix=system.get("bgp_prefix"),
                country=location.get("country") or system.get("country_code"),
                services=len(services),
                hostnames=[
                    n for n in (host.get("dns") or {}).get("reverse_dns", {}).get("names", [])
                ][:20],
            )
        ]
        for svc in services[:MAX_SERVICES]:
            if found := self.try_emit(
                entity,
                EntityType.SERVICE,
                f"{entity.value}:{svc['port']}",
                port=svc["port"],
                transport=svc.get("transport_protocol"),
                service=svc.get("protocol") or svc.get("extended_service_name"),
                product=((svc.get("software") or [{}])[0] or {}).get("product"),
            ):
                out.append(found)
        return out

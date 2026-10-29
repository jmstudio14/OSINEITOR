"""Servicios, banners y vulnerabilidades de la IP vía la API de Shodan (requiere key)."""

from __future__ import annotations

from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module, ModuleError, status_error


class Shodan(Module):
    name = "shodan"
    description = "Servicios con producto/versión, SO y CVEs (API de Shodan)"
    consumes = frozenset({EntityType.IP})
    produces = frozenset({EntityType.SERVICE, EntityType.VULNERABILITY, EntityType.RECORD})
    requires_key = "shodan"
    canary = "1.1.1.1"

    async def run(self, entity: Entity) -> list[Entity]:
        response = await self.ctx.http.get(
            f"https://api.shodan.io/shodan/host/{entity.value}", params={"key": self.api_key}
        )
        if response.status_code == 404:
            return []
        if response.status_code == 401:
            raise ModuleError("API key de Shodan inválida o sin acceso a /shodan/host")
        if response.status_code != 200:
            raise status_error("api.shodan.io", response)
        data = response.json()
        out = [
            self.emit(
                entity,
                EntityType.RECORD,
                f"shodan:{entity.value}",
                org=data.get("org"),
                isp=data.get("isp"),
                asn=data.get("asn"),
                os=data.get("os"),
                hostnames=data.get("hostnames", []),
                country=data.get("country_name"),
                last_update=data.get("last_update"),
            )
        ]
        for svc in data.get("data", []):
            port = svc.get("port")
            out.append(
                self.emit(
                    entity,
                    EntityType.SERVICE,
                    f"{entity.value}:{port}",
                    port=port,
                    transport=svc.get("transport"),
                    product=svc.get("product"),
                    version=svc.get("version"),
                    http_title=(svc.get("http") or {}).get("title"),
                )
            )
        vulns = data.get("vulns") or []
        out += [
            self.emit(entity, EntityType.VULNERABILITY, cve, ip=entity.value)
            for cve in (vulns if isinstance(vulns, list) else list(vulns))
        ]
        return out

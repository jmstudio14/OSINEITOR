"""Escaneos públicos del dominio en urlscan.io: IPs, subdominios y URLs vistas."""

from __future__ import annotations

from osineitor.errors import InvalidEntityValue
from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module, status_error
from osineitor.modules.domain._util import in_domain, is_root_domain
from osineitor.normalize import canonical_hostname

MAX_ITEMS = 20


class Urlscan(Module):
    name = "urlscan"
    description = "Escaneos públicos del dominio en urlscan.io: IPs, subdominios y URLs"
    consumes = frozenset({EntityType.DOMAIN})
    produces = frozenset({EntityType.RECORD, EntityType.IP, EntityType.DOMAIN, EntityType.URL})
    canary = "example.com"
    min_interval = 1.0

    def accepts(self, entity: Entity) -> bool:
        return is_root_domain(entity)

    async def run(self, entity: Entity) -> list[Entity]:
        domain = entity.value
        # La key es opcional (sube la cuota), así que no hay `requires_key`: sin ella no se omite.
        key = self.ctx.config.key("urlscan")
        response = await self.ctx.http.get(
            "https://urlscan.io/api/v1/search/",
            params={"q": f"domain:{domain}", "size": "100"},
            headers={"API-Key": key} if key else {},
        )
        if response.status_code != 200:
            raise status_error("urlscan.io", response)
        results = response.json().get("results") or []

        ips: dict[str, None] = {}
        hosts: dict[str, None] = {}
        urls: dict[str, None] = {}
        countries: dict[str, None] = {}
        times: list[str] = []
        for item in results:
            page, task = item.get("page") or {}, item.get("task") or {}
            try:
                host = canonical_hostname(str(page.get("domain") or ""))
            except InvalidEntityValue:
                continue
            if not in_domain(host, domain):
                continue  # un escaneo ajeno que solo menciona el dominio: no es del objetivo
            hosts[host] = None
            if ip := page.get("ip"):
                ips[str(ip)] = None
            if country := page.get("country"):
                countries[str(country)] = None
            if url := task.get("url"):
                urls[str(url)] = None
            if when := task.get("time"):
                times.append(str(when))
        if not hosts:
            return []

        out = [
            self.emit(
                entity,
                EntityType.RECORD,
                f"urlscan:{domain}",
                scans=len(results),
                first_scan=min(times, default=None),
                last_scan=max(times, default=None),
                countries=sorted(countries),
                hosts=len(hosts),
            )
        ]
        found = [self.try_emit(entity, EntityType.IP, ip) for ip in list(ips)[:MAX_ITEMS]]
        found += [
            self.try_emit(entity, EntityType.DOMAIN, host, subdomain=True)
            for host in list(hosts)[:MAX_ITEMS]
            if host != domain
        ]
        found += [self.try_emit(entity, EntityType.URL, url) for url in list(urls)[:MAX_ITEMS]]
        return out + [item for item in found if item]

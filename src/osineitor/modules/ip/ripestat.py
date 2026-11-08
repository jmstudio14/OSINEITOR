"""ASN, prefijo, país de registro e historial de enrutamiento de la IP (RIPEstat)."""

from __future__ import annotations

import ipaddress
from typing import Any

from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module, ModuleSkipped, status_error

BASE = "https://stat.ripe.net/data"
MAX_ORIGINS = 10


def _history(data: dict[str, Any], prefix: str) -> dict[str, object]:
    """Primera y última vez que RIPEstat vio el prefijo anunciado, y quién lo originó."""
    first, last, origins = None, None, []
    for item in data.get("by_origin", []):
        for entry in item.get("prefixes", []):
            if entry.get("prefix") != prefix:
                continue
            origins.append(f"AS{item.get('origin')}")
            for line in entry.get("timelines", []):
                start, end = line.get("starttime"), line.get("endtime")
                first = min(filter(None, (first, start)), default=None)
                last = max(filter(None, (last, end)), default=None)
    return {"first_seen": first, "last_seen": last, "origins_seen": origins[:MAX_ORIGINS]}


class RipeStat(Module):
    name = "ripestat"
    description = "ASN, prefijo, país de registro e historial de enrutamiento (RIPEstat)"
    consumes = frozenset({EntityType.IP})
    produces = frozenset({EntityType.ASN, EntityType.NETBLOCK, EntityType.RECORD})
    canary = "1.1.1.1"
    min_interval = 0.2

    async def _get(self, call: str, resource: str) -> dict[str, Any]:
        response = await self.ctx.http.get(
            f"{BASE}/{call}/data.json", params={"resource": resource, "sourceapp": "osineitor"}
        )
        if response.status_code != 200:
            raise status_error("stat.ripe.net", response)
        return response.json().get("data") or {}

    async def run(self, entity: Entity) -> list[Entity]:
        if not ipaddress.ip_address(entity.value).is_global:
            raise ModuleSkipped("la IP no es pública: RIPEstat no tiene datos de ella")
        overview = await self._get("prefix-overview", entity.value)
        prefix = overview.get("resource")
        asns = [a for a in overview.get("asns", []) if a.get("asn")]
        if not prefix:
            return []
        geo = await self._get("rir-geo", entity.value)
        country = next(
            (r.get("location") for r in geo.get("located_resources", []) if r.get("location")),
            None,
        )
        history = _history(await self._get("routing-history", prefix), prefix) if asns else {}
        block = overview.get("block") or {}

        out = [
            self.emit(
                entity,
                EntityType.RECORD,
                f"ripestat:{entity.value}",
                prefix=prefix,
                announced=overview.get("announced"),
                asns=[f"AS{a['asn']}" for a in asns],
                holders=[a.get("holder") for a in asns],
                country=country,
                registry=block.get("desc"),
                **history,
            )
        ]
        if netblock := self.try_emit(
            entity,
            EntityType.NETBLOCK,
            prefix,
            announced=overview.get("announced"),
            country=country,
        ):
            out.append(netblock)
        for item in asns:
            if asn := self.try_emit(
                entity, EntityType.ASN, str(item["asn"]), holder=item.get("holder"), prefix=prefix
            ):
                out.append(asn)
        return out

"""Registros DNS del dominio, incluidas políticas SPF y DMARC."""

from __future__ import annotations

import dns.exception
import dns.resolver

from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module

RECORD_TYPES = ("A", "AAAA", "CNAME", "MX", "NS", "TXT", "CAA")


class Dns(Module):
    name = "dns"
    description = "Registros A/AAAA/CNAME/MX/NS/TXT/CAA, SPF y DMARC"
    consumes = frozenset({EntityType.DOMAIN})
    produces = frozenset({EntityType.IP, EntityType.RECORD})

    async def _query(self, name: str, rtype: str) -> list[str]:
        try:
            answer = await self.ctx.resolver.resolve(name, rtype, lifetime=10)
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.NoNameservers):
            return []
        except dns.exception.Timeout:
            return []
        values = []
        for rdata in answer:
            if rtype == "TXT":
                values.append(b"".join(rdata.strings).decode(errors="replace"))
            else:
                values.append(rdata.to_text().rstrip("."))
        return values

    async def run(self, entity: Entity) -> list[Entity]:
        records = {rtype: await self._query(entity.value, rtype) for rtype in RECORD_TYPES}
        records = {k: v for k, v in records.items() if v}
        dmarc = [
            t
            for t in await self._query(f"_dmarc.{entity.value}", "TXT")
            if t.lower().startswith("v=dmarc1")
        ]
        spf = [t for t in records.get("TXT", []) if t.lower().startswith("v=spf1")]
        if not records and not dmarc:
            return []

        out = [
            self.emit(
                entity,
                EntityType.RECORD,
                f"dns:{entity.value}",
                **records,
                SPF=spf[0] if spf else None,
                DMARC=dmarc[0] if dmarc else None,
            )
        ]
        for ip in records.get("A", []) + records.get("AAAA", []):
            out.append(self.emit(entity, EntityType.IP, ip, resolved_from=entity.value))
        return out

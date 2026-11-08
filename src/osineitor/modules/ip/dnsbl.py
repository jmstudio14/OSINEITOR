"""Presencia de la IP en listas negras DNS (DNSBL) de uso gratuito."""

from __future__ import annotations

import asyncio
import ipaddress

import dns.exception
import dns.resolver

from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module, ModuleError, ModuleQuota, ModuleSkipped

ZONES = (
    "zen.spamhaus.org",
    "bl.spamcop.net",
    "dnsbl-1.uceprotect.net",
    "dnsbl.dronebl.org",
)
# Códigos de zen.spamhaus.org que no dicen «listada»: la consulta no se ha podido atender.
SPAMHAUS_ERRORS = {
    "127.255.255.252": "consulta mal formada",
    "127.255.255.254": "consulta desde un resolvedor público o abierto",
    "127.255.255.255": "demasiadas consultas",
}
ZEN_CODES = {
    "127.0.0.2": "SBL",
    "127.0.0.3": "SBL (CSS)",
    "127.0.0.4": "XBL",
    "127.0.0.9": "SBL (DROP)",
    "127.0.0.10": "PBL (ISP)",
    "127.0.0.11": "PBL (Spamhaus)",
}


class Dnsbl(Module):
    name = "dnsbl"
    description = "Listas negras DNS (Spamhaus ZEN, SpamCop, UCEPROTECT nivel 1, DroneBL)"
    consumes = frozenset({EntityType.IP})
    produces = frozenset({EntityType.RECORD})
    canary = "1.1.1.1"
    direct_dns = True

    async def _query(self, ip: str, zone: str) -> list[str] | None:
        """Códigos devueltos por la lista; `[]` si no figura, `None` si no respondió."""
        reverse = ".".join(reversed(ip.split(".")))
        name = f"{reverse}.{zone}"
        try:
            answer = await self.ctx.resolver.resolve(name, "A", lifetime=10)
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer) as exc:
            self.record_evidence(f"dns://{name}/A", type(exc).__name__.upper())
            return []
        except (dns.resolver.NoNameservers, dns.exception.Timeout):
            return None
        codes = [rdata.to_text() for rdata in answer]
        self.record_evidence(f"dns://{name}/A", "\n".join(codes))
        return codes

    async def run(self, entity: Entity) -> list[Entity]:
        address = ipaddress.ip_address(entity.value)
        if address.version != 4:
            raise ModuleSkipped("solo se consultan IPv4")
        if not address.is_global:
            raise ModuleSkipped("la IP no es pública: no se consulta en listas negras")
        results = await asyncio.gather(*(self._query(entity.value, zone) for zone in ZONES))
        if all(r is None for r in results):
            raise ModuleError("el resolvedor DNS no respondió a ninguna lista")

        listed, unanswered = [], []
        for zone, codes in zip(ZONES, results, strict=True):
            if codes is None:
                unanswered.append(zone)
                continue
            for code in codes:
                if zone == "zen.spamhaus.org" and code in SPAMHAUS_ERRORS:
                    # 127.255.255.x no es un «listada»: Spamhaus rechaza al resolvedor, no a la IP.
                    raise ModuleQuota(
                        f"zen.spamhaus.org rechazó la consulta: {SPAMHAUS_ERRORS[code]} "
                        "(necesita un resolvedor propio)"
                    )
                item = {"list": zone, "code": code}
                if zone == "zen.spamhaus.org" and code in ZEN_CODES:
                    item["meaning"] = ZEN_CODES[code]
                listed.append(item)
        if not listed:
            return []
        return [
            self.emit(
                entity,
                EntityType.RECORD,
                f"dnsbl:{entity.value}",
                listed=listed,
                listed_on=sorted({item["list"] for item in listed}),
                unanswered=unanswered,
            )
        ]

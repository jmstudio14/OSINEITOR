"""Hostnames alojados en la misma IP según la API gratuita de HackerTarget."""

from __future__ import annotations

import ipaddress

from osineitor.errors import InvalidEntityValue
from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module, ModuleError, ModuleQuota, ModuleSkipped, status_error
from osineitor.normalize import canonical_hostname

# Una IP con más hostnames es un alojamiento compartido o una CDN: pivotar sobre todos sería
# investigar a terceros sin relación con el objetivo.
MAX_PIVOT = 50
SAMPLE = 20
NO_RECORDS = ("no dns a records found", "no records found")


class ReverseIp(Module):
    name = "reverse_ip"
    description = "Hostnames alojados en la misma IP (HackerTarget, solo fuentes pasivas)"
    consumes = frozenset({EntityType.IP})
    produces = frozenset({EntityType.DOMAIN, EntityType.RECORD})
    probe_url = "https://hackertarget.com"  # la API gratuita admite pocas consultas diarias
    min_interval = 2.0

    async def run(self, entity: Entity) -> list[Entity]:
        if not ipaddress.ip_address(entity.value).is_global:
            raise ModuleSkipped("la IP no es pública: no se envía a un tercero")
        response = await self.ctx.http.get(
            "https://api.hackertarget.com/reverseiplookup/", params={"q": entity.value}
        )
        if response.status_code != 200:
            raise status_error("api.hackertarget.com", response)
        text = response.text.strip()
        # Los errores de la API llegan como texto con código 200.
        if text.lower().startswith("api count exceeded"):
            raise ModuleQuota("api.hackertarget.com agotó la cuota diaria gratuita")
        if text.lower() in NO_RECORDS:
            return []
        if text.lower().startswith("error"):
            raise ModuleError(f"api.hackertarget.com: {text[:100]}")
        hosts: list[str] = []
        for line in text.splitlines():
            try:
                host = canonical_hostname(line.strip())
            except InvalidEntityValue:
                continue
            if host not in hosts:
                hosts.append(host)
        if len(hosts) > MAX_PIVOT:
            return [
                self.emit(
                    entity,
                    EntityType.RECORD,
                    f"reverse_ip:{entity.value}",
                    hostnames=len(hosts),
                    sample=hosts[:SAMPLE],
                )
            ]
        return [self.emit(entity, EntityType.DOMAIN, host, via="reverse_ip") for host in hosts]

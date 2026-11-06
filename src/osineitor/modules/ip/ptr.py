"""Nombre inverso (PTR) de la IP."""

from __future__ import annotations

import ipaddress

import dns.exception
import dns.resolver
import dns.reversename

from osineitor.errors import InvalidEntityValue
from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module, ModuleError, ModuleSkipped
from osineitor.normalize import canonical_hostname


class Ptr(Module):
    name = "ptr"
    authority = "authoritative"
    description = "DNS inverso (PTR) de la IP"
    consumes = frozenset({EntityType.IP})
    produces = frozenset({EntityType.DOMAIN, EntityType.RECORD})
    canary = "1.1.1.1"
    direct_dns = True

    async def run(self, entity: Entity) -> list[Entity]:
        if not ipaddress.ip_address(entity.value).is_global:
            # Una IP privada no tiene PTR público y preguntarlo filtraría la consulta al resolvedor.
            raise ModuleSkipped("la IP no es pública: no se consulta su PTR")
        name = dns.reversename.from_address(entity.value).to_text(omit_final_dot=True)
        try:
            answer = await self.ctx.resolver.resolve(name, "PTR", lifetime=10)
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer) as exc:
            self.record_evidence(f"dns://{name}/PTR", type(exc).__name__.upper())
            return []
        except (dns.resolver.NoNameservers, dns.exception.Timeout) as exc:
            raise ModuleError("el resolvedor DNS no respondió a la consulta PTR") from exc
        hosts = []
        for rdata in answer:
            try:
                hosts.append(canonical_hostname(rdata.to_text()))
            except InvalidEntityValue:
                continue  # el PTR lo controla el dueño de la IP: puede ser basura
        self.record_evidence(f"dns://{name}/PTR", "\n".join(hosts))
        if not hosts:
            return []
        out = [self.emit(entity, EntityType.RECORD, f"ptr:{entity.value}", names=hosts)]
        # Un PTR es un host, no necesariamente un dominio registrable: `subdomain` evita lanzar
        # sobre él RDAP o crt.sh como si fuera el dominio investigado.
        for host in hosts:
            if domain := self.try_emit(
                entity, EntityType.DOMAIN, host, subdomain=True, ptr_of=entity.value
            ):
                out.append(domain)
        return out

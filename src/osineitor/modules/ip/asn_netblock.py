"""De IP a ASN y prefijo (Team Cymru, por DNS) y de ASN a sus prefijos anunciados (RIPEstat)."""

from __future__ import annotations

import ipaddress

import dns.exception
import dns.resolver

from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module, ModuleError, ModuleSkipped, status_error

MAX_PREFIXES = 50
MAX_ASNS = 5
ANNOUNCED = "https://stat.ripe.net/data/announced-prefixes/data.json"


def _origin_name(ip: str) -> str:
    address = ipaddress.ip_address(ip)
    if address.version == 4:
        return ".".join(reversed(ip.split("."))) + ".origin.asn.cymru.com"
    return ".".join(reversed(address.exploded.replace(":", ""))) + ".origin6.asn.cymru.com"


def _fields(txt: str) -> list[str]:
    return [part.strip() for part in txt.split("|")]


class AsnNetblock(Module):
    name = "asn_netblock"
    description = "De IP a ASN y prefijo (Team Cymru) y de ASN a sus prefijos (RIPEstat, máx. 50)"
    consumes = frozenset({EntityType.IP, EntityType.ASN})
    produces = frozenset({EntityType.ASN, EntityType.NETBLOCK})
    canary = "1.1.1.1"
    direct_dns = True  # la consulta a Team Cymru es DNS: con --proxy se omite

    async def _txt(self, name: str) -> list[str]:
        try:
            answer = await self.ctx.resolver.resolve(name, "TXT", lifetime=10)
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer) as exc:
            self.record_evidence(f"dns://{name}/TXT", type(exc).__name__.upper())
            return []
        except (dns.resolver.NoNameservers, dns.exception.Timeout) as exc:
            raise ModuleError("el resolvedor DNS no respondió a Team Cymru") from exc
        values = [b"".join(rdata.strings).decode(errors="replace") for rdata in answer]
        self.record_evidence(f"dns://{name}/TXT", "\n".join(values))
        return values

    async def _holder(self, asn: str) -> str | None:
        """Nombre del titular del AS: último campo de `AS<n>.asn.cymru.com`."""
        for txt in await self._txt(f"AS{asn}.asn.cymru.com"):
            fields = _fields(txt)
            if len(fields) >= 5:
                return fields[-1]
        return None

    async def _from_ip(self, entity: Entity) -> list[Entity]:
        if not ipaddress.ip_address(entity.value).is_global:
            raise ModuleSkipped("la IP no es pública: Team Cymru no tiene datos de ella")
        out: list[Entity] = []
        for txt in await self._txt(_origin_name(entity.value)):
            fields = _fields(txt)
            if len(fields) < 5:
                continue
            asns = [a for a in fields[0].split() if a.isdigit()][:MAX_ASNS]
            prefix, country, registry, allocated = fields[1], fields[2], fields[3], fields[4]
            if block := self.try_emit(
                entity,
                EntityType.NETBLOCK,
                prefix,
                asns=[f"AS{a}" for a in asns],
                country=country,
                registry=registry,
                allocated=allocated,
            ):
                out.append(block)
            for asn in asns:
                if item := self.try_emit(
                    entity,
                    EntityType.ASN,
                    asn,
                    holder=await self._holder(asn),
                    prefix=prefix,
                    country=country,
                    registry=registry,
                ):
                    out.append(item)
        return out

    async def _from_asn(self, entity: Entity) -> list[Entity]:
        number = entity.value.removeprefix("AS")
        response = await self.ctx.http.get(
            ANNOUNCED, params={"resource": entity.value, "sourceapp": "osineitor"}
        )
        if response.status_code != 200:
            raise status_error("stat.ripe.net", response)
        prefixes = set()
        for item in (response.json().get("data") or {}).get("prefixes", []):
            try:
                prefixes.add(ipaddress.ip_network(item["prefix"], strict=False))
            except (KeyError, TypeError, ValueError):
                continue  # dato de un tercero: un prefijo raro no debe perder el resto
        # Los bloques más amplios (prefijo más corto) dicen más del AS que las rutas específicas.
        ordered = sorted(prefixes, key=lambda n: (n.version, n.prefixlen, int(n.network_address)))
        out = [
            block
            for network in ordered[:MAX_PREFIXES]
            if (
                block := self.try_emit(
                    entity, EntityType.NETBLOCK, str(network), asns=[entity.value]
                )
            )
        ]
        # Misma clave que la semilla: se fusiona en ella con el titular y el total anunciado.
        if item := self.try_emit(
            entity,
            EntityType.ASN,
            number,
            holder=await self._holder(number),
            announced_prefixes=len(prefixes),
        ):
            out.append(item)
        return out

    async def run(self, entity: Entity) -> list[Entity]:
        if entity.type == EntityType.ASN:
            return await self._from_asn(entity)
        return await self._from_ip(entity)

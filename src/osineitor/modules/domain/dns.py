"""Registros DNS del dominio, incluidas políticas SPF y DMARC."""

from __future__ import annotations

import secrets

import dns.exception
import dns.resolver

from osineitor.models import Entity, EntityType
from osineitor.modules.base import Context, Module, ModuleError

RECORD_TYPES = ("A", "AAAA", "CNAME", "MX", "NS", "TXT", "CAA")


class Dns(Module):
    name = "dns"
    authority = "authoritative"
    description = "Registros A/AAAA/CNAME/MX/NS/TXT/CAA, SPF y DMARC"
    consumes = frozenset({EntityType.DOMAIN})
    produces = frozenset({EntityType.IP, EntityType.RECORD, EntityType.DOMAIN})
    canary = "example.com"
    direct_dns = True

    def __init__(self, ctx: Context) -> None:
        super().__init__(ctx)
        self._wildcards: dict[str, frozenset[str]] = {}  # zona → IPs de una etiqueta aleatoria

    async def _query(
        self, name: str, rtype: str, refused: set[str] | None = None
    ) -> list[str] | None:
        """Valores del registro; `None` si el resolvedor no pudo responder (≠ «no existe»).

        Si algún servidor contestó REFUSED, añade `rtype` a `refused` para poder distinguirlo de
        un tiempo agotado.
        """
        try:
            answer = await self.ctx.resolver.resolve(name, rtype, lifetime=10)
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer) as exc:
            self.record_evidence(f"dns://{name}/{rtype}", type(exc).__name__.upper())
            return []
        except dns.resolver.NoNameservers as exc:
            if refused is not None and any(
                err[3] == "REFUSED" for err in exc.kwargs.get("errors", [])
            ):
                refused.add(rtype)
            return None
        except dns.exception.Timeout:
            return None
        values = []
        for rdata in answer:
            if rtype == "TXT":
                values.append(b"".join(rdata.strings).decode(errors="replace"))
            else:
                values.append(rdata.to_text().rstrip("."))
        self.record_evidence(f"dns://{name}/{rtype}", "\n".join(values))
        return values

    async def _wildcard_addresses(self, zone: str) -> frozenset[str]:
        """IPs a las que resuelve una etiqueta aleatoria de `zone`: vacío si no hay wildcard.

        Se sondea una vez por zona y escaneo: un subdominio que resuelve solo a esas IPs no
        demuestra que exista.
        """
        if zone not in self._wildcards:
            probe = f"osineitor-{secrets.token_hex(8)}.{zone}"
            found: set[str] = set()
            for rtype in ("A", "AAAA"):
                found.update(await self._query(probe, rtype) or [])
            self._wildcards[zone] = frozenset(found)
        return self._wildcards[zone]

    async def run(self, entity: Entity) -> list[Entity]:
        refused: set[str] = set()
        answers = {rtype: await self._query(entity.value, rtype, refused) for rtype in RECORD_TYPES}
        if all(v is None for v in answers.values()):
            # Sin esto, un resolvedor caído se confundiría con «el dominio no tiene registros».
            if refused:
                raise ModuleError(
                    f"el resolvedor DNS rechazó la consulta de {entity.value} (REFUSED); "
                    "algo en la red puede estar filtrando ese nombre"
                )
            raise ModuleError("el resolvedor DNS no respondió (tiempo agotado o sin servidores)")
        records = {k: v for k, v in answers.items() if v}
        dmarc = [
            t
            for t in await self._query(f"_dmarc.{entity.value}", "TXT") or []
            if t.lower().startswith("v=dmarc1")
        ]
        spf = [t for t in records.get("TXT", []) if t.lower().startswith("v=spf1")]
        if not records and not dmarc:
            return []

        addresses = records.get("A", []) + records.get("AAAA", [])
        wildcard = False
        if entity.data.get("subdomain") and addresses:
            zone = entity.value.split(".", 1)[1]
            wild = await self._wildcard_addresses(zone)
            wildcard = bool(wild) and set(addresses) <= wild

        out = [
            self.emit(
                entity,
                EntityType.RECORD,
                f"dns:{entity.value}",
                **records,
                SPF=spf[0] if spf else None,
                DMARC=dmarc[0] if dmarc else None,
                wildcard=True if wildcard else None,
            )
        ]
        if wildcard:
            # Se marca el propio subdominio (el motor funde los datos) y no se pivota a las IPs
            # del wildcard: no dicen nada del objetivo y cada una costaría consultas a terceros.
            out.append(self.emit(entity, EntityType.DOMAIN, entity.value, wildcard=True))
            return out
        for ip in addresses:
            out.append(self.emit(entity, EntityType.IP, ip, resolved_from=entity.value))
        return out

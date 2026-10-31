"""Datos de registro del dominio vía RDAP (el sucesor estructurado de WHOIS)."""

from __future__ import annotations

from typing import Any

from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module, ModuleSkipped, status_error
from osineitor.modules.domain._bootstrap import rdap_tlds
from osineitor.modules.domain._util import is_root_domain

CONTACT_ROLES = {"registrant", "administrative", "technical"}


def _vcard(entity: dict[str, Any]) -> dict[str, str]:
    fields: dict[str, str] = {}
    vcard = entity.get("vcardArray") or [None, []]
    for item in vcard[1] if len(vcard) > 1 else []:
        name, _params, _type, value = item[:4]
        if name in {"fn", "email", "org", "tel"} and value:
            fields.setdefault(name, value if isinstance(value, str) else str(value))
    return fields


class Rdap(Module):
    name = "rdap"
    authority = "authoritative"
    description = "Registrador, fechas, estado y nameservers vía RDAP (rdap.org)"
    consumes = frozenset({EntityType.DOMAIN})
    produces = frozenset({EntityType.RECORD, EntityType.EMAIL})
    canary = "example.com"

    def accepts(self, entity: Entity) -> bool:
        return is_root_domain(entity)

    async def run(self, entity: Entity) -> list[Entity]:
        tld = entity.value.rsplit(".", 1)[-1]
        tlds = await rdap_tlds(self.ctx.http)
        if tlds is not None and tld not in tlds:
            raise ModuleSkipped(
                f"el TLD .{tld} no tiene servidor RDAP según IANA "
                "(ver docs/RDAP_COBERTURA.md; algunos los cubre el módulo whois)"
            )
        response = await self.ctx.http.get(f"https://rdap.org/domain/{entity.value}")
        if response.status_code == 404:
            return []
        if response.status_code != 200:
            raise status_error("rdap.org", response)
        data = response.json()

        events = {e.get("eventAction"): e.get("eventDate") for e in data.get("events", [])}
        registrar = None
        contacts = []
        for ent in data.get("entities", []):
            roles = set(ent.get("roles", []))
            card = _vcard(ent)
            if "registrar" in roles:
                registrar = card.get("fn")
            elif roles & CONTACT_ROLES and card:
                contacts.append({"roles": sorted(roles), **card})

        out = [
            self.emit(
                entity,
                EntityType.RECORD,
                f"rdap:{entity.value}",
                registrar=registrar,
                created=events.get("registration"),
                expires=events.get("expiration"),
                updated=events.get("last changed"),
                status=data.get("status", []),
                nameservers=[
                    n["ldhName"].lower() for n in data.get("nameservers", []) if n.get("ldhName")
                ],
                dnssec=data.get("secureDNS", {}).get("delegationSigned"),
                contacts=contacts,
            )
        ]
        for contact in contacts:
            if "@" in contact.get("email", ""):
                email = self.try_emit(
                    entity, EntityType.EMAIL, contact["email"], roles=contact["roles"]
                )
                if email:
                    out.append(email)
        return out

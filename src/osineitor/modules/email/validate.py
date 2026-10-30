"""Validación del email (sintaxis, MX, desechable) y pivote a dominio y username."""

from __future__ import annotations

import re

import dns.exception
import dns.resolver

from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module
from osineitor.sanitize import is_valid_username

EMAIL_RE = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@([A-Za-z0-9-]+\.)+[A-Za-z]{2,}$")
FREE_PROVIDERS = {
    "gmail.com",
    "googlemail.com",
    "outlook.com",
    "hotmail.com",
    "hotmail.es",
    "live.com",
    "msn.com",
    "yahoo.com",
    "yahoo.es",
    "icloud.com",
    "me.com",
    "aol.com",
    "proton.me",
    "protonmail.com",
    "gmx.com",
    "gmx.es",
    "zoho.com",
    "yandex.com",
    "mail.com",
    "tutanota.com",
}
DISPOSABLE = {
    "mailinator.com",
    "guerrillamail.com",
    "10minutemail.com",
    "temp-mail.org",
    "yopmail.com",
    "trashmail.com",
    "sharklasers.com",
    "getnada.com",
    "dispostable.com",
    "maildrop.cc",
}


class EmailValidate(Module):
    name = "email_validate"
    authority = "authoritative"
    description = "Sintaxis, MX y proveedor desechable; pivota a dominio y username"
    consumes = frozenset({EntityType.EMAIL})
    produces = frozenset({EntityType.RECORD, EntityType.DOMAIN, EntityType.USERNAME})
    canary = "test@example.com"
    direct_dns = True

    async def run(self, entity: Entity) -> list[Entity]:
        email = entity.value.strip().lower()
        if not EMAIL_RE.match(email):
            return [self.emit(entity, EntityType.RECORD, f"email:{email}", valid_syntax=False)]
        local, domain = email.rsplit("@", 1)
        try:
            answer = await self.ctx.resolver.resolve(domain, "MX", lifetime=10)
            mx = sorted(r.exchange.to_text().rstrip(".") for r in answer)
            self.record_evidence(f"dns://{domain}/MX", "\n".join(mx))
        except (
            dns.resolver.NXDOMAIN,
            dns.resolver.NoAnswer,
            dns.resolver.NoNameservers,
            dns.exception.Timeout,
        ) as exc:
            if isinstance(exc, dns.resolver.NXDOMAIN | dns.resolver.NoAnswer):
                self.record_evidence(f"dns://{domain}/MX", type(exc).__name__.upper())
            mx = []

        out = [
            self.emit(
                entity,
                EntityType.RECORD,
                f"email:{email}",
                valid_syntax=True,
                mx=mx,
                accepts_mail=bool(mx),
                free_provider=domain in FREE_PROVIDERS,
                disposable=domain in DISPOSABLE,
            )
        ]
        if domain not in FREE_PROVIDERS and domain not in DISPOSABLE:
            out.append(self.emit(entity, EntityType.DOMAIN, domain))
        # La parte local suele reutilizarse como username (sin el sufijo +etiqueta).
        handle = local.split("+", 1)[0]
        if len(handle) >= 3 and is_valid_username(handle):
            out.append(self.emit(entity, EntityType.USERNAME, handle, derived_from_email=True))
        return out

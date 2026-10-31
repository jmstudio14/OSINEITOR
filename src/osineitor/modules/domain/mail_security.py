"""MTA-STS, TLS-RPT, BIMI y selectores DKIM comunes, solo con consultas DNS."""

from __future__ import annotations

import asyncio

import dns.exception
import dns.resolver

from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module, ModuleError
from osineitor.modules.domain._util import is_root_domain

# Selectores DKIM de uso muy extendido: DKIM no se puede enumerar, solo comprobar nombres conocidos.
DKIM_SELECTORS = (
    "default",
    "google",
    "selector1",
    "selector2",
    "k1",
    "k2",
    "mail",
    "dkim",
    "s1",
    "s2",
    "smtp",
    "mandrill",
    "mxvault",
    "everlytickey1",
    "scph1118",
)


class MailSecurity(Module):
    name = "mail_security"
    authority = "authoritative"
    description = "MTA-STS, TLS-RPT, BIMI y selectores DKIM comunes (solo DNS)"
    consumes = frozenset({EntityType.DOMAIN})
    produces = frozenset({EntityType.RECORD})
    canary = "example.com"
    direct_dns = True

    def accepts(self, entity: Entity) -> bool:
        return is_root_domain(entity)

    async def _txt(self, name: str) -> list[str] | None:
        """Valores TXT; `None` si el resolvedor no pudo responder (≠ «no existe»)."""
        try:
            answer = await self.ctx.resolver.resolve(name, "TXT", lifetime=10)
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer) as exc:
            self.record_evidence(f"dns://{name}/TXT", type(exc).__name__.upper())
            return []
        except (dns.resolver.NoNameservers, dns.exception.Timeout):
            return None
        values = [b"".join(rdata.strings).decode(errors="replace") for rdata in answer]
        self.record_evidence(f"dns://{name}/TXT", "\n".join(values))
        return values

    async def run(self, entity: Entity) -> list[Entity]:
        domain = entity.value
        policies = {
            "MTA_STS": (f"_mta-sts.{domain}", "v=stsv1"),
            "TLS_RPT": (f"_smtp._tls.{domain}", "v=tlsrptv1"),
            "BIMI": (f"default._bimi.{domain}", "v=bimi1"),
        }
        names = [name for name, _ in policies.values()]
        names += [f"{selector}._domainkey.{domain}" for selector in DKIM_SELECTORS]
        results = await asyncio.gather(*(self._txt(name) for name in names))
        if all(r is None for r in results):
            # Un resolvedor caído no es «el dominio no tiene estas políticas».
            raise ModuleError("el resolvedor DNS no respondió (tiempo agotado o sin servidores)")
        answers = dict(zip(names, results, strict=True))

        found = {
            key: next((t for t in answers[name] or [] if t.lower().startswith(prefix)), None)
            for key, (name, prefix) in policies.items()
        }
        # `v=DKIM1` es opcional en una clave DKIM; lo que la define es el parámetro `p=`.
        dkim = [
            selector
            for selector in DKIM_SELECTORS
            if any("p=" in t.lower() for t in answers[f"{selector}._domainkey.{domain}"] or [])
        ]
        if not dkim and not any(found.values()):
            return []
        return [self.emit(entity, EntityType.RECORD, f"mail_security:{domain}", **found, DKIM=dkim)]

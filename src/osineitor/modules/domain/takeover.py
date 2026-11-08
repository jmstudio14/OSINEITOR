"""Subdominios con CNAME a un servicio donde el recurso ya no está reclamado (módulo ACTIVO).

Solo detecta: nunca intenta reclamar el recurso.
"""

from __future__ import annotations

import dns.exception
import dns.resolver
import httpx

from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module, ModuleError

SIGNATURES_VERSION = 1
MAX_BODY = 200_000
# (servicio, sufijos del CNAME, textos de «recurso sin reclamar» en minúsculas). Sin textos, solo
# cuenta que el destino del CNAME ya no exista.
SIGNATURES = (
    ("GitHub Pages", (".github.io",), ("there isn't a github pages site here",)),
    ("Heroku", (".herokuapp.com", ".herokudns.com"), ("no such app",)),
    (
        "Amazon S3",
        (".s3.amazonaws.com",),
        ("nosuchbucket", "the specified bucket does not exist"),
    ),
    ("Shopify", (".myshopify.com",), ("sorry, this shop is currently unavailable",)),
    ("Fastly", (".fastly.net",), ("fastly error: unknown domain",)),
    ("Zendesk", (".zendesk.com",), ("help center closed",)),
    ("Surge", (".surge.sh",), ("project not found",)),
    ("Bitbucket", (".bitbucket.io",), ("repository not found",)),
    ("Ghost", (".ghost.io",), ("the thing you were looking for is no longer here",)),
    ("Pantheon", (".pantheonsite.io",), ("404 error unknown site",)),
    (
        "Tumblr",
        (".tumblr.com",),
        ("whatever you were looking for doesn't currently exist at this address",),
    ),
    (
        "Microsoft Azure",
        (
            ".azurewebsites.net",
            ".cloudapp.net",
            ".cloudapp.azure.com",
            ".trafficmanager.net",
            ".blob.core.windows.net",
            ".azureedge.net",
        ),
        (),
    ),
)


class Takeover(Module):
    name = "takeover"
    authority = "authoritative"
    description = "Subdominios con CNAME a un servicio sin reclamar (contacta al objetivo)"
    consumes = frozenset({EntityType.DOMAIN})
    produces = frozenset({EntityType.RECORD})
    passive = False
    direct_dns = True
    canary = "example.com"

    async def _cname(self, name: str) -> str | None:
        try:
            answer = await self.ctx.resolver.resolve(name, "CNAME", lifetime=10)
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
            return None
        except (dns.resolver.NoNameservers, dns.exception.Timeout) as exc:
            raise ModuleError("el resolvedor DNS no respondió a la consulta CNAME") from exc
        target = next(iter(answer), None)
        if target is None:
            return None
        self.record_evidence(f"dns://{name}/CNAME", target.to_text().rstrip("."))
        return target.to_text().rstrip(".").lower()

    async def _dangling(self, target: str) -> bool:
        """True si el destino del CNAME no existe (NXDOMAIN); un fallo del resolvedor no cuenta."""
        try:
            await self.ctx.resolver.resolve(target, "A", lifetime=10)
        except dns.resolver.NXDOMAIN:
            self.record_evidence(f"dns://{target}/A", "NXDOMAIN")
            return True
        except (dns.resolver.NoAnswer, dns.resolver.NoNameservers, dns.exception.Timeout):
            return False
        return False

    async def _unclaimed_page(self, host: str, texts: tuple[str, ...]) -> bool:
        for scheme in ("https", "http"):
            try:
                response = await self.ctx.http.get(f"{scheme}://{host}/")
            except httpx.TransportError:
                continue
            body = response.text[:MAX_BODY].lower()
            return any(text in body for text in texts)
        return False

    async def run(self, entity: Entity) -> list[Entity]:
        target = await self._cname(entity.value)
        if target is None:
            return []
        for service, suffixes, texts in SIGNATURES:
            if not any(target.endswith(suffix) for suffix in suffixes):
                continue
            evidence = []
            if await self._dangling(target):
                evidence.append("el CNAME apunta a un nombre que no existe (NXDOMAIN)")
            if texts and await self._unclaimed_page(entity.value, texts):
                evidence.append("la página responde con el mensaje de recurso sin reclamar")
            if not evidence:
                return []
            return [
                self.emit(
                    entity,
                    EntityType.RECORD,
                    f"takeover:{entity.value}",
                    service=service,
                    cname=target,
                    evidence=evidence,
                    signatures=SIGNATURES_VERSION,
                )
            ]
        return []

"""CDN y nube de un dominio, deducidos de su CNAME y de la huella HTTP ya recogidos."""

from __future__ import annotations

from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module

SIGNATURES_VERSION = 1
# (proveedor, categoría, sufijos del CNAME)
CNAME_SIGNATURES = (
    ("Amazon CloudFront", "cdn", (".cloudfront.net",)),
    ("Cloudflare", "cdn", (".cdn.cloudflare.net", ".cloudflare.net")),
    ("Akamai", "cdn", (".akamaiedge.net", ".akamai.net", ".edgekey.net", ".edgesuite.net")),
    ("Fastly", "cdn", (".fastly.net",)),
    ("Azure CDN", "cdn", (".azureedge.net",)),
    ("Azure Front Door", "cdn", (".azurefd.net",)),
    ("Imperva", "cdn", (".incapdns.net",)),
    ("Sucuri", "cdn", (".sucuri.net",)),
    ("Bunny CDN", "cdn", (".b-cdn.net",)),
    ("StackPath", "cdn", (".stackpathdns.com",)),
    ("AWS Elastic Load Balancing", "cloud", (".elb.amazonaws.com",)),
    ("Amazon S3", "cloud", (".s3.amazonaws.com",)),
    ("Azure Traffic Manager", "cloud", (".trafficmanager.net",)),
    ("Azure App Service", "cloud", (".azurewebsites.net",)),
    ("Google App Engine", "cloud", (".appspot.com", ".ghs.googlehosted.com")),
    ("Heroku", "cloud", (".herokuapp.com", ".herokudns.com")),
    ("Vercel", "cloud", (".vercel-dns.com", ".vercel.app")),
    ("Netlify", "cloud", (".netlify.app", ".netlify.com")),
    ("GitHub Pages", "cloud", (".github.io",)),
)
# Tecnologías de `http_fingerprint` que son un CDN o una nube.
HTTP_TECHNOLOGIES = {
    "Cloudflare": "cdn",
    "Akamai": "cdn",
    "AWS CloudFront": "cdn",
    "Vercel": "cloud",
    "Netlify": "cloud",
}
PROVIDER_NAMES = {"AWS CloudFront": "Amazon CloudFront"}


class CloudAttribution(Module):
    name = "cloud_attribution"
    description = "CDN y nube deducidos del CNAME y de la huella HTTP ya recogidos"
    consumes = frozenset({EntityType.RECORD})
    produces = frozenset({EntityType.TECHNOLOGY})
    analyzer = True
    canary = "example.com"

    def accepts(self, entity: Entity) -> bool:
        return entity.type == EntityType.RECORD and entity.value.startswith(("dns:", "http:"))

    async def run(self, entity: Entity) -> list[Entity]:
        found: dict[str, tuple[str, list[str]]] = {}

        def add(provider: str, category: str, evidence: str) -> None:
            found.setdefault(provider, (category, []))[1].append(evidence)

        if entity.value.startswith("dns:"):
            for target in entity.data.get("CNAME", []):
                host = target.lower().rstrip(".")
                for provider, category, suffixes in CNAME_SIGNATURES:
                    if any(host.endswith(suffix) for suffix in suffixes):
                        add(provider, category, f"CNAME {host}")
        else:
            for tech in entity.data.get("technologies", []):
                if category := HTTP_TECHNOLOGIES.get(tech):
                    add(PROVIDER_NAMES.get(tech, tech), category, "huella HTTP")
        return [
            self.emit(
                entity,
                EntityType.TECHNOLOGY,
                provider,
                category=category,
                evidence=sorted(set(evidence)),
                signatures=SIGNATURES_VERSION,
            )
            for provider, (category, evidence) in sorted(found.items())
        ]

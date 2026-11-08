"""CDN y nube de un dominio (por su CNAME y su huella HTTP) y de una IP (por los rangos del
proveedor que instala `osineitor update-data`), todo a partir de lo ya recogido."""

from __future__ import annotations

import ipaddress
import json

from osineitor import datasets
from osineitor.models import Entity, EntityType
from osineitor.modules.base import Context, Module

Network = ipaddress.IPv4Network | ipaddress.IPv6Network
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
# (proveedor, categoría, datasets de `update-data` con sus rangos de IP)
RANGE_DATASETS = (
    ("Amazon Web Services", "cloud", ("aws-ip-ranges",)),
    ("Google Cloud", "cloud", ("gcp-ip-ranges",)),
    ("Microsoft Azure", "cloud", ("azure-ip-ranges",)),
    ("Cloudflare", "cdn", ("cloudflare-ips-v4", "cloudflare-ips-v6")),
)


class CloudAttribution(Module):
    name = "cloud_attribution"
    description = "CDN y nube deducidos del CNAME, la huella HTTP y los rangos de IP ya recogidos"
    consumes = frozenset({EntityType.RECORD, EntityType.IP})
    produces = frozenset({EntityType.TECHNOLOGY})
    analyzer = True
    canary = "example.com"

    def __init__(self, ctx: Context) -> None:
        super().__init__(ctx)
        self._ranges: list[tuple[str, str, list[Network]]] = []
        self._loaded = False

    def accepts(self, entity: Entity) -> bool:
        if entity.type == EntityType.IP:
            return True
        return entity.type == EntityType.RECORD and entity.value.startswith(("dns:", "http:"))

    def _load_ranges(self) -> None:
        """Rangos de los datasets instalados; los que faltan simplemente no etiquetan."""
        self._loaded = True
        for provider, category, names in RANGE_DATASETS:
            networks = []
            for name in names:
                if path := datasets.installed_path(name):
                    networks += [ipaddress.ip_network(c) for c in json.loads(path.read_bytes())]
            if networks:
                self._ranges.append((provider, category, networks))

    async def run(self, entity: Entity) -> list[Entity]:
        found: dict[str, tuple[str, list[str]]] = {}

        def add(provider: str, category: str, evidence: str) -> None:
            found.setdefault(provider, (category, []))[1].append(evidence)

        if entity.type == EntityType.IP:
            if not self._loaded:
                self._load_ranges()
            address = ipaddress.ip_address(entity.value)
            for provider, category, networks in self._ranges:
                if network := next((n for n in networks if address in n), None):
                    add(provider, category, f"IP {entity.value} en {network}")
        elif entity.value.startswith("dns:"):
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

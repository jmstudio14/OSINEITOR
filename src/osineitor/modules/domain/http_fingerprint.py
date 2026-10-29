"""Huella HTTP del sitio: servidor, tecnologías y cabeceras de seguridad (módulo ACTIVO)."""

from __future__ import annotations

import re

import httpx

from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module, ModuleError

SECURITY_HEADERS = (
    "strict-transport-security",
    "content-security-policy",
    "x-frame-options",
    "x-content-type-options",
    "referrer-policy",
    "permissions-policy",
)
# (tecnología, dónde buscar, patrón)
SIGNATURES = (
    ("WordPress", "body", r"wp-content|wp-includes"),
    ("Drupal", "body", r"Drupal\.settings|/sites/default/files"),
    ("Joomla", "body", r"/media/jui/|Joomla!"),
    ("Shopify", "body", r"cdn\.shopify\.com"),
    ("Next.js", "body", r"__NEXT_DATA__|/_next/static"),
    ("React", "body", r"data-reactroot|react-dom"),
    ("Angular", "body", r"ng-version="),
    ("Vue.js", "body", r"data-v-[0-9a-f]{8}|__vue__"),
    ("jQuery", "body", r"jquery[.-]"),
    ("Google Analytics", "body", r"googletagmanager\.com|google-analytics\.com"),
    ("Cloudflare", "headers", r"cf-ray|cloudflare"),
    ("Akamai", "headers", r"akamai"),
    ("AWS CloudFront", "headers", r"cloudfront"),
    ("Vercel", "headers", r"x-vercel-id"),
    ("Netlify", "headers", r"x-nf-request-id|netlify"),
    ("PHP", "headers", r"php"),
    ("ASP.NET", "headers", r"asp\.net|x-aspnet-version"),
)
TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


class HttpFingerprint(Module):
    name = "http_fingerprint"
    description = "Servidor, tecnologías y cabeceras de seguridad (contacta al objetivo)"
    consumes = frozenset({EntityType.DOMAIN})
    produces = frozenset({EntityType.RECORD})
    passive = False
    canary = "example.com"

    async def run(self, entity: Entity) -> list[Entity]:
        response = None
        for scheme in ("https", "http"):
            try:
                response = await self.ctx.http.get(f"{scheme}://{entity.value}")
                break
            except httpx.TransportError:
                continue
        if response is None:
            raise ModuleError("el sitio no responde por HTTP(S)")

        headers = {k.lower(): v for k, v in response.headers.items()}
        header_blob = "\n".join(f"{k}: {v}" for k, v in headers.items())
        body = response.text[:500_000]
        tech = sorted(
            {
                name
                for name, where, pattern in SIGNATURES
                if re.search(pattern, body if where == "body" else header_blob, re.IGNORECASE)
            }
        )
        title = TITLE.search(body)
        return [
            self.emit(
                entity,
                EntityType.RECORD,
                f"http:{entity.value}",
                status=response.status_code,
                final_url=str(response.url),
                title=" ".join(title.group(1).split())[:200] if title else None,
                server=headers.get("server"),
                powered_by=headers.get("x-powered-by"),
                technologies=tech,
                missing_security_headers=[h for h in SECURITY_HEADERS if h not in headers],
            )
        ]

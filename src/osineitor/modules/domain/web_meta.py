"""robots.txt, sitemap.xml y security.txt del sitio (módulo ACTIVO)."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from urllib.parse import urljoin, urlsplit

import httpx

from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module, ModuleError
from osineitor.modules.domain._util import is_root_domain

MAX_TEXT = 1_000_000
MAX_URLS = 50
MAX_SITEMAPS = 3
# Sin `\s*` alrededor de un `*?`: se solapan y el coste crece con el cuadrado. Se recorta después.
LOC = re.compile(r"<loc>([^<]*+)</loc>", re.IGNORECASE)
SECURITY_TXT_PATHS = ("/.well-known/security.txt", "/security.txt")


def _is_html(text: str) -> bool:
    """Muchos sitios devuelven su página de inicio (200) para cualquier ruta que no existe."""
    return "<html" in text[:500].lower() or "<!doctype html" in text[:500].lower()


def _same_site(url: str, domain: str) -> bool:
    host = urlsplit(url).hostname or ""
    return host == domain or host.endswith(f".{domain}")


def parse_robots(text: str) -> tuple[list[str], list[str]]:
    """(rutas `Disallow` concretas, URLs `Sitemap`). Sin comodines: no son rutas que visitar."""
    disallow: list[str] = []
    sitemaps: list[str] = []
    for line in text.splitlines():
        key, _, value = line.split("#", 1)[0].partition(":")
        key, value = key.strip().lower(), value.strip()
        if key == "disallow" and value.startswith("/") and len(value) > 1:
            if not re.search(r"[*$]", value) and value not in disallow:
                disallow.append(value)
        elif key == "sitemap" and value and value not in sitemaps:
            sitemaps.append(value)
    return disallow, sitemaps


def parse_security_txt(text: str) -> dict[str, list[str]]:
    """Campos de RFC 9116 en minúsculas; ignora la firma PGP si la hay."""
    fields: dict[str, list[str]] = {}
    for line in text.splitlines():
        if line.startswith(("-----", "Hash:")) or ":" not in line or line.lstrip().startswith("#"):
            continue
        key, _, value = line.partition(":")
        if value.strip():
            fields.setdefault(key.strip().lower(), []).append(value.strip())
    return fields


class WebMeta(Module):
    name = "web_meta"
    authority = "authoritative"
    description = "robots.txt, sitemap.xml y security.txt del sitio (contacta al objetivo)"
    consumes = frozenset({EntityType.DOMAIN})
    produces = frozenset({EntityType.RECORD, EntityType.URL, EntityType.EMAIL})
    passive = False
    canary = "example.com"

    def accepts(self, entity: Entity) -> bool:
        return is_root_domain(entity)

    async def _fetch(self, base: str, path: str) -> str | None:
        """Texto de una ruta del sitio; `None` si no existe o es la página de inicio de relleno."""
        response = await self.ctx.http.get(urljoin(base, path))
        if response.status_code != 200:
            return None
        text = response.text[:MAX_TEXT]
        return None if _is_html(text) else text

    async def run(self, entity: Entity) -> list[Entity]:
        domain = entity.value
        base = None
        robots = None
        for scheme in ("https", "http"):
            try:
                robots = await self._fetch(f"{scheme}://{domain}", "/robots.txt")
            except httpx.TransportError:
                continue
            base = f"{scheme}://{domain}"
            break
        if base is None:
            raise ModuleError("el sitio no responde por HTTP(S)")

        disallow, declared = parse_robots(robots) if robots else ([], [])
        # Solo se visitan sitemaps del propio sitio: robots.txt es un dato del objetivo.
        candidates = [u for u in declared if _same_site(u, domain)] or [
            urljoin(base, "/sitemap.xml")
        ]
        pages: list[str] = []
        sitemap_index = False
        for sitemap in candidates[:MAX_SITEMAPS]:
            text = await self._fetch(sitemap, "")
            if not text or not re.search(r"<(urlset|sitemapindex)", text, re.IGNORECASE):
                continue
            sitemap_index = sitemap_index or "<sitemapindex" in text.lower()
            known = set(pages)  # `in` sobre la lista sería cuadrático con sitemaps enormes
            pages += [loc for raw in LOC.findall(text) if (loc := raw.strip()) and loc not in known]

        security: dict[str, list[str]] = {}
        security_url = None
        for path in SECURITY_TXT_PATHS:
            text = await self._fetch(base, path)
            if text and (fields := parse_security_txt(text)).get("contact"):
                security, security_url = fields, urljoin(base, path)
                break

        if not (robots or pages or security):
            return []
        expires = security.get("expires", [None])[0]
        expired = None
        if expires:
            try:
                expired = datetime.fromisoformat(expires.replace("Z", "+00:00")) < datetime.now(UTC)
            except ValueError:
                expired = None
        out = [
            self.emit(
                entity,
                EntityType.RECORD,
                f"web_meta:{domain}",
                robots_txt=bool(robots),
                disallow=disallow[:MAX_URLS],
                sitemaps=declared,
                sitemap_index=sitemap_index or None,
                sitemap_urls=len(pages) or None,
                security_txt=security_url,
                security_contact=security.get("contact"),
                security_expires=expires,
                security_expired=expired,
                security_policy=security.get("policy"),
                security_encryption=security.get("encryption"),
            )
        ]
        urls = [urljoin(base, path) for path in disallow] + pages
        for url in dict.fromkeys(urls[:MAX_URLS]):
            if found := self.try_emit(entity, EntityType.URL, url, from_file="web_meta"):
                out.append(found)
        for contact in security.get("contact", []):
            if contact.lower().startswith("mailto:"):
                address = contact[7:].split("?", 1)[0]
                if email := self.try_emit(entity, EntityType.EMAIL, address, role="security.txt"):
                    out.append(email)
        return out

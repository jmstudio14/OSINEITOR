"""Plantillas de búsqueda sobre un dominio con la API oficial de Brave Search (requiere key).

Nunca se hace scraping de buscadores. Cada plantilla es una petición de pago en cuanto se agota el
crédito mensual de Brave, así que la lista es corta y fija.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from osineitor.errors import InvalidEntityValue
from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module, ModuleError, status_error
from osineitor.modules.domain._util import in_domain, is_document_url, is_root_domain
from osineitor.normalize import canonical_hostname

API = "https://api.search.brave.com/res/v1/web/search"
DORKS = (
    "site:{domain} filetype:pdf",
    "site:{domain} filetype:docx",
    "site:{domain} filetype:xlsx",
    "site:{domain} filetype:pptx",
    'site:{domain} intitle:"index of"',
)
RESULTS_PER_DORK = "20"  # el máximo de la API


class SearchDorks(Module):
    name = "search_dorks"
    description = "Documentos e índices públicos del dominio con plantillas (API de Brave Search)"
    consumes = frozenset({EntityType.DOMAIN})
    produces = frozenset({EntityType.URL})
    requires_key = "brave"
    canary = "example.com"
    min_interval = 1.1

    def accepts(self, entity: Entity) -> bool:
        return is_root_domain(entity)

    def _in_domain(self, url: str, domain: str) -> bool:
        try:
            return in_domain(canonical_hostname(urlsplit(url).hostname or ""), domain)
        except (InvalidEntityValue, ValueError):
            return False

    async def run(self, entity: Entity) -> list[Entity]:
        found: dict[str, Entity] = {}
        for template in DORKS:
            dork = template.format(domain=entity.value)
            response = await self.ctx.http.get(
                API,
                params={"q": dork, "count": RESULTS_PER_DORK},
                headers={"Accept": "application/json", "X-Subscription-Token": self.api_key or ""},
            )
            if response.status_code in (401, 403):
                raise ModuleError("API key de Brave Search inválida o sin acceso")
            if response.status_code != 200:
                raise status_error("api.search.brave.com", response)
            for hit in (response.json().get("web") or {}).get("results") or []:
                url = str(hit.get("url") or "") if isinstance(hit, dict) else ""
                if url in found or not self._in_domain(url, entity.value):
                    continue
                item = self.try_emit(
                    entity,
                    EntityType.URL,
                    url,
                    dork=dork,
                    title=hit.get("title"),
                    document=is_document_url(url) or None,
                )
                if item:
                    found[url] = item
        return list(found.values())

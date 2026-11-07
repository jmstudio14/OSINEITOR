"""IDs de analítica y publicidad de Google que declara la página de inicio (módulo ACTIVO)."""

from __future__ import annotations

import re

import httpx

from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module, ModuleError
from osineitor.modules.domain._util import is_root_domain

MAX_TEXT = 1_000_000
# (tipo, patrón). GA4 y GTM exigen al menos un dígito para no confundirse con clases CSS o texto.
PATTERNS = (
    ("Google Analytics 4", re.compile(r"\bG-(?=[A-Z0-9]*\d)[A-Z0-9]{8,12}\b")),
    ("Google Analytics (Universal)", re.compile(r"\bUA-\d{4,10}-\d{1,4}\b")),
    ("Google Ads", re.compile(r"\bAW-\d{8,12}\b")),
    ("Google Tag Manager", re.compile(r"\bGTM-(?=[A-Z0-9]*\d)[A-Z0-9]{4,8}\b")),
    ("Google AdSense", re.compile(r"\bca-pub-\d{10,20}\b")),
)


class AnalyticsIds(Module):
    name = "analytics_ids"
    authority = "authoritative"
    description = "IDs de Google Analytics, Tag Manager, Ads y AdSense de la página (contacta)"
    consumes = frozenset({EntityType.DOMAIN})
    produces = frozenset({EntityType.RECORD})
    passive = False
    canary = "example.com"

    def accepts(self, entity: Entity) -> bool:
        return is_root_domain(entity)

    async def run(self, entity: Entity) -> list[Entity]:
        domain = entity.value
        page = None
        for scheme in ("https", "http"):
            try:
                response = await self.ctx.http.get(f"{scheme}://{domain}/")
            except httpx.TransportError:
                continue
            page = response.text[:MAX_TEXT] if response.status_code == 200 else ""
            break
        if page is None:
            raise ModuleError("el sitio no responde por HTTP(S)")
        found: dict[str, str] = {}
        for kind, pattern in PATTERNS:
            for tracking_id in pattern.findall(page):
                found.setdefault(tracking_id, kind)
        return [
            self.emit(entity, EntityType.RECORD, f"analytics:{tid}", kind=kind, domain=domain)
            for tid, kind in found.items()
        ]

"""Histórico de URLs del dominio en la Wayback Machine, destacando las sensibles."""

from __future__ import annotations

import re

import httpx

from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module, ModuleError
from osineitor.modules.domain._util import is_root_domain

LIMIT = 5000
INTERESTING = re.compile(
    r"(\.(env|sql|bak|old|zip|tar|gz|log|conf|config|ini|ya?ml|json|xml|db|swp|git)(\?|$))"
    r"|(/(admin|wp-admin|wp-login|login|signin|dashboard|phpmyadmin|api|graphql|swagger|debug)"
    r"(/|\?|$))"
    r"|([?&](token|key|apikey|api_key|secret|password|passwd|auth)=)",
    re.IGNORECASE,
)


class Wayback(Module):
    name = "wayback"
    description = "URLs archivadas en la Wayback Machine (con rutas sensibles destacadas)"
    consumes = frozenset({EntityType.DOMAIN})
    produces = frozenset({EntityType.RECORD, EntityType.URL})

    def accepts(self, entity: Entity) -> bool:
        return is_root_domain(entity)

    async def run(self, entity: Entity) -> list[Entity]:
        params = {
            "url": f"{entity.value}/*",
            "output": "json",
            "fl": "timestamp,original",
            "collapse": "urlkey",
            "limit": str(LIMIT),
        }
        try:
            response = await self.ctx.http.get(
                "https://web.archive.org/cdx/search/cdx", params=params, timeout=60
            )
        except httpx.TimeoutException as exc:
            raise ModuleError("web.archive.org no respondió a tiempo") from exc
        if response.status_code != 200:
            raise ModuleError(f"web.archive.org respondió {response.status_code}")
        rows = response.json()[1:] if response.text.strip() else []
        if not rows:
            return []

        timestamps = sorted(r[0] for r in rows)
        interesting = sorted({r[1] for r in rows if INTERESTING.search(r[1])})
        out = [
            self.emit(
                entity,
                EntityType.RECORD,
                f"wayback:{entity.value}",
                urls=len(rows),
                truncated=len(rows) >= LIMIT,
                first_seen=timestamps[0],
                last_seen=timestamps[-1],
                interesting=len(interesting),
            )
        ]
        out += [self.emit(entity, EntityType.URL, url, archived=True) for url in interesting[:200]]
        return out

"""Coincidencias en listas de sanciones y de personas políticamente expuestas (OpenSanctions).

Datos CC BY-NC 4.0, gratis para uso no comercial: https://www.opensanctions.org/licensing/
"""

from __future__ import annotations

from typing import Any

from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module, ModuleError, status_error
from osineitor.sanitize import quote_segment

MATCH = "https://api.opensanctions.org/match/default"
PAGE = "https://www.opensanctions.org/entities"
SCHEMAS = {EntityType.ORGANIZATION: "Organization", EntityType.PERSON: "Person"}
MAX_RESULTS = 5


class OpenSanctions(Module):
    name = "opensanctions"
    description = "Coincidencias en listas de sanciones y de personas expuestas (OpenSanctions)"
    consumes = frozenset({EntityType.ORGANIZATION, EntityType.PERSON})
    produces = frozenset({EntityType.RECORD})
    requires_key = "opensanctions"
    canary = "Gazprom"
    min_interval = 1.0

    def accepts(self, entity: Entity) -> bool:
        # Las organizaciones de GitHub no son personas jurídicas: no se buscan en estas listas.
        return entity.type in self.consumes and not entity.data.get("platform")

    async def run(self, entity: Entity) -> list[Entity]:
        query = {"schema": SCHEMAS[entity.type], "properties": {"name": [entity.value]}}
        response = await self.ctx.http.post(
            MATCH,
            params={"limit": str(MAX_RESULTS)},
            json={"queries": {"q": query}},
            headers={"Authorization": f"ApiKey {self.api_key}"},
        )
        if response.status_code in (401, 403):
            raise ModuleError("API key de OpenSanctions inválida o sin acceso")
        if response.status_code != 200:
            raise status_error("api.opensanctions.org", response)
        answer: dict[str, Any] = (response.json().get("responses") or {}).get("q") or {}
        out = []
        for hit in answer.get("results") or []:
            if not isinstance(hit, dict) or not hit.get("match") or not hit.get("id"):
                continue
            found = self.try_emit(
                entity,
                EntityType.RECORD,
                f"opensanctions:{hit['id']}",
                name=hit.get("caption"),
                schema=hit.get("schema"),
                score=hit.get("score"),
                topics=(hit.get("properties") or {}).get("topics"),
                datasets=hit.get("datasets"),
                first_seen=hit.get("first_seen"),
                last_seen=hit.get("last_seen"),
                last_change=hit.get("last_change"),
                url=f"{PAGE}/{quote_segment(str(hit['id']))}/",
            )
            if found:
                out.append(found)
        return out

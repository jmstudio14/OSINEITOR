"""Identificador LEI de una organización y su relación matriz–filial (API pública de GLEIF).

Datos de GLEIF en dominio público (licencia CC0): https://www.gleif.org/en/lei-data/gleif-terms
"""

from __future__ import annotations

from typing import Any

from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module, status_error
from osineitor.sanitize import quote_segment

BASE = "https://api.gleif.org/api/v1/lei-records"
MAX_CANDIDATES = 3
MAX_CHILDREN = 20


def _summary(record: dict[str, Any]) -> dict[str, Any]:
    attrs = record.get("attributes") or {}
    entity = attrs.get("entity") or {}
    registration = attrs.get("registration") or {}
    address = entity.get("legalAddress") or {}
    return {
        "lei": attrs.get("lei") or record.get("id"),
        "legal_name": (entity.get("legalName") or {}).get("name"),
        "country": address.get("country"),
        "city": address.get("city"),
        "jurisdiction": entity.get("jurisdiction"),
        "entity_status": entity.get("status"),
        "registration_status": registration.get("status"),
        "registered_as": entity.get("registeredAs"),
        "created": entity.get("creationDate"),
        "last_update": registration.get("lastUpdateDate"),
    }


def _related(record: dict[str, Any], relation: str) -> bool:
    links = ((record.get("relationships") or {}).get(relation) or {}).get("links") or {}
    return "related" in links


class Gleif(Module):
    name = "gleif"
    description = "LEI de una organización y relaciones matriz–filial (GLEIF)"
    consumes = frozenset({EntityType.ORGANIZATION})
    produces = frozenset({EntityType.RECORD, EntityType.ORGANIZATION})
    canary = "Banco Santander, S.A."
    min_interval = 1.0

    def accepts(self, entity: Entity) -> bool:
        # Las organizaciones de GitHub no son personas jurídicas: no se buscan en GLEIF.
        return entity.type == EntityType.ORGANIZATION and not entity.data.get("platform")

    async def _json(self, url: str, **params: str) -> Any:
        response = await self.ctx.http.get(url, params=params)
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise status_error("api.gleif.org", response)
        return response.json()

    async def _records(self, **params: str) -> list[dict[str, Any]]:
        body = await self._json(BASE, **params)
        return [r for r in (body or {}).get("data") or [] if isinstance(r, dict)]

    async def run(self, entity: Entity) -> list[Entity]:
        name = entity.value
        exact = await self._records(**{"filter[entity.legalName]": name, "page[size]": "5"})
        approximate = not exact
        records = exact or await self._records(
            **{"filter[fulltext]": name, "page[size]": str(MAX_CANDIDATES)}
        )
        out: list[Entity] = []
        for record in records[:MAX_CANDIDATES]:
            summary = _summary(record)
            if not summary["lei"]:
                continue
            made = self.try_emit(
                entity,
                EntityType.RECORD,
                f"gleif:{summary['lei']}",
                match="approximate" if approximate else "exact",
                **summary,
            )
            if made:
                out.append(made)
        # Solo con un único LEI exacto se siguen las relaciones: con varios candidatos o con una
        # coincidencia aproximada se estaría atribuyendo la cadena de otra empresa.
        if not approximate and len(exact) == 1:
            out += await self._family(entity, exact[0])
        return out

    async def _family(self, entity: Entity, record: dict[str, Any]) -> list[Entity]:
        lei = quote_segment(str(record.get("id", "")))
        found: list[Entity] = []
        if _related(record, "direct-parent"):
            body = await self._json(f"{BASE}/{lei}/direct-parent")
            parent = (body or {}).get("data")
            if isinstance(parent, dict) and (name := _summary(parent)["legal_name"]):
                made = self.try_emit(
                    entity,
                    EntityType.ORGANIZATION,
                    name,
                    relationship="parent",
                    lei=parent.get("id"),
                )
                found += [made] if made else []
        if _related(record, "direct-children"):
            body = await self._json(
                f"{BASE}/{lei}/direct-children", **{"page[size]": str(MAX_CHILDREN)}
            )
            for child in (body or {}).get("data") or []:
                if isinstance(child, dict) and (name := _summary(child)["legal_name"]):
                    made = self.try_emit(
                        entity,
                        EntityType.ORGANIZATION,
                        name,
                        relationship="subsidiary",
                        lei=child.get("id"),
                    )
                    found += [made] if made else []
        return found

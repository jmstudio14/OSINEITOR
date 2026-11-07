"""Filtraciones en las que aparece el email según la API pública de LeakCheck (sin key)."""

from __future__ import annotations

from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module, ModuleError, status_error

MAX_BREACHES = 200
NOT_FOUND = "not found"


class Leakcheck(Module):
    name = "leakcheck"
    description = "Filtraciones en las que aparece el email (LeakCheck, API pública sin datos)"
    consumes = frozenset({EntityType.EMAIL})
    produces = frozenset({EntityType.BREACH})
    canary = "test@example.com"
    min_interval = 1.0  # la API pública admite 1 petición por segundo

    async def run(self, entity: Entity) -> list[Entity]:
        response = await self.ctx.http.get(
            "https://leakcheck.io/api/public", params={"check": entity.value}
        )
        if response.status_code != 200:
            raise status_error("leakcheck.io", response)
        body = response.json()
        if not isinstance(body, dict):
            raise ModuleError("leakcheck.io devolvió una respuesta inesperada")
        if not body.get("success"):
            error = str(body.get("error") or "error desconocido")
            if error.strip().lower() == NOT_FOUND:
                return []
            raise ModuleError(f"leakcheck.io: {error[:100]}")
        found = (
            self.try_emit(
                entity,
                EntityType.BREACH,
                str(source["name"]),
                date=source.get("date") or None,
                via="leakcheck",
            )
            for source in body.get("sources") or []
            if isinstance(source, dict) and source.get("name")
        )
        return [e for e in found if e][:MAX_BREACHES]

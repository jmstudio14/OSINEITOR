"""Filtraciones de datos en las que aparece el email (Have I Been Pwned, requiere key)."""

from __future__ import annotations

from urllib.parse import quote

from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module, ModuleError, status_error


class Hibp(Module):
    name = "hibp"
    description = "Brechas de datos en las que aparece el email (Have I Been Pwned)"
    consumes = frozenset({EntityType.EMAIL})
    produces = frozenset({EntityType.BREACH})
    requires_key = "hibp"
    canary = "test@example.com"

    async def run(self, entity: Entity) -> list[Entity]:
        response = await self.ctx.http.get(
            f"https://haveibeenpwned.com/api/v3/breachedaccount/{quote(entity.value)}",
            params={"truncateResponse": "false"},
            headers={"hibp-api-key": self.api_key or ""},
        )
        if response.status_code == 404:
            return []
        if response.status_code == 401:
            raise ModuleError("API key de HIBP inválida")
        if response.status_code != 200:
            raise status_error("haveibeenpwned.com", response)
        return [
            self.emit(
                entity,
                EntityType.BREACH,
                breach["Name"],
                title=breach.get("Title"),
                domain=breach.get("Domain"),
                date=breach.get("BreachDate"),
                accounts=breach.get("PwnCount"),
                data_classes=breach.get("DataClasses", []),
                verified=breach.get("IsVerified"),
            )
            for breach in response.json()
        ]

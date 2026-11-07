"""Apariciones del email en *pastes* (Have I Been Pwned, misma key que `hibp`)."""

from __future__ import annotations

from urllib.parse import quote

from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module, ModuleError, status_error


class HibpPastes(Module):
    name = "hibp_pastes"
    description = "Pastes en los que aparece el email (Have I Been Pwned)"
    consumes = frozenset({EntityType.EMAIL})
    produces = frozenset({EntityType.RECORD})
    requires_key = "hibp"
    canary = "test@example.com"
    min_interval = 12.0  # plan más bajo: 10/min por key, compartidos con `hibp`

    async def run(self, entity: Entity) -> list[Entity]:
        response = await self.ctx.http.get(
            f"https://haveibeenpwned.com/api/v3/pasteaccount/{quote(entity.value, safe='')}",
            headers={"hibp-api-key": self.api_key or ""},
        )
        if response.status_code == 404:
            return []
        if response.status_code == 401:
            raise ModuleError("API key de HIBP inválida")
        if response.status_code != 200:
            raise status_error("haveibeenpwned.com", response)
        pastes = [p for p in response.json() if isinstance(p, dict)]
        if not pastes:
            return []
        dates = [p["Date"] for p in pastes if p.get("Date")]
        return [
            self.emit(
                entity,
                EntityType.RECORD,
                f"hibp_pastes:{entity.value}",
                pastes=len(pastes),
                sources=sorted({p["Source"] for p in pastes if p.get("Source")}),
                first_paste=min(dates, default=None),
                last_paste=max(dates, default=None),
                titles=[p["Title"] for p in pastes if p.get("Title")][:10],
            )
        ]

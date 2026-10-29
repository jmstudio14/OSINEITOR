"""Clasificación de la IP como escáner/ruido de Internet o servicio conocido (GreyNoise)."""

from __future__ import annotations

from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module, status_error


class GreyNoise(Module):
    name = "greynoise"
    description = "¿Escáner masivo, bot o servicio legítimo conocido? (GreyNoise Community)"
    consumes = frozenset({EntityType.IP})
    produces = frozenset({EntityType.RECORD})
    requires_key = "greynoise"
    canary = "1.1.1.1"

    async def run(self, entity: Entity) -> list[Entity]:
        response = await self.ctx.http.get(
            f"https://api.greynoise.io/v3/community/{entity.value}",
            headers={"key": self.api_key or "", "Accept": "application/json"},
        )
        if response.status_code == 404:
            return []  # GreyNoise no ha visto esta IP
        if response.status_code != 200:
            raise status_error("api.greynoise.io", response)
        data = response.json()
        return [
            self.emit(
                entity,
                EntityType.RECORD,
                f"greynoise:{entity.value}",
                noise=data.get("noise"),
                riot=data.get("riot"),
                classification=data.get("classification"),
                name=data.get("name"),
                last_seen=data.get("last_seen"),
                link=data.get("link"),
            )
        ]

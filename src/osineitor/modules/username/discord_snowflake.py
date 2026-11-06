"""Fecha de creación de una cuenta de Discord a partir de su ID (en local, sin red)."""

from __future__ import annotations

from datetime import UTC, datetime

from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module

DISCORD_EPOCH_MS = 1_420_070_400_000


def created_at(snowflake: int) -> datetime:
    return datetime.fromtimestamp(((snowflake >> 22) + DISCORD_EPOCH_MS) / 1000, tz=UTC)


class DiscordSnowflake(Module):
    name = "discord_snowflake"
    description = "Fecha de creación de la cuenta de Discord a partir de su ID (sin red)"
    consumes = frozenset({EntityType.USERNAME})
    produces = frozenset({EntityType.RECORD})
    canary = "80351110224678912"  # ID de ejemplo de la documentación de Discord

    def accepts(self, entity: Entity) -> bool:
        return (
            entity.type == EntityType.USERNAME
            and entity.value.isdigit()
            and 17 <= len(entity.value) <= 20
        )

    async def run(self, entity: Entity) -> list[Entity]:
        created = created_at(int(entity.value))
        if not datetime(2015, 5, 13, tzinfo=UTC) <= created <= datetime.now(UTC):
            return []  # fuera del rango posible: no es un ID de Discord
        return [
            self.emit(
                entity,
                EntityType.RECORD,
                f"discord:{entity.value}",
                created_at=created.isoformat().replace("+00:00", "Z"),
            )
        ]

"""Geolocalización de la IP con una base GeoLite2 local: la IP no sale del equipo.

OSINEITOR no incluye ni descarga la base: la coloca el usuario (ver docs/MODULES.md).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import maxminddb

from osineitor.config import data_dir
from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module, ModuleError

# El EULA de GeoLite (§6.3) pide dejar de usar una versión a los 30 días de salir la siguiente.
MAX_AGE = timedelta(days=30)


def database_path() -> Path:
    return data_dir() / "geoip" / "GeoLite2-City.mmdb"


def _now() -> datetime:
    return datetime.now(UTC)


def _english(item: dict) -> str | None:
    return item.get("names", {}).get("en")


class GeoipOffline(Module):
    name = "geoip_offline"
    description = "Geolocalización con una base GeoLite2 local, sin enviar la IP a terceros"
    consumes = frozenset({EntityType.IP})
    produces = frozenset({EntityType.RECORD})
    analyzer = True
    canary = "8.8.8.8"

    @classmethod
    def unavailable(cls) -> str | None:
        path = database_path()
        return None if path.is_file() else f"falta la base GeoLite2: colócala en {path}"

    async def run(self, entity: Entity) -> list[Entity]:
        path = database_path()
        try:
            with maxminddb.open_database(path) as reader:
                metadata = reader.metadata()
                if "City" not in metadata.database_type:
                    raise ModuleError(f"{path} es {metadata.database_type}, no una base City")
                found = reader.get(entity.value)
        except (maxminddb.InvalidDatabaseError, OSError, ValueError) as exc:
            raise ModuleError(f"no se pudo leer {path}: {exc}") from exc
        # Las IP anycast solo traen `registered_country`: dónde se registró el bloque, no la IP.
        if not found or not (found.get("country") or found.get("location")):
            return []
        built = datetime.fromtimestamp(metadata.build_epoch, UTC)
        location = found.get("location", {})
        latitude, longitude = location.get("latitude"), location.get("longitude")
        return [
            self.emit(
                entity,
                EntityType.RECORD,
                f"geoip:{entity.value}",
                city=_english(found.get("city", {})),
                region=_english((found.get("subdivisions") or [{}])[0]),
                country=found.get("country", {}).get("iso_code"),
                loc=f"{latitude},{longitude}" if latitude is not None else None,
                timezone=location.get("time_zone"),
                accuracy_radius=location.get("accuracy_radius"),
                database_date=built.date().isoformat(),
                stale_database=_now() - built > MAX_AGE or None,
            )
        ]

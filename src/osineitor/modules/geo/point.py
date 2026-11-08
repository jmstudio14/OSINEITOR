"""Coordenadas como punto: formatos y enlaces a mapas (en local, sin red)."""

from __future__ import annotations

from urllib.parse import quote

from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module
from osineitor.normalize import COORDS_RE


def _dms(value: float, positive: str, negative: str) -> str:
    hemisphere = positive if value >= 0 else negative
    value = abs(value)
    degrees = int(value)
    minutes = int((value - degrees) * 60)
    seconds = (value - degrees - minutes / 60) * 3600
    return f"{degrees}°{minutes:02d}'{seconds:05.2f}\"{hemisphere}"


class GeoPoint(Module):
    name = "geo_point"
    description = "Coordenadas: grados-minutos-segundos y enlaces a mapas (sin red)"
    consumes = frozenset({EntityType.LOCATION})
    produces = frozenset({EntityType.RECORD})
    canary = "40.416775,-3.703790"

    def accepts(self, entity: Entity) -> bool:
        return entity.type == EntityType.LOCATION and bool(COORDS_RE.fullmatch(entity.value))

    async def run(self, entity: Entity) -> list[Entity]:
        lat, lon = (float(part) for part in entity.value.split(","))
        osm = f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=17/{lat}/{lon}"
        return [
            self.emit(
                entity,
                EntityType.RECORD,
                f"geo:{entity.value}",
                latitude=lat,
                longitude=lon,
                dms=f"{_dms(lat, 'N', 'S')} {_dms(lon, 'E', 'W')}",
                openstreetmap=osm,
                google_maps=f"https://www.google.com/maps/search/?api=1&query={quote(entity.value)}",
            )
        ]

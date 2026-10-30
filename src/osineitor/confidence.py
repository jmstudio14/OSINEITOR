"""Confianza de una entidad (bajo, medio, alto): cuánto respalda el dato lo que se ha visto."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from osineitor.models import Entity

LEVELS = ("bajo", "medio", "alto")
# Más antiguo que esto, el dato baja un nivel.
MAX_AGE = timedelta(days=90)
# Claves de `Entity.data` en las que un tercero dice cuándo vio o actualizó el dato por última vez
# (Shodan, GreyNoise, AbuseIPDB, Hunter, Wayback). No cuentan fechas de alta o de brecha (`created`,
# `date`): son antiguas por naturaleza y no dicen que el dato esté desfasado.
THIRD_PARTY_DATES = ("last_update", "last_seen", "last_reported", "seen")


def _parse(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        try:
            parsed = datetime.strptime(value, "%Y%m%d%H%M%S")  # formato de Wayback
        except ValueError:
            return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def data_date(entity: Entity) -> datetime | None:
    """Fecha del dato: la que aporta un tercero (la más reciente) o, si no, la última vez visto."""
    dates = [d for key in THIRD_PARTY_DATES if (d := _parse(entity.data.get(key)))]
    return max(dates) if dates else entity.last_seen


def assess(entity: Entity, authoritative: set[str], reference: datetime) -> str | None:
    """Nivel de confianza, o `None` si la entidad no tiene observaciones que lo respalden.

    Puntos: uno por cada fuente distinta y uno más si alguna es autoritativa (DNS, RDAP, el propio
    objetivo). Tres o más es `alto`, dos `medio`, y una sola fuente agregada `bajo`. Un dato de hace
    más de `MAX_AGE` (respecto a `reference`, normalmente el fin del scan) baja un nivel.
    """
    sources = set(entity.sources)
    if not entity.observations or not sources:
        return None
    points = len(sources) + bool(sources & authoritative)
    level = 2 if points >= 3 else 1 if points == 2 else 0
    date = data_date(entity)
    if date is not None and reference - date > MAX_AGE:
        level = max(level - 1, 0)
    return LEVELS[level]

"""Línea temporal de un scan: las fechas que traen los datos, en orden.

Solo cuentan fechas **del dato** (cuándo se registró un dominio, cuándo caduca un certificado,
cuándo fue una filtración…), no cuándo lo vio OSINEITOR: eso ya está en las observaciones. Cada
fecha es la que declara la fuente; ninguna se verifica.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from osineitor.models import Entity, EntityType, ScanResult

# Clave de `data` → qué cuenta como hecho. Una clave solo se mira donde su sentido es claro:
# `date` es la fecha de la filtración en un `breach`, y poco más en el resto de tipos.
FIELDS: dict[str, str] = {
    "created": "Alta o creación",
    "created_at": "Cuenta creada",
    "updated": "Última modificación del registro",
    "modified": "Última modificación",
    "expires": "Caducidad",
    "not_before": "Certificado válido desde",
    "not_after": "Certificado caduca",
    "first_seen": "Primera vez visto por la fuente",
    "last_seen": "Última vez visto por la fuente",
    "first_scan": "Primera captura",
    "last_scan": "Última captura",
    "first_activity": "Primera actividad en la cadena",
    "last_activity": "Última actividad en la cadena",
    "first_commit": "Primer commit público",
    "last_commit": "Último commit público",
    "first_paste": "Primer paste",
    "last_paste": "Último paste",
    "last_reported": "Último reporte",
    "last_update": "Última actualización de la fuente",
    "last_post": "Última publicación",
}
TYPED_FIELDS: dict[tuple[EntityType, str], str] = {
    (EntityType.BREACH, "date"): "Fecha de la filtración",
}
STAMP_RE = re.compile(r"^\d{14}$")  # los de Wayback: aaaammddhhmmss


def parse_moment(value: Any) -> datetime | None:
    """Fecha ISO 8601 (con o sin hora y zona) o sello de Wayback, en UTC; `None` si no es una."""
    if not isinstance(value, str) or not (text := value.strip()):
        return None
    try:
        if STAMP_RE.match(text):
            return datetime.strptime(text, "%Y%m%d%H%M%S").replace(tzinfo=UTC)
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _label(entity: Entity, field: str) -> str | None:
    return TYPED_FIELDS.get((entity.type, field)) or FIELDS.get(field)


def build(result: ScanResult) -> list[dict[str, Any]]:
    """Hechos con fecha del scan, del más antiguo al más reciente.

    `future` marca los posteriores al inicio del scan (caducidades). Dentro de una misma fecha el
    orden es el de las entidades, de modo que el resultado es estable.
    """
    events: list[dict[str, Any]] = []
    for entity in [result.target, *result.entities]:
        for field, value in entity.data.items():
            if (label := _label(entity, field)) is None or (moment := parse_moment(value)) is None:
                continue
            events.append(
                {
                    "at": moment.isoformat(),
                    "event": label,
                    "field": field,
                    "entity": entity.key,
                    "type": entity.type.value,
                    "value": entity.value,
                    "source": entity.source,
                    "future": moment > result.started_at,
                }
            )
    events.sort(key=lambda e: e["at"])
    return events

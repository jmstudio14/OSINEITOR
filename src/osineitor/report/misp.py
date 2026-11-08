"""Exportación a un evento MISP (F8.2): atributos de infraestructura, sin compartir.

Se exporta lo mismo que a STIX (dominios, IP, URL, emails y CVE). Ningún atributo se marca
`to_ids`: lo que sale de un scan OSINT es contexto, no un indicador listo para detectar. El evento
queda con distribución 0 (solo tu organización): compartirlo es una decisión posterior, en MISP.
Los UUID son deterministas, así que reimportar el mismo scan no duplica atributos. No se ha
probado contra un servidor MISP; el formato lo construye y valida la librería `pymisp`.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from osineitor.errors import ExportUnavailable
from osineitor.models import Entity, EntityType, ScanResult

NAMESPACE = uuid.UUID("5f0c5f1e-6f3b-4c7e-9b0e-0c3b1f4d2a11")  # propio de OSINEITOR
NETWORK = "Network activity"
ATTRIBUTES: dict[EntityType, tuple[str, str]] = {
    EntityType.DOMAIN: ("domain", NETWORK),
    EntityType.IP: ("ip-dst", NETWORK),
    EntityType.URL: ("url", NETWORK),
    EntityType.EMAIL: ("email-dst", NETWORK),
    EntityType.VULNERABILITY: ("vulnerability", "External analysis"),
}
PRIVATE = 0  # distribución: solo tu organización
THREAT_UNDEFINED = 4
ANALYSIS_INITIAL = 0


def _comment(entity: Entity) -> str:
    return f"OSINEITOR: {', '.join(entity.sources)}" if entity.sources else "OSINEITOR"


def to_misp(result: ScanResult) -> str:
    try:
        from pymisp import MISPEvent
    except ImportError as exc:
        raise ExportUnavailable(
            "la exportación MISP necesita la librería pymisp: pip install 'osineitor[misp]'"
        ) from exc

    when = result.started_at
    event: Any = MISPEvent()
    event.uuid = str(uuid.uuid5(NAMESPACE, f"{result.target.key}@{when.isoformat()}"))
    event.info = f"OSINEITOR: {result.target.type}:{result.target.value}"
    event.date = when.strftime("%Y-%m-%d")
    event.distribution = PRIVATE
    event.threat_level_id = THREAT_UNDEFINED
    event.analysis = ANALYSIS_INITIAL
    seen: set[str] = set()
    for entity in [result.target, *result.entities]:
        if entity.key in seen or entity.type not in ATTRIBUTES:
            continue
        seen.add(entity.key)
        kind, category = ATTRIBUTES[entity.type]
        event.add_attribute(
            kind,
            entity.value,
            category=category,
            to_ids=False,
            comment=_comment(entity),
            uuid=str(uuid.uuid5(NAMESPACE, f"{event.uuid}:{entity.key}")),
        )
    if result.purpose:
        event.add_attribute(
            "comment",
            result.purpose,
            category="Other",
            to_ids=False,
            comment="Propósito declarado del scan (--purpose)",
            uuid=str(uuid.uuid5(NAMESPACE, f"{event.uuid}:purpose")),
        )
    return json.dumps({"Event": json.loads(event.to_json())}, indent=2, ensure_ascii=False)

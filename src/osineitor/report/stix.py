"""Exportación a STIX 2.1: observables de infraestructura (F8.1).

Solo se exporta lo que STIX describe como infraestructura: dominios, IP, URL, emails y
vulnerabilidades (CVE). Cuentas, hallazgos y demás no tienen equivalente y se omiten. Los
observables llevan el identificador determinista que define STIX, así que el mismo dato da el mismo
id en cualquier exportación; los vínculos descubiertos salen como `related-to`, salvo dominio → IP,
que usa `resolves_to_refs`, que es lo que define STIX para una resolución.
"""

from __future__ import annotations

import ipaddress
import logging
import uuid
from typing import Any

from osineitor.errors import ExportUnavailable
from osineitor.models import Entity, EntityType, ScanResult

log = logging.getLogger(__name__)
SUPPORTED = (
    EntityType.DOMAIN,
    EntityType.IP,
    EntityType.URL,
    EntityType.EMAIL,
    EntityType.VULNERABILITY,
)
NAMESPACE = uuid.UUID("5f0c5f1e-6f3b-4c7e-9b0e-0c3b1f4d2a10")  # propio de OSINEITOR
DESCRIPTION = "Vínculo descubierto por OSINEITOR al pivotar desde el dato de origen"


def _observable(stix2: Any, entity: Entity) -> Any:
    value = entity.value
    match entity.type:
        case EntityType.DOMAIN:
            return stix2.DomainName(value=value)
        case EntityType.IP:
            version = ipaddress.ip_address(value).version
            return (stix2.IPv4Address if version == 4 else stix2.IPv6Address)(value=value)
        case EntityType.URL:
            return stix2.URL(value=value)
        case EntityType.EMAIL:
            return stix2.EmailAddress(value=value)
    raise ValueError(entity.type)


def to_stix(result: ScanResult) -> str:
    try:
        import stix2
    except ImportError as exc:
        raise ExportUnavailable(
            "la exportación STIX necesita la librería stix2: pip install 'osineitor[stix]'"
        ) from exc

    when = result.started_at
    index: dict[str, Entity] = {}
    for entity in [result.target, *result.entities]:
        index.setdefault(entity.key, entity)
    exported = {k: e for k, e in index.items() if e.type in SUPPORTED}

    def nearest(entity: Entity) -> Entity | None:
        """Antepasado exportable más cercano (puede haber un `record` o un perfil en medio)."""
        seen = {entity.key}
        current = index.get(entity.parent) if entity.parent else None
        while current is not None and current.key not in seen:
            if current.key in exported:
                return current
            seen.add(current.key)
            current = index.get(current.parent) if current.parent else None
        return None

    ids: dict[str, str] = {}
    objects: dict[str, Any] = {}
    skipped = 0
    for key, entity in exported.items():
        try:
            if entity.type == EntityType.VULNERABILITY:
                objects[key] = stix2.Vulnerability(
                    id=f"vulnerability--{uuid.uuid5(NAMESPACE, entity.value)}",
                    name=entity.value,
                    external_references=[
                        stix2.ExternalReference(source_name="cve", external_id=entity.value)
                    ],
                    created=when,
                    modified=when,
                )
            else:
                objects[key] = _observable(stix2, entity)
        except (ValueError, TypeError) as exc:
            skipped += 1
            log.warning("STIX: se omite %s %r: %s", entity.type, entity.value, exc)
            continue
        ids[key] = objects[key].id
    if skipped:
        log.warning("STIX: %d valores omitidos por no ser representables", skipped)

    resolves: dict[str, list[str]] = {}
    links: list[tuple[str, str]] = []
    for key in ids:
        parent = nearest(exported[key])
        if parent is None or parent.key not in ids:
            continue
        if parent.type == EntityType.DOMAIN and exported[key].type == EntityType.IP:
            resolves.setdefault(parent.key, []).append(ids[key])
        else:
            links.append((parent.key, key))

    final: list[Any] = []
    for key, obj in objects.items():
        if key in resolves:
            obj = stix2.DomainName(value=exported[key].value, resolves_to_refs=resolves[key])
        final.append(obj)
    for source, target in links:
        final.append(
            stix2.Relationship(
                id=f"relationship--{uuid.uuid5(NAMESPACE, f'{ids[source]}>{ids[target]}')}",
                relationship_type="related-to",
                source_ref=ids[source],
                target_ref=ids[target],
                description=DESCRIPTION,
                created=when,
                modified=when,
            )
        )
    bundle_id = uuid.uuid5(NAMESPACE, f"{result.target.key}@{when.isoformat()}")
    return stix2.Bundle(*final, id=f"bundle--{bundle_id}", allow_custom=False).serialize(
        pretty=True
    )

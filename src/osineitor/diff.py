"""Comparación de dos scans: qué entidades y hallazgos son nuevos, desaparecidos o distintos."""

from __future__ import annotations

from typing import Any

from osineitor.models import Entity, ScanResult


def _brief(entity: Entity) -> dict[str, Any]:
    return {"key": entity.key, "type": entity.type.value, "value": entity.value}


def _changes(before: Entity, after: Entity) -> list[dict[str, Any]]:
    """Campos de `data` que valen otra cosa (o que solo existen en un lado)."""
    keys = sorted(before.data.keys() | after.data.keys())
    return [
        {"field": k, "before": before.data.get(k), "after": after.data.get(k)}
        for k in keys
        if before.data.get(k) != after.data.get(k)
    ]


def diff_scans(a: ScanResult, b: ScanResult) -> dict[str, Any]:
    """Cambios de `a` (antes) a `b` (después), por la clave de cada entidad.

    Un hallazgo es una entidad más (tipo `finding`), así que aparece también en las listas
    generales; `findings` los separa para verlos de un vistazo.
    """
    old = {e.key: e for e in a.entities}
    new = {e.key: e for e in b.entities}
    added = [_brief(new[k]) for k in new.keys() - old.keys()]
    removed = [_brief(old[k]) for k in old.keys() - new.keys()]
    changed = [
        {**_brief(new[k]), "changes": changes}
        for k in new.keys() & old.keys()
        if (changes := _changes(old[k], new[k]))
    ]
    for group in (added, removed, changed):
        group.sort(key=lambda item: item["key"])

    def only_findings(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [i for i in items if i["type"] == "finding"]

    return {
        "from": {"scan_id": a.scan_id, "target": a.target.key, "started_at": a.started_at},
        "to": {"scan_id": b.scan_id, "target": b.target.key, "started_at": b.started_at},
        "same_target": a.target.key == b.target.key,
        "added": added,
        "removed": removed,
        "changed": changed,
        "findings": {
            "added": only_findings(added),
            "removed": only_findings(removed),
            "changed": only_findings(changed),
        },
        "unchanged": len(old.keys() & new.keys()) - len(changed),
    }

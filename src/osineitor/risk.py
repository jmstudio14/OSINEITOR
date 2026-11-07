"""Puntuación de riesgo por activo (dominio o IP): hallazgos, exposición y confianza.

Es una **heurística para ordenar qué mirar primero**, no una medida: los pesos son estimaciones
razonables y no se han contrastado con scans reales (ver «Riesgo por activo» en
`docs/USO.md`). El resultado siempre lleva el desglose de por qué sale esa nota.

Un activo es el dominio o la IP más cercano subiendo por `parent`: un hallazgo sobre
`record:dns:www.example.com` cuenta para `domain:www.example.com`, y uno sobre un servicio
`1.2.3.4:443`, para `ip:1.2.3.4`.
"""

from __future__ import annotations

from typing import Any

from osineitor.models import Entity, EntityType, ScanResult

SEVERITY_POINTS = {"critical": 40, "high": 25, "medium": 10, "low": 3, "info": 0}
# Un hallazgo sobre un dato con poco respaldo pesa menos; sin confianza conocida, un término medio.
CONFIDENCE_FACTOR = {"alto": 1.0, "medio": 0.8, "bajo": 0.5}
DEFAULT_FACTOR = 0.8
# Exposición: cada servicio abierto y cada CVE suman un poco, con tope, aunque no tengan hallazgo.
EXPOSURE_POINTS = {EntityType.SERVICE: 2, EntityType.VULNERABILITY: 2}
EXPOSURE_CAP = 10
LEVELS = ((75, "critical"), (50, "high"), (20, "medium"), (1, "low"))
ASSET_TYPES = (EntityType.DOMAIN, EntityType.IP)


def level_for(score: int) -> str:
    return next((name for floor, name in LEVELS if score >= floor), "info")


def _asset_of(entity: Entity, index: dict[str, Entity], seed: Entity) -> Entity:
    """Dominio o IP al que se atribuye `entity`; la semilla si la cadena no llega a ninguno."""
    seen: set[str] = set()
    current: Entity | None = entity
    while current is not None and current.key not in seen:
        if current.type in ASSET_TYPES:
            return current
        seen.add(current.key)
        current = index.get(current.parent) if current.parent else None
    return seed


def score(result: ScanResult) -> list[dict[str, Any]]:
    """Riesgo de cada activo con algo que puntuar, de mayor a menor (desempate por clave)."""
    seed = result.target
    index = {e.key: e for e in result.entities}
    index[seed.key] = seed
    assets: dict[str, dict[str, Any]] = {}

    def slot(asset: Entity) -> dict[str, Any]:
        return assets.setdefault(
            asset.key,
            {
                "asset": asset.key,
                "type": asset.type.value,
                "value": asset.value,
                "findings": {},
                "points": 0.0,
                "exposure": {"services": 0, "vulnerabilities": 0},
                "reasons": [],
            },
        )

    for entity in result.entities:
        if entity.type == EntityType.FINDING:
            severity = str(entity.data.get("severity", "info"))
            affected = [index[k] for k in entity.data.get("affected") or [] if k in index]
            subject = affected[0] if affected else entity
            row = slot(_asset_of(subject, index, seed))
            levels = [CONFIDENCE_FACTOR.get(a.confidence or "", DEFAULT_FACTOR) for a in affected]
            factor = sum(levels) / len(levels) if levels else DEFAULT_FACTOR
            points = SEVERITY_POINTS.get(severity, 0) * factor
            row["points"] += points
            row["findings"][severity] = row["findings"].get(severity, 0) + 1
            if points:
                row["reasons"].append(
                    f"{severity}: {entity.data.get('title', entity.value)} (+{points:.0f})"
                )
        elif entity.type in EXPOSURE_POINTS:
            row = slot(_asset_of(entity, index, seed))
            key = "services" if entity.type == EntityType.SERVICE else "vulnerabilities"
            row["exposure"][key] += 1

    out = []
    for row in assets.values():
        exposed = sum(
            min(n * EXPOSURE_POINTS[t], EXPOSURE_CAP)
            for t, n in (
                (EntityType.SERVICE, row["exposure"]["services"]),
                (EntityType.VULNERABILITY, row["exposure"]["vulnerabilities"]),
            )
        )
        if exposed:
            row["reasons"].append(
                f"exposición: {row['exposure']['services']} servicio(s), "
                f"{row['exposure']['vulnerabilities']} CVE (+{exposed})"
            )
        total = min(100, round(row.pop("points") + exposed))
        out.append({**row, "score": total, "level": level_for(total)})
    out.sort(key=lambda r: (-r["score"], r["asset"]))
    return out

"""Resolución de entidades (F7.10): agrupa cuentas que podrían ser de la misma persona.

Todo lo que sale de aquí es una **hipótesis con su evidencia**, nunca una identidad confirmada:
dos cuentas con el mismo username o nombre pueden ser de personas distintas. Por eso la puntuación
no llega nunca a 1, cada grupo lleva las señales que lo justifican y los informes lo etiquetan como
hipótesis. No se usa el avatar: ningún módulo guarda su huella y bajar imágenes de terceros para
compararlas queda fuera del alcance.
"""

from __future__ import annotations

from typing import Any

from osineitor.models import Entity, EntityType, ScanResult

LABEL = "hipótesis"
# Peso de cada señal: probabilidad orientativa de que dos cuentas con esa coincidencia sean de la
# misma persona. Son estimaciones sin contrastar con datos reales.
WEIGHTS = {"email": 0.8, "username": 0.4, "display_name": 0.3}
SHORT_USERNAME = 5  # un username corto o común coincide por azar
SHORT_USERNAME_WEIGHT = 0.2
MIN_SCORE = 0.4  # por debajo no se informa
MAX_SCORE = 0.95
NAME_FIELDS = ("display_name", "name")


def _ancestors(entity: Entity, index: dict[str, Entity]) -> list[Entity]:
    chain: list[Entity] = []
    seen = {entity.key}
    current = index.get(entity.parent) if entity.parent else None
    while current is not None and current.key not in seen:
        chain.append(current)
        seen.add(current.key)
        current = index.get(current.parent) if current.parent else None
    return chain


def _name(profile: Entity) -> str | None:
    for field in NAME_FIELDS:
        value = profile.data.get(field)
        if isinstance(value, str) and len(value.split()) >= 2:
            return " ".join(value.casefold().split())
    return None


def _signals_of(profile: Entity, index: dict[str, Entity]) -> set[tuple[str, str]]:
    signals: set[tuple[str, str]] = set()
    if isinstance(profile.data.get("username"), str) and profile.data["username"].strip():
        signals.add(("username", profile.data["username"].strip().casefold()))
    for ancestor in _ancestors(profile, index):
        if ancestor.type == EntityType.USERNAME:
            signals.add(("username", ancestor.value.strip().casefold()))
        elif ancestor.type == EntityType.EMAIL:
            signals.add(("email", ancestor.value.strip().casefold()))
    if name := _name(profile):
        signals.add(("display_name", name))
    return signals


def _weight(kind: str, value: str) -> float:
    if kind == "username" and len(value) < SHORT_USERNAME:
        return SHORT_USERNAME_WEIGHT
    return WEIGHTS[kind]


def hypotheses(result: ScanResult) -> list[dict[str, Any]]:
    """Grupos de cuentas (`profile`) con señales en común, de mayor a menor puntuación."""
    index = {e.key: e for e in result.entities}
    index[result.target.key] = result.target
    profiles = [e for e in result.entities if e.type == EntityType.PROFILE]

    by_signal: dict[tuple[str, str], set[str]] = {}
    for profile in profiles:
        for signal in _signals_of(profile, index):
            by_signal.setdefault(signal, set()).add(profile.key)
    shared = {s: keys for s, keys in by_signal.items() if len(keys) >= 2}

    parent = {p.key: p.key for p in profiles}

    def find(key: str) -> str:
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    for keys in shared.values():
        first, *rest = sorted(keys)
        for other in rest:
            parent[find(other)] = find(first)

    groups: dict[str, set[str]] = {}
    for profile in profiles:
        groups.setdefault(find(profile.key), set()).add(profile.key)

    out = []
    for members in groups.values():
        signals = sorted(
            (s for s, keys in shared.items() if keys & members), key=lambda s: (s[0], s[1])
        )
        if len(members) < 2 or not signals:
            continue
        miss = 1.0
        for kind, value in signals:
            miss *= 1 - _weight(kind, value)
        score = round(min(MAX_SCORE, 1 - miss), 2)
        if score < MIN_SCORE:
            continue
        out.append(
            {
                "label": LABEL,
                "score": score,
                "accounts": sorted(members),
                "signals": [{"kind": k, "value": v, "weight": _weight(k, v)} for k, v in signals],
            }
        )
    out.sort(key=lambda h: (-h["score"], h["accounts"]))
    return out

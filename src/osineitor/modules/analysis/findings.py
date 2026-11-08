"""Hallazgos: aplica las reglas de `data/rules/default.yml` a las entidades ya recogidas."""

from __future__ import annotations

from osineitor.findings import evaluate, load_rules
from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module

RULES = load_rules()
MAX_SUBJECT = 400


class Findings(Module):
    name = "findings"
    description = "Hallazgos con severidad y recomendación según reglas declarativas (YAML)"
    consumes = frozenset(EntityType(rule.type) for rule in RULES)
    produces = frozenset({EntityType.FINDING})
    analyzer = True
    canary = "example.com"

    def accepts(self, entity: Entity) -> bool:
        return entity.type in self.consumes

    async def run(self, entity: Entity) -> list[Entity]:
        return [
            self.emit(
                entity,
                EntityType.FINDING,
                f"{match.rule.id}: {entity.value[:MAX_SUBJECT]}",
                rule=match.rule.id,
                title=match.rule.title,
                severity=match.rule.severity,
                recommendation=match.rule.recommendation,
                affected=[entity.key],
                evidence=match.evidence,
            )
            for match in evaluate(RULES, entity)
        ]

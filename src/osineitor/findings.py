"""Motor de hallazgos: reglas declarativas en YAML evaluadas sobre las entidades de un scan.

Una regla dice a qué entidades se aplica (`type`, `value_prefix`, `value_regex`) y qué deben
cumplir (`when`). Cada entidad que las cumple todas produce un hallazgo.

    - id: dmarc-missing
      title: El dominio no publica DMARC
      severity: medium            # info | low | medium | high | critical
      type: record
      value_prefix: "dns:"
      when:
        - {field: DMARC, op: missing}
        - {field: subject, op: root_domain}
      evidence: [DMARC]           # campos de la entidad que se copian como evidencia
      recommendation: Publica un registro TXT en _dmarc con una política de al menos quarantine.

Campos: `value` (el valor de la entidad), `subject` (lo que va tras el primer `:` de un record,
p. ej. el dominio de `dns:example.com`) o cualquier clave de `entity.data`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from osineitor.models import Entity

RULES_FILE = Path(__file__).parent / "data" / "rules" / "default.yml"
SEVERITIES = ("info", "low", "medium", "high", "critical")
OPS = {
    "eq",
    "ne",
    "in",
    "gt",
    "gte",
    "lt",
    "lte",
    "exists",
    "missing",
    "regex",
    "contains",
    "days_lte",
    "root_domain",
}


class RuleError(ValueError):
    """Un fichero de reglas no es válido."""


@dataclass(frozen=True)
class Condition:
    field: str
    op: str
    value: Any = None


@dataclass(frozen=True)
class Rule:
    id: str
    title: str
    severity: str
    recommendation: str
    type: str
    when: tuple[Condition, ...]
    value_prefix: tuple[str, ...] = ()
    value_regex: re.Pattern[str] | None = None
    evidence: tuple[str, ...] = ()


@dataclass
class Match:
    rule: Rule
    entity: Entity
    evidence: dict[str, Any] = field(default_factory=dict)


def _condition(raw: Any, rule_id: str) -> Condition:
    if not isinstance(raw, dict) or "field" not in raw or raw.get("op") not in OPS:
        raise RuleError(f"{rule_id}: condición no válida {raw!r}")
    if raw["op"] == "regex":
        try:
            re.compile(str(raw.get("value", "")))
        except re.error as exc:
            raise RuleError(f"{rule_id}: expresión regular no válida ({exc})") from exc
    return Condition(str(raw["field"]), raw["op"], raw.get("value"))


def _rule(raw: Any) -> Rule:
    if not isinstance(raw, dict):
        raise RuleError(f"regla no válida: {raw!r}")
    rule_id = str(raw.get("id", ""))
    for key in ("id", "title", "severity", "recommendation", "type"):
        if not raw.get(key):
            raise RuleError(f"{rule_id or '?'}: falta '{key}'")
    if raw["severity"] not in SEVERITIES:
        raise RuleError(f"{rule_id}: severidad desconocida {raw['severity']!r}")
    prefix = raw.get("value_prefix", ())
    prefixes = (prefix,) if isinstance(prefix, str) else tuple(prefix)
    pattern = raw.get("value_regex")
    return Rule(
        id=rule_id,
        title=str(raw["title"]),
        severity=raw["severity"],
        recommendation=str(raw["recommendation"]).strip(),
        type=str(raw["type"]),
        when=tuple(_condition(c, rule_id) for c in raw.get("when", ())),
        value_prefix=prefixes,
        value_regex=re.compile(pattern) if pattern else None,
        evidence=tuple(raw.get("evidence", ())),
    )


def load_rules(path: Path = RULES_FILE) -> list[Rule]:
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise RuleError(f"{path.name}: YAML no válido ({exc})") from exc
    rules = [_rule(raw) for raw in document.get("rules", [])]
    ids = [r.id for r in rules]
    if len(ids) != len(set(ids)):
        raise RuleError(f"{path.name}: hay ids de regla repetidos")
    return rules


def _subject(entity: Entity) -> str:
    if entity.type == "record" and ":" in entity.value:
        return entity.value.split(":", 1)[1]
    return entity.value


def _lookup(entity: Entity, name: str) -> Any:
    if name == "value":
        return entity.value
    if name == "subject":
        return _subject(entity)
    return entity.data.get(name)


def _date(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _present(value: Any) -> bool:
    return value not in (None, "", [], {}, False)


def _compare(op: str, left: Any, right: Any) -> bool:
    try:
        match op:
            case "gt":
                return float(left) > float(right)
            case "gte":
                return float(left) >= float(right)
            case "lt":
                return float(left) < float(right)
            case "lte":
                return float(left) <= float(right)
    except (TypeError, ValueError):
        return False
    return False


def _holds(cond: Condition, entity: Entity, now: datetime) -> bool:
    value = _lookup(entity, cond.field)
    match cond.op:
        case "exists":
            return _present(value)
        case "missing":
            return not _present(value)
        case "eq":
            return value == cond.value
        case "ne":
            return value != cond.value
        case "in":
            return value in (cond.value or ())
        case "gt" | "gte" | "lt" | "lte":
            return _compare(cond.op, value, cond.value)
        case "regex":
            return isinstance(value, str) and re.search(str(cond.value), value) is not None
        case "contains":
            return _present(value) and cond.value in value
        case "days_lte":
            date = _date(value)
            return date is not None and (date - now).days <= int(cond.value)
        case "root_domain":
            # Sin lista de sufijos públicos, es raíz lo que tiene forma `nombre.tld`: un dominio
            # como `example.co.uk` no se evalúa (falso negativo) y ningún subdominio se confunde.
            return isinstance(value, str) and value.count(".") == 1
    return False


def applies(rule: Rule, entity: Entity) -> bool:
    if entity.type != rule.type:
        return False
    if rule.value_prefix and not entity.value.startswith(rule.value_prefix):
        return False
    return not rule.value_regex or rule.value_regex.search(entity.value) is not None


def evaluate(rules: list[Rule], entity: Entity, now: datetime | None = None) -> list[Match]:
    """Hallazgos de una entidad: una `Match` por regla que se cumple."""
    now = now or datetime.now(UTC)
    found = []
    for rule in rules:
        if applies(rule, entity) and all(_holds(c, entity, now) for c in rule.when):
            evidence = {k: entity.data[k] for k in rule.evidence if _present(entity.data.get(k))}
            found.append(Match(rule, entity, evidence))
    return found

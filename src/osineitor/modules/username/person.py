"""Generadores de candidatos a partir de una persona: usernames y emails (sin red).

Solo **generan** candidatos: ni los verifican por SMTP ni hacen petición alguna. Lo que pase a
los módulos de email y username sale de aquí marcado como `candidate`.
"""

from __future__ import annotations

import re
import unicodedata

from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module

MAX_CANDIDATES = 12
MIN_LENGTH = 3
PARTICLES = frozenset({"de", "del", "la", "las", "los", "y", "e", "van", "von", "da", "di", "do"})


def name_parts(full_name: str) -> tuple[str, list[str]]:
    """(nombre, apellidos) en minúsculas y sin acentos ni signos. Vacío si no hay nombre usable.

    Se usan el primer y el último apellido: en español suelen ser los dos que se ven en un email.
    """
    ascii_name = unicodedata.normalize("NFKD", full_name).encode("ascii", "ignore").decode()
    tokens = [re.sub(r"[^a-z0-9]", "", t) for t in ascii_name.lower().split()]
    tokens = [t for t in tokens if t and t not in PARTICLES]
    if not tokens:
        return "", []
    surnames = list(dict.fromkeys([tokens[1], tokens[-1]])) if len(tokens) > 1 else []
    return tokens[0], surnames


def combine(full_name: str, patterns: tuple[tuple[str, str], ...]) -> list[tuple[str, str]]:
    """`[(candidato, patrón)]` sin repetidos, en el orden de las plantillas, con tope."""
    first, surnames = name_parts(full_name)
    found: dict[str, str] = {}
    for last in surnames:
        for pattern, template in patterns:
            candidate = template.format(f=first, l=last, fi=first[:1], li=last[:1])
            if len(candidate) >= MIN_LENGTH:
                found.setdefault(candidate, pattern)
    return list(found.items())[:MAX_CANDIDATES]


USERNAME_PATTERNS = (
    ("{f}.{l}", "{f}.{l}"),
    ("{f}{l}", "{f}{l}"),
    ("{fi}{l}", "{fi}{l}"),
    ("{f}_{l}", "{f}_{l}"),
    ("{l}.{f}", "{l}.{f}"),
    ("{f}-{l}", "{f}-{l}"),
    ("{fi}.{l}", "{fi}.{l}"),
    ("{f}{li}", "{f}{li}"),
)
EMAIL_PATTERNS = (
    ("{f}.{l}", "{f}.{l}"),
    ("{f}{l}", "{f}{l}"),
    ("{fi}{l}", "{fi}{l}"),
    ("{f}_{l}", "{f}_{l}"),
    ("{l}.{f}", "{l}.{f}"),
    ("{fi}.{l}", "{fi}.{l}"),
    ("{f}{li}", "{f}{li}"),
    ("{f}", "{f}"),
    ("{l}", "{l}"),
)


class UsernameVariants(Module):
    name = "username_variants"
    description = "Candidatos de username a partir del nombre de una persona (sin red)"
    consumes = frozenset({EntityType.PERSON})
    produces = frozenset({EntityType.USERNAME})
    canary = "Ana García López"

    async def run(self, entity: Entity) -> list[Entity]:
        out = (
            self.try_emit(entity, EntityType.USERNAME, candidate, candidate=True, pattern=pattern)
            for candidate, pattern in combine(entity.value, USERNAME_PATTERNS)
        )
        return [e for e in out if e]


class EmailCandidates(Module):
    name = "email_candidates"
    description = "Candidatos de email de una persona en un dominio (no se verifican por SMTP)"
    consumes = frozenset({EntityType.PERSON})
    produces = frozenset({EntityType.EMAIL})
    canary = "Ana García López"

    def accepts(self, entity: Entity) -> bool:
        return entity.type == EntityType.PERSON and bool(entity.data.get("domain"))

    async def run(self, entity: Entity) -> list[Entity]:
        domain = entity.data["domain"]
        out = (
            self.try_emit(
                entity, EntityType.EMAIL, f"{candidate}@{domain}", candidate=True, pattern=pattern
            )
            for candidate, pattern in combine(entity.value, EMAIL_PATTERNS)
        )
        return [e for e in out if e]

"""Subdominios con Subfinder (herramienta externa, solo fuentes pasivas)."""

from __future__ import annotations

from typing import Any

from osineitor.errors import InvalidEntityValue
from osineitor.models import Entity, EntityType
from osineitor.modules._external import ExternalToolModule
from osineitor.modules.domain._util import in_domain, is_root_domain
from osineitor.normalize import canonical_hostname

MAX_SUBDOMAINS = 500


class ExtSubfinder(ExternalToolModule):
    name = "ext_subfinder"
    description = "Subdominios con Subfinder, solo fuentes pasivas (binario del usuario)"
    consumes = frozenset({EntityType.DOMAIN})
    produces = frozenset({EntityType.DOMAIN})
    binary = "subfinder"
    version_args = ("-version",)
    canary = "example.com"

    def accepts(self, entity: Entity) -> bool:
        return is_root_domain(entity)

    def args(self, entity: Entity) -> list[str]:
        # Subfinder solo consulta fuentes pasivas; no se pasa `-active` ni `-b` (resolución).
        return ["-d", entity.value, "-silent", "-json"]

    def parse(self, entity: Entity, documents: list[Any]) -> list[Entity]:
        found: dict[str, list[str]] = {}
        for doc in documents:
            if not isinstance(doc, dict):
                continue
            try:
                host = canonical_hostname(str(doc.get("host") or ""))
            except InvalidEntityValue:
                continue
            # Las fuentes de Subfinder devuelven ruido: solo valen los subdominios del objetivo.
            if host == entity.value or not in_domain(host, entity.value):
                continue
            sources = doc.get("source")
            if isinstance(sources, str):
                sources = [sources]
            found.setdefault(host, []).extend(sources if isinstance(sources, list) else [])
        return [
            self.emit(entity, EntityType.DOMAIN, host, subdomain=True, sources=sorted(set(src)))
            for host, src in sorted(found.items())[:MAX_SUBDOMAINS]
        ]

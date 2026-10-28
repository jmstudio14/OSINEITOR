"""Hunter.io: verificación de emails y emails públicos de un dominio (requiere key)."""

from __future__ import annotations

from typing import Any

from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module, ModuleError
from osineitor.modules.domain._util import is_root_domain


class _HunterBase(Module):
    requires_key = "hunter"

    async def _get(self, endpoint: str, **params: str) -> dict[str, Any]:
        response = await self.ctx.http.get(
            f"https://api.hunter.io/v2/{endpoint}", params={**params, "api_key": self.api_key}
        )
        if response.status_code == 401:
            raise ModuleError("API key de Hunter inválida")
        if response.status_code == 429:
            raise ModuleError("cuota de Hunter agotada")
        if response.status_code != 200:
            raise ModuleError(f"api.hunter.io respondió {response.status_code}")
        return response.json().get("data") or {}


class HunterVerify(_HunterBase):
    name = "hunter_verify"
    description = "Entregabilidad del email y fuentes públicas donde aparece (Hunter)"
    consumes = frozenset({EntityType.EMAIL})
    produces = frozenset({EntityType.RECORD, EntityType.URL})

    async def run(self, entity: Entity) -> list[Entity]:
        data = await self._get("email-verifier", email=entity.value)
        sources = data.get("sources") or []
        out = [
            self.emit(
                entity,
                EntityType.RECORD,
                f"hunter:{entity.value}",
                status=data.get("status"),
                score=data.get("score"),
                disposable=data.get("disposable"),
                webmail=data.get("webmail"),
                accept_all=data.get("accept_all"),
                sources=len(sources),
            )
        ]
        out += [
            self.emit(entity, EntityType.URL, s["uri"], seen=s.get("last_seen_on"))
            for s in sources
            if s.get("uri")
        ]
        return out


class HunterDomain(_HunterBase):
    name = "hunter_domain"
    description = "Emails públicos asociados a un dominio y su patrón (Hunter)"
    consumes = frozenset({EntityType.DOMAIN})
    produces = frozenset({EntityType.EMAIL, EntityType.RECORD})

    def accepts(self, entity: Entity) -> bool:
        return is_root_domain(entity)

    async def run(self, entity: Entity) -> list[Entity]:
        data = await self._get("domain-search", domain=entity.value, limit="10")
        out = [
            self.emit(
                entity,
                EntityType.RECORD,
                f"hunter:{entity.value}",
                organization=data.get("organization"),
                pattern=data.get("pattern"),
                disposable=data.get("disposable"),
                webmail=data.get("webmail"),
            )
        ]
        for email in data.get("emails") or []:
            name = " ".join(filter(None, [email.get("first_name"), email.get("last_name")]))
            out.append(
                self.emit(
                    entity,
                    EntityType.EMAIL,
                    email["value"].lower(),
                    name=name or None,
                    position=email.get("position"),
                    confidence=email.get("confidence"),
                    email_type=email.get("type"),
                )
            )
        return out

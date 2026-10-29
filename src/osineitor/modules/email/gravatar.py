"""Perfil público de Gravatar asociado al email y cuentas que enlaza."""

from __future__ import annotations

import hashlib

from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module, ModuleError


class Gravatar(Module):
    name = "gravatar"
    description = "Perfil público de Gravatar y cuentas enlazadas"
    consumes = frozenset({EntityType.EMAIL})
    produces = frozenset({EntityType.PROFILE, EntityType.USERNAME})

    async def run(self, entity: Entity) -> list[Entity]:
        digest = hashlib.sha256(entity.value.strip().lower().encode()).hexdigest()
        response = await self.ctx.http.get(f"https://gravatar.com/{digest}.json")
        if response.status_code == 404:
            return []
        if response.status_code != 200:
            raise ModuleError(f"gravatar.com respondió {response.status_code}")
        entries = response.json().get("entry") or []
        if not entries:
            return []
        profile = entries[0]
        out = [
            self.emit(
                entity,
                EntityType.PROFILE,
                profile.get("profileUrl") or f"https://gravatar.com/{digest}",
                site="Gravatar",
                display_name=profile.get("displayName"),
                location=profile.get("currentLocation"),
                about=(profile.get("aboutMe") or "")[:300] or None,
            )
        ]
        if profile.get("preferredUsername"):
            username = self.try_emit(entity, EntityType.USERNAME, profile["preferredUsername"])
            if username:
                out.append(username)
        for account in profile.get("accounts", []):
            if account.get("url"):
                out.append(
                    self.emit(
                        entity,
                        EntityType.PROFILE,
                        account["url"],
                        site=account.get("shortname") or account.get("domain"),
                        username=account.get("username"),
                    )
                )
        return out

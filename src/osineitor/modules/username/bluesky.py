"""Perfil público de Bluesky por handle de atproto (API pública sin sesión)."""

from __future__ import annotations

import re

from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module, ModuleSkipped, status_error
from osineitor.sanitize import quote_segment

API = "https://public.api.bsky.app/xrpc/app.bsky.actor.getProfile"
DEFAULT_DOMAIN = "bsky.social"
# Sintaxis de handle de atproto: dominio con al menos dos etiquetas y TLD que no empieza por dígito.
HANDLE = re.compile(
    r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?$"
)
MAX_HANDLE = 253


class Bluesky(Module):
    name = "bluesky"
    description = "Perfil público de Bluesky: nombre, bio, fecha de alta y actividad"
    consumes = frozenset({EntityType.USERNAME})
    produces = frozenset({EntityType.PROFILE})
    canary = "bsky.app"
    min_interval = 1.0

    async def run(self, entity: Entity) -> list[Entity]:
        handle = entity.value.strip().lower()
        if "." not in handle:
            handle = f"{handle}.{DEFAULT_DOMAIN}"
        if len(handle) > MAX_HANDLE or not HANDLE.fullmatch(handle):
            raise ModuleSkipped(f"«{entity.value}» no puede ser un handle de Bluesky")
        response = await self.ctx.http.get(API, params={"actor": handle})
        # Un handle que no existe responde 400 («Profile not found»), no 404.
        if response.status_code in (400, 404):
            return []
        if response.status_code != 200:
            raise status_error("public.api.bsky.app", response)
        body = response.json()
        found = str(body.get("handle") or "") if isinstance(body, dict) else ""
        if not HANDLE.fullmatch(found):
            return []
        profile = self.try_emit(
            entity,
            EntityType.PROFILE,
            f"https://bsky.app/profile/{quote_segment(found)}",
            site="Bluesky",
            display_name=body.get("displayName"),
            bio=body.get("description"),
            created_at=body.get("createdAt"),
            followers=body.get("followersCount"),
            follows=body.get("followsCount"),
            posts=body.get("postsCount"),
            did=body.get("did"),
            verified=True,
        )
        return [profile] if profile else []

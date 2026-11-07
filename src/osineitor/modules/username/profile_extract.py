"""Perfil enriquecido desde las APIs públicas oficiales de DEV Community y Codeberg.

Solo se leen datos que el propio dueño publicó en su perfil (nombre, bio, web, usernames de otras
redes). No se extrae nada de páginas HTML ni se guarda el email que una API pudiera devolver. Los
usernames y la web declarados se emiten como entidades, así que el motor los pivota en el
siguiente nivel; el límite de profundidad del scan acota esa recursión.
"""

from __future__ import annotations

import contextlib
import html
import re
from datetime import datetime
from typing import Any

from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module, ModuleError, status_error
from osineitor.sanitize import quote_segment

MAX_TEXT = 300
TAGS = re.compile(r"<[^>]+>")
SPACES = re.compile(r"\s+")
HTTP_URL = re.compile(r"^https?://", re.IGNORECASE)


def _text(value: object) -> str | None:
    """Texto plano y corto de un campo de tercero, o `None` si queda vacío."""
    if not isinstance(value, str):
        return None
    clean = SPACES.sub(" ", html.unescape(TAGS.sub(" ", value))).strip()
    return clean[:MAX_TEXT] or None


class ProfileExtract(Module):
    name = "profile_extract"
    description = "Nombre, bio, web y usernames declarados en DEV Community y Codeberg"
    consumes = frozenset({EntityType.USERNAME})
    produces = frozenset({EntityType.PROFILE, EntityType.USERNAME, EntityType.URL})
    canary = "ben"
    min_interval = 1.0

    async def _get(
        self, service: str, url: str, params: dict[str, str] | None = None
    ) -> dict[str, Any] | None:
        response = await self.ctx.http.get(url, params=params)
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise status_error(service, response)
        body = response.json()
        return body if isinstance(body, dict) else None

    async def _devto(self, name: str) -> dict[str, Any] | None:
        user = await self._get("dev.to", "https://dev.to/api/users/by_username", {"url": name})
        if not user or not user.get("username"):
            return None
        created = None
        with contextlib.suppress(ValueError):  # «Dec 27, 2015»; otro formato = sin fecha
            joined = datetime.strptime(str(user.get("joined_at")), "%b %d, %Y")
            created = joined.date().isoformat()
        return {
            "url": f"https://dev.to/{quote_segment(str(user['username']))}",
            "data": {
                "site": "DEV Community",
                "display_name": _text(user.get("name")),
                "bio": _text(user.get("summary")),
                "location": _text(user.get("location")),
                "created_at": created,
            },
            "website": user.get("website_url"),
            "handles": {
                "twitter": user.get("twitter_username"),
                "github": user.get("github_username"),
            },
        }

    async def _codeberg(self, name: str) -> dict[str, Any] | None:
        user = await self._get(
            "codeberg.org", f"https://codeberg.org/api/v1/users/{quote_segment(name)}"
        )
        if not user or not user.get("login"):
            return None
        return {
            "url": f"https://codeberg.org/{quote_segment(str(user['login']))}",
            "data": {
                "site": "Codeberg",
                "display_name": _text(user.get("full_name")),
                "bio": _text(user.get("description")),
                "location": _text(user.get("location")),
                "created_at": user.get("created"),
            },
            "website": user.get("website"),
            "handles": {},
        }

    def _entities(self, entity: Entity, found: dict[str, Any]) -> list[Entity]:
        url = found["url"]
        made = [self.try_emit(entity, EntityType.PROFILE, url, verified=True, **found["data"])]
        website = str(found["website"] or "").strip()
        if HTTP_URL.match(website):
            made.append(self.try_emit(entity, EntityType.URL, website, declared_on=url))
        for platform, handle in found["handles"].items():
            if isinstance(handle, str) and handle.casefold() != entity.value.casefold():
                made.append(
                    self.try_emit(
                        entity, EntityType.USERNAME, handle, platform=platform, declared_on=url
                    )
                )
        return [e for e in made if e]

    async def run(self, entity: Entity) -> list[Entity]:
        out: list[Entity] = []
        errors: list[ModuleError] = []
        for lookup in (self._devto, self._codeberg):
            try:
                found = await lookup(entity.value)
            except ModuleError as exc:  # una fuente caída no debe tapar a la otra
                errors.append(exc)
                continue
            if found:
                out += self._entities(entity, found)
        if errors and not out:
            raise errors[0]
        return out

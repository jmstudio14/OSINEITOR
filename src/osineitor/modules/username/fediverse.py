"""Cuenta de Mastodon/fediverso de `usuario@instancia` (API de búsqueda y WebFinger). ACTIVO.

Contacta con el servidor del dominio del email, que puede ser el propio objetivo: por eso es
un módulo activo.
"""

from __future__ import annotations

import re

from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module, status_error

TAGS = re.compile(r"<[^>]+>")
PROFILE_REL = "http://webfinger.net/rel/profile-page"


class Fediverse(Module):
    name = "fediverse"
    description = (
        "Cuenta de Mastodon de usuario@instancia por lookup y WebFinger (contacta al host)"
    )
    consumes = frozenset({EntityType.EMAIL})
    produces = frozenset({EntityType.PROFILE})
    passive = False
    canary = "Gargron@mastodon.social"

    async def _lookup(self, host: str, user: str) -> dict[str, object] | None:
        response = await self.ctx.http.get(
            f"https://{host}/api/v1/accounts/lookup", params={"acct": user}
        )
        if response.status_code in (401, 403, 404, 410):
            return None  # no es Mastodon, o exige autenticación para consultar cuentas
        if response.status_code != 200:
            raise status_error(host, response)
        data = response.json()
        return data if isinstance(data, dict) and data.get("url") else None

    async def _webfinger(self, host: str, user: str) -> str | None:
        response = await self.ctx.http.get(
            f"https://{host}/.well-known/webfinger", params={"resource": f"acct:{user}@{host}"}
        )
        if response.status_code != 200:
            return None
        try:
            links = response.json().get("links") or []
        except ValueError:
            return None
        return next(
            (
                link["href"]
                for link in links
                if isinstance(link, dict) and link.get("rel") == PROFILE_REL and link.get("href")
            ),
            None,
        )

    async def run(self, entity: Entity) -> list[Entity]:
        user, _, host = entity.value.rpartition("@")
        if account := await self._lookup(host, user):
            made = self.try_emit(
                entity,
                EntityType.PROFILE,
                str(account["url"]),
                site=f"Mastodon ({host})",
                display_name=account.get("display_name"),
                bio=TAGS.sub("", str(account.get("note") or "")).strip() or None,
                created_at=account.get("created_at"),
                followers=account.get("followers_count"),
                posts=account.get("statuses_count"),
                last_post=account.get("last_status_at"),
                bot=account.get("bot"),
                verified=True,
            )
            return [made] if made else []
        if url := await self._webfinger(host, user):
            made = self.try_emit(
                entity, EntityType.PROFILE, url, site=f"Fediverso ({host})", verified=True
            )
            return [made] if made else []
        return []

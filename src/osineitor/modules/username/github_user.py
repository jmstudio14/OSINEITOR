"""Perfil público de GitHub: datos, organizaciones y emails de sus commits públicos."""

from __future__ import annotations

from typing import Any

from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module, ModuleQuota, status_error
from osineitor.sanitize import quote_segment

BASE = "https://api.github.com"
MAX_ORGS = 20
MAX_EMAILS = 10
# Direcciones que GitHub genera para ocultar el email real: no identifican a nadie.
NOREPLY = "@users.noreply.github.com"


class GithubUser(Module):
    name = "github_user"
    description = "Perfil público de GitHub: nombre, empresa, blog, organizaciones y emails"
    consumes = frozenset({EntityType.USERNAME})
    produces = frozenset(
        {EntityType.PROFILE, EntityType.ORGANIZATION, EntityType.EMAIL, EntityType.URL}
    )
    canary = "octocat"
    min_interval = 1.0

    async def _get(self, path: str, **params: str) -> Any:
        headers = {"Accept": "application/vnd.github+json"}
        if key := self.ctx.config.key("github"):  # opcional: de 60 a 5.000 peticiones por hora
            headers["Authorization"] = f"Bearer {key}"
        response = await self.ctx.http.get(f"{BASE}/{path}", params=params, headers=headers)
        if response.status_code == 404:
            return None
        if response.status_code == 403 and response.headers.get("x-ratelimit-remaining") == "0":
            raise ModuleQuota("api.github.com rechazó la petición por límite de uso")
        if response.status_code != 200:
            raise status_error("api.github.com", response)
        return response.json()

    async def run(self, entity: Entity) -> list[Entity]:
        login = quote_segment(entity.value)
        user = await self._get(f"users/{login}")
        if not isinstance(user, dict) or not user.get("html_url"):
            return []
        out = [
            self.emit(
                entity,
                EntityType.PROFILE,
                user["html_url"],
                site="GitHub",
                name=user.get("name"),
                company=user.get("company"),
                blog=user.get("blog"),
                location=user.get("location"),
                bio=user.get("bio"),
                twitter=user.get("twitter_username"),
                public_repos=user.get("public_repos"),
                followers=user.get("followers"),
                created_at=user.get("created_at"),
                verified=True,
            )
        ]
        extra: list[Entity | None] = []
        blog = str(user.get("blog") or "").strip()
        if blog:
            extra.append(
                self.try_emit(entity, EntityType.URL, blog if "://" in blog else f"https://{blog}")
            )
        orgs = await self._get(f"users/{login}/orgs") or []
        extra += [
            self.try_emit(entity, EntityType.ORGANIZATION, str(org["login"]), platform="github")
            for org in orgs[:MAX_ORGS]
            if isinstance(org, dict) and org.get("login")
        ]
        emails: dict[str, str | None] = {}
        for event in await self._get(f"users/{login}/events/public", per_page="100") or []:
            if not isinstance(event, dict) or event.get("type") != "PushEvent":
                continue
            for commit in (event.get("payload") or {}).get("commits") or []:
                author = commit.get("author") or {}
                mail = str(author.get("email") or "").lower()
                if mail and not mail.endswith(NOREPLY):
                    emails.setdefault(mail, author.get("name"))
        extra += [
            self.try_emit(entity, EntityType.EMAIL, mail, role="commit", commit_author=name)
            for mail, name in list(emails.items())[:MAX_EMAILS]
        ]
        return out + [item for item in extra if item]

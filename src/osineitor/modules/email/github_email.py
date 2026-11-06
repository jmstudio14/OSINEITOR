"""Commits públicos de GitHub firmados con el email (API de búsqueda de commits)."""

from __future__ import annotations

from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module, ModuleQuota, status_error

MAX_USERS = 5
MAX_REPOS = 10


class GithubEmail(Module):
    name = "github_email"
    description = "Commits públicos de GitHub con ese email: autores y repositorios"
    consumes = frozenset({EntityType.EMAIL})
    produces = frozenset({EntityType.RECORD, EntityType.USERNAME})
    canary = "octocat@github.com"
    # Búsqueda sin key: 10 peticiones por minuto.
    min_interval = 6.0

    async def run(self, entity: Entity) -> list[Entity]:
        headers = {"Accept": "application/vnd.github+json"}
        if key := self.ctx.config.key("github"):  # opcional: sube la cuota
            headers["Authorization"] = f"Bearer {key}"
        response = await self.ctx.http.get(
            "https://api.github.com/search/commits",
            params={"q": f"author-email:{entity.value}", "per_page": "30"},
            headers=headers,
        )
        if response.status_code == 403 and response.headers.get("x-ratelimit-remaining") == "0":
            raise ModuleQuota("api.github.com rechazó la petición por límite de uso")
        if response.status_code != 200:
            raise status_error("api.github.com", response)
        body = response.json()
        items = [i for i in body.get("items") or [] if isinstance(i, dict)]
        if not items:
            return []

        names, repos, logins, dates = {}, {}, {}, []
        for item in items:
            commit = item.get("commit") or {}
            author = commit.get("author") or {}
            if author.get("name"):
                names[str(author["name"])] = None
            if author.get("date"):
                dates.append(str(author["date"]))
            if (repo := (item.get("repository") or {}).get("full_name")) is not None:
                repos[str(repo)] = None
            if login := (item.get("author") or {}).get("login"):
                logins[str(login)] = None
        out = [
            self.emit(
                entity,
                EntityType.RECORD,
                f"github_email:{entity.value}",
                commits=body.get("total_count"),
                names=list(names),
                repositories=list(repos)[:MAX_REPOS],
                first_commit=min(dates, default=None),
                last_commit=max(dates, default=None),
            )
        ]
        found = [
            self.try_emit(entity, EntityType.USERNAME, login, platform="github")
            for login in list(logins)[:MAX_USERS]
        ]
        return out + [item for item in found if item]

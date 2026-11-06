"""Perfiles y paquetes públicos del username en npm, crates.io y Docker Hub."""

from __future__ import annotations

from typing import Any

from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module, ModuleError, status_error
from osineitor.sanitize import quote_segment

MAX_PACKAGES = 20
# crates.io exige un User-Agent que identifique la herramienta, no uno de navegador.
HEADERS = {"User-Agent": "osineitor"}


class DevRegistries(Module):
    name = "dev_registries"
    description = "Perfiles y paquetes públicos en npm, crates.io y Docker Hub"
    consumes = frozenset({EntityType.USERNAME})
    produces = frozenset({EntityType.PROFILE})
    canary = "sindresorhus"
    min_interval = 1.0

    async def _json(self, url: str, **params: str) -> Any:
        response = await self.ctx.http.get(url, params=params, headers=HEADERS)
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise status_error(url.split("/")[2], response)
        return response.json()

    async def _npm(self, name: str) -> dict[str, object] | None:
        body = await self._json(
            "https://registry.npmjs.org/-/v1/search", text=f"maintainer:{name}", size="50"
        )
        packages = [
            o["package"]["name"]
            for o in (body or {}).get("objects") or []
            if any(
                str(m.get("username", "")).lower() == name.lower()
                for m in o.get("package", {}).get("maintainers") or []
            )
        ]
        if not packages:
            return None
        return {
            "url": f"https://www.npmjs.com/~{quote_segment(name)}",
            "site": "npm",
            "packages": packages[:MAX_PACKAGES],
            "package_count": len(packages),
        }

    async def _crates(self, name: str) -> dict[str, object] | None:
        body = await self._json(f"https://crates.io/api/v1/users/{quote_segment(name)}")
        user = (body or {}).get("user") or {}
        if not user.get("login"):
            return None
        return {
            "url": f"https://crates.io/users/{quote_segment(str(user['login']))}",
            "site": "crates.io",
            "name": user.get("name"),
        }

    async def _docker(self, name: str) -> dict[str, object] | None:
        user = await self._json(f"https://hub.docker.com/v2/users/{quote_segment(name)}/")
        if not isinstance(user, dict) or not user.get("username"):
            return None
        repos = await self._json(
            f"https://hub.docker.com/v2/repositories/{quote_segment(name)}/", page_size="25"
        )
        return {
            "url": f"https://hub.docker.com/u/{quote_segment(str(user['username']))}",
            "site": "Docker Hub",
            "name": user.get("full_name"),
            "company": user.get("company"),
            "location": user.get("location"),
            "created_at": user.get("date_joined"),
            "packages": [r["name"] for r in (repos or {}).get("results") or [] if r.get("name")][
                :MAX_PACKAGES
            ],
        }

    async def run(self, entity: Entity) -> list[Entity]:
        out: list[Entity] = []
        errors: list[ModuleError] = []
        for lookup in (self._npm, self._crates, self._docker):
            try:
                found = await lookup(entity.value)
            except ModuleError as exc:  # una fuente caída no debe tapar a las demás
                errors.append(exc)
                continue
            if found:
                url = str(found.pop("url"))
                if profile := self.try_emit(
                    entity, EntityType.PROFILE, url, verified=True, **found
                ):
                    out.append(profile)
        if errors and not out:
            raise errors[0]
        return out

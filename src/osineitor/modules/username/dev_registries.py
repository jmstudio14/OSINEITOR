"""Perfiles y paquetes públicos del username en npm, crates.io, Docker Hub, PyPI y Stack Overflow.

PyPI no tiene API de usuarios: se lee su página pública de perfil (sin sesión). Stack Overflow no
tiene usernames, solo nombres visibles: solo se conservan las coincidencias exactas de nombre y se
marcan `match: display_name`, porque un nombre repetido no prueba que sea la misma persona.
"""

from __future__ import annotations

import html
import re
from datetime import UTC, datetime
from typing import Any

from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module, ModuleError, status_error
from osineitor.sanitize import quote_segment

MAX_PACKAGES = 20
MAX_STACK_MATCHES = 3
PYPI_TITLE = re.compile(r"<title>\s*Profile of\s+(.+?)\s*·", re.IGNORECASE)
PYPI_NAME = re.compile(r"<h1[^>]*>(.*?)</h1>", re.IGNORECASE | re.DOTALL)
PYPI_PROJECT = re.compile(r'href="/project/([^/"]+)/"')
PACKAGE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
TAGS = re.compile(r"<[^>]+>")
# crates.io exige un User-Agent que identifique la herramienta, no uno de navegador.
HEADERS = {"User-Agent": "osineitor"}


class DevRegistries(Module):
    name = "dev_registries"
    description = (
        "Perfiles y paquetes públicos en npm, crates.io, Docker Hub, PyPI y Stack Overflow"
    )
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

    async def _pypi(self, name: str) -> dict[str, object] | None:
        url = f"https://pypi.org/user/{quote_segment(name)}/"
        response = await self.ctx.http.get(url, headers=HEADERS)
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise status_error("pypi.org", response)
        page = response.text
        title = PYPI_TITLE.search(page)
        if not title or html.unescape(title.group(1)).casefold() != name.casefold():
            return None  # no es la página de este usuario
        projects = list(
            dict.fromkeys(p for p in PYPI_PROJECT.findall(page) if PACKAGE_NAME.fullmatch(p))
        )
        shown = PYPI_NAME.search(page)
        display = html.unescape(TAGS.sub("", shown.group(1))).strip()[:100] if shown else ""
        return {
            "url": url,
            "site": "PyPI",
            "name": display if display.casefold() != name.casefold() else None,
            "packages": projects[:MAX_PACKAGES],
            "package_count": len(projects),
        }

    async def _stack(self, name: str) -> list[dict[str, object]]:
        body = await self._json(
            "https://api.stackexchange.com/2.3/users",
            inname=name,
            site="stackoverflow",
            pagesize="30",
        )
        matches = [
            u
            for u in (body or {}).get("items") or []
            if isinstance(u, dict)
            and str(u.get("display_name", "")).casefold() == name.casefold()
            and u.get("link")
        ][:MAX_STACK_MATCHES]
        return [
            {
                "url": str(u["link"]),
                "site": "Stack Overflow",
                "display_name": u.get("display_name"),
                "reputation": u.get("reputation"),
                "location": u.get("location") or None,
                "created_at": datetime.fromtimestamp(u["creation_date"], UTC).isoformat()
                if isinstance(u.get("creation_date"), int)
                else None,
                "match": "display_name",
            }
            for u in matches
        ]

    async def run(self, entity: Entity) -> list[Entity]:
        out: list[Entity] = []
        errors: list[ModuleError] = []
        lookups = (self._npm, self._crates, self._docker, self._pypi, self._stack)
        for lookup in lookups:
            try:
                found = await lookup(entity.value)
            except ModuleError as exc:  # una fuente caída no debe tapar a las demás
                errors.append(exc)
                continue
            for item in found if isinstance(found, list) else [found] if found else []:
                url = str(item.pop("url"))
                # Stack Overflow solo coincide por nombre: no se marca como verificado.
                data = item if item.get("match") else {"verified": True, **item}
                if profile := self.try_emit(entity, EntityType.PROFILE, url, **data):
                    out.append(profile)
        if errors and not out:
            raise errors[0]
        return out

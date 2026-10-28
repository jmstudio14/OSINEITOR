"""Subdominios a partir de los logs de Certificate Transparency (crt.sh)."""

from __future__ import annotations

import httpx

from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module, ModuleError
from osineitor.modules.domain._util import is_root_domain

MAX_SUBDOMAINS = 500


class CrtSh(Module):
    name = "crtsh"
    description = "Subdominios desde Certificate Transparency (crt.sh)"
    consumes = frozenset({EntityType.DOMAIN})
    produces = frozenset({EntityType.DOMAIN})

    def accepts(self, entity: Entity) -> bool:
        return is_root_domain(entity)

    async def run(self, entity: Entity) -> list[Entity]:
        domain = entity.value.lower()
        try:
            response = await self.ctx.http.get(
                "https://crt.sh/", params={"q": f"%.{domain}", "output": "json"}, timeout=60
            )
        except httpx.TimeoutException as exc:
            raise ModuleError("crt.sh no respondió a tiempo (suele estar saturado)") from exc
        if response.status_code != 200:
            raise ModuleError(f"crt.sh respondió {response.status_code}")

        names: set[str] = set()
        for cert in response.json():
            for name in str(cert.get("name_value", "")).splitlines():
                name = name.strip().lower().removeprefix("*.")
                if name.endswith(f".{domain}") and " " not in name:
                    names.add(name)
        return [
            self.emit(entity, EntityType.DOMAIN, name, subdomain=True)
            for name in sorted(names)[:MAX_SUBDOMAINS]
        ]

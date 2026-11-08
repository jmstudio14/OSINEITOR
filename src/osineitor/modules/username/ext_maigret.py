"""Cuentas de un username con Maigret (herramienta externa que escribe su informe en un fichero)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from osineitor.errors import ModuleError
from osineitor.models import URL_RE, Entity, EntityType
from osineitor.modules._external import ExternalToolModule
from osineitor.tool_import import MAX_BYTES, claimed

MAX_PROFILES = 500


class ExtMaigret(ExternalToolModule):
    name = "ext_maigret"
    description = "Cuentas de un username con Maigret, sin recursión (binario del usuario)"
    consumes = frozenset({EntityType.USERNAME})
    produces = frozenset({EntityType.PROFILE})
    binary = "maigret"
    canary = "octocat"
    timeout = 600.0  # Maigret comprueba cientos de sitios

    def args(self, entity: Entity, folder: str = "reports") -> list[str]:
        # `--no-recursion` y `--no-extracting`: no investiga por su cuenta otros usernames de las
        # páginas; de los pivotes se encarga el motor. El informe va a `folder`, no a stdout.
        return [
            "--json",
            "simple",
            "-fo",
            folder,
            "--no-progressbar",
            "--no-color",
            "--no-recursion",
            "--no-extracting",
            "--",
            entity.value,
        ]

    def parse(self, entity: Entity, documents: list[Any]) -> list[Entity]:
        found: dict[str, Entity] = {}
        for doc in documents:
            for site, entry in doc.items() if isinstance(doc, dict) else []:
                if not isinstance(entry, dict) or not claimed(entry):
                    continue
                url = str(entry.get("url_user") or "").strip()
                if URL_RE.match(url) and (
                    profile := self.try_emit(
                        entity, EntityType.PROFILE, url, site=str(site), via="maigret"
                    )
                ):
                    found.setdefault(profile.key, profile)
        return list(found.values())[:MAX_PROFILES]

    async def run(self, entity: Entity) -> list[Entity]:
        path = self._executable(entity)
        with tempfile.TemporaryDirectory(prefix="osineitor-maigret-") as folder:
            await self._exec([path, *self.args(entity, folder)])
            report = Path(folder, f"report_{entity.value}_simple.json")
            if not report.is_file():
                raise ModuleError("maigret no escribió el informe esperado")
            if report.stat().st_size > MAX_BYTES:
                raise ModuleError("el informe de maigret es demasiado grande")
            try:
                document = json.loads(report.read_text(encoding="utf-8"))
            except ValueError as exc:
                raise ModuleError("el informe de maigret no es JSON válido") from exc
        return self.parse(entity, [document])

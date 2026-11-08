"""Metadatos de los documentos públicos de un dominio (activo: los descarga del objetivo).

Dos pasos, uno por nivel de pivoteo: el dominio da las URLs de documentos del histórico de Wayback,
y cada URL marcada como documento (también las de `search_dorks`) se descarga y se analiza. El
documento pasa por un fichero temporal que se borra al terminar: solo se guardan sus metadatos.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import tempfile
from typing import Any

import httpx

from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module, ModuleError, status_error
from osineitor.modules.domain._util import is_root_domain
from osineitor.modules.files.meta import metadata_entities, read_metadata

CDX = "https://web.archive.org/cdx/search/cdx"
# Por tipo MIME: en la prueba real, filtrar por extensión con `(?i)` hizo que el CDX diera 504.
DOCUMENTS = r"application/(pdf|vnd\.openxmlformats-officedocument\..*|vnd\.oasis\.opendocument\..*)"
MAX_DOCUMENTS = 20


def _read_bytes(body: bytes) -> dict[str, Any]:
    descriptor, path = tempfile.mkstemp(prefix="osineitor-doc-")
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(body)
        return read_metadata(path)
    finally:
        os.unlink(path)


class DocHarvest(Module):
    name = "doc_harvest"
    description = "Descarga documentos públicos del dominio y extrae sus metadatos (activo)"
    consumes = frozenset({EntityType.DOMAIN, EntityType.URL})
    produces = frozenset({EntityType.URL, EntityType.RECORD, EntityType.LOCATION})
    passive = False
    canary = "example.com"
    min_interval = 1.0
    timeout = 240.0

    def accepts(self, entity: Entity) -> bool:
        return is_root_domain(entity) or (
            entity.type == EntityType.URL and bool(entity.data.get("document"))
        )

    async def _discover(self, entity: Entity) -> list[Entity]:
        try:
            response = await self.ctx.http.get(
                CDX,
                params={
                    "url": f"{entity.value}/*",  # con `matchType=domain` el CDX agota el tiempo
                    "output": "json",
                    "fl": "original",
                    "collapse": "urlkey",
                    "filter": f"mimetype:{DOCUMENTS}",
                    "limit": str(MAX_DOCUMENTS),
                },
                timeout=60,
            )
        except httpx.TimeoutException as exc:
            raise ModuleError("web.archive.org no respondió a tiempo") from exc
        if response.status_code != 200:
            raise status_error("web.archive.org", response)
        rows = response.json()[1:] if response.text.strip() else []
        found = (self.try_emit(entity, EntityType.URL, row[0], document=True) for row in rows)
        return [item for item in found if item]

    async def _harvest(self, entity: Entity) -> list[Entity]:
        response = await self.ctx.http.get(entity.value)
        if response.status_code != 200:  # un documento histórico que ya no está
            return []
        body = response.content
        found = await asyncio.to_thread(_read_bytes, body)
        return metadata_entities(
            self,
            entity,
            f"doc_harvest:{entity.value}",
            found,
            sha256=hashlib.sha256(body).hexdigest(),
            size=len(body),
        )

    async def run(self, entity: Entity) -> list[Entity]:
        if entity.type == EntityType.DOMAIN:
            return await self._discover(entity)
        return await self._harvest(entity)

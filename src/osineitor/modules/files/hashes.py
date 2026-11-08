"""MD5, SHA-1 y SHA-256 de un fichero local. El contenido nunca sale del equipo."""

from __future__ import annotations

import asyncio
import hashlib
import os
from pathlib import Path

from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module, ModuleSkipped

CHUNK = 1024 * 1024


def hash_file(path: str) -> tuple[int, dict[str, str]]:
    """(tamaño, {algoritmo: huella}) leyendo el fichero por bloques."""
    digests = {name: hashlib.new(name) for name in ("md5", "sha1", "sha256")}
    size = 0
    with open(path, "rb") as handle:
        while chunk := handle.read(CHUNK):
            size += len(chunk)
            for digest in digests.values():
                digest.update(chunk)
    return size, {name: digest.hexdigest() for name, digest in digests.items()}


class FileHash(Module):
    name = "file_hash"
    description = "MD5, SHA-1 y SHA-256 de un fichero local (sin red)"
    consumes = frozenset({EntityType.FILE})
    produces = frozenset({EntityType.RECORD})
    canary = str(Path(__file__).resolve())  # su propio código fuente: existe siempre

    async def run(self, entity: Entity) -> list[Entity]:
        if not os.path.isfile(entity.value):
            raise ModuleSkipped("el fichero no existe en este equipo")
        size, hashes = await asyncio.to_thread(hash_file, entity.value)
        return [
            self.emit(
                entity, EntityType.RECORD, f"file_hash:{hashes['sha256']}", size=size, **hashes
            )
        ]

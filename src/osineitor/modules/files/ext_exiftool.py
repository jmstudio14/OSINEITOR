"""Metadatos con ExifTool (binario del usuario) para formatos que `file_meta` no cubre.

Se lee en local: ni el fichero ni sus metadatos salen del equipo.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from osineitor.models import Entity, EntityType
from osineitor.modules._external import ExternalToolModule, json_documents
from osineitor.modules.base import ModuleError, ModuleSkipped

MAX_FIELDS = 100
MAX_VALUE = 500
# Datos del sistema de archivos del analista, no del documento.
LOCAL_FIELDS = frozenset(
    {
        "SourceFile",
        "File:Directory",
        "File:FileName",
        "File:FileAccessDate",
        "File:FileCreateDate",
        "File:FileModifyDate",
        "File:FilePermissions",
    }
)


class ExtExifTool(ExternalToolModule):
    name = "ext_exiftool"
    description = "Metadatos con ExifTool de formatos que file_meta no cubre (binario del usuario)"
    consumes = frozenset({EntityType.FILE})
    produces = frozenset({EntityType.RECORD, EntityType.LOCATION})
    binary = "exiftool"
    version_args = ("-ver",)
    ok_exit_codes = (0, 1)  # 1 también es un formato desconocido, que sí imprime su JSON
    direct_dns = False  # no usa la red: no hay nada que enrutar por --proxy
    timeout = 60.0
    canary = str(Path(__file__).resolve())  # su propio código fuente: existe siempre

    def args(self, entity: Entity) -> list[str]:
        # En Windows, Perl recibe `argv` en ANSI y no encuentra una ruta con otros caracteres: la
        # ruta va en UTF-8 por la entrada estándar (`-@ -`), donde además no puede ser una opción.
        return ["-j", "-G", "-n", "-charset", "filename=utf8", "-@", "-"]

    def parse(self, entity: Entity, documents: list[Any]) -> list[Entity]:
        docs = [d for group in documents for d in (group if isinstance(group, list) else [group])]
        if not docs or not isinstance(docs[0], dict):  # el código 1 de un fichero ilegible
            raise ModuleError("ExifTool no devolvió metadatos del fichero")
        tags = docs[0]
        kept = {
            name: value[:MAX_VALUE] if isinstance(value, str) else value
            for name, value in tags.items()
            if name not in LOCAL_FIELDS and not name.startswith("ExifTool:")
        }
        if all(name.startswith("File:") for name in kept):  # sin metadatos del documento
            return []
        fields = dict(list(kept.items())[:MAX_FIELDS])
        out = [self.emit(entity, EntityType.RECORD, f"ext_exiftool:{entity.value}", **fields)]
        latitude, longitude = kept.get("Composite:GPSLatitude"), kept.get("Composite:GPSLongitude")
        if isinstance(latitude, int | float) and isinstance(longitude, int | float):
            location = self.try_emit(
                entity,
                EntityType.LOCATION,
                f"{latitude:.6f},{longitude:.6f}",
                source_field="exiftool_gps",
            )
            if location:
                out.append(location)
        return out

    async def run(self, entity: Entity) -> list[Entity]:
        if not os.path.isfile(entity.value):
            raise ModuleSkipped("el fichero no existe en este equipo")
        path = self._executable(entity)
        stdout = await self._exec(
            [path, *self.args(entity)], stdin=os.path.abspath(entity.value).encode() + b"\n"
        )
        return self.parse(entity, json_documents(stdout))

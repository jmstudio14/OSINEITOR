"""Metadatos de un fichero local: EXIF de JPEG, Info de PDF y propiedades de Office y OpenDocument.

Todo se lee en local con la biblioteca estándar; el contenido nunca sale del equipo. Alcance:
JPEG con EXIF (cámara, software, fecha, autor y GPS), PDF con diccionario Info en texto claro
(no los que lo guardan en flujos comprimidos ni el XMP), y DOCX, XLSX, PPTX, ODT, ODS y ODP.
"""

from __future__ import annotations

import asyncio
import os
import re
import struct
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module, ModuleError, ModuleSkipped

HEAD = 512 * 1024  # el EXIF y el Info de un PDF lineal están al principio...
TAIL = 64 * 1024  # ...y el de un PDF normal, en el tráiler
MAX_MEMBER = 1024 * 1024  # tope de lo que se lee de un miembro del zip (bomba de descompresión)
MAX_VALUE = 500

# --- EXIF ------------------------------------------------------------------------------------

IFD0_TAGS = {0x010F: "camera_make", 0x0110: "camera_model", 0x0131: "software", 0x013B: "author"}
IFD0_TAGS |= {0x0132: "modified", 0x8298: "copyright"}
EXIF_TAGS = {0x9003: "created", 0xA430: "owner", 0xA431: "body_serial", 0xA435: "lens_serial"}
TYPE_SIZE = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 7: 1}


def _exif_segment(data: bytes) -> bytes | None:
    """El bloque TIFF del primer segmento APP1 «Exif» de un JPEG."""
    position = 2
    while position + 4 <= len(data) and data[position] == 0xFF:
        marker = data[position + 1]
        (length,) = struct.unpack(">H", data[position + 2 : position + 4])
        if marker == 0xE1 and data[position + 4 : position + 10] == b"Exif\x00\x00":
            return data[position + 10 : position + 2 + length]
        if marker == 0xDA:  # inicio de la imagen: ya no hay más cabeceras
            return None
        position += 2 + length
    return None


def _ifd(tiff: bytes, offset: int, order: str) -> dict[int, tuple[int, int, bytes]]:
    """{etiqueta: (tipo, nº de valores, bytes del valor)} de un directorio IFD."""
    entries: dict[int, tuple[int, int, bytes]] = {}
    if offset + 2 > len(tiff):
        return entries
    (count,) = struct.unpack(f"{order}H", tiff[offset : offset + 2])
    for i in range(min(count, 200)):
        raw = tiff[offset + 2 + i * 12 : offset + 14 + i * 12]
        if len(raw) < 12:
            break
        tag, kind, number = struct.unpack(f"{order}HHI", raw[:8])
        size = TYPE_SIZE.get(kind, 0) * number
        if size <= 4:
            value = raw[8 : 8 + size]
        else:
            (pointer,) = struct.unpack(f"{order}I", raw[8:12])
            value = tiff[pointer : pointer + size]
        if len(value) == size:
            entries[tag] = (kind, number, value)
    return entries


def _text(entry: tuple[int, int, bytes]) -> str | None:
    if entry[0] != 2:
        return None
    return entry[2].split(b"\x00")[0].decode("utf-8", "replace").strip() or None


def _degrees(entry: tuple[int, int, bytes], order: str) -> float | None:
    if entry[0] != 5 or entry[1] != 3:
        return None
    parts = struct.unpack(f"{order}6I", entry[2])
    try:
        d, m, s = (parts[i] / parts[i + 1] for i in (0, 2, 4))
    except ZeroDivisionError:
        return None
    return d + m / 60 + s / 3600


def parse_exif(data: bytes) -> dict[str, Any]:
    tiff = _exif_segment(data)
    if not tiff or tiff[:2] not in (b"II", b"MM"):
        return {}
    order = "<" if tiff[:2] == b"II" else ">"
    (first,) = struct.unpack(f"{order}I", tiff[4:8])
    ifd0 = _ifd(tiff, first, order)
    found: dict[str, Any] = {
        name: _text(ifd0[tag]) for tag, name in IFD0_TAGS.items() if tag in ifd0
    }
    if 0x8769 in ifd0:
        (pointer,) = struct.unpack(f"{order}I", ifd0[0x8769][2])
        sub = _ifd(tiff, pointer, order)
        found |= {name: _text(sub[tag]) for tag, name in EXIF_TAGS.items() if tag in sub}
    if 0x8825 in ifd0:
        (pointer,) = struct.unpack(f"{order}I", ifd0[0x8825][2])
        gps = _ifd(tiff, pointer, order)
        if {1, 2, 3, 4} <= gps.keys():
            lat, lon = _degrees(gps[2], order), _degrees(gps[4], order)
            if lat is not None and lon is not None:
                found["gps"] = (
                    -lat if _text(gps[1]) == "S" else lat,
                    -lon if _text(gps[3]) == "W" else lon,
                )
    return {key: value for key, value in found.items() if value is not None}


# --- PDF -------------------------------------------------------------------------------------

PDF_KEYS = {
    "Title": "title",
    "Author": "author",
    "Subject": "subject",
    "Keywords": "keywords",
    "Creator": "software",
    "Producer": "producer",
    "CreationDate": "created",
    "ModDate": "modified",
}
PDF_VALUE = r"(\((?:\\.|[^\\)])*\)|<[0-9A-Fa-f\s]*>)"
ESCAPES = {b"n": b"\n", b"r": b"\r", b"t": b"\t", b"b": b"\b", b"f": b"\f"}


def _pdf_string(token: bytes) -> str:
    if token.startswith(b"<"):
        hexa = re.sub(rb"\s", b"", token[1:-1])
        raw = bytes.fromhex((hexa + b"0" * (len(hexa) % 2)).decode())
    else:
        body = token[1:-1]
        raw = re.sub(
            rb"\\([0-7]{1,3}|.)",
            lambda m: (
                bytes([int(m[1], 8) & 255]) if m[1][:1].isdigit() else ESCAPES.get(m[1], m[1])
            ),
            body,
        )
    if raw.startswith(b"\xfe\xff"):
        return raw[2:].decode("utf-16-be", "replace")
    return raw.decode("latin-1")


def _pdf_date(value: str) -> str:
    """`D:20240131120000+01'00'` → `2024-01-31T12:00:00` (sin zona horaria)."""
    match = re.match(r"D:(\d{4})(\d{2})?(\d{2})?(\d{2})?(\d{2})?(\d{2})?", value)
    if not match:
        return value
    year, month, day, hour, minute, second = (
        group or default
        for group, default in zip(match.groups(), ("", "01", "01", "00", "00", "00"), strict=True)
    )
    return f"{year}-{month}-{day}T{hour}:{minute}:{second}"


def parse_pdf(head: bytes, tail: bytes) -> dict[str, Any]:
    found: dict[str, Any] = {}
    for key, name in PDF_KEYS.items():
        pattern = re.compile(rb"/" + key.encode() + rb"\s*" + PDF_VALUE.encode())
        # El último ejemplar manda: una actualización incremental sustituye al Info anterior.
        matches = pattern.findall(head) + pattern.findall(tail)
        if matches:
            text = _pdf_string(matches[-1]).strip("\x00 ")
            found[name] = _pdf_date(text) if name in ("created", "modified") else text
    return {k: v for k, v in found.items() if v}


# --- Office y OpenDocument -------------------------------------------------------------------

OOXML = {
    "docProps/core.xml": {
        "creator": "author",
        "lastModifiedBy": "last_modified_by",
        "created": "created",
        "modified": "modified",
        "title": "title",
        "subject": "subject",
        "keywords": "keywords",
    },
    "docProps/app.xml": {
        "Application": "software",
        "AppVersion": "software_version",
        "Company": "company",
        "Manager": "manager",
        "Template": "template",
    },
}
ODF = {
    "initial-creator": "author",
    "creator": "last_modified_by",
    "creation-date": "created",
    "date": "modified",
    "generator": "software",
    "title": "title",
}


def _xml_fields(raw: bytes, names: dict[str, str]) -> dict[str, Any]:
    # Un DOCTYPE o una entidad en un fichero ajeno es un intento de expansión de entidades.
    if re.search(rb"<!(DOCTYPE|ENTITY)", raw, re.IGNORECASE):
        raise ModuleError("el XML del fichero declara entidades: no se analiza")
    found: dict[str, Any] = {}
    for element in ElementTree.fromstring(raw).iter():
        local = element.tag.rsplit("}", 1)[-1]
        if local in names and (element.text or "").strip():
            found.setdefault(names[local], element.text.strip())
    return found


def parse_zip(path: str) -> dict[str, Any]:
    with zipfile.ZipFile(path) as archive:
        members = set(archive.namelist())

        def read(name: str) -> bytes:
            with archive.open(name) as handle:
                return handle.read(MAX_MEMBER)

        found: dict[str, Any] = {}
        if "docProps/core.xml" in members or "docProps/app.xml" in members:
            found["format"] = "ooxml"
            for member, names in OOXML.items():
                if member in members:
                    found |= _xml_fields(read(member), names)
        elif "meta.xml" in members and "mimetype" in members:
            found["format"] = "opendocument"
            found |= _xml_fields(read("meta.xml"), ODF)
        return found


# --- Módulo ----------------------------------------------------------------------------------


def read_metadata(path: str) -> dict[str, Any]:
    with open(path, "rb") as handle:
        head = handle.read(HEAD)
        size = os.fstat(handle.fileno()).st_size
        handle.seek(max(size - TAIL, 0))
        tail = handle.read(TAIL)
    if head.startswith(b"\xff\xd8"):
        return {"format": "jpeg", **parse_exif(head)}
    if head.startswith(b"%PDF"):
        return {"format": "pdf", **parse_pdf(head, tail)}
    if head.startswith(b"PK\x03\x04"):
        try:
            return parse_zip(path)
        except zipfile.BadZipFile as exc:
            raise ModuleError("el fichero zip está dañado") from exc
        except ElementTree.ParseError as exc:
            raise ModuleError("el XML de los metadatos no es válido") from exc
    return {}


class FileMeta(Module):
    name = "file_meta"
    description = "Metadatos de un fichero local: EXIF, PDF, Office y OpenDocument (sin red)"
    consumes = frozenset({EntityType.FILE})
    produces = frozenset({EntityType.RECORD, EntityType.LOCATION})
    canary = str(Path(__file__).resolve())  # su propio código fuente: existe, aunque sin metadatos

    async def run(self, entity: Entity) -> list[Entity]:
        if not os.path.isfile(entity.value):
            raise ModuleSkipped("el fichero no existe en este equipo")
        found = await asyncio.to_thread(read_metadata, entity.value)
        if len(found) <= 1:  # solo el formato, o nada: sin metadatos que informar
            return []
        gps = found.pop("gps", None)
        data = {k: (v[:MAX_VALUE] if isinstance(v, str) else v) for k, v in found.items()}
        out = [self.emit(entity, EntityType.RECORD, f"file_meta:{entity.value}", **data)]
        if gps:
            location = self.try_emit(
                entity, EntityType.LOCATION, f"{gps[0]:.6f},{gps[1]:.6f}", source_field="exif_gps"
            )
            if location:
                out.append(location)
        return out

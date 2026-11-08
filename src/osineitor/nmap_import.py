"""Importa un XML de Nmap (`-oX`) como un scan guardado: solo lee un fichero, no ejecuta Nmap."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path
from xml.etree import ElementTree

from pydantic import ValidationError

from osineitor.models import Entity, EntityType, ModuleRun, Observation, ScanEvent, ScanResult

MODULE = "import_nmap"
MAX_XML_BYTES = 32 * 1024 * 1024
MAX_TEXT = 300
MAX_CPE = 10


class NmapImportError(Exception):
    """El fichero no se puede leer o no es un XML de Nmap utilizable."""


def _clip(value: str | None) -> str | None:
    return value.strip()[:MAX_TEXT] if value and value.strip() else None


def _entity(
    parent: str, etype: EntityType, value: str, query: str, data: dict[str, object]
) -> Entity:
    return Entity(
        type=etype,
        value=value,
        data=data,
        source=MODULE,
        parent=parent,
        observations=[Observation(module=MODULE, query=query)],
    )


def _service_data(port: ElementTree.Element, portid: int) -> dict[str, object]:
    data: dict[str, object] = {"port": portid, "transport": port.get("protocol")}
    if (service := port.find("service")) is not None:
        for field in ("name", "product", "version", "extrainfo", "tunnel"):
            data[field] = _clip(service.get(field))
        cpes = [_clip(c.text) for c in service.findall("cpe")]
        data["cpe"] = [c for c in cpes if c][:MAX_CPE]
    return {k: v for k, v in data.items() if v not in (None, [])}


def _read(path: Path) -> bytes:
    try:
        if path.stat().st_size > MAX_XML_BYTES:
            raise NmapImportError(
                f"el fichero es demasiado grande (máximo {MAX_XML_BYTES // 1024 // 1024} MiB)"
            )
        return path.read_bytes()
    except OSError as exc:
        raise NmapImportError(f"no se puede leer {path.name}: {exc.strerror or exc}") from exc


def _parse_xml(raw: bytes) -> ElementTree.Element:
    # Un DOCTYPE o una entidad en un fichero ajeno es un intento de expansión de entidades.
    if re.search(rb"<!(DOCTYPE|ENTITY)", raw, re.IGNORECASE):
        raise NmapImportError("el XML contiene un DOCTYPE o entidades, que no se admiten")
    try:
        root = ElementTree.fromstring(raw)
    except ElementTree.ParseError as exc:
        raise NmapImportError(f"XML no válido: {exc}") from exc
    if root.tag != "nmaprun":
        raise NmapImportError("no es un XML de Nmap (falta el elemento <nmaprun>)")
    return root


def parse_nmap(path: Path) -> ScanResult:
    """Hosts activos, sus nombres y sus puertos abiertos de un XML de Nmap, como un `ScanResult`.

    El objetivo es un `record` con la huella SHA-256 del fichero; la línea de comandos de Nmap
    (`args`) no se guarda porque puede llevar credenciales. Lo que no es válido se descarta y se
    cuenta en un evento, no en silencio.
    """
    raw = _read(path)
    root = _parse_xml(raw)
    target = Entity(
        type=EntityType.RECORD,
        value=f"nmap:{path.name}",
        data={
            "sha256": hashlib.sha256(raw).hexdigest(),
            "nmap_version": _clip(root.get("version")),
        },
    )
    entities: dict[str, Entity] = {}
    discarded = 0
    hosts_up = 0

    def add(entity: Entity) -> None:
        entities.setdefault(entity.key, entity)

    for host in root.findall("host"):
        status = host.find("status")
        if status is None or status.get("state") != "up":
            continue
        hosts_up += 1
        address = next(
            (
                a.get("addr")
                for a in host.findall("address")
                if a.get("addrtype") in ("ipv4", "ipv6")
            ),
            None,
        )
        try:
            ip = _entity(target.key, EntityType.IP, address or "", target.key, {})
        except ValidationError:
            discarded += 1
            continue
        add(ip)
        for hostname in host.findall("hostnames/hostname"):
            try:
                add(
                    _entity(
                        ip.key,
                        EntityType.DOMAIN,
                        hostname.get("name") or "",
                        ip.key,
                        {"hostname_type": _clip(hostname.get("type"))},
                    )
                )
            except ValidationError:
                discarded += 1
        for port in host.findall("ports/port"):
            state = port.find("state")
            if state is None or state.get("state") != "open":
                continue
            try:
                portid = int(port.get("portid", ""))
                if not 0 < portid < 65536:
                    raise ValueError(portid)
            except ValueError:
                discarded += 1
                continue
            add(
                _entity(
                    ip.key,
                    EntityType.SERVICE,
                    f"{ip.value}:{portid}",
                    ip.key,
                    _service_data(port, portid),
                )
            )
    target.data["hosts_up"] = hosts_up
    found = list(entities.values())
    events = []
    if discarded:
        events.append(
            ScanEvent(
                kind="skipped",
                module=MODULE,
                message=f"{discarded} valores descartados por no ser válidos (IP, host o puerto)",
            )
        )
    return ScanResult(
        target=target,
        depth=1,
        finished_at=datetime.now(UTC),
        entities=found,
        events=events,
        runs=[
            ModuleRun(
                module=MODULE,
                status="ok" if found else "empty",
                entity=target.key,
                entities=len(found),
            )
        ],
    )

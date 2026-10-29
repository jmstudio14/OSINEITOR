"""Eventos del contrato CLI↔GUI (docs/CLI_CONTRACT.md), interpretados con tolerancia.

La CLI solo cambia de forma aditiva, así que aquí se ignora lo que no se conoce: campos nuevos,
tipos de evento nuevos y líneas que no son JSON no rompen nada.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

SUPPORTED_VERSION = 1

# Códigos de salida de la CLI (un test los compara con osineitor.events).
EXIT_OK = 0
EXIT_INTERNAL = 1
EXIT_USAGE = 2
EXIT_MODULE_ERRORS = 3
EXIT_TRUNCATED = 4
EXIT_CANCELLED = 130


@dataclass(frozen=True)
class ScanStart:
    target_type: str
    target_value: str
    depth: int
    modules: list[str]
    skipped: list[dict[str, str]]
    budget: dict[str, Any]
    ts: str = ""


@dataclass(frozen=True)
class ModuleStart:
    module: str
    entity: str
    ts: str = ""


@dataclass(frozen=True)
class ModuleEnd:
    module: str
    status: str  # ok | empty | error | quota | skipped
    entity: str
    entities: int = 0
    requests: int = 0
    cache_hits: int = 0
    duration_ms: int = 0
    message: str = ""
    ts: str = ""


@dataclass(frozen=True)
class EntityFound:
    entity: dict[str, Any]
    ts: str = ""


@dataclass(frozen=True)
class Progress:
    done: int
    total: int
    entities: int
    requests: int
    ts: str = ""


@dataclass(frozen=True)
class Notice:
    code: str
    message: str
    ts: str = ""


@dataclass(frozen=True)
class ScanEnd:
    status: str  # complete | truncated | cancelled | failed
    scan_id: int | None
    exit_code: int
    entities: int = 0
    message: str = ""
    ts: str = ""


@dataclass(frozen=True)
class UnknownEvent:
    """Evento de un tipo que esta versión no conoce: se ignora."""

    type: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FutureVersion:
    """Evento de una versión del contrato posterior a la soportada."""

    version: int
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RawLine:
    """Línea de stdout que no es un evento JSON (no debería ocurrir con `--ndjson`)."""

    text: str


Event = (
    ScanStart
    | ModuleStart
    | ModuleEnd
    | EntityFound
    | Progress
    | Notice
    | ScanEnd
    | UnknownEvent
    | FutureVersion
    | RawLine
)


def _int(value: Any, default: int = 0) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def parse_event(line: str | bytes) -> Event | None:
    """Interpreta una línea de stdout. `None` si está vacía."""
    if isinstance(line, bytes):
        line = line.decode("utf-8", errors="replace")
    line = line.strip()
    if not line:
        return None
    try:
        data = json.loads(line)
    except ValueError:
        return RawLine(line)
    if not isinstance(data, dict) or not isinstance(data.get("type"), str):
        return RawLine(line)
    version = _int(data.get("v"), 1)
    if version > SUPPORTED_VERSION:
        return FutureVersion(version, data)
    ts = str(data.get("ts") or "")
    kind = data["type"]
    if kind == "scan.start":
        target = data.get("target") or {}
        return ScanStart(
            target_type=str(target.get("type", "")),
            target_value=str(target.get("value", "")),
            depth=_int(data.get("depth"), 1),
            modules=[str(m) for m in data.get("modules") or []],
            skipped=[s for s in data.get("skipped") or [] if isinstance(s, dict)],
            budget=data.get("budget") or {},
            ts=ts,
        )
    if kind == "module.start":
        return ModuleStart(str(data.get("module", "")), str(data.get("entity", "")), ts)
    if kind == "module.end":
        return ModuleEnd(
            module=str(data.get("module", "")),
            status=str(data.get("status", "")),
            entity=str(data.get("entity", "")),
            entities=_int(data.get("entities")),
            requests=_int(data.get("requests")),
            cache_hits=_int(data.get("cache_hits")),
            duration_ms=_int(data.get("duration_ms")),
            message=str(data.get("message") or ""),
            ts=ts,
        )
    if kind == "entity" and isinstance(data.get("entity"), dict):
        return EntityFound(data["entity"], ts)
    if kind == "progress":
        return Progress(
            _int(data.get("done")),
            _int(data.get("total")),
            _int(data.get("entities")),
            _int(data.get("requests")),
            ts,
        )
    if kind == "notice":
        return Notice(str(data.get("code", "")), str(data.get("message", "")), ts)
    if kind == "scan.end":
        scan_id = data.get("scan_id")
        return ScanEnd(
            status=str(data.get("status", "")),
            scan_id=scan_id if isinstance(scan_id, int) else None,
            exit_code=_int(data.get("exit_code")),
            entities=_int(data.get("entities")),
            message=str(data.get("message") or ""),
            ts=ts,
        )
    return UnknownEvent(kind, data)

"""Importa resultados de otras herramientas como un scan guardado: Subfinder y Maigret.

Solo lee un fichero: no ejecuta la herramienta ni contacta con nadie. Como con Nmap
(`nmap_import.py`), lo importado no pivota ni lleva confianza: son datos de un tercero que
OSINEITOR no ha comprobado (por eso los perfiles de Maigret no llevan `verified`).

Formatos (verificados en el código fuente de cada herramienta):

- Subfinder `-oJ`: un objeto JSON por línea con `host`, `input` y `source` (o `sources`); con `-ip`
  añade `ip`.
- Maigret `--json simple`: un único objeto `{sitio: {username, url_user, status, ...}}`.
  Maigret `--json ndjson`: un objeto por línea con las mismas claves más `sitename`. Maigret solo
  escribe las cuentas que ha dado por encontradas.

No se importa Amass: su salida JSON cambió entre versiones y no hay una especificación estable que
comprobar, así que se prefiere no leer en silencio un formato que no se ha verificado.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from osineitor.errors import InvalidEntityValue
from osineitor.models import (
    URL_RE,
    Entity,
    EntityType,
    ModuleRun,
    Observation,
    ScanEvent,
    ScanResult,
)
from osineitor.normalize import canonical_hostname

MAX_BYTES = 32 * 1024 * 1024
MAX_TEXT = 300
MAX_SOURCES = 20
MAX_INPUTS = 20


class ToolImportError(Exception):
    """El fichero no se puede leer o no es una salida utilizable de la herramienta."""


def _read(path: Path) -> bytes:
    try:
        if path.stat().st_size > MAX_BYTES:
            raise ToolImportError(
                f"el fichero es demasiado grande (máximo {MAX_BYTES // 1024 // 1024} MiB)"
            )
        return path.read_bytes()
    except OSError as exc:
        raise ToolImportError(f"no se puede leer {path.name}: {exc.strerror or exc}") from exc


def _text(value: object) -> str | None:
    return value.strip()[:MAX_TEXT] if isinstance(value, str) and value.strip() else None


def _entity(
    module: str, parent: str, etype: EntityType, value: str, data: dict[str, object]
) -> Entity:
    return Entity(
        type=etype,
        value=value,
        data={k: v for k, v in data.items() if v not in (None, [], "")},
        source=module,
        parent=parent,
        observations=[Observation(module=module, query=parent)],
    )


def _result(
    module: str, target: Entity, found: list[Entity], discarded: int, what: str
) -> ScanResult:
    events = []
    if discarded:
        events.append(
            ScanEvent(
                kind="skipped",
                module=module,
                message=f"{discarded} {what} descartados por no ser válidos",
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
                module=module,
                status="ok" if found else "empty",
                entity=target.key,
                entities=len(found),
            )
        ],
    )


def _lines(raw: bytes) -> list[str]:
    return [line for line in raw.decode("utf-8", errors="replace").splitlines() if line.strip()]


def parse_subfinder(path: Path) -> ScanResult:
    """Subdominios (y las IP, si el fichero las trae) de una salida `subfinder -oJ`."""
    module = "import_subfinder"
    raw = _read(path)
    entities: dict[str, Entity] = {}
    inputs: set[str] = set()
    discarded = 0
    target = Entity(
        type=EntityType.RECORD,
        value=f"subfinder:{path.name}",
        data={"sha256": hashlib.sha256(raw).hexdigest()},
    )
    parsed = 0
    for line in _lines(raw):
        try:
            item = json.loads(line)
        except ValueError:
            discarded += 1
            continue
        if not isinstance(item, dict) or not isinstance(item.get("host"), str):
            discarded += 1
            continue
        try:
            host = canonical_hostname(item["host"])
            domain = _entity(
                module,
                target.key,
                EntityType.DOMAIN,
                host,
                {"subdomain": True, "sources": _sources(item)},
            )
        except (InvalidEntityValue, ValidationError):
            discarded += 1
            continue
        parsed += 1
        if root := _text(item.get("input")):
            inputs.add(root.lower())
        domain = entities.setdefault(domain.key, domain)
        if ip_value := _text(item.get("ip")):
            try:
                ip = _entity(module, domain.key, EntityType.IP, ip_value, {})
            except ValidationError:
                discarded += 1
            else:
                entities.setdefault(ip.key, ip)
    if not parsed:
        raise ToolImportError(
            "no es una salida de Subfinder (se esperaba JSON por líneas con `host`)"
        )
    target.data["inputs"] = sorted(inputs)[:MAX_INPUTS]
    return _result(module, target, list(entities.values()), discarded, "líneas")


def _sources(item: dict[str, Any]) -> list[str]:
    raw = item.get("sources")
    if raw is None:
        raw = [item.get("source")]
    names = raw if isinstance(raw, list) else [raw]
    return sorted({n for n in map(_text, names) if n})[:MAX_SOURCES]


def _maigret_entries(raw: bytes) -> list[tuple[str, dict[str, Any]]]:
    """Pares (sitio, entrada) de un informe `simple` o `ndjson`; vacío si no es ninguno."""
    try:
        whole = json.loads(raw.decode("utf-8", errors="replace"))
    except ValueError:
        whole = None
    if isinstance(whole, dict) and "sitename" not in whole:
        return [(str(k), v) for k, v in whole.items() if isinstance(v, dict)]
    entries = []
    for line in _lines(raw):
        try:
            item = json.loads(line)
        except ValueError:
            continue
        if isinstance(item, dict) and isinstance(item.get("sitename"), str):
            entries.append((item["sitename"], item))
    return entries


def claimed(entry: dict[str, Any]) -> bool:
    status = entry.get("status")
    if isinstance(status, dict):
        status = status.get("status")
    return isinstance(status, str) and status.strip().lower() == "claimed"


def parse_maigret(path: Path) -> ScanResult:
    """Cuentas que Maigret dio por encontradas, de un informe `--json simple` o `ndjson`."""
    module = "import_maigret"
    raw = _read(path)
    entries = _maigret_entries(raw)
    if not any(isinstance(e.get("url_user"), str) for _, e in entries):
        raise ToolImportError(
            "no es un informe de Maigret (se esperaba `--json simple` o `--json ndjson`)"
        )
    target = Entity(
        type=EntityType.RECORD,
        value=f"maigret:{path.name}",
        data={"sha256": hashlib.sha256(raw).hexdigest()},
    )
    entities: dict[str, Entity] = {}
    discarded = 0
    for site, entry in entries:
        if not claimed(entry):
            continue
        url = str(entry.get("url_user") or "").strip()
        if not URL_RE.match(url):
            discarded += 1
            continue
        try:
            profile = _entity(
                module,
                target.key,
                EntityType.PROFILE,
                url,
                {"site": _text(site), "username": _text(entry.get("username"))},
            )
        except ValidationError:
            discarded += 1
            continue
        entities.setdefault(profile.key, profile)
    return _result(module, target, list(entities.values()), discarded, "perfiles")

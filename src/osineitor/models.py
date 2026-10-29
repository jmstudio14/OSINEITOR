"""Modelos de datos compartidos por el núcleo y los módulos."""

from __future__ import annotations

import ipaddress
import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator

from osineitor.errors import InvalidEntityValue
from osineitor.normalize import canonical, canonical_hostname


class EntityType(StrEnum):
    DOMAIN = "domain"
    IP = "ip"
    EMAIL = "email"
    USERNAME = "username"
    URL = "url"
    PROFILE = "profile"
    SERVICE = "service"
    VULNERABILITY = "vulnerability"
    BREACH = "breach"
    RECORD = "record"


class Entity(BaseModel):
    """Una pieza de información descubierta (o la semilla de un scan)."""

    type: EntityType
    value: str
    data: dict[str, Any] = Field(default_factory=dict)
    source: str | None = None
    parent: str | None = None

    @model_validator(mode="after")
    def _canonicalize(self) -> Entity:
        """El valor se guarda en forma canónica: así la deduplicación y la clave son fiables."""
        self.value = canonical(self.type, self.value)
        return self

    @property
    def key(self) -> str:
        return f"{self.type}:{self.value.lower()}"


class ScanEvent(BaseModel):
    """Error u omisión de un módulo durante un scan."""

    kind: str  # "error" | "skipped" | "budget"
    module: str
    message: str
    entity: str | None = None


class ScanResult(BaseModel):
    target: Entity
    depth: int
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None
    entities: list[Entity] = Field(default_factory=list)
    events: list[ScanEvent] = Field(default_factory=list)
    scan_id: int | None = None
    truncated: bool = False  # el scan se detuvo por agotar el presupuesto

    def by_type(self) -> dict[EntityType, list[Entity]]:
        grouped: dict[EntityType, list[Entity]] = {}
        for entity in self.entities:
            grouped.setdefault(entity.type, []).append(entity)
        return grouped


DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+([a-z]{2,63}|xn--[a-z0-9-]{1,59})$"
)


def detect_type(value: str) -> EntityType:
    """Deduce el tipo de entidad de una entrada libre del usuario."""
    value = value.strip()
    try:
        ipaddress.ip_address(value)
        return EntityType.IP
    except ValueError:
        pass
    if "@" in value and "." in value.rsplit("@", 1)[1]:
        return EntityType.EMAIL
    try:
        host = canonical_hostname(value)  # admite IDN: `münchen.de` es un dominio
    except InvalidEntityValue:
        return EntityType.USERNAME
    if DOMAIN_RE.match(host.removeprefix("www.")):
        return EntityType.DOMAIN
    return EntityType.USERNAME

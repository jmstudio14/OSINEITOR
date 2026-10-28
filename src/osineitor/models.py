"""Modelos de datos compartidos por el núcleo y los módulos."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


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

    @property
    def key(self) -> str:
        return f"{self.type}:{self.value.lower()}"


class ScanEvent(BaseModel):
    """Error u omisión de un módulo durante un scan."""

    kind: str  # "error" | "skipped"
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

    def by_type(self) -> dict[EntityType, list[Entity]]:
        grouped: dict[EntityType, list[Entity]] = {}
        for entity in self.entities:
            grouped.setdefault(entity.type, []).append(entity)
        return grouped

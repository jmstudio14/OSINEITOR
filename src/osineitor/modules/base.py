"""Contrato que implementa cada fuente de datos."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import ClassVar

import dns.asyncresolver

from osineitor.config import Config
from osineitor.http import HttpClient
from osineitor.models import Entity, EntityType


class ModuleError(Exception):
    """Fallo esperado de un módulo (respuesta inesperada, cuota agotada...)."""


@dataclass
class Context:
    config: Config
    http: HttpClient
    resolver: dns.asyncresolver.Resolver = field(default_factory=dns.asyncresolver.Resolver)


class Module(ABC):
    name: ClassVar[str]
    description: ClassVar[str]
    consumes: ClassVar[frozenset[EntityType]]
    produces: ClassVar[frozenset[EntityType]] = frozenset()
    # Nombre de la API key en la configuración; None si no necesita ninguna.
    requires_key: ClassVar[str | None] = None
    # Pasivo = no envía tráfico al objetivo, solo a terceros.
    passive: ClassVar[bool] = True

    def __init__(self, ctx: Context) -> None:
        self.ctx = ctx

    @property
    def api_key(self) -> str | None:
        return self.ctx.config.key(self.requires_key) if self.requires_key else None

    def accepts(self, entity: Entity) -> bool:
        """Filtro adicional sobre `consumes` (p. ej. no repetir sobre subdominios)."""
        return entity.type in self.consumes

    def emit(self, parent: Entity, type: EntityType, value: str, /, **data: object) -> Entity:
        return Entity(type=type, value=value, data=dict(data), source=self.name, parent=parent.key)

    @abstractmethod
    async def run(self, entity: Entity) -> list[Entity]: ...

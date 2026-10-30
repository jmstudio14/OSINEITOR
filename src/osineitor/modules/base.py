"""Contrato que implementa cada fuente de datos."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import ClassVar, Literal

import dns.asyncresolver
import httpx
from pydantic import ValidationError

from osineitor.config import Config
from osineitor.errors import ModuleError, ModuleQuota, ModuleSkipped
from osineitor.evidence import capture
from osineitor.http import HttpClient, SourceHttp, current_stats
from osineitor.models import Entity, EntityType, Observation

__all__ = ["Context", "Module", "ModuleError", "ModuleQuota", "ModuleSkipped", "status_error"]


def status_error(service: str, response: httpx.Response) -> ModuleError:
    """Error de una respuesta inesperada; un 429 es una cuota agotada, no un fallo del módulo."""
    if response.status_code == 429:
        return ModuleQuota(f"{service} rechazó la petición por límite de uso (429)")
    return ModuleError(f"{service} respondió {response.status_code}")


@dataclass
class Context:
    config: Config
    http: HttpClient | SourceHttp
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
    # Consulta DNS por UDP (`ctx.resolver`) fuera de `ctx.http`: no pasa por --proxy, así que con
    # proxy se omite en lugar de filtrar las consultas al resolvedor local.
    direct_dns: ClassVar[bool] = False
    # «authoritative»: la respuesta viene de quien administra el dato (DNS, RDAP, el propio
    # objetivo). «aggregated»: una base de terceros que lo recopiló. Pesa en la confianza.
    authority: ClassVar[Literal["authoritative", "aggregated"]] = "aggregated"
    # Segundos máximos por ejecución (módulo × entidad); al agotarse se registra como error.
    timeout: ClassVar[float] = 180.0
    # Segundos de caché de las respuestas GET. Nunca se cachean los módulos activos ni los que
    # usan API key. 0 desactiva la caché de este módulo.
    cache_ttl: ClassVar[int] = 6 * 3600
    # Segundos mínimos entre dos peticiones a esta fuente (límite de uso de la fuente).
    min_interval: ClassVar[float] = 0.0
    # Valor de prueba seguro para `osineitor doctor`; `probe_url` si no hay caso seguro.
    canary: ClassVar[str | None] = None
    probe_url: ClassVar[str | None] = None

    def __init__(self, ctx: Context) -> None:
        self.ctx = ctx

    @property
    def api_key(self) -> str | None:
        return self.ctx.config.key(self.requires_key) if self.requires_key else None

    def accepts(self, entity: Entity) -> bool:
        """Filtro adicional sobre `consumes` (p. ej. no repetir sobre subdominios)."""
        return entity.type in self.consumes

    def emit(self, parent: Entity, type: EntityType, value: str, /, **data: object) -> Entity:
        return Entity(
            type=type,
            value=value,
            data=dict(data),
            source=self.name,
            parent=parent.key,
            observations=[Observation(module=self.name, query=parent.key)],
        )

    def record_evidence(self, url: str, body: str, *, method: str = "DNS") -> None:
        """Guarda la respuesta original para `--evidence`; solo para lo que no pasa por `ctx.http`
        (las consultas HTTP ya las captura el cliente)."""
        stats = current_stats.get()
        if stats is not None and stats.evidence is not None:
            stats.evidence.append(capture("dns", url, body.encode(), method=method))

    def try_emit(
        self, parent: Entity, type: EntityType, value: str, /, **data: object
    ) -> Entity | None:
        """Como `emit`, pero devuelve `None` si el valor no es válido para ese tipo.

        Úsalo con datos de terceros: un valor raro no debe descartar el resto del resultado.
        """
        try:
            return self.emit(parent, type, value, **data)
        except ValidationError:
            return None

    @abstractmethod
    async def run(self, entity: Entity) -> list[Entity]: ...

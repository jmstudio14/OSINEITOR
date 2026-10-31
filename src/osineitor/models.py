"""Modelos de datos compartidos por el núcleo y los módulos."""

from __future__ import annotations

import hashlib
import ipaddress
import re
from collections.abc import Iterable
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, computed_field, model_validator

from osineitor.errors import InvalidEntityValue
from osineitor.normalize import ASN_RE, canonical, canonical_hostname


def digest(hashes: Iterable[str]) -> str:
    """SHA-256 de las huellas ordenadas: no depende del orden en que terminaron los módulos."""
    return hashlib.sha256("\n".join(sorted(hashes)).encode()).hexdigest()


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
    ASN = "asn"
    NETBLOCK = "netblock"
    CERTIFICATE = "certificate"  # el valor es la huella SHA-256
    TECHNOLOGY = "technology"
    ORGANIZATION = "organization"
    PERSON = "person"
    PHONE = "phone"
    CRYPTO_ADDRESS = "crypto_address"
    FILE = "file"
    LOCATION = "location"
    FINDING = "finding"  # reservado a F7.8


class Observation(BaseModel):
    """Una vez que un módulo vio una entidad: quién, sobre qué entidad y cuándo."""

    module: str
    query: str  # clave de la entidad sobre la que corrió el módulo (p. ej. `domain:example.com`)
    at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Entity(BaseModel):
    """Una pieza de información descubierta (o la semilla de un scan)."""

    type: EntityType
    value: str
    data: dict[str, Any] = Field(default_factory=dict)
    source: str | None = None  # la primera fuente que la vio; todas están en `observations`
    parent: str | None = None
    observations: list[Observation] = Field(default_factory=list)
    confidence: str | None = None  # "bajo" | "medio" | "alto"; ver confidence.py

    @model_validator(mode="after")
    def _canonicalize(self) -> Entity:
        """El valor se guarda en forma canónica: así la deduplicación y la clave son fiables."""
        self.value = canonical(self.type, self.value)
        return self

    @property
    def key(self) -> str:
        return f"{self.type}:{self.value.lower()}"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def first_seen(self) -> datetime | None:
        """Primera vez que un módulo la vio en este scan; `None` en datos sin observaciones."""
        return min((o.at for o in self.observations), default=None)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def last_seen(self) -> datetime | None:
        """Última vez que un módulo la vio en este scan. No es la fecha del dato de un tercero."""
        return max((o.at for o in self.observations), default=None)

    @property
    def sources(self) -> list[str]:
        """Módulos que la vieron, sin repetir y en orden de llegada.

        Un dato guardado antes de existir las observaciones solo tiene `source`.
        """
        names = list(dict.fromkeys(o.module for o in self.observations))
        return names or ([self.source] if self.source else [])


class Evidence(BaseModel):
    """Respuesta original de una fuente con su huella SHA-256: permite comprobar un dato después.

    `module` y `entity` (clave consultada) la unen con las `Observation` que dio esa ejecución.
    El cuerpo no sale en JSON: solo viaja a la base de datos.
    """

    module: str = ""
    entity: str | None = None
    kind: str  # "http" | "dns"
    url: str  # sin credenciales ni valores de API key
    method: str
    status: int | None = None
    at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    sha256: str
    size: int  # bytes de la respuesta original (puede ser mayor que `body` si se recortó)
    truncated: bool = False
    body: bytes = Field(default=b"", exclude=True, repr=False)


class ScanEvent(BaseModel):
    """Error u omisión de un módulo durante un scan."""

    kind: str  # "error" | "skipped" | "budget" | "cancelled"
    module: str
    message: str
    entity: str | None = None


class ModuleRun(BaseModel):
    """Qué pasó con un módulo en un scan: permite distinguir «sin datos» de «falló»."""

    module: str
    status: str  # "ok" | "empty" | "error" | "skipped" | "quota"
    entity: str | None = None  # clave de la entidad sobre la que corrió; None si ni arrancó
    entities: int = 0
    requests: int = 0
    cache_hits: int = 0
    duration_ms: int = 0
    message: str = ""


class ScanResult(BaseModel):
    target: Entity
    depth: int
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None
    entities: list[Entity] = Field(default_factory=list)
    events: list[ScanEvent] = Field(default_factory=list)
    runs: list[ModuleRun] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    scope: dict[str, list[str]] | None = None  # alcance declarado (ver scope.py)
    purpose: str | None = None  # para qué se hizo el scan (`--purpose`)
    scan_id: int | None = None
    truncated: bool = False  # el scan se detuvo por agotar el presupuesto

    @property
    def cancelled(self) -> bool:
        return any(ev.kind == "cancelled" for ev in self.events)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def status(self) -> str:
        """`cancelled` > `truncated` > `complete`: lo primero que debe saber quien lo consume."""
        if self.cancelled:
            return "cancelled"
        return "truncated" if self.truncated else "complete"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def evidence_digest(self) -> str | None:
        """Huella de todas las evidencias (para anotarla fuera de la base de datos)."""
        return digest(e.sha256 for e in self.evidence) if self.evidence else None

    def by_type(self) -> dict[EntityType, list[Entity]]:
        grouped: dict[EntityType, list[Entity]] = {}
        for entity in self.entities:
            grouped.setdefault(entity.type, []).append(entity)
        return grouped


URL_RE = re.compile(r"^https?://\S+$", re.IGNORECASE)
DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+([a-z]{2,63}|xn--[a-z0-9-]{1,59})$"
)


def detect_type(value: str) -> EntityType:
    """Deduce el tipo de entidad de una entrada libre del usuario.

    `AS` seguido de dígitos es un ASN: para un username con esa forma hay que usar `username`.
    """
    value = value.strip()
    try:
        ipaddress.ip_address(value)
        return EntityType.IP
    except ValueError:
        pass
    try:
        ipaddress.ip_network(value, strict=False)
        return EntityType.NETBLOCK
    except ValueError:
        pass
    if URL_RE.match(value):  # antes que el email: una URL puede llevar `@` (usuario:clave@host)
        return EntityType.URL
    if "@" in value and "." in value.rsplit("@", 1)[1]:
        return EntityType.EMAIL
    if value[:2].lower() == "as" and ASN_RE.fullmatch(value):
        return EntityType.ASN
    try:
        host = canonical_hostname(value)  # admite IDN: `münchen.de` es un dominio
    except InvalidEntityValue:
        return EntityType.USERNAME
    if DOMAIN_RE.match(host.removeprefix("www.")):
        return EntityType.DOMAIN
    return EntityType.USERNAME


def decompose(seed: Entity) -> list[Entity]:
    """Entidades que se deducen de la semilla: de una URL, su host (dominio o IP).

    Lanza `InvalidEntityValue` si la URL no tiene un host investigable.
    """
    if seed.type != EntityType.URL:
        return []
    host = urlsplit(seed.value).hostname
    if not host:
        raise InvalidEntityValue(f"la URL no tiene host: {seed.value!r}")
    try:
        ipaddress.ip_address(host)
        kind = EntityType.IP
    except ValueError:
        kind = EntityType.DOMAIN
    try:
        found = Entity(
            type=kind,
            value=host,
            source="engine",
            parent=seed.key,
            observations=[Observation(module="engine", query=seed.key)],
        )
    except ValueError as exc:  # pydantic envuelve el error de normalización
        raise InvalidEntityValue(f"host no válido en {seed.value!r}") from exc
    return [found]

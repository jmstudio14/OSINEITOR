"""Petición de scan: valida las opciones y las convierte en los argumentos de la CLI."""

from __future__ import annotations

import re
from dataclasses import dataclass

from osineitor.models import detect_type

KINDS = ("auto", "domain", "ip", "email", "username")
MODULE_RE = re.compile(r"^[a-z0-9_]+$")


class InvalidRequest(ValueError):
    """Las opciones del scan no son válidas."""


class ConfirmationRequired(InvalidRequest):
    """Una opción de riesgo se pidió sin la confirmación explícita del usuario."""


def detect_kind(text: str) -> str:
    """Tipo que deduciría la CLI para este texto (para mostrarlo mientras se escribe)."""
    return detect_type(text).value


@dataclass
class ScanRequest:
    target: str
    kind: str = "auto"
    depth: int | None = None  # None: 2 si el tipo es automático (pivotea), 1 si es explícito
    modules: tuple[str, ...] = ()
    # Módulos que contactan al objetivo. Exigen la confirmación explícita del usuario.
    active: bool = False
    confirm_active: bool = False
    # Permite conectar a redes privadas. También exige confirmación.
    allow_private: bool = False
    confirm_private: bool = False
    # Presupuesto: None = valor por defecto de la CLI; 0 = sin límite.
    max_entities: int | None = None
    max_requests: int | None = None
    max_time: float | None = None
    no_cache: bool = False
    refresh: bool = False
    no_save: bool = False

    def validate(self) -> None:
        if not self.target.strip():
            raise InvalidRequest("indica un objetivo")
        if self.kind not in KINDS:
            raise InvalidRequest(f"tipo desconocido: {self.kind}")
        if self.depth is not None and not 1 <= self.depth <= 4:
            raise InvalidRequest("la profundidad va de 1 a 4")
        for name in self.modules:
            if not MODULE_RE.match(name):
                raise InvalidRequest(f"nombre de módulo no válido: {name!r}")
        for label, value in (
            ("entidades", self.max_entities),
            ("peticiones", self.max_requests),
            ("tiempo", self.max_time),
        ):
            if value is not None and value < 0:
                raise InvalidRequest(f"el máximo de {label} no puede ser negativo")
        if self.no_cache and self.refresh:
            raise InvalidRequest("«sin caché» y «refrescar» son contradictorios")
        if self.active and not self.confirm_active:
            raise ConfirmationRequired(
                "los módulos activos contactan con el objetivo: requieren confirmación"
            )
        if self.allow_private and not self.confirm_private:
            raise ConfirmationRequired(
                "permitir redes privadas desactiva una protección: requiere confirmación"
            )

    def to_args(self) -> list[str]:
        """Argumentos para `CliProcess`. Lanza `InvalidRequest` si algo no es válido."""
        self.validate()
        command = "scan" if self.kind == "auto" else self.kind
        args = ["--no-color", command]
        depth = self.depth if self.depth is not None else (2 if self.kind == "auto" else 1)
        args += ["--depth", str(depth), "--ndjson", "--control-stdin"]
        for name in self.modules:
            args += ["-m", name]
        if self.active:
            args.append("--active")
        if self.allow_private:
            args.append("--allow-private")
        if self.max_entities is not None:
            args += ["--max-entities", str(self.max_entities)]
        if self.max_requests is not None:
            args += ["--max-requests", str(self.max_requests)]
        if self.max_time is not None:
            args += ["--max-time", f"{self.max_time:g}"]
        if self.no_cache:
            args.append("--no-cache")
        if self.refresh:
            args.append("--refresh")
        if self.no_save:
            args.append("--no-save")
        # `--` antes del objetivo: uno que empiece por «-» no se interpreta como opción.
        return [*args, "--", self.target.strip()]

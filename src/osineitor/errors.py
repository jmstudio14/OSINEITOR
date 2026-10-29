"""Excepciones compartidas por el núcleo y los módulos."""

from __future__ import annotations


class ModuleError(Exception):
    """Fallo esperado de un módulo (respuesta inesperada, cuota agotada...)."""


class ModuleSkipped(ModuleError):
    """El módulo no aplica a esta entidad: no es un fallo, se registra como omitido."""


class NetworkGuardError(ModuleError):
    """Se bloqueó una conexión a una dirección privada, loopback o reservada."""


class BudgetExceeded(Exception):
    """Se agotó el presupuesto del scan (entidades, peticiones o tiempo)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class InvalidEntityValue(ValueError):
    """El valor no es válido para el tipo de entidad indicado."""

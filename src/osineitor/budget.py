"""Presupuesto de un scan: tope de entidades, de peticiones y de tiempo."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from osineitor.errors import BudgetExceeded

DEFAULT_MAX_ENTITIES = 2000
DEFAULT_MAX_REQUESTS = 3000
DEFAULT_MAX_SECONDS = 900.0


@dataclass
class Budget:
    """Límites del scan. `None` significa sin límite."""

    max_entities: int | None = DEFAULT_MAX_ENTITIES
    max_requests: int | None = DEFAULT_MAX_REQUESTS
    max_seconds: float | None = DEFAULT_MAX_SECONDS
    requests: int = 0
    blocked_reason: str | None = None  # se fija cuando una petición no pudo hacerse
    _started: float | None = field(default=None, repr=False)

    @classmethod
    def from_limits(cls, entities: int, requests: int, seconds: float) -> Budget:
        """Construye el presupuesto desde la CLI, donde `0` significa sin límite."""
        return cls(
            max_entities=entities or None,
            max_requests=requests or None,
            max_seconds=seconds or None,
        )

    def start(self) -> None:
        self._started = time.monotonic()

    def remaining_seconds(self) -> float | None:
        if self.max_seconds is None:
            return None
        elapsed = 0.0 if self._started is None else time.monotonic() - self._started
        return max(self.max_seconds - elapsed, 0.0)

    def entities_full(self, entities: int) -> str | None:
        """Motivo por el que ya no caben más entidades, o `None`."""
        if self.max_entities is not None and entities >= self.max_entities:
            return f"máximo de entidades alcanzado ({self.max_entities})"
        return None

    def exhausted(self, entities: int = 0) -> str | None:
        """Motivo por el que el presupuesto está agotado, o `None` si queda margen."""
        if self.blocked_reason:
            return self.blocked_reason
        if reason := self.entities_full(entities):
            return reason
        if self.remaining_seconds() == 0.0:
            return f"tiempo máximo agotado ({self.max_seconds:g} s)"
        return None

    def charge_request(self) -> None:
        """Contabiliza una petición; lanza `BudgetExceeded` si ya no hay margen."""
        if self.max_requests is not None and self.requests >= self.max_requests:
            self.blocked_reason = f"máximo de peticiones alcanzado ({self.max_requests})"
            raise BudgetExceeded(self.blocked_reason)
        self.requests += 1

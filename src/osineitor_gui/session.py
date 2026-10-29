"""Estado de un scan en curso o guardado, listo para que lo pinten las vistas (sin Qt)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from osineitor_gui.events import (
    EXIT_CANCELLED,
    EXIT_INTERNAL,
    EntityFound,
    Event,
    ModuleEnd,
    ModuleStart,
    Notice,
    Progress,
    ScanEnd,
    ScanStart,
)

IDLE, RUNNING = "idle", "running"
COMPLETE, TRUNCATED, CANCELLED, FAILED = "complete", "truncated", "cancelled", "failed"
FINISHED = (COMPLETE, TRUNCATED, CANCELLED, FAILED)

# Cuando un módulo corrió varias veces, manda su peor resultado.
_SEVERITY = ("error", "quota", "skipped", "ok", "empty")


@dataclass
class ModuleState:
    name: str
    running: int = 0  # ejecuciones en curso ahora mismo
    counts: dict[str, int] = field(default_factory=dict)  # estado → ejecuciones
    entities: int = 0
    requests: int = 0
    cache_hits: int = 0
    duration_ms: int = 0
    message: str = ""  # último mensaje no vacío (error, motivo de omisión…)

    @property
    def status(self) -> str:
        if self.running:
            return "running"
        for status in _SEVERITY:
            if self.counts.get(status):
                return status
        return "pending"

    @property
    def runs(self) -> int:
        return sum(self.counts.values())


class ScanSession:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.state = IDLE
        self.target_type = ""
        self.target_value = ""
        self.depth = 0
        self.modules: dict[str, ModuleState] = {}
        self.entities: list[dict[str, Any]] = []
        self.notices: list[Notice] = []
        self.done = 0
        self.total = 0
        self.requests = 0
        self.scan_id: int | None = None
        self.exit_code: int | None = None
        self.message = ""

    # --- alimentación -----------------------------------------------------------------------

    def begin(self) -> None:
        """Se llama al lanzar la CLI: hasta `scan.start` ya consta que algo está en marcha."""
        self.reset()
        self.state = RUNNING

    def _module(self, name: str) -> ModuleState:
        return self.modules.setdefault(name, ModuleState(name))

    def feed(self, event: Event) -> None:
        if isinstance(event, ScanStart):
            self.target_type, self.target_value = event.target_type, event.target_value
            self.depth = event.depth
            for name in event.modules:
                self._module(name)
            for skipped in event.skipped:
                module = self._module(str(skipped.get("module", "")))
                module.counts["skipped"] = 1
                module.message = str(skipped.get("message", ""))
        elif isinstance(event, ModuleStart):
            self._module(event.module).running += 1
        elif isinstance(event, ModuleEnd):
            self._end_module(event)
        elif isinstance(event, EntityFound):
            self.entities.append(event.entity)
        elif isinstance(event, Progress):
            self.done, self.total, self.requests = event.done, event.total, event.requests
        elif isinstance(event, Notice):
            self.notices.append(event)
        elif isinstance(event, ScanEnd):
            self.state = event.status if event.status in FINISHED else FAILED
            self.scan_id, self.exit_code = event.scan_id, event.exit_code
            self.message = event.message

    def _end_module(self, event: ModuleEnd) -> None:
        module = self._module(event.module)
        module.running = max(module.running - 1, 0)
        module.counts[event.status] = module.counts.get(event.status, 0) + 1
        module.entities += event.entities
        module.requests += event.requests
        module.cache_hits += event.cache_hits
        module.duration_ms += event.duration_ms
        if event.message:
            module.message = event.message

    def process_exited(self, code: int, stderr_tail: list[str] | None = None) -> None:
        """La CLI terminó. Si lo hizo sin `scan.end` (se cayó o la mataron) el scan falló."""
        if self.state != RUNNING:
            return
        self.exit_code = code
        self.state = CANCELLED if code == EXIT_CANCELLED else FAILED
        detail = "\n".join((stderr_tail or [])[-5:])
        self.message = detail or f"la CLI terminó sin cerrar el scan (código {code})"
        if code == EXIT_INTERNAL and not detail:
            self.message = "error interno de la CLI"

    def load_result(self, result: dict[str, Any]) -> None:
        """Carga un scan guardado (la salida de `show --json`) con la misma forma que uno vivo."""
        self.reset()
        target = result.get("target") or {}
        self.target_type, self.target_value = target.get("type", ""), target.get("value", "")
        self.depth = int(result.get("depth", 0))
        self.entities = list(result.get("entities") or [])
        self.scan_id = result.get("scan_id")
        for run in result.get("runs") or []:
            module = self._module(run["module"])
            status = run.get("status", "")
            module.counts[status] = module.counts.get(status, 0) + 1
            module.entities += run.get("entities", 0)
            module.requests += run.get("requests", 0)
            module.cache_hits += run.get("cache_hits", 0)
            module.duration_ms += run.get("duration_ms", 0)
            if run.get("message"):
                module.message = run["message"]
        status = result.get("status", COMPLETE)
        self.state = status if status in FINISHED else COMPLETE
        self.done = self.total = sum(m.runs for m in self.modules.values())

    # --- consulta --------------------------------------------------------------------------------

    @property
    def finished(self) -> bool:
        return self.state in FINISHED

    @property
    def incomplete(self) -> bool:
        """El resultado no es el scan entero (presupuesto agotado, cancelado o fallido)."""
        return self.state in (TRUNCATED, CANCELLED, FAILED)

    def counts_by_type(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for entity in self.entities:
            counts[entity["type"]] = counts.get(entity["type"], 0) + 1
        return dict(sorted(counts.items()))

    def filtered(self, types: set[str] | None = None, text: str = "") -> list[dict[str, Any]]:
        """Entidades de esos tipos que contienen `text` (sin distinguir mayúsculas)."""
        needle = text.strip().lower()
        found = []
        for entity in self.entities:
            if types is not None and entity["type"] not in types:
                continue
            if needle:
                haystack = " ".join(
                    (
                        str(entity.get("value", "")),
                        str(entity.get("source") or ""),
                        json.dumps(entity.get("data") or {}, ensure_ascii=False),
                    )
                ).lower()
                if needle not in haystack:
                    continue
            found.append(entity)
        return found

"""Orquestador: ejecuta los módulos que consumen cada entidad y pivotea por niveles."""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import time
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from typing import Any

from osineitor import events, logs
from osineitor.budget import Budget
from osineitor.errors import BudgetExceeded, ModuleError, ModuleQuota, ModuleSkipped
from osineitor.http import RunStats, current_stats
from osineitor.models import Entity, ModuleRun, ScanEvent, ScanResult
from osineitor.modules.base import Context, Module

log = logs.get("engine")


class Engine:
    def __init__(
        self,
        ctx: Context,
        module_classes: Iterable[type[Module]],
        *,
        depth: int = 1,
        active: bool = False,
        concurrency: int = 10,
        on_entity: Callable[[Entity], None] | None = None,
        budget: Budget | None = None,
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.depth = max(depth, 1)
        self.on_entity = on_entity
        self.on_event = on_event  # eventos del contrato CLI↔GUI (ver osineitor.events)
        self.budget = budget or Budget()
        self._sem = asyncio.Semaphore(concurrency)
        self._cancel = asyncio.Event()
        self._jobs_total = 0
        self._ranks: dict[str, dict[str, int]] = {}  # entidad → campo → rank que lo aportó
        self._jobs_done = 0
        self._proxy: str | None = getattr(ctx.http, "proxy", None)
        self.modules: list[Module] = []
        self.skipped: list[ScanEvent] = []
        for cls in module_classes:
            if not cls.passive and not active:
                self._skip(cls, "módulo activo (usa --active)")
            elif cls.requires_key and not ctx.config.key(cls.requires_key):
                self._skip(cls, f"falta la API key '{cls.requires_key}'")
            elif cls.direct_dns and self._proxy:
                self._skip(cls, "consulta DNS directa: no se enruta por --proxy")
            else:
                self.modules.append(cls(self._bind(ctx, cls)))

    def _skip(self, cls: type[Module], message: str) -> None:
        self.skipped.append(ScanEvent(kind="skipped", module=cls.name, message=message))

    @staticmethod
    def _bind(ctx: Context, cls: type[Module]) -> Context:
        """Contexto propio del módulo: su fuente tiene caché y límite de uso independientes."""
        bind = getattr(ctx.http, "bind", None)
        if bind is None:
            return ctx
        # Con API key o contactando al objetivo no se cachea: sería persistir datos sensibles.
        ttl = cls.cache_ttl if cls.passive and not cls.requires_key else 0
        http = bind(cls.name, cache_ttl=ttl, min_interval=cls.min_interval)
        return dataclasses.replace(ctx, http=http)

    def cancel(self) -> None:
        """Pide detener el scan: se cancelan los módulos en curso y se conserva lo terminado."""
        self._cancel.set()

    def _emit(self, type_: str, **fields: Any) -> None:
        if self.on_event:
            self.on_event(events.event(type_, **fields))

    async def _collect(
        self,
        tasks: list[asyncio.Task],
        index: dict[str, Entity],
        result: ScanResult,
        layer: list[Entity],
    ) -> None:
        """Recoge los resultados de un nivel **según terminan** (no al final del más lento).

        Acaba cuando terminan todas las tareas, se agota el tiempo o se pide cancelar. Lo que quede
        en curso se cancela; lo ya terminado se conserva.
        """
        remaining = self.budget.remaining_seconds()
        deadline = None if remaining is None else time.monotonic() + remaining
        absorbed: set[asyncio.Task] = set()
        pending = set(tasks)
        canceller = asyncio.ensure_future(self._cancel.wait())
        try:
            while pending and not self._cancel.is_set():
                left = None if deadline is None else max(deadline - time.monotonic(), 0.0)
                done, _ = await asyncio.wait(
                    pending | {canceller}, timeout=left, return_when=asyncio.FIRST_COMPLETED
                )
                if not done:
                    break  # se agotó el tiempo
                # En el orden de creación: dos módulos que terminan a la vez dan siempre el mismo
                # resultado.
                for rank, task in enumerate(tasks):
                    if task in done:
                        pending.discard(task)
                        absorbed.add(task)
                        self._absorb(task.result(), rank, index, result, layer)
                        self._emit_progress(result)
        finally:
            canceller.cancel()
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        # Una tarea puede haber terminado justo antes de cancelar: su trabajo no se pierde.
        for rank, task in enumerate(tasks):
            if task.done() and not task.cancelled() and task not in absorbed:
                self._absorb(task.result(), rank, index, result, layer)
        if pending:
            if self._cancel.is_set():
                self._mark_cancelled(result)
            else:
                self._truncate(result, self.budget.exhausted() or "tiempo máximo agotado")

    def _merge(self, existing: Entity, incoming: Entity, rank: int) -> None:
        """Misma entidad desde otra fuente: completa lo que falte.

        Si dos fuentes discrepan en un campo gana la de menor `rank` (el orden de los módulos),
        llegue cuando llegue: el resultado no depende de quién termine antes.
        """
        ranks = self._ranks.setdefault(existing.key, {})
        for k, v in incoming.data.items():
            if v in (None, "", [], {}):
                continue
            current = existing.data.get(k)
            if current in (None, "", [], {}) or rank < ranks.get(k, rank):
                existing.data[k] = v
                ranks[k] = rank

    @staticmethod
    def _observe(existing: Entity, incoming: Entity) -> None:
        """Suma quién más la vio. El mismo módulo sobre la misma entidad no cuenta dos veces."""
        seen = {(o.module, o.query) for o in existing.observations}
        for obs in incoming.observations:
            if (obs.module, obs.query) not in seen:
                existing.observations.append(obs)
                seen.add((obs.module, obs.query))

    def _emit_progress(self, result: ScanResult) -> None:
        self._emit(
            "progress",
            done=self._jobs_done,
            total=self._jobs_total,
            entities=len(result.entities),
            requests=self.budget.requests,
        )

    def _absorb(
        self,
        found: list[Entity],
        rank: int,
        index: dict[str, Entity],
        result: ScanResult,
        layer: list[Entity],
    ) -> None:
        for entity in found:
            existing = index.get(entity.key)
            if existing is not None:
                self._merge(existing, entity, rank)
                self._observe(existing, entity)
                continue
            # Solo el tope de entidades impide guardar: lo que un módulo terminó a
            # tiempo se conserva aunque se haya agotado el tiempo o las peticiones.
            if reason := self.budget.entities_full(len(result.entities)):
                self._truncate(result, reason)
                continue
            index[entity.key] = entity
            self._ranks[entity.key] = dict.fromkeys(entity.data, rank)
            result.entities.append(entity)
            layer.append(entity)
            if self.on_entity:
                self.on_entity(entity)
            self._emit("entity", entity=entity.model_dump(mode="json"))

    @staticmethod
    def _truncate(result: ScanResult, reason: str) -> None:
        if not result.truncated:
            result.truncated = True
            result.events.append(ScanEvent(kind="budget", module="engine", message=reason))
            log.warning("scan.truncated", extra={"fields": {"reason": reason}})

    @staticmethod
    def _mark_cancelled(result: ScanResult) -> None:
        if not result.cancelled:
            result.events.append(
                ScanEvent(kind="cancelled", module="engine", message="scan cancelado")
            )
            log.warning("scan.cancelled")

    async def run(self, seed: Entity) -> ScanResult:
        result = ScanResult(target=seed, depth=self.depth, events=list(self.skipped))
        result.runs = [
            ModuleRun(module=ev.module, status="skipped", message=ev.message) for ev in self.skipped
        ]
        self.budget.start()
        log.info(
            "scan.start",
            extra={
                "fields": {
                    "target": seed.key,
                    "depth": self.depth,
                    "modules": [m.name for m in self.modules],
                    "skipped": [ev.module for ev in self.skipped],
                    "proxy": logs.redact_url(proxy) if (proxy := self._proxy) else None,
                }
            },
        )
        self._emit(
            "scan.start",
            target={"type": seed.type.value, "value": seed.value},
            depth=self.depth,
            modules=[m.name for m in self.modules],
            skipped=[{"module": ev.module, "message": ev.message} for ev in self.skipped],
            budget={
                "max_entities": self.budget.max_entities,
                "max_requests": self.budget.max_requests,
                "max_seconds": self.budget.max_seconds,
            },
        )
        index: dict[str, Entity] = {seed.key: seed}
        layer = [seed]
        for _ in range(self.depth):
            if self._cancel.is_set():
                self._mark_cancelled(result)
                break
            if reason := self.budget.exhausted(len(result.entities)):
                self._truncate(result, reason)
                break
            jobs = [(m, e) for e in layer for m in self.modules if m.accepts(e)]
            if not jobs:
                break
            self._jobs_total += len(jobs)
            tasks = [asyncio.create_task(self._run_one(m, e, result)) for m, e in jobs]
            layer = []
            await self._collect(tasks, index, result, layer)
            if self.budget.blocked_reason:
                self._truncate(result, self.budget.blocked_reason)
            if self._cancel.is_set():
                self._mark_cancelled(result)
            if not layer or result.truncated or result.cancelled:
                break
        result.finished_at = datetime.now(UTC)
        log.info(
            "scan.end",
            extra={
                "fields": {
                    "status": result.status,
                    "entities": len(result.entities),
                    "requests": self.budget.requests,
                }
            },
        )
        return result

    async def _run_one(self, module: Module, entity: Entity, result: ScanResult) -> list[Entity]:
        async with self._sem:
            if reason := self.budget.exhausted(len(result.entities)):
                self._truncate(result, reason)
                return []
            stats = RunStats()
            current_stats.set(stats)  # esta ejecución corre en su propia tarea
            self._emit("module.start", module=module.name, entity=entity.key)
            started = time.monotonic()
            found: list[Entity] = []
            status, message = "ok", ""
            event_kind: str | None = None  # None: no se anota en `events` (p. ej. presupuesto)
            try:
                found = await asyncio.wait_for(module.run(entity), module.timeout)
                if not found:
                    status = "empty"
            except BudgetExceeded as exc:
                self._truncate(result, exc.reason)
                status, message = "skipped", exc.reason
            except ModuleSkipped as exc:
                status, message, event_kind = "skipped", str(exc), "skipped"
            except ModuleQuota as exc:
                status, message, event_kind = "quota", str(exc), "error"
            except ModuleError as exc:
                status, message, event_kind = "error", str(exc), "error"
            except TimeoutError:
                status, message = "error", f"sin respuesta tras {module.timeout:g} s"
                event_kind = "error"
            except asyncio.CancelledError:
                # El tiempo del scan se agotó mientras corría: queda constancia de ello.
                self._record(result, module, entity, stats, started, "skipped", "cancelado")
                raise
            except Exception as exc:  # un módulo roto no debe tumbar el scan
                status, message = "error", f"{type(exc).__name__}: {exc}"
                event_kind = "error"
        self._record(result, module, entity, stats, started, status, message, len(found))
        if event_kind:
            result.events.append(
                ScanEvent(kind=event_kind, module=module.name, message=message, entity=entity.key)
            )
        return found

    def _record(
        self,
        result: ScanResult,
        module: Module,
        entity: Entity,
        stats: RunStats,
        started: float,
        status: str,
        message: str,
        count: int = 0,
    ) -> None:
        run = ModuleRun(
            module=module.name,
            status=status,
            entity=entity.key,
            entities=count,
            requests=stats.requests,
            cache_hits=stats.cache_hits,
            duration_ms=round((time.monotonic() - started) * 1000),
            message=message,
        )
        result.runs.append(run)
        level = logging.WARNING if status in ("error", "quota") else logging.INFO
        log.log(level, "module.end", extra={"fields": run.model_dump()})
        self._jobs_done += 1
        self._emit("module.end", **run.model_dump())

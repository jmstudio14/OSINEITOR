"""Orquestador: ejecuta los módulos que consumen cada entidad y pivotea por niveles."""

from __future__ import annotations

import asyncio
import dataclasses
import time
from collections.abc import Callable, Iterable
from datetime import UTC, datetime

from osineitor.budget import Budget
from osineitor.errors import BudgetExceeded, ModuleError, ModuleQuota, ModuleSkipped
from osineitor.http import RunStats, current_stats
from osineitor.models import Entity, ModuleRun, ScanEvent, ScanResult
from osineitor.modules.base import Context, Module


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
    ) -> None:
        self.depth = max(depth, 1)
        self.on_entity = on_entity
        self.budget = budget or Budget()
        self._sem = asyncio.Semaphore(concurrency)
        self.modules: list[Module] = []
        self.skipped: list[ScanEvent] = []
        for cls in module_classes:
            if not cls.passive and not active:
                self._skip(cls, "módulo activo (usa --active)")
            elif cls.requires_key and not ctx.config.key(cls.requires_key):
                self._skip(cls, f"falta la API key '{cls.requires_key}'")
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

    @staticmethod
    def _truncate(result: ScanResult, reason: str) -> None:
        if not result.truncated:
            result.truncated = True
            result.events.append(ScanEvent(kind="budget", module="engine", message=reason))

    async def run(self, seed: Entity) -> ScanResult:
        result = ScanResult(target=seed, depth=self.depth, events=list(self.skipped))
        result.runs = [
            ModuleRun(module=ev.module, status="skipped", message=ev.message) for ev in self.skipped
        ]
        self.budget.start()
        index: dict[str, Entity] = {seed.key: seed}
        layer = [seed]
        for _ in range(self.depth):
            if reason := self.budget.exhausted(len(result.entities)):
                self._truncate(result, reason)
                break
            jobs = [(m, e) for e in layer for m in self.modules if m.accepts(e)]
            if not jobs:
                break
            tasks = [asyncio.create_task(self._run_one(m, e, result)) for m, e in jobs]
            done, pending = await asyncio.wait(tasks, timeout=self.budget.remaining_seconds())
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
                self._truncate(result, self.budget.exhausted() or "tiempo máximo agotado")
            layer = []
            for task in tasks:
                if task not in done:
                    continue
                for entity in task.result():
                    existing = index.get(entity.key)
                    if existing is not None:
                        # Misma entidad desde otra fuente: completa los datos que falten.
                        for k, v in entity.data.items():
                            if existing.data.get(k) in (None, "", [], {}):
                                existing.data[k] = v
                        continue
                    # Solo el tope de entidades impide guardar: lo que un módulo terminó a
                    # tiempo se conserva aunque se haya agotado el tiempo o las peticiones.
                    if reason := self.budget.entities_full(len(result.entities)):
                        self._truncate(result, reason)
                        continue
                    index[entity.key] = entity
                    result.entities.append(entity)
                    layer.append(entity)
                    if self.on_entity:
                        self.on_entity(entity)
            if self.budget.blocked_reason:
                self._truncate(result, self.budget.blocked_reason)
            if not layer or result.truncated:
                break
        result.finished_at = datetime.now(UTC)
        return result

    async def _run_one(self, module: Module, entity: Entity, result: ScanResult) -> list[Entity]:
        async with self._sem:
            if reason := self.budget.exhausted(len(result.entities)):
                self._truncate(result, reason)
                return []
            stats = RunStats()
            current_stats.set(stats)  # esta ejecución corre en su propia tarea
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

    @staticmethod
    def _record(
        result: ScanResult,
        module: Module,
        entity: Entity,
        stats: RunStats,
        started: float,
        status: str,
        message: str,
        count: int = 0,
    ) -> None:
        result.runs.append(
            ModuleRun(
                module=module.name,
                status=status,
                entity=entity.key,
                entities=count,
                requests=stats.requests,
                cache_hits=stats.cache_hits,
                duration_ms=round((time.monotonic() - started) * 1000),
                message=message,
            )
        )

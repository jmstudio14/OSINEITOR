"""Orquestador: ejecuta los módulos que consumen cada entidad y pivotea por niveles."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable
from datetime import UTC, datetime

from osineitor.budget import Budget
from osineitor.errors import BudgetExceeded, ModuleError, ModuleSkipped
from osineitor.models import Entity, ScanEvent, ScanResult
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
                self.skipped.append(
                    ScanEvent(
                        kind="skipped", module=cls.name, message="módulo activo (usa --active)"
                    )
                )
            elif cls.requires_key and not ctx.config.key(cls.requires_key):
                self.skipped.append(
                    ScanEvent(
                        kind="skipped",
                        module=cls.name,
                        message=f"falta la API key '{cls.requires_key}'",
                    )
                )
            else:
                self.modules.append(cls(ctx))

    @staticmethod
    def _truncate(result: ScanResult, reason: str) -> None:
        if not result.truncated:
            result.truncated = True
            result.events.append(ScanEvent(kind="budget", module="engine", message=reason))

    async def run(self, seed: Entity) -> ScanResult:
        result = ScanResult(target=seed, depth=self.depth, events=list(self.skipped))
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
            try:
                return await module.run(entity)
            except BudgetExceeded as exc:
                self._truncate(result, exc.reason)
                return []
            except ModuleSkipped as exc:
                kind, message = "skipped", str(exc)
            except ModuleError as exc:
                kind, message = "error", str(exc)
            except Exception as exc:  # un módulo roto no debe tumbar el scan
                kind, message = "error", f"{type(exc).__name__}: {exc}"
        result.events.append(
            ScanEvent(kind=kind, module=module.name, message=message, entity=entity.key)
        )
        return []
